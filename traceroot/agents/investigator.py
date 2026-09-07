from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import signal
from time import monotonic
from uuid import uuid4

from ..contracts import ToolResult, ToolError, utc_now
from ..llms.provider import ModelFailure
from ..tools import TOOLS
from .prompt import SYSTEM_PROMPT
from .schemas import CATALOG, DECISION_SCHEMA, FINAL_SCHEMA, TASK_SCHEMA, TOOL_INPUTS, output_schema, validate

class DeadlineExpired(BaseException):
    pass

@contextmanager
def deadline(seconds: float):
    if seconds <= 0:
        raise DeadlineExpired()
    def expire(signum, frame):
        raise DeadlineExpired()
    previous = signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)

@dataclass(frozen=True)
class Budget:
    max_tool_calls: int = 15
    max_seconds: int = 300
    model_timeout: int = 60

    def __post_init__(self):
        if type(self.max_tool_calls) is not int or not 1 <= self.max_tool_calls <= 15:
            raise ValueError("Tool-call budget must be between 1 and 15.")
        if type(self.max_seconds) is not int or not 1 <= self.max_seconds <= 900:
            raise ValueError("Time budget must be between 1 and 900 seconds.")
        if type(self.model_timeout) is not int or not 1 <= self.model_timeout <= 120:
            raise ValueError("Model timeout must be between 1 and 120 seconds.")

ALLOWED_CONSTRAINTS = {
    "read-only investigation", "benchmark folder forbidden", "no code changes", "no database changes",
    "benchmark ground truth inaccessible", "no modifications",
}

def validate_task(task, context):
    validate(task, TASK_SCHEMA)
    context.repository.validate(task["repository"])
    if not task["constraints"] or any(c not in ALLOWED_CONSTRAINTS for c in task["constraints"]):
        raise ValueError("Unsupported constraints; mandatory restrictions cannot be relaxed.")
    if not context.config.get("active"):
        raise ValueError("Prepare an active disposable environment first.")

def reproduction_status(steps):
    reproductions = [s for s in steps if s["tool"] == "run_reproduction"]
    for step in steps:
        data = step["result"].get("data") or {}
        if step["result"]["status"] == "ok" and (
            data.get("reproduced") is True or
            any(o["expected"] != o["observed"] for o in data.get("http_observations", []))
        ):
            return "CONFIRMED"
    if any((s["result"].get("data") or {}).get("reproduced") is False for s in reproductions):
        return "NOT_REPRODUCED"
    return "UNAVAILABLE" if reproductions else "NOT_ATTEMPTED"

def pointer_value(document, pointer):
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("Evidence requires a JSON pointer.")
    value = document
    try:
        for key in pointer[1:].split("/"):
            key = key.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
    except (ValueError, KeyError, TypeError, IndexError):
        raise ValueError("Evidence pointer does not identify an observation.") from None
    return value

def validate_final(report, steps):
    validate(report, FINAL_SCHEMA)
    if report["reproduction_status"] != reproduction_status(steps):
        raise ValueError("Reproduction status must agree with actual observations.")
    by_step = {step["step"]: step for step in steps}
    groups = set()
    families = {"run_reproduction": "execution", "run_tests": "execution",
                "search_code": "source", "read_file": "source",
                "read_logs": "runtime", "inspect_database": "database"}
    for item in report["evidence"]:
        step = by_step.get(item["step"])
        if not step or step["result"]["status"] != "ok":
            raise ValueError("Evidence must reference a successful tool observation.")
        if not item["pointer"].startswith("/data/"):
            raise ValueError("Evidence must cite tool data, not metadata.")
        value = pointer_value(step["result"], item["pointer"])
        rendered = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False)
        if item["quote"] not in rendered:
            raise ValueError("Evidence excerpt does not match its cited observation.")
        groups.add(families[step["tool"]])
    for hypothesis in report["rejected_hypotheses"]:
        if not hypothesis["evidence_steps"] or any(
            i not in by_step or by_step[i]["result"]["status"] != "ok" for i in hypothesis["evidence_steps"]
        ):
            raise ValueError("Rejected hypotheses need observed evidence.")
    if report["status"] == "ROOT_CAUSE_IDENTIFIED":
        if not report["root_cause"] or len(groups) < 2 or groups <= {"source"}:
            raise ValueError("Root cause requires independent evidence families, not suspicious code alone.")
        if report["reproduction_status"] != "CONFIRMED" and not report["limitations"]:
            raise ValueError("Unconfirmed reproduction must be acknowledged as a limitation.")
    elif report["root_cause"] is not None:
        raise ValueError("Unestablished root causes must remain null.")

def fallback(task, steps, status, limitation):
    return {
        "status": status, "symptom": task["bug_report"], "reproduction_status": reproduction_status(steps),
        "root_cause": None, "root_cause_category": None, "affected_subsystem": None,
        "evidence": [], "rejected_hypotheses": [], "confidence": "low",
        "recommended_next_action": "Review the recorded observations and resolve the stated limitation before continuing.",
        "limitations": [limitation],
    }

def observation_view(result, max_chars=24000):
    # No silent context loss: preserve structure and advertise any field truncation.
    changes = []
    def shrink(value, path=""):
        if isinstance(value, str) and len(value) > 4500:
            changes.append(path)
            return value[:4500] + " [truncated for model]"
        if isinstance(value, dict):
            return {k: shrink(v, path + "/" + k) for k, v in value.items()}
        if isinstance(value, list):
            if len(value) > 30:
                changes.append(path)
            return [shrink(v, path + "/" + str(i)) for i, v in enumerate(value[:30])]
        return value
    view = shrink(result)
    if len(json.dumps(view)) > max_chars:
        return {"status": result["status"], "data": None,
                "error": {"code": "observation_too_large", "message": "Request a narrower result to inspect evidence."},
                "metadata": result["metadata"], "view_truncated": True}
    if changes:
        view["view_truncated"] = True
        view["truncated_paths"] = changes
    return view

def investigate(context, task, provider, budget=Budget(), progress=None):
    validate_task(task, context)
    if set(TOOLS) != set(TOOL_INPUTS):
        raise ValueError("Only the six approved tools may be registered.")
    run_id = uuid4().hex
    directory = context.session_dir / "agent-runs" / run_id
    directory.mkdir(parents=True, mode=0o700)
    start = monotonic()
    end = start + budget.max_seconds
    steps, events = [], []
    turns, invalid, consecutive_invalid = 0, 0, 0
    usage = {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}
    fingerprint = hashlib.sha256(json.dumps(
        {"prompt": SYSTEM_PROMPT, "catalog": CATALOG, "decision": DECISION_SCHEMA}, sort_keys=True).encode()).hexdigest()
    model_config = asdict(provider.config)
    initial = {"task": task, "model": model_config, "budget": asdict(budget),
               "prompt_contract_sha256": fingerprint, "snapshot_id": context.repository.snapshot_id}
    (directory / "initial.json").write_text(json.dumps(initial, indent=2))
    transcript = [{"role": "user", "text": json.dumps({"task": task, "tools": CATALOG})}]

    def emit(event):
        events.append(event)
        with (directory / "trajectory.jsonl").open("a") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        if progress:
            progress({k: event[k] for k in ("event", "step", "tool", "status") if k in event})

    final = None
    stopping_reason = None
    while turns < budget.max_tool_calls + 3:
        remaining = end - monotonic()
        if remaining <= 0:
            stopping_reason = "time_budget"
            break
        turns += 1
        request = [*transcript, {"role": "user", "text": json.dumps({
            "budget": {"tool_calls_remaining": budget.max_tool_calls - len(steps),
                       "seconds_remaining": round(remaining, 1)},
            "instruction": "Choose one next action or finish with supported findings.",
        })}]
        if sum(len(m["text"]) for m in request) > 240000:
            stopping_reason = "context_budget"
            break
        try:
            with deadline(min(budget.model_timeout, remaining)):
                reply = provider.generate(SYSTEM_PROMPT, request, DECISION_SCHEMA,
                                          min(budget.model_timeout, remaining))
            for key in usage:
                usage[key] += reply.usage.get(key, 0)
            decision = reply.decision
            validate(decision, DECISION_SCHEMA)
            if (decision["action"] is None) == (decision["final_report"] is None):
                raise ValueError("Choose exactly one action or final report.")
            if decision["final_report"] is not None:
                validate_final(decision["final_report"], steps)
        except DeadlineExpired:
            stopping_reason = "time_budget" if monotonic() >= end else "model_timeout"
            break
        except ModelFailure as exc:
            emit({"event": "model_failure", "status": "TOOL_FAILURE", "code": exc.code, "message": exc.message})
            stopping_reason = exc.code
            break
        except ValueError as exc:
            invalid += 1
            consecutive_invalid += 1
            emit({"event": "decision_rejected", "status": "rejected", "message": str(exc)[:300]})
            if consecutive_invalid >= 2:
                stopping_reason = "invalid_decisions"
                break
            transcript.append({"role": "user", "text": json.dumps({
                "decision_error": str(exc)[:300], "instruction": "Correct the structure or gather the missing evidence.",
            })})
            continue
        consecutive_invalid = 0
        transcript.append({"role": "model", "text": json.dumps(decision)})
        if decision["final_report"] is not None:
            final = decision["final_report"]
            stopping_reason = "model_finished"
            emit({"event": "final", "status": final["status"],
                  "hypothesis_summary": decision["hypothesis_summary"],
                  "evidence_summary": decision["evidence_summary"]})
            break
        if len(steps) >= budget.max_tool_calls:
            stopping_reason = "tool_call_budget"
            break
        action = decision["action"]
        name, arguments = action["name"], action["arguments"]
        # Validation and tool implementation both enforce permissions. Context is never supplied by the model.
        validate(arguments, TOOL_INPUTS[name])
        step_number = len(steps) + 1
        emit({"event": "tool_selected", "step": step_number, "tool": name, "arguments": arguments,
              "hypothesis_summary": decision["hypothesis_summary"],
              "evidence_summary": decision["evidence_summary"], "status": "running"})
        try:
            context.operation_deadline = end
            with deadline(end - monotonic()):
                result = TOOLS[name](context, **arguments).to_dict()
            validate(result, output_schema(name))
        except DeadlineExpired:
            result = ToolResult("timeout", error=ToolError("investigation_timeout", "Investigation deadline reached.")).to_dict()
        except ValueError:
            result = ToolResult("error", error=ToolError("output_contract_failed", "Tool output violated its contract.")).to_dict()
        finally:
            context.operation_deadline = None
        step = {"step": step_number, "tool": name, "arguments": arguments, "result": result}
        steps.append(step)
        emit({"event": "tool_result", **step, "status": result["status"]})
        transcript.append({"role": "user", "text": json.dumps({
            "tool_step": step_number, "tool": name, "result": observation_view(result),
        })})
        if monotonic() >= end:
            stopping_reason = "time_budget"
            break
    if final is None:
        stopping_reason = stopping_reason or "model_turn_budget"
        status = "MAX_STEPS_REACHED" if stopping_reason in {
            "time_budget", "tool_call_budget", "model_turn_budget", "context_budget",
        } else "TOOL_FAILURE"
        final = fallback(task, steps, status, stopping_reason)
    validate(final, FINAL_SCHEMA)
    summary = {
        "run_id": run_id, "model": provider.config.model_name,
        "status": final["status"], "stopping_reason": stopping_reason,
        "tool_calls": len(steps), "model_turns": turns,
        "tools_used": [s["tool"] for s in steps],
        "incorrect_calls": sum(s["result"]["status"] != "ok" for s in steps),
        "invalid_decisions": invalid, "duration_ms": round((monotonic() - start) * 1000, 2),
        "usage": usage, "budget": asdict(budget), "prompt_contract_sha256": fingerprint,
        "snapshot_id": context.repository.snapshot_id, "artifacts": str(directory),
    }
    (directory / "final.json").write_text(json.dumps(final, indent=2))
    (directory / "summary.json").write_text(json.dumps(summary, indent=2))
    return {"final": final, "summary": summary}

"""Day 5 explicit LangGraph orchestration for the one read-only investigator."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from time import monotonic, sleep
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from ..contracts import ToolError, ToolResult, utc_now
from ..llms.provider import ModelFailure
from ..tools import TOOLS
from .investigator import (Budget, DeadlineExpired, deadline, fallback, observation_view,
                           reproduction_status, validate_final, validate_hypotheses, validate_task)
from .prompt import GRAPH_PROMPT as SYSTEM_PROMPT
from .auditor import AUDITOR_PROMPT, audit_request
from .schemas import (CATALOG, AUDIT_SCHEMA, FINAL_SCHEMA, INVESTIGATION_DECISION_SCHEMA,
                      TOOL_INPUTS, output_schema, validate)
from .state import STATE_SCHEMA, atomic_json, load_state, run_directory, session_lock, sync_investigation_view


class InvestigationState(TypedDict, total=False):
    """Typed view of the existing persisted Day 4 investigation state."""
    version: int
    run_id: str
    session_id: str
    initial: dict[str, Any]
    phase: str
    graph_next: str
    steps: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    reviewed_step: int
    pending_action: dict[str, Any] | None
    pending_model: bool
    transcript: list[dict[str, Any]]
    events: list[dict[str, Any]]
    provider_failures: list[dict[str, Any]]
    tool_failures: list[dict[str, Any]]
    turns: int
    decisions: int
    invalid: int
    consecutive_invalid: int
    decision_repair_attempts: int
    resume_count: int
    elapsed_seconds: float
    usage: dict[str, int]
    usage_by_role: dict[str, dict[str, int]]
    latency_ms_by_role: dict[str, float]
    final: dict[str, Any] | None
    stopping_reason: str | None
    updated_at: str
    provider_retry_count: int
    evaluation: dict[str, Any] | None
    audits: list[dict[str, Any]]
    audit_cycles: int
    incident: dict[str, Any]
    reproduction: dict[str, Any] | None
    observations: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    tool_history: list[dict[str, Any]]
    provider_errors: list[dict[str, Any]]
    current_subsystem: str | None
    status: str
    step_count: int
    model_calls: int
    limitation: str | None
    recovery_target: str
    planned_action: dict[str, Any]


class GraphRuntime:
    def __init__(self, context, provider, budget: Budget, directory: Path, state: dict, progress=None):
        self.context = context
        self.provider = provider
        self.budget = budget
        self.directory = directory
        self.state = state
        self.progress = progress
        self.started = monotonic()
        self.prior_elapsed = state["elapsed_seconds"]
        self.deadline_at = self.started + max(0, budget.max_seconds - self.prior_elapsed)

    def emit(self, event, **data):
        if self.progress:
            self.progress({"event": event, "run_id": self.state["run_id"], **data})

    def operator_boundary(self):
        """Consume steering once, only between operations; preserve the next graph node."""
        path = self.context.session_dir / "operator-events.jsonl"
        cursor = self.state["initial"].get("operator_cursor", 0)
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines[cursor:], cursor + 1):
                try:
                    entry = json.loads(line)
                except ValueError:
                    break
                if entry.get("kind") == "message" and len(self.state["transcript"]) < 90:
                    self.state["transcript"].append({"role": "user", "text": json.dumps({
                        "operator_message": entry["message"], "instruction":
                        "Apply this direction within the existing read-only tool permissions and budgets."})})
                    self.emit("operator.message_applied", message_id=entry.get("id"), message="Operator direction included at this safe boundary.")
                self.state["initial"]["operator_cursor"] = index
            self.checkpoint("operator_boundary")
        control_path = self.context.session_dir / "operator-control.json"
        control = json.loads(control_path.read_text()) if control_path.exists() else {}
        action = control.get("state")
        if action in {"PAUSE_REQUESTED", "STOP_REQUESTED"} and not self.state.get("final"):
            self.state["phase"] = "paused" if action == "PAUSE_REQUESTED" else "stopped"
            self.state["stopping_reason"] = "operator_" + self.state["phase"]
            self.checkpoint("operator_boundary", self.state["phase"])
            self.emit("run." + self.state["phase"], message="Checkpoint saved at a safe execution boundary.")
            raise OperatorHalt()

    def checkpoint(self, node: str, status: str = "running"):
        sync_investigation_view(self.state)
        self.state["updated_at"] = utc_now()
        self.state["events"].append({"sequence": len(self.state["events"]) + 1,
            "at": self.state["updated_at"], "event": "graph_transition", "node": node, "status": status,
            "step": len(self.state["steps"])})
        self.state["elapsed_seconds"] = self.prior_elapsed + monotonic() - self.started
        validate(self.state, STATE_SCHEMA)
        atomic_json(self.directory / "state.json", self.state)
        with (self.directory / "trajectory.jsonl").open("w", encoding="utf-8") as stream:
            for event in self.state["events"]:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        if self.progress:
            self.progress({"event": "graph_transition", "node": node, "status": status,
                           "step": len(self.state["steps"]), "run_id": self.state["run_id"]})

    def record_provider_failure(self, exc: ModelFailure, target: str):
        self.emit("provider.error", code=exc.code, message=exc.message, retryable=exc.retryable)
        failure = {"code": exc.code, "message": exc.message, "retryable": exc.retryable,
                   "after_step": len(self.state["steps"]), "target": target,
                   "attempt": self.state["provider_retry_count"] + 1}
        self.state["provider_failures"].append(failure)
        self.state["pending_model"] = False
        self.state["recovery_target"] = target
        self.state["limitation"] = exc.code
        self.state["graph_next"] = "recovery"
        self.checkpoint("provider_recovery", "MODEL_PROVIDER_FAILURE")

    def call_model(self, system: str, messages: list[dict], schema: dict, target: str):
        label = "Evidence Auditor" if target == "evidence_auditor" else "Investigator"
        self.emit("stage.changed", label="Evidence audit" if target == "evidence_auditor" else "Investigation")
        self.emit("agent.started", label=label)
        if self.state["model_calls"] >= self.budget.max_model_calls or monotonic() >= self.deadline_at:
            self.state["limitation"] = "model_call_budget" if self.state["model_calls"] >= self.budget.max_model_calls else "time_budget"
            self.state["graph_next"] = "report_limitation"
            self.emit("agent.finished", label=label, status="budget_exhausted")
            return None
        remaining = self.deadline_at - monotonic()
        self.state["turns"] += 1
        self.state["model_calls"] += 1
        self.state["pending_model"] = True
        self.checkpoint("model_request", "running")
        try:
            call_started = monotonic()
            with deadline(min(self.budget.model_timeout, remaining)):
                reply = self.provider.generate(system, messages, schema, min(self.budget.model_timeout, remaining))
            self.state["pending_model"] = False
            failover = getattr(self.provider, "last_failover", None)
            if failover:
                self.emit("provider.fallback", **failover)
                self.state["provider_failures"].append({**failover, "retryable": True,
                    "after_step": len(self.state["steps"]), "target": target, "fallback_succeeded": True})
            role = "auditor" if target == "evidence_auditor" else ("feedback_investigator" if self.state.get("audit_cycles", 0) else "investigator")
            self.state.setdefault("usage_by_role", {}).setdefault(role, {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0})
            self.state.setdefault("latency_ms_by_role", {}).setdefault(role, 0.0)
            for key in self.state["usage"]:
                amount = reply.usage.get(key, 0)
                self.state["usage"][key] += amount
                self.state["usage_by_role"][role][key] += amount
            self.state["latency_ms_by_role"][role] += round((monotonic() - call_started) * 1000, 2)
            self.state["provider_retry_count"] = 0
            actual = self.provider.fallback if failover and hasattr(self.provider, "fallback") else self.provider
            self.emit("agent.finished", label=label, usage=reply.usage, model=actual.config.model_name,
                      duration_ms=round((monotonic() - call_started) * 1000, 2))
            return reply.decision
        except DeadlineExpired:
            self.record_provider_failure(ModelFailure("model_timeout", "Model request exceeded its deadline.", True), target)
        except ModelFailure as exc:
            self.record_provider_failure(exc, target)
        self.emit("agent.failed", label=label)
        return None

    def add_step(self, name: str, arguments: dict, result: dict):
        step = {"step": len(self.state["steps"]) + 1, "tool": name, "arguments": arguments, "result": result}
        self.state["steps"].append(step)
        self.emit("tool.completed" if result["status"] == "ok" else "tool.failed",
                  tool=name, step=step["step"], status=result["status"],
                  code=(result.get("error") or {}).get("code"))
        # Tool outputs are bounded by their existing contracts and redacted by the event bridge.
        self.emit("evidence.added", id=f"E-{step['step']}", title=name, tool=name,
                  step=step["step"], result=observation_view(result),
                  path=arguments.get("file_path"))
        if name == "run_reproduction":
            self.emit("reproduction.result", result=observation_view(result))
        if result["status"] != "ok":
            self.state["tool_failures"].append({"step": step["step"], "tool": name, "error": result["error"]})
        self.state["transcript"].append({"role": "user", "text": json.dumps({
            "tool_step": step["step"], "tool": name, "result": observation_view(result)})})
        return step


def _tool(runtime: GraphRuntime, name: str, arguments: dict) -> dict:
    runtime.emit("tool.started", tool=name, step=len(runtime.state["steps"]) + 1)
    if name == "run_reproduction":
        runtime.emit("stage.changed", label="Reproduction")
    elif name == "read_logs":
        runtime.emit("stage.changed", label="Runtime evidence")
    runtime.state["pending_action"] = {"step": len(runtime.state["steps"]) + 1, "name": name, "arguments": arguments}
    runtime.checkpoint("tool_dispatch", "running")
    try:
        runtime.context.operation_deadline = runtime.deadline_at
        with deadline(runtime.deadline_at - monotonic()):
            result = TOOLS[name](runtime.context, **arguments).to_dict()
        validate(result, output_schema(name))
    except DeadlineExpired:
        result = ToolResult("timeout", error=ToolError("investigation_timeout", "Investigation deadline reached.")).to_dict()
    except ValueError:
        result = ToolResult("error", error=ToolError("output_contract_failed", "Tool output violated its contract.")).to_dict()
    except Exception:
        result = ToolResult("error", error=ToolError("tool_exception", "Tool failed unexpectedly.")).to_dict()
    finally:
        runtime.context.operation_deadline = None
    runtime.state["pending_action"] = None
    return runtime.add_step(name, arguments, result)


def _request(runtime: GraphRuntime, instruction: str) -> list[dict]:
    state = runtime.state
    return [{"role": "user", "text": json.dumps({"task": state["initial"]["task"], "tools": CATALOG})},
            *state["transcript"], {"role": "user", "text": json.dumps({
                "state": {"latest_tool_step": len(state["steps"]), "reproduction_status": reproduction_status(state["steps"])},
                "incident": state["incident"], "observations": state["observations"],
                "hypotheses": state["hypotheses"], "evidence": state["evidence"],
                "current_subsystem": state["current_subsystem"],
                "budget": {"tool_calls_remaining": runtime.budget.max_tool_calls - len(state["steps"]),
                           "model_calls_remaining": runtime.budget.max_model_calls - state["model_calls"],
                           "seconds_remaining": round(max(0, runtime.deadline_at - monotonic()), 1)},
                "instruction": instruction})}]



def _auditor_final_report(state: dict, hypothesis: dict) -> dict:
    """Build the fixed report contract after the Auditor supports a cited hypothesis."""
    final = {"status": "ROOT_CAUSE_SUPPORTED", "symptom": state["initial"]["task"]["bug_report"],
        "reproduction_status": reproduction_status(state["steps"]), "root_cause": hypothesis["claim"],
        "root_cause_category": "application", "affected_subsystem": state.get("current_subsystem") or "unknown",
        "evidence": hypothesis["evidence"], "rejected_hypotheses": [], "confidence": hypothesis["confidence"],
        "recommended_next_action": "Review the evidence-backed root cause before planning remediation.", "limitations": []}
    validate_final(final, state["steps"])
    return final

class OperatorHalt(Exception):
    pass


def build_graph(runtime: GraphRuntime):
    graph = StateGraph(InvestigationState)

    def check_budget(state: InvestigationState):
        runtime.state = state
        runtime.operator_boundary()
        if state.get("final"):
            state["graph_next"] = "finalize"
        elif monotonic() >= runtime.deadline_at:
            state["limitation"] = "time_budget"
            state["graph_next"] = "report_limitation"
        elif len(state["steps"]) >= runtime.budget.max_tool_calls:
            state["limitation"] = "tool_call_budget"
            state["graph_next"] = "report_limitation"
        elif state["model_calls"] >= runtime.budget.max_model_calls and state["graph_next"] in {"investigate", "evidence_auditor", "recovery"}:
            state["limitation"] = "model_call_budget"
            state["graph_next"] = "report_limitation"
        return state

    def reproduce(state: InvestigationState):
        runtime.state = state
        if any(step["tool"] == "run_reproduction" for step in state["steps"]):
            state["graph_next"] = "collect_runtime_evidence"
            return state
        task = state["initial"]["task"]
        arguments = {"repository_path": task["repository"]}
        if task.get("reproduction_command") is not None:
            arguments["reproduction_command"] = task["reproduction_command"]
        _tool(runtime, "run_reproduction", arguments)
        state["graph_next"] = "report_limitation" if reproduction_status(state["steps"]) == "UNAVAILABLE" else "collect_runtime_evidence"
        runtime.checkpoint("reproduce", state["steps"][-1]["result"]["status"])
        return state

    def collect_runtime_evidence(state: InvestigationState):
        runtime.state = state
        if reproduction_status(state["steps"]) != "CONFIRMED":
            state["graph_next"] = "report_limitation"
            state["limitation"] = "reproduction_unavailable"
            return state
        if not any(step["tool"] == "read_logs" for step in state["steps"]):
            reproduce_step = next(step for step in state["steps"] if step["tool"] == "run_reproduction")
            run_id = (reproduce_step["result"].get("metadata") or {}).get("run_id")
            arguments = {"source": "application", "run_id": run_id} if run_id else {"source": "application"}
            _tool(runtime, "read_logs", arguments)
            if state["steps"][-1]["result"]["status"] != "ok":
                state["limitation"] = "runtime_evidence_unavailable"
                state["graph_next"] = "report_limitation"
                runtime.checkpoint("collect_runtime_evidence", "TOOL_FAILURE")
                return state
        state["graph_next"] = "investigate"
        runtime.checkpoint("collect_runtime_evidence")
        return state

    def investigate(state: InvestigationState):
        runtime.state = state
        decision = runtime.call_model(SYSTEM_PROMPT, _request(runtime,
            "Choose action=TOOL_CALL to gather evidence, or action=FINAL for independent audit. Always include a nonempty evidence_goal. Do not issue a final report."),
            INVESTIGATION_DECISION_SCHEMA, "investigate")
        if decision is None:
            return state
        try:
            validate(decision, INVESTIGATION_DECISION_SCHEMA)
            mode = decision["action"]
            if mode == "TOOL_CALL" and (decision["tool"] is None or decision["arguments"] is None):
                raise ValueError("TOOL_CALL requires tool and arguments.")
            if mode == "FINAL" and (decision["tool"] is not None or decision["arguments"] is not None):
                raise ValueError("FINAL requires no tool or arguments.")
            if mode == "BLOCKED" and (decision["tool"] is not None or decision["arguments"] is not None):
                raise ValueError("BLOCKED requires no tool or arguments.")
            if not decision["evidence_goal"]:
                raise ValueError("Every decision requires an evidence_goal.")
            if decision["reviewed_step"] != len(state["steps"]):
                raise ValueError("reviewed_step must equal the latest tool step.")
            validate_hypotheses(decision["hypotheses"], state["hypotheses"], state["steps"])
            if mode == "TOOL_CALL":
                arguments = decision["arguments"]
                validate(arguments, TOOL_INPUTS[decision["tool"]])
                expected_repository = state["initial"]["task"]["repository"]
                supplied_repository = arguments.get("repository", arguments.get("repository_path"))
                if supplied_repository is not None and supplied_repository != expected_repository:
                    raise ValueError("Tool repository must exactly match the investigation repository.")
        except ValueError as exc:
            state["invalid"] += 1
            state["consecutive_invalid"] += 1
            state["decision_repair_attempts"] += 1
            runtime.emit("decision.rejected", message=str(exc)[:300], attempt=state["decision_repair_attempts"])
            state["transcript"].append({"role": "user", "text": json.dumps({"decision_validation": {"valid": False, "error": str(exc)[:300], "attempt": state["decision_repair_attempts"], "max_attempts": 2, "required": ["action", "evidence_goal", "tool", "arguments", "hypothesis_id", "stable hypotheses"]}})})
            state["limitation"] = "invalid_decisions" if state["decision_repair_attempts"] >= 2 else None
            state["graph_next"] = "report_limitation" if state["limitation"] else "investigate"
            runtime.checkpoint("hypothesis_update", "rejected")
            return state
        state["consecutive_invalid"] = 0
        state["decision_repair_attempts"] = 0
        state["hypotheses"] = decision["hypotheses"]
        runtime.emit("hypothesis.updated", hypotheses=state["hypotheses"])
        state["reviewed_step"] = decision["reviewed_step"]
        state["planned_action"] = {"name": decision["tool"], "arguments": decision["arguments"]} if mode == "TOOL_CALL" else None
        state["transcript"].append({"role": "model", "text": json.dumps({
            "hypothesis_summary": decision["hypothesis_summary"], "evidence_summary": decision["evidence_summary"],
            "action": mode, "tool": decision["tool"], "arguments": decision["arguments"]})})
        if mode == "BLOCKED":
            state["limitation"] = "insufficient_evidence"
            state["graph_next"] = "report_limitation"
        else:
            state["graph_next"] = "evidence_auditor" if mode == "FINAL" else "execute_tool"
        runtime.checkpoint("hypothesis_update")
        return state

    def execute_tool(state: InvestigationState):
        runtime.state = state
        action = state.get("planned_action")
        if not action:
            state["limitation"] = "missing_tool_action"
            state["graph_next"] = "report_limitation"
            return state
        name, arguments = action["name"], action["arguments"]
        if name == "run_reproduction" and any(step["tool"] == "run_reproduction" for step in state["steps"]):
            state["limitation"] = "duplicate_reproduction"
            state["graph_next"] = "report_limitation"
            return state
        step = _tool(runtime, name, arguments)
        state["planned_action"] = None
        if step["result"]["status"] != "ok":
            state["limitation"] = "tool_failure"
            state["graph_next"] = "report_limitation"
        else:
            state["graph_next"] = "investigate"
        runtime.checkpoint("tool_result", step["result"]["status"])
        return state

    def evidence_auditor(state: InvestigationState):
        runtime.state = state
        audit = runtime.call_model(AUDITOR_PROMPT, audit_request(runtime.state), AUDIT_SCHEMA, "evidence_auditor")
        if audit is None:
            return state
        try:
            validate(audit, AUDIT_SCHEMA)
            verdict = audit["verdict"]
            if verdict == "SUPPORTED":
                matches = [h for h in state["hypotheses"] if h["status"] == "supported"]
                if not matches:
                    raise ValueError("SUPPORTED requires an evidence-linked supported hypothesis.")
                _auditor_final_report(state, matches[0])
        except ValueError as exc:
            state["invalid"] += 1
            state["consecutive_invalid"] += 1
            state["transcript"].append({"role": "user", "text": json.dumps({"audit_error": str(exc)[:300]})})
            state["limitation"] = "invalid_decisions" if state["consecutive_invalid"] >= 3 else None
            state["graph_next"] = "report_limitation" if state["limitation"] else "evidence_auditor"
            runtime.checkpoint("evidence_auditor", "rejected")
            return state
        state["consecutive_invalid"] = 0
        state["evaluation"] = audit
        runtime.emit("auditor.verdict", **audit)
        state["audits"].append(audit)
        state["audit_cycles"] += 1
        if audit["verdict"] == "SUPPORTED":
            state["graph_next"] = "root_cause_report"
        elif state["audit_cycles"] >= 3:
            state["limitation"] = "audit_cycle_budget"
            state["graph_next"] = "report_limitation"
        elif audit["verdict"] == "INSUFFICIENT":
            state["graph_next"] = "investigate_missing_evidence"
        else:
            state["transcript"].append({"role": "user", "text": json.dumps({"auditor_verdict": "CONTRADICTED", "unsupported_claims": audit["unsupported_claims"], "missing_evidence": audit["missing_evidence"], "required_next_evidence": audit["required_next_evidence"], "reason": audit["reason"], "instruction": "Reopen hypotheses and choose evidence needed to resolve the contradiction."})})
            state["graph_next"] = "investigate"
        runtime.checkpoint("evidence_auditor", audit["verdict"])
        return state

    def investigate_missing_evidence(state: InvestigationState):
        runtime.state = state
        audit = state["audits"][-1]
        state["transcript"].append({"role": "user", "text": json.dumps({"auditor_verdict": "INSUFFICIENT", "unsupported_claims": audit["unsupported_claims"], "missing_evidence": audit["missing_evidence"], "required_next_evidence": audit["required_next_evidence"], "reason": audit["reason"], "instruction": "Choose the permitted tool that best gathers this evidence. The Auditor does not choose tools."})})
        state["graph_next"] = "investigate"
        runtime.checkpoint("investigate_missing_evidence")
        return state

    def recovery(state: InvestigationState):
        runtime.state = state
        latest = state["provider_failures"][-1]
        if latest["retryable"] and state["provider_retry_count"] < runtime.provider.config.max_transient_retries:
            delay = 0.5 * (2 ** state["provider_retry_count"])
            state["provider_retry_count"] += 1
            runtime.emit("provider.retry", attempt=state["provider_retry_count"], delay_seconds=delay,
                         code=latest["code"])
            runtime.checkpoint("provider_recovery", "retrying")
            if monotonic() + delay < runtime.deadline_at:
                sleep(delay)
                state["graph_next"] = state.get("recovery_target") or "investigate"
            else:
                state["limitation"] = "time_budget"
                state["graph_next"] = "report_limitation"
        else:
            state["limitation"] = latest["code"]
            state["graph_next"] = "report_limitation"
            state["phase"] = "paused"
            runtime.checkpoint("provider_recovery", "MODEL_PROVIDER_FAILURE")
        return state

    def report_limitation(state: InvestigationState):
        runtime.state = state
        reason = state.get("limitation") or "insufficient_evidence"
        if reproduction_status(state["steps"]) == "UNAVAILABLE":
            status = "REPRODUCTION_UNAVAILABLE"
        elif reproduction_status(state["steps"]) == "NOT_REPRODUCED":
            status = "REPRODUCTION_FAILED"
        elif reason in {"provider_error", "model_timeout"}:
            status = "MODEL_PROVIDER_FAILURE"
        elif reason == "invalid_decisions":
            status = "MODEL_DECISION_FAILURE"
        elif reason == "tool_failure":
            last_error = (state["tool_failures"][-1].get("error") or {}).get("code") if state["tool_failures"] else ""
            status = "TOOL_PERMISSION_FAILURE" if last_error in {"path_denied", "benchmark_denied", "permission_denied"} else "TOOL_EXECUTION_FAILURE"
        elif reason == "contradicted":
            status = "CONTRADICTED"
        else:
            status = "INSUFFICIENT_EVIDENCE"
        state["final"] = fallback(state["initial"]["task"], state["steps"], status, reason)
        state["graph_next"] = "finalize"
        runtime.checkpoint("report_limitation", status)
        return state

    def root_cause_report(state: InvestigationState):
        runtime.state = state
        hypothesis = next(item for item in state["hypotheses"] if item["status"] == "supported")
        state["final"] = _auditor_final_report(state, hypothesis)
        runtime.emit("stage.changed", label="Root cause")
        runtime.emit("report.ready", report=state["final"])
        state["graph_next"] = "finalize"
        runtime.checkpoint("root_cause_report", "ROOT_CAUSE_SUPPORTED")
        return state

    def finalize(state: InvestigationState):
        runtime.state = state
        validate(state["final"], FINAL_SCHEMA)
        validate_final(state["final"], state["steps"])
        state["phase"] = "paused" if state["final"]["status"] == "MODEL_PROVIDER_FAILURE" else "finished"
        state["stopping_reason"] = state.get("limitation") or "graph_finished"
        state["graph_next"] = "finalize"
        runtime.checkpoint("finalize", state["final"]["status"])
        return state

    graph.add_node("check_budget", check_budget)
    graph.add_node("reproduce", reproduce)
    graph.add_node("collect_runtime_evidence", collect_runtime_evidence)
    graph.add_node("investigate", investigate)
    graph.add_node("execute_tool", execute_tool)
    graph.add_node("evidence_auditor", evidence_auditor)
    graph.add_node("investigate_missing_evidence", investigate_missing_evidence)
    def paused(state: InvestigationState):
        runtime.state = state
        return state

    graph.add_node("recovery", recovery)
    graph.add_node("report_limitation", report_limitation)
    graph.add_node("root_cause_report", root_cause_report)
    graph.add_node("finalize", finalize)
    graph.add_node("paused", paused)
    routes = {name: name for name in ["reproduce", "collect_runtime_evidence", "investigate", "execute_tool", "paused",
        "evidence_auditor", "investigate_missing_evidence", "recovery", "report_limitation", "root_cause_report", "finalize"]}
    graph.add_edge(START, "check_budget")
    for name in ["check_budget", "reproduce", "collect_runtime_evidence", "investigate", "execute_tool", "evidence_auditor", "investigate_missing_evidence", "recovery", "report_limitation", "root_cause_report"]:
        graph.add_edge(name, "check_budget") if name != "check_budget" else None
    graph.add_conditional_edges("check_budget", lambda state: state.get("graph_next") or "report_limitation", routes)
    graph.add_edge("finalize", END)
    graph.add_edge("paused", END)
    return graph.compile()


def _initial_state(context, task, provider, budget):
    validate_task(task, context)
    fingerprint = hashlib.sha256(json.dumps({"prompt": SYSTEM_PROMPT, "catalog": CATALOG,
        "investigate": INVESTIGATION_DECISION_SCHEMA, "auditor": AUDIT_SCHEMA}, sort_keys=True).encode()).hexdigest()
    return {"version": 2, "run_id": uuid4().hex, "session_id": context.config["id"],
        "initial": {"task": task, "model": asdict(provider.config), "budget": asdict(budget),
                    "prompt_contract_sha256": fingerprint, "snapshot_id": context.repository.snapshot_id},
        "phase": "running", "graph_next": "reproduce", "steps": [], "hypotheses": [], "reviewed_step": 0,
        "pending_action": None, "pending_model": False, "transcript": [], "events": [], "provider_failures": [], "tool_failures": [],
        "turns": 0, "decisions": 0, "invalid": 0, "consecutive_invalid": 0, "decision_repair_attempts": 0, "resume_count": 0,
        "elapsed_seconds": 0.0, "usage": {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0},
        "usage_by_role": {role: {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0} for role in ("investigator", "auditor", "feedback_investigator")},
        "latency_ms_by_role": {role: 0.0 for role in ("investigator", "auditor", "feedback_investigator")},
        "final": None, "stopping_reason": None, "updated_at": utc_now(), "provider_retry_count": 0, "evaluation": None, "audits": [], "audit_cycles": 0,
        "incident": {}, "reproduction": None, "observations": [], "evidence": [], "tool_history": [], "provider_errors": [],
        "current_subsystem": None, "status": "RUNNING", "step_count": 0, "model_calls": 0,
        "planned_action": None, "recovery_target": None, "limitation": None}


def investigate_graph(context, task, provider, budget=Budget(), progress=None, *, resume_run_id=None, retry_invalid=False):
    """Run or resume the Day 5 LangGraph state machine using one existing checkpoint."""
    with session_lock(context):
        if resume_run_id:
            state = load_state(context, resume_run_id)
            initial = state["initial"]
            if task is not None and task != initial["task"]:
                raise ValueError("Resume cannot change the original task.")
            task = initial["task"]
            budget = Budget(**initial["budget"])
            can_retry_invalid = retry_invalid and (state.get("final") or {}).get("status") == "MODEL_DECISION_FAILURE" and state.get("limitation") == "invalid_decisions"
            if state["phase"] in {"finished", "stopped"} and not can_retry_invalid:
                return _result(context, provider, budget, state, run_directory(context, state["run_id"]))
            if can_retry_invalid:
                state["final"] = None
                state["invalid"] = 0
                state["consecutive_invalid"] = 0
                state["decision_repair_attempts"] = 0
                state["limitation"] = None
                state["graph_next"] = "evidence_auditor"
            state["resume_count"] += 1
            state["phase"] = "running"
            previous_provider_failure = bool(state.get("provider_failures"))
            if ((state.get("final") or {}).get("status") == "MODEL_PROVIDER_FAILURE" or
                    (state.get("final") is None and state.get("graph_next") == "finalize" and previous_provider_failure)) and                     (state.get("limitation") in {"provider_error", "model_timeout"} or previous_provider_failure):
                state["final"] = None
                state["provider_retry_count"] = 0
                state["graph_next"] = state.get("recovery_target") or "investigate"
            if state.get("pending_action"):
                state["limitation"] = "tool_failure"
                state["graph_next"] = "report_limitation"
            elif state.get("pending_model"):
                state["pending_model"] = False
                state["recovery_target"] = state.get("graph_next", "investigate")
                state["provider_failures"].append({"code": "model_interrupted", "message": "Process stopped during a model request.",
                    "retryable": True, "after_step": len(state["steps"]), "target": state["recovery_target"], "attempt": 0})
                state["graph_next"] = "recovery"
        else:
            state = _initial_state(context, task, provider, budget)
        directory = run_directory(context, state["run_id"])
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        if not (directory / "initial.json").exists():
            atomic_json(directory / "initial.json", state["initial"])
        runtime = GraphRuntime(context, provider, budget, directory, state, progress)
        runtime.checkpoint("graph_start", "running")
        graph = build_graph(runtime)
        try:
            graph.invoke(state, {"recursion_limit": 200})
        except OperatorHalt:
            pass
        except KeyboardInterrupt:
            runtime.state["phase"] = "stopped"
            runtime.state["stopping_reason"] = "operator_stopped"
            runtime.checkpoint("operator_stop", "stopped")
            runtime.emit("run.stopped", message="Stopped; unfinished operations are not replayed.")
        return _result(context, provider, budget, runtime.state, directory)


def _result(context, provider, budget, state, directory):
    sync_investigation_view(state)
    final = state["final"]
    if final is None and state["phase"] not in {"paused", "stopped"}:
        final = fallback(state["initial"]["task"], state["steps"], "TOOL_EXECUTION_FAILURE", "graph_incomplete")
    summary = {"run_id": state["run_id"], "model": provider.config.model_name, "orchestrator": "langgraph",
        "status": final["status"] if final else state["phase"].upper(), "stopping_reason": state.get("stopping_reason"), "tool_calls": len(state["steps"]),
        "model_calls": state["model_calls"], "tools_used": [step["tool"] for step in state["steps"]],
        "incorrect_calls": sum(step["result"]["status"] != "ok" for step in state["steps"]), "invalid_decisions": state["invalid"],
        "duration_ms": round(state["elapsed_seconds"] * 1000, 2), "usage": state["usage"], "usage_by_role": state.get("usage_by_role", {}), "latency_ms_by_role": state.get("latency_ms_by_role", {}), "budget": asdict(budget),
        "snapshot_id": context.repository.snapshot_id, "artifacts": str(directory), "phase": state["phase"],
        "resumable": state["phase"] == "paused", "resume_count": state["resume_count"],
        "provider_failures": len(state["provider_failures"]), "tool_failures": len(state["tool_failures"]),
        "hypotheses": state["hypotheses"], "graph_next": state["graph_next"]}
    atomic_json(directory / "final.json", final)
    atomic_json(directory / "summary.json", summary)
    return {"final": final, "summary": summary}


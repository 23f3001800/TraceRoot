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
from .prompt import SYSTEM_PROMPT
from .schemas import (CATALOG, EVALUATION_SCHEMA, FINAL_SCHEMA, INVESTIGATION_DECISION_SCHEMA,
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
    resume_count: int
    elapsed_seconds: float
    usage: dict[str, int]
    final: dict[str, Any] | None
    stopping_reason: str | None
    updated_at: str
    provider_retry_count: int
    evaluation: dict[str, Any] | None
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

EVALUATION_PROMPT = """You are the evidence evaluation boundary for one read-only investigation.
You do not choose a new tool and you do not change hypotheses. Assess only the supplied
observations, hypothesis registry and evidence links. Return YES only if one supported
hypothesis is a root cause backed by exact citations from independent evidence families.
Return NO when more useful investigation remains. Return BLOCKED when access or evidence
cannot support a conclusion. A final report is required only for YES. Never invent evidence,
paths, failures, or modifications. Confidence is secondary to cited observations."""


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
        failure = {"code": exc.code, "message": exc.message, "retryable": exc.retryable,
                   "after_step": len(self.state["steps"]), "target": target,
                   "attempt": self.state["provider_retry_count"] + 1}
        self.state["provider_failures"].append(failure)
        self.state["pending_model"] = False
        self.state["recovery_target"] = target
        self.state["limitation"] = exc.code
        self.state["graph_next"] = "recovery"
        self.checkpoint("provider_recovery", "TOOL_FAILURE")

    def call_model(self, system: str, messages: list[dict], schema: dict, target: str):
        if self.state["model_calls"] >= self.budget.max_model_calls or monotonic() >= self.deadline_at:
            self.state["limitation"] = "model_call_budget" if self.state["model_calls"] >= self.budget.max_model_calls else "time_budget"
            self.state["graph_next"] = "report_limitation"
            return None
        remaining = self.deadline_at - monotonic()
        self.state["turns"] += 1
        self.state["model_calls"] += 1
        self.state["pending_model"] = True
        self.checkpoint("model_request", "running")
        try:
            with deadline(min(self.budget.model_timeout, remaining)):
                reply = self.provider.generate(system, messages, schema, min(self.budget.model_timeout, remaining))
            self.state["pending_model"] = False
            for key in self.state["usage"]:
                self.state["usage"][key] += reply.usage.get(key, 0)
            self.state["provider_retry_count"] = 0
            return reply.decision
        except DeadlineExpired:
            self.record_provider_failure(ModelFailure("model_timeout", "Model request exceeded its deadline.", True), target)
        except ModelFailure as exc:
            self.record_provider_failure(exc, target)
        return None

    def add_step(self, name: str, arguments: dict, result: dict):
        step = {"step": len(self.state["steps"]) + 1, "tool": name, "arguments": arguments, "result": result}
        self.state["steps"].append(step)
        if result["status"] != "ok":
            self.state["tool_failures"].append({"step": step["step"], "tool": name, "error": result["error"]})
        self.state["transcript"].append({"role": "user", "text": json.dumps({
            "tool_step": step["step"], "tool": name, "result": observation_view(result)})})
        return step


def _tool(runtime: GraphRuntime, name: str, arguments: dict) -> dict:
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
                "state": {"latest_tool_step": len(state["steps"]), "reproduction_status": reproduction_status(state["steps"])},
                "incident": state["incident"], "observations": state["observations"],
                "hypotheses": state["hypotheses"], "evidence": state["evidence"],
                "current_subsystem": state["current_subsystem"],
                "budget": {"tool_calls_remaining": runtime.budget.max_tool_calls - len(state["steps"]),
                           "model_calls_remaining": runtime.budget.max_model_calls - state["model_calls"],
                           "seconds_remaining": round(max(0, runtime.deadline_at - monotonic()), 1)},
                "instruction": instruction})}]


def build_graph(runtime: GraphRuntime):
    graph = StateGraph(InvestigationState)

    def check_budget(state: InvestigationState):
        runtime.state = state
        if state.get("final"):
            state["graph_next"] = "finalize"
        elif monotonic() >= runtime.deadline_at:
            state["limitation"] = "time_budget"
            state["graph_next"] = "report_limitation"
        elif len(state["steps"]) >= runtime.budget.max_tool_calls:
            state["limitation"] = "tool_call_budget"
            state["graph_next"] = "report_limitation"
        elif state["model_calls"] >= runtime.budget.max_model_calls and state["graph_next"] in {"investigate", "evaluate_evidence", "recovery"}:
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
            "Choose one permitted evidence-gathering tool, or mark ready_for_evaluation when no further evidence is needed. Do not issue a final report; evidence evaluation is separate."),
            INVESTIGATION_DECISION_SCHEMA, "investigate")
        if decision is None:
            return state
        try:
            validate(decision, INVESTIGATION_DECISION_SCHEMA)
            if (decision["action"] is None) == (decision["ready_for_evaluation"] is False):
                raise ValueError("Choose one action or mark the evidence ready for evaluation.")
            if decision["reviewed_step"] != len(state["steps"]):
                raise ValueError("reviewed_step must equal the latest tool step.")
            validate_hypotheses(decision["hypotheses"], state["hypotheses"], state["steps"])
            if decision["action"] is not None:
                validate(decision["action"]["arguments"], TOOL_INPUTS[decision["action"]["name"]])
        except ValueError as exc:
            state["invalid"] += 1
            state["consecutive_invalid"] += 1
            state["transcript"].append({"role": "user", "text": json.dumps({"decision_error": str(exc)[:300]})})
            state["limitation"] = "invalid_decisions" if state["consecutive_invalid"] >= 3 else None
            state["graph_next"] = "report_limitation" if state["limitation"] else "investigate"
            runtime.checkpoint("hypothesis_update", "rejected")
            return state
        state["consecutive_invalid"] = 0
        state["hypotheses"] = decision["hypotheses"]
        state["reviewed_step"] = decision["reviewed_step"]
        state["planned_action"] = decision["action"]
        state["transcript"].append({"role": "model", "text": json.dumps({
            "hypothesis_summary": decision["hypothesis_summary"], "evidence_summary": decision["evidence_summary"],
            "action": decision["action"], "ready_for_evaluation": decision["ready_for_evaluation"]})})
        state["graph_next"] = "evaluate_evidence" if decision["ready_for_evaluation"] else "execute_tool"
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

    def evaluate_evidence(state: InvestigationState):
        runtime.state = state
        decision = runtime.call_model(EVALUATION_PROMPT, _request(runtime,
            "Evaluate whether the current evidence is sufficient. Return YES, NO, or BLOCKED. Do not select tools."),
            EVALUATION_SCHEMA, "evaluate_evidence")
        if decision is None:
            return state
        try:
            validate(decision, EVALUATION_SCHEMA)
            verdict = decision["decision"]
            if verdict == "YES":
                if decision["final_report"] is None:
                    raise ValueError("YES requires a final report.")
                validate_final(decision["final_report"], state["steps"])
                final = decision["final_report"]
                matches = [h for h in state["hypotheses"] if h["status"] == "supported" and h["claim"] == final["root_cause"]]
                if not matches or not any(all(item in h["evidence"] for item in final["evidence"]) for h in matches):
                    raise ValueError("Root cause must match a supported hypothesis and evidence links.")
            elif decision["final_report"] is not None:
                raise ValueError("Only YES may include a final report.")
        except ValueError as exc:
            state["invalid"] += 1
            state["consecutive_invalid"] += 1
            state["transcript"].append({"role": "user", "text": json.dumps({"evaluation_error": str(exc)[:300]})})
            state["limitation"] = "invalid_decisions" if state["consecutive_invalid"] >= 3 else None
            state["graph_next"] = "report_limitation" if state["limitation"] else "evaluate_evidence"
            runtime.checkpoint("evaluate_evidence", "rejected")
            return state
        state["consecutive_invalid"] = 0
        state["evaluation"] = decision
        state["graph_next"] = {"YES": "root_cause_report", "NO": "investigate", "BLOCKED": "report_limitation"}[decision["decision"]]
        if decision["decision"] == "BLOCKED":
            state["limitation"] = decision["reason"]
        runtime.checkpoint("evaluate_evidence", decision["decision"])
        return state

    def recovery(state: InvestigationState):
        runtime.state = state
        latest = state["provider_failures"][-1]
        if latest["retryable"] and state["provider_retry_count"] < runtime.provider.config.max_transient_retries:
            delay = 0.5 * (2 ** state["provider_retry_count"])
            state["provider_retry_count"] += 1
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
            runtime.checkpoint("provider_recovery", "TOOL_FAILURE")
        return state

    def report_limitation(state: InvestigationState):
        runtime.state = state
        reason = state.get("limitation") or "insufficient_evidence"
        if reason in {"reproduction_unavailable"} or reproduction_status(state["steps"]) in {"UNAVAILABLE", "NOT_REPRODUCED"}:
            status = "REPRODUCTION_FAILED"
        elif reason in {"time_budget", "tool_call_budget", "model_call_budget"}:
            status = "MAX_STEPS_REACHED"
        elif reason in {"tool_failure", "invalid_decisions", "provider_error", "model_timeout", "missing_tool_action", "duplicate_reproduction"}:
            status = "TOOL_FAILURE"
        else:
            status = "INSUFFICIENT_EVIDENCE"
        state["final"] = fallback(state["initial"]["task"], state["steps"], status, reason)
        state["graph_next"] = "finalize"
        runtime.checkpoint("report_limitation", status)
        return state

    def root_cause_report(state: InvestigationState):
        runtime.state = state
        state["final"] = state["evaluation"]["final_report"]
        state["graph_next"] = "finalize"
        runtime.checkpoint("root_cause_report", "ROOT_CAUSE_IDENTIFIED")
        return state

    def finalize(state: InvestigationState):
        runtime.state = state
        validate(state["final"], FINAL_SCHEMA)
        validate_final(state["final"], state["steps"])
        state["phase"] = "paused" if state["final"]["status"] == "TOOL_FAILURE" and state.get("limitation") in {"provider_error", "model_timeout"} else "finished"
        state["stopping_reason"] = state.get("limitation") or "graph_finished"
        state["graph_next"] = "finalize"
        runtime.checkpoint("finalize", state["final"]["status"])
        return state

    graph.add_node("check_budget", check_budget)
    graph.add_node("reproduce", reproduce)
    graph.add_node("collect_runtime_evidence", collect_runtime_evidence)
    graph.add_node("investigate", investigate)
    graph.add_node("execute_tool", execute_tool)
    graph.add_node("evaluate_evidence", evaluate_evidence)
    graph.add_node("recovery", recovery)
    graph.add_node("report_limitation", report_limitation)
    graph.add_node("root_cause_report", root_cause_report)
    graph.add_node("finalize", finalize)
    routes = {name: name for name in ["reproduce", "collect_runtime_evidence", "investigate", "execute_tool",
        "evaluate_evidence", "recovery", "report_limitation", "root_cause_report", "finalize"]}
    graph.add_conditional_edges(START, lambda state: state.get("graph_next") or "reproduce", routes)
    for name in ["check_budget", "reproduce", "collect_runtime_evidence", "investigate", "execute_tool", "evaluate_evidence", "recovery", "report_limitation", "root_cause_report"]:
        graph.add_edge(name, "check_budget") if name != "check_budget" else None
    graph.add_conditional_edges("check_budget", lambda state: state.get("graph_next") or "report_limitation", routes)
    graph.add_edge("finalize", END)
    return graph.compile()


def _initial_state(context, task, provider, budget):
    validate_task(task, context)
    fingerprint = hashlib.sha256(json.dumps({"prompt": SYSTEM_PROMPT, "catalog": CATALOG,
        "investigate": INVESTIGATION_DECISION_SCHEMA, "evaluate": EVALUATION_SCHEMA}, sort_keys=True).encode()).hexdigest()
    return {"version": 2, "run_id": uuid4().hex, "session_id": context.config["id"],
        "initial": {"task": task, "model": asdict(provider.config), "budget": asdict(budget),
                    "prompt_contract_sha256": fingerprint, "snapshot_id": context.repository.snapshot_id},
        "phase": "running", "graph_next": "reproduce", "steps": [], "hypotheses": [], "reviewed_step": 0,
        "pending_action": None, "pending_model": False, "transcript": [], "events": [], "provider_failures": [], "tool_failures": [],
        "turns": 0, "decisions": 0, "invalid": 0, "consecutive_invalid": 0, "resume_count": 0,
        "elapsed_seconds": 0.0, "usage": {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0},
        "final": None, "stopping_reason": None, "updated_at": utc_now(), "provider_retry_count": 0, "evaluation": None,
        "incident": {}, "reproduction": None, "observations": [], "evidence": [], "tool_history": [], "provider_errors": [],
        "current_subsystem": None, "status": "RUNNING", "step_count": 0, "model_calls": 0,
        "planned_action": None, "recovery_target": None, "limitation": None}


def investigate_graph(context, task, provider, budget=Budget(), progress=None, *, resume_run_id=None):
    """Run or resume the Day 5 LangGraph state machine using one existing checkpoint."""
    with session_lock(context):
        if resume_run_id:
            state = load_state(context, resume_run_id)
            initial = state["initial"]
            if task is not None and task != initial["task"]:
                raise ValueError("Resume cannot change the original task.")
            task = initial["task"]
            budget = Budget(**initial["budget"])
            if state["phase"] == "finished":
                return _result(context, provider, budget, state, run_directory(context, state["run_id"]))
            state["resume_count"] += 1
            state["phase"] = "running"
            previous_provider_failure = bool(state.get("provider_failures"))
            if state.get("final", {}).get("status") == "TOOL_FAILURE" and (state.get("limitation") in {"provider_error", "model_timeout"} or previous_provider_failure):
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
        graph.invoke(state, {"recursion_limit": 200})
        return _result(context, provider, budget, runtime.state, directory)


def _result(context, provider, budget, state, directory):
    sync_investigation_view(state)
    final = state["final"] or fallback(state["initial"]["task"], state["steps"], "TOOL_FAILURE", "graph_incomplete")
    summary = {"run_id": state["run_id"], "model": provider.config.model_name, "orchestrator": "langgraph",
        "status": final["status"], "stopping_reason": state.get("stopping_reason"), "tool_calls": len(state["steps"]),
        "model_calls": state["model_calls"], "tools_used": [step["tool"] for step in state["steps"]],
        "incorrect_calls": sum(step["result"]["status"] != "ok" for step in state["steps"]), "invalid_decisions": state["invalid"],
        "duration_ms": round(state["elapsed_seconds"] * 1000, 2), "usage": state["usage"], "budget": asdict(budget),
        "snapshot_id": context.repository.snapshot_id, "artifacts": str(directory), "phase": state["phase"],
        "resumable": state["phase"] == "paused", "resume_count": state["resume_count"],
        "provider_failures": len(state["provider_failures"]), "tool_failures": len(state["tool_failures"]),
        "hypotheses": state["hypotheses"], "graph_next": state["graph_next"]}
    atomic_json(directory / "final.json", final)
    atomic_json(directory / "summary.json", summary)
    return {"final": final, "summary": summary}




"""Proposal-only remediation boundary; it has no tools and cannot modify targets."""
from __future__ import annotations
import json
from .schemas import FINAL_SCHEMA, REMEDIATION_PLAN_SCHEMA, validate

PLANNER_PROMPT = """You are the Remediation Planner. You receive one evidence-supported root-cause report. Propose minimal source/configuration changes and validation steps. You have no tools, cannot inspect files, cannot apply changes, and cannot execute tests. Do not invent evidence. Set requires_human_approval=true. Use REQUIRES_HUMAN_REVIEW for medium/high risk or any operational/database change."""

def planner_request(report: dict) -> list[dict[str, str]]:
    validate(report, FINAL_SCHEMA)
    if report["status"] != "ROOT_CAUSE_SUPPORTED":
        raise ValueError("Remediation planning requires ROOT_CAUSE_SUPPORTED.")
    return [{"role": "user", "text": json.dumps({"supported_root_cause": report, "instruction": "Produce a proposal only; no patch or execution."})}]

def plan_remediation(provider, report: dict, timeout: int = 60) -> dict:
    reply = provider.generate(PLANNER_PROMPT, planner_request(report), REMEDIATION_PLAN_SCHEMA, timeout)
    plan = reply.decision
    validate(plan, REMEDIATION_PLAN_SCHEMA)
    if not plan["requires_human_approval"]:
        raise ValueError("Every remediation proposal requires human approval.")
    return {"plan": plan, "usage": reply.usage}

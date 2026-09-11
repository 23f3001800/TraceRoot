"""Provider-neutral JSON contracts. No benchmark-specific tool hints."""
from copy import deepcopy
from jsonschema import Draft202012Validator

def obj(properties, required=None, extra=False):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required, "additionalProperties": extra}

def string(limit=400):
    return {"type": "string", "maxLength": limit}

def integer(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}

def array(items, limit=20):
    return {"type": "array", "items": items, "maxItems": limit}

def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}

REPOSITORY = string(500)
TIMEOUT = integer(1, 120)
SCALAR = {"type": ["string", "integer", "number", "boolean", "null"]}
TOOL_INPUTS = {
    "run_reproduction": obj({
        "repository_path": REPOSITORY,
        "reproduction_command": nullable(array(string(300), 12)), "timeout": TIMEOUT,
    }, ["repository_path"]),
    "read_logs": obj({
        "source": {"type": "string", "enum": ["application"]},
        "start_time": nullable(string(80)), "end_time": nullable(string(80)),
        "request_id": nullable(string(128)), "run_id": nullable(string(128)), "limit": integer(1, 100),
    }, []),
    "search_code": obj({
        "repository": REPOSITORY, "query": string(200), "path_scope": string(300),
        "result_limit": integer(1, 100),
    }, ["repository", "query"]),
    "read_file": obj({
        "repository": REPOSITORY, "file_path": string(300),
        "start_line": integer(1, 1000000), "end_line": integer(1, 1000199),
    }, ["repository", "file_path"]),
    "inspect_database": obj({
        "operation": {"type": "string", "enum": ["list_tables", "describe_table", "list_constraints", "sample_rows"]},
        "table": nullable(string(63)), "columns": nullable(array(string(63), 30)),
        "filters": nullable({"type": "object", "additionalProperties": SCALAR, "maxProperties": 10}),
        "limit": integer(1, 100),
    }, ["operation"]),
    "run_tests": obj({
        "repository": REPOSITORY, "test_selector": nullable(string(300)),
        "timeout": TIMEOUT, "marker": nullable(string(100)),
    }, ["repository"]),
}
DESCRIPTIONS = {
    "run_reproduction": "Establish a failure using an approved command or uniquely marked public test. Unavailable reproduction is explicit.",
    "read_logs": "Retrieve bounded application logs when runtime evidence may explain an observed failure. Filter using returned request and run IDs.",
    "search_code": "Locate implementation related to an observed symptom, symbol, endpoint, or exception. Queries are literal, not semantic.",
    "read_file": "Inspect selected lines of a public file discovered during investigation. Source is read-only; protected paths are rejected.",
    "inspect_database": "Check actual public PostgreSQL tables, columns, constraints, or bounded rows. Only fixed read-only operations are permitted.",
    "run_tests": "Run a discovered test, file, or marker-filtered suite to confirm or reject hypotheses and measure failure scope.",
}
EXECUTION = obj({
    "command": array(string(500), 40), "exit_code": nullable({"type": "integer"}),
    "stdout": string(65536), "stderr": string(65536), "duration_ms": {"type": "number"},
    "passed": nullable({"type": "integer"}), "failed": nullable({"type": "integer"}),
    "skipped": nullable({"type": "integer"}), "errors": nullable({"type": "integer"}),
    "collected": nullable({"type": "integer"}), "failing_tests": array(string(500), 1000),
    "http_observations": array(obj({"expected": integer(100, 599), "observed": integer(100, 599), "source": string()}), 1000),
    "outcome": string(), "stdout_truncated": {"type": "boolean"}, "stderr_truncated": {"type": "boolean"},
}, extra=True)
DATA_SCHEMAS = {
    "run_tests": EXECUTION,
    "run_reproduction": {**deepcopy(EXECUTION), "properties": {
        **deepcopy(EXECUTION["properties"]), "selection_reason": string(),
        "reproduced": {"type": ["boolean", "null"]}, "expected": nullable(integer(100, 599)),
        "observed": nullable(integer(100, 599)),
    }},
    "read_logs": obj({"source": string(), "collected_at": string(),
        "entries": array({"type": "object"}, 100), "truncated": {"type": "boolean"},
        "missing_fields": array({"type": "object"}, 100), "collector_errors": array({"type": "object"}, 100)}),
    "search_code": obj({"query": string(200), "matches": array(obj({
        "file": string(500), "line": {"type": "integer"}, "text": string(1000),
        "context": array(obj({"line": {"type": "integer"}, "text": string(1000)}), 3),
        "text_truncated": {"type": "boolean"},
    }), 100), "returned_matches": {"type": "integer"}, "truncated": {"type": "boolean"}}),
    "read_file": obj({"file": string(500), "lines": array(obj({"line": {"type": "integer"}, "text": string(131072)}), 200),
        "total_lines": {"type": "integer"}, "sha256": string(64), "truncated": {"type": "boolean"},
        "next_line": nullable({"type": "integer"})}),
    "inspect_database": obj({"database": string(), "schema": string(), "role": string(),
        "transaction_read_only": {"type": "boolean"}, "operation": string(),
        "rows": array({"type": "object"}, 100), "truncated": {"type": "boolean"}}),
}

def output_schema(name):
    return obj({
        "status": {"type": "string", "enum": ["ok", "rejected", "unavailable", "timeout", "error"]},
        "data": nullable(DATA_SCHEMAS[name]),
        "error": nullable(obj({"code": string(), "message": string(1000)})),
        "metadata": {"type": "object"},
    })

CATALOG = [{"name": name, "description": DESCRIPTIONS[name],
            "input_schema": schema, "output_schema": output_schema(name)} for name, schema in TOOL_INPUTS.items()]

STATUSES = ["ROOT_CAUSE_IDENTIFIED", "INSUFFICIENT_EVIDENCE", "REPRODUCTION_FAILED", "TOOL_FAILURE", "MAX_STEPS_REACHED"]
EVIDENCE = obj({
    "step": integer(1, 15), "pointer": string(300), "quote": {"type": "string", "minLength": 1, "maxLength": 800},
    "supports": string(400),
})
FINAL_SCHEMA = obj({
    "status": {"type": "string", "enum": STATUSES}, "symptom": string(1000),
    "reproduction_status": {"type": "string", "enum": ["CONFIRMED", "NOT_REPRODUCED", "UNAVAILABLE", "NOT_ATTEMPTED"]},
    "root_cause": nullable(string(1600)), "root_cause_category": nullable(string(200)),
    "affected_subsystem": nullable(string(200)), "evidence": array(EVIDENCE, 15),
    "rejected_hypotheses": array(obj({
        "hypothesis": string(300), "reason": string(400), "evidence_steps": array(integer(1, 15), 15),
    }), 10),
    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    "recommended_next_action": string(800), "limitations": array(string(400), 12),
})
ACTION_SCHEMA = {"anyOf": [
    obj({"name": {"type": "string", "enum": [name]}, "arguments": schema})
    for name, schema in TOOL_INPUTS.items()
]}
HYPOTHESIS = obj({
    "id": {"type": "string", "pattern": "^H[1-9][0-9]?$"},
    "claim": {"type": "string", "minLength": 1, "maxLength": 1600},
    "status": {"type": "string", "enum": ["proposed", "supported", "rejected"]},
    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    "evidence": array(EVIDENCE, 15),
    "missing_evidence": array(string(300), 5),
})
DECISION_SCHEMA = obj({
    "reviewed_step": integer(0, 15), "hypotheses": array(HYPOTHESIS, 8),
    "hypothesis_summary": string(300), "evidence_summary": string(300),
    "action": nullable(ACTION_SCHEMA), "final_report": nullable(FINAL_SCHEMA),
})
INVESTIGATION_DECISION_SCHEMA = obj({
    "reviewed_step": integer(0, 15), "hypotheses": array(HYPOTHESIS, 8),
    "hypothesis_summary": string(300), "evidence_summary": string(300),
    "action": nullable(ACTION_SCHEMA), "ready_for_evaluation": {"type": "boolean"},
})
EVALUATION_SCHEMA = obj({
    "decision": {"type": "string", "enum": ["YES", "NO", "BLOCKED"]},
    "reason": string(500), "final_report": nullable(FINAL_SCHEMA),
})
TASK_SCHEMA = obj({
    "repository": {"type": "string", "minLength": 1, "maxLength": 500},
    "bug_report": {"type": "string", "minLength": 1, "maxLength": 1000},
    "reproduction_command": nullable(array(string(300), 12)),
    "constraints": array({"type": "string", "minLength": 1, "maxLength": 200}, 10),
}, ["repository", "bug_report", "constraints"])

def validate(value, schema):
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda error: str(list(error.path)))
    if errors:
        # Never return invalid model text or private reasoning in validation errors.
        path = "/".join(str(p) for p in errors[0].path)
        raise ValueError(f"Invalid structured value at /{path}: {errors[0].validator}")

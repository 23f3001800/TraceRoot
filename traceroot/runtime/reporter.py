"""Trusted pytest reporting plugin, installed outside the repository."""
import json
from pathlib import Path
import re

records = []
logs = []
seen_logs = set()

def pytest_runtest_logreport(report):
    record = {"node_id": report.nodeid, "phase": report.when, "outcome": report.outcome,
              "duration_ms": round(report.duration * 1000, 2)}
    if report.failed:
        failure = report.longreprtext[:16000]
        record["failure"] = failure
        # Only report HTTP observations when a status_code assertion supplies both values.
        if "status_code" in failure:
            match = re.search(r"assert ([1-5][0-9]{2}) == ([1-5][0-9]{2})", failure)
            if match:
                record["http_observation"] = {"observed": int(match[1]), "expected": int(match[2]),
                                              "source": "pytest status_code assertion"}
    records.append(record)
    for line in report.capstderr.splitlines():
        try:
            entry = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(entry, dict) and "timestamp" in entry and "message" in entry:
            canonical = json.dumps(entry, sort_keys=True)
            if canonical not in seen_logs and len(logs) < 200:
                seen_logs.add(canonical)
                logs.append(entry)

def pytest_sessionfinish(session, exitstatus):
    result = {
        "exit_code": int(exitstatus),
        "collected": session.testscollected,
        "passed": sum(r["phase"] == "call" and r["outcome"] == "passed" for r in records),
        "failed": sum(r["phase"] == "call" and r["outcome"] == "failed" for r in records),
        "skipped": sum(r["outcome"] == "skipped" for r in records),
        "errors": sum(r["phase"] != "call" and r["outcome"] == "failed" for r in records),
        "records": records, "logs": logs,
    }
    print("\nTRACEROOT_REPORT_V1=" + json.dumps(result), flush=True)

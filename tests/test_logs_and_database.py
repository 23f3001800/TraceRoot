import json
import pytest
from traceroot.tools import read_logs, inspect_database

def write_logs(context, records):
    (context.session_dir / "application.jsonl").write_text("\n".join(json.dumps(r) for r in records))

def test_logs_order_filter_and_application_errors(context):
    write_logs(context, [
        {"timestamp": "2026-09-06T10:00:02Z", "request_id": "b", "message": "later"},
        {"timestamp": "2026-09-06T10:00:01Z", "request_id": "a", "status": 500,
         "exception_type": "IntegrityError", "message": "application failed"},
    ])
    result = read_logs(context)
    assert result.status == "ok"
    assert result.data["entries"][0]["status"] == 500
    assert result.data["collector_errors"] == []
    assert read_logs(context, request_id="b").data["entries"][0]["message"] == "later"
    assert read_logs(context, limit=1).data["truncated"]
    assert read_logs(context, start_time="2026-09-06T10:00:02Z").data["entries"][0]["request_id"] == "b"

def test_collector_failure_is_separate(context):
    (context.session_dir / "application.jsonl").write_text('not json\n')
    result = read_logs(context)
    assert result.status == "error" and result.error.code == "collector_error"
    assert result.data["entries"] == []

def test_log_missing_and_redaction(context):
    write_logs(context, [{"message": "password=abc a-secret postgresql://u:p@db/x", "token": "top-secret"}])
    result = read_logs(context)
    assert result.status == "ok"
    assert result.data["missing_fields"]
    assert "top-secret" not in str(result.to_dict())
    assert "a-secret" not in str(result.to_dict())
    assert "u:p@" not in str(result.to_dict())

def test_logs_denied_source_and_timezone(context):
    assert read_logs(context, source="/etc/passwd").status == "rejected"
    assert read_logs(context, start_time="2026-09-06").status == "rejected"
    assert read_logs(context, request_id=123).status == "rejected"

@pytest.mark.parametrize("operation", ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "SELECT * FROM orders"])
def test_database_arbitrary_sql_denied(context, operation):
    assert inspect_database(context, operation).error.code == "operation_denied"

def test_database_identifier_injection_denied(context):
    assert inspect_database(context, "sample_rows", table="orders; DROP TABLE users").status == "rejected"
    assert inspect_database(context, "sample_rows", table="orders", columns=["id;DELETE"]).status == "rejected"
    assert inspect_database(context, "sample_rows", table="orders", filters={"id": {"$sql": "DELETE"}}).status == "rejected"

def test_all_tools_reject_unknown_keyword_structurally(context):
    result = inspect_database(context, sql="DELETE FROM orders")
    assert result.status == "rejected" and result.error.code == "invalid_input"

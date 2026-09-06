"""Opt-in tests against the operator-provisioned, disposable Docker environment."""
import json
import os
from pathlib import Path
from uuid import uuid4
import pytest
from traceroot.context import Context
from traceroot.docker_runtime import checked, container_options, docker, inspector_url
from traceroot.tools import inspect_database, run_tests

@pytest.fixture
def live():
    path = os.environ.get("TRACEROOT_TEST_SESSION")
    if not path:
        pytest.skip("Set TRACEROOT_TEST_SESSION to a prepared disposable session.")
    context = Context.load(Path(path))
    assert context.config["active"]
    return context

def probe(live, script):
    name = "traceroot-security-" + uuid4().hex[:10]
    try:
        checked(live, ["create", *container_options(live, name),
                      "--env", f"INSPECTION_DATABASE_URL={inspector_url(live)}",
                      live.config["image"], "python", "-c", script])
        result = docker(live, ["start", "-a", name], 20)
        assert result.exit_code == 0, result.stderr.decode()
        return json.loads(result.stdout)
    finally:
        checked(live, ["rm", "-f", name])

def test_live_database_operations(live):
    tables = inspect_database(live, "list_tables")
    assert tables.status == "ok", tables.to_dict()
    assert {r["table_name"] for r in tables.data["rows"]} == {"users", "orders", "payments"}
    schema = inspect_database(live, "describe_table", table="orders")
    assert schema.status == "ok"
    assert any(r["column_name"] == "total_amount" for r in schema.data["rows"])
    constraints = inspect_database(live, "list_constraints", table="orders")
    assert constraints.status == "ok"
    rows = inspect_database(live, "sample_rows", table="orders", columns=["id", "product_name"],
                            filters={"product_name": "' OR 1=1; DELETE FROM orders; --"}, limit=1)
    assert rows.status == "ok" and rows.data["rows"] == []
    assert constraints.data["role"] == "inspection" and constraints.data["transaction_read_only"]

def test_database_role_denies_writes_without_transaction_safety(live):
    # Trusted negative test: bypass the tool's read-only transaction to verify role permissions independently.
    result = probe(live, """
import json, os, psycopg
statements = [
    "INSERT INTO public.users (name,email) VALUES ('x','x@example.com')",
    "UPDATE public.orders SET quantity=1",
    "DELETE FROM public.orders",
    "DROP TABLE public.orders",
    "ALTER TABLE public.orders ADD COLUMN bad int",
    "TRUNCATE public.orders",
    "CREATE TABLE public.bad (id int)",
    "CREATE TEMP TABLE bad (id int)",
]
codes = []
for statement in statements:
    with psycopg.connect(os.environ["INSPECTION_DATABASE_URL"],
                        options="-c default_transaction_read_only=off") as connection:
        try:
            connection.execute(statement)
        except psycopg.Error as exc:
            codes.append(exc.sqlstate)
        else:
            connection.rollback()
            raise AssertionError("Write was permitted")
assert codes == ["42501"] * len(statements), codes
print(json.dumps({"blocked_statements": len(codes), "sqlstate": "42501"}))
""")
    assert result["blocked_statements"] == 8

def test_container_blocks_source_writes_and_external_network(live):
    result = probe(live, """
import errno, json, os, socket
from pathlib import Path
blocked = False
try:
    Path("/repo/app/main.py").write_text("changed")
except OSError as exc:
    assert exc.errno in (errno.EROFS, errno.EACCES)
    blocked = True
assert blocked
assert os.getuid() == 10001
assert not Path("/repo/benchmarks").exists()
assert not Path("/repo/.git").exists()
assert not Path("/var/run/docker.sock").exists()
Path("/tmp/allowed-scratch").write_text("temporary")
network_blocked = False
try:
    socket.create_connection(("1.1.1.1", 443), timeout=1).close()
except OSError:
    network_blocked = True
assert network_blocked
print(json.dumps({"source_write_blocked": blocked, "external_network_blocked": network_blocked}))
""")
    assert result["source_write_blocked"] and result["external_network_blocked"]

def test_real_timeout_removes_execution_container(live, monkeypatch):
    import traceroot.execution as execution
    real_checked = execution.checked
    created = []
    def slow_create(context, args, *rest, **kwargs):
        if args[0] == "create":
            created.append(args[args.index("--name") + 1])
            image_index = args.index(context.config["image"])
            args = args[:image_index + 1] + ["python", "-c", "import time; time.sleep(30)"]
        return real_checked(context, args, *rest, **kwargs)
    monkeypatch.setattr(execution, "checked", slow_create)
    # This injection is test harness code, not a command accepted by any agent tool.
    result = run_tests(live, live.repository.source, timeout=1)
    assert result.status == "timeout", result.to_dict()
    assert created and docker(live, ["inspect", created[0]]).exit_code != 0

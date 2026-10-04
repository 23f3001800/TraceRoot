import pytest
from traceroot.durable_state import PostgresStateStore, SCHEMA, configured_store
from traceroot.workspace_events import IncidentStore

def test_postgres_schema_covers_durable_state_domains():
    assert "traceroot_incidents" in SCHEMA
    assert "traceroot_events" in SCHEMA
    assert "traceroot_records" in SCHEMA
    assert "UNIQUE (investigation_id, sequence)" in SCHEMA
    assert hasattr(PostgresStateStore, "save_evaluation")

def test_postgres_store_requires_postgres_dsn():
    with pytest.raises(ValueError, match="PostgreSQL"):
        PostgresStateStore("sqlite:///tmp/test.db", connect=lambda _: None)

def test_configured_store_preserves_file_default(tmp_path, monkeypatch):
    monkeypatch.delenv("TRACEROOT_DATABASE_URL", raising=False)
    assert isinstance(configured_store(tmp_path), IncidentStore)

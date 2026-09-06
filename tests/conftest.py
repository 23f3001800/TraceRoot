from pathlib import Path
import pytest
from traceroot.context import Context
from traceroot.repository import make_snapshot

@pytest.fixture
def context(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app").mkdir()
    (source / "tests").mkdir()
    (source / "benchmarks/bug-001").mkdir(parents=True)
    (source / "benchmarks/bug-001/README.md").write_text("EVALUATOR_SENTINEL")
    (source / ".git").mkdir()
    (source / ".git/config").write_text("EVALUATOR_SENTINEL")
    (source / "readme.md").write_text("Evaluator explanation EVALUATOR_SENTINEL")
    (source / "app/main.py").write_text('def create_order():\n    return "hello"\n')
    (source / "pytest.ini").write_text("[pytest]\ntestpaths = tests\nmarkers =\n    regression: public regression\n")
    (source / "requirements.txt").write_text("pytest==8.3.5\n")
    (source / "tests/test_api.py").write_text(
        "import pytest\n@pytest.mark.regression\ndef test_public_case():\n    assert 1 == 2\n"
        "\ndef test_normal():\n    assert True\n")
    session = tmp_path / "session"
    session.mkdir()
    manifest = make_snapshot(source, session / "snapshot")
    config = {"id": "unit", "repository": str(source), "snapshot": str(session / "snapshot"),
              "manifest": manifest, "active": False, "app_password": "a-secret", "inspector_password": "i-secret",
              "admin_password": "admin-secret"}
    return Context(config, session)

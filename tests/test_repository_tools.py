import os
import pytest
from traceroot.repository import safe_bytes, make_snapshot
from traceroot.contracts import ToolFailure
from traceroot.tools import read_file, search_code

def test_search_and_read_contract(context):
    result = search_code(context, context.repository.source, "create_order")
    assert result.status == "ok"
    assert result.data["matches"][0]["file"] == "app/main.py"
    assert result.data["matches"][0]["line"] == 1
    assert result.metadata["snapshot_id"]
    read = read_file(context, context.repository.source, "app/main.py", 1, 1)
    assert read.data["lines"] == [{"line": 1, "text": "def create_order():"}]
    assert read.data["next_line"] == 2
    assert set(read.to_dict()) == {"status", "data", "error", "metadata"}

@pytest.mark.parametrize("path", [
    "../app/main.py", "../../etc/passwd", "/etc/passwd", "app/../../etc/passwd",
    "benchmarks/bug-001/README.md", ".git/config", "venv/x.py", ".venv/x.py",
    "app/../benchmarks/bug-001/README.md", "C:/Windows/system.ini",
    "app\\main.py", "readme.md", ".env", "app/__pycache__/x.py",
])
def test_blocked_paths(context, path):
    result = read_file(context, context.repository.source, path)
    assert result.status == "rejected"
    assert "EVALUATOR_SENTINEL" not in str(result.to_dict())

def test_search_never_reads_evaluator(context):
    result = search_code(context, context.repository.source, "EVALUATOR_SENTINEL")
    assert result.status == "ok" and result.data["matches"] == []
    assert not (context.repository.root / "benchmarks").exists()
    assert not (context.repository.root / ".git").exists()

def test_symlink_escape_rejected(context, tmp_path):
    target = tmp_path / "outside.py"
    target.write_text("PRIVATE")
    link = context.repository.root / "app/main.py"
    link.unlink()
    link.symlink_to(target)
    assert read_file(context, context.repository.source, "app/main.py").status == "rejected"

def test_directory_symlink_rejected(context, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "entry.py").write_text("PRIVATE")
    (context.repository.root / "app/alias").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ToolFailure):
        safe_bytes(context.repository.root, "app/alias/entry.py")

def test_snapshot_integrity(context):
    (context.repository.root / "app/main.py").write_text("modified")
    result = read_file(context, context.repository.source, "app/main.py")
    assert result.error.code == "snapshot_changed"

def test_unknown_repository(context):
    result = search_code(context, "/tmp/unapproved", "x")
    assert result.error.code == "repository_denied"

def test_bounds_and_no_matches(context):
    assert read_file(context, context.repository.source, "app/main.py", 1, 201).status == "rejected"
    assert search_code(context, context.repository.source, "absent").data["matches"] == []
    assert search_code(context, context.repository.source, "x", result_limit=0).status == "rejected"

def test_hardlink_and_size_denied(tmp_path):
    (tmp_path / "app").mkdir()
    source = tmp_path / "app/one.py"
    source.write_text("x")
    os.link(source, tmp_path / "app/two.py")
    with pytest.raises(ToolFailure):
        safe_bytes(tmp_path, "app/one.py")
    large = tmp_path / "app/large.py"
    large.write_bytes(b"x" * 131073)
    with pytest.raises(ToolFailure):
        safe_bytes(tmp_path, "app/large.py")

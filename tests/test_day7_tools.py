from traceroot.tools import inspect_configuration, inspect_git

def test_configuration_is_bounded_and_redacts_secrets(context):
    (context.repository.root / "app" / "config.py").write_text("PAYMENTS_REGION = 'us-east-1'\nAPI_KEY = 'secret'\n")
    context.repository.manifest["app/config.py"] = __import__("hashlib").sha256((context.repository.root / "app" / "config.py").read_bytes()).hexdigest()
    result = inspect_configuration(context, context.repository.source, "app/config.py")
    assert result.status == "ok"
    assert result.data["entries"][0]["key"] == "PAYMENTS_REGION"
    assert any(item["redacted"] and item["value"] == "[redacted]" for item in result.data["entries"])

def test_git_does_not_expose_protected_paths(context, monkeypatch):
    import traceroot.tools.git_evidence as module
    monkeypatch.setattr(module, "_git", lambda *args: "M\tbenchmarks/bug-001/truth.md\nM\tapp/main.py\n")
    result = inspect_git(context, context.repository.source, "changed_files")
    assert result.status == "ok" and result.data["entries"] == [{"status": "M", "file": "app/main.py"}]

from pathlib import Path


def test_workspace_submit_handlers_capture_form_before_await():
    source = Path("ui/workspace/src/main.js").read_text(encoding="utf-8")

    assert "const form = event.currentTarget;" in source
    assert "new FormData(form)" in source
    assert "form.reset();" in source
    assert "event.currentTarget.reset()" not in source

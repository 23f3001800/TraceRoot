from pathlib import Path
from traceroot.approval_ui import serve_approval
def test_ui_is_loopback_only():
 import inspect
 assert '("127.0.0.1",port)' in inspect.getsource(serve_approval)

def test_ui_module_defines_asset_root():
    from pathlib import Path
    import traceroot.approval_ui as module
    assert (Path(module.__file__).parent.parent / "ui").is_dir()

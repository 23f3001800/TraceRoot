from pathlib import Path
from traceroot.approval_ui import serve_approval
def test_ui_is_loopback_only():
 import inspect
 assert '("127.0.0.1",port)' in inspect.getsource(serve_approval)

def test_ui_module_defines_asset_root():
    from pathlib import Path
    import traceroot.approval_ui as module
    assert (Path(module.__file__).parent.parent / "ui").is_dir()

def test_ui_hash_preserves_patch_bytes(tmp_path, context):
    from traceroot.api.approval import ApprovalAPI
    patch=tmp_path/"patch"; patch.write_bytes(("diff --git a/a b/a"+chr(13)+chr(10)).encode())
    api=ApprovalAPI(context,patch,"run")
    from traceroot.agents.approval import patch_hash
    assert api.digest == patch_hash(patch.read_bytes().decode("utf-8"))

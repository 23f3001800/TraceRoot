from pathlib import Path
from traceroot.approval_ui import serve_approval
def test_ui_is_loopback_only():
 import inspect
 assert '("127.0.0.1",port)' in inspect.getsource(serve_approval)

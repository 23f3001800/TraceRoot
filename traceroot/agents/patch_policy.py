"""Deterministic unified-diff policy; never delegated to a model."""
from __future__ import annotations
import re
from ..contracts import ToolFailure
BLOCKED=(".git/", "benchmarks/", ".env", "venv/", "__pycache__/")
def validate_patch(patch: str) -> list[str]:
    if not isinstance(patch,str) or not patch.startswith("diff --git ") or len(patch.encode())>65536: raise ToolFailure("invalid_patch","Patch must be a bounded unified diff.")
    if "GIT binary patch" in patch or "new file mode 120000" in patch or "deleted file mode" in patch: raise ToolFailure("patch_policy_denied","Binary, symlink, and deletion patches are denied.")
    files=[]
    for line in patch.splitlines():
      if line.startswith("diff --git "):
       parts=line.split()
       if len(parts)!=4 or not parts[2].startswith("a/") or not parts[3].startswith("b/"): raise ToolFailure("invalid_patch","Malformed diff header.")
       path=parts[3][2:]
       if not path or ".." in path.split("/") or any(x in path or path.startswith(x) for x in BLOCKED): raise ToolFailure("patch_policy_denied","Patch changes a protected path.")
       files.append(path)
    if not files or len(set(files))>10 or sum(1 for x in patch.splitlines() if x.startswith(("+","-")) and not x.startswith(("+++","---")))>500: raise ToolFailure("patch_policy_denied","Patch exceeds file or line limits.")
    return files

"""Select the test-tooling derivative of the already patched sandbox image."""
from pathlib import Path

from traceroot.context import Context

root = Path(__file__).resolve().parents[3]
context = Context.load(root / ".traceroot-runs" / "eduforgeb57b")
expected = "traceroot-investigation:eduforgeb57b-patch-52e01708935b"
verifier = "traceroot-investigation:eduforgeb57b-verify-52e01708935b"
v2 = "traceroot-investigation:eduforgeb57b-verify-52e01708935b-patch-2378784d5a8c"
current = context.config.get("image")
if current not in {expected, verifier, v2}:
    raise RuntimeError("patched image does not match the consumed approval")
context.config["docker"] = "/mnt/c/Program Files/Docker/Docker/resources/bin/docker"
context.config["memory"] = "1g"
context.config["pytest_plugins"] = ["pytest_asyncio.plugin"]
context.config["execution_image"] = expected
context.config["image"] = v2 if current == v2 else verifier
context.config["verification_image"] = context.config["image"]
context.save()
print(context.config["image"])

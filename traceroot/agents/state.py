"""Durable operator-owned checkpoints; never exposed as an agent tool."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile

from .schemas import obj, array, string, integer, nullable, HYPOTHESIS, FINAL_SCHEMA, validate

STATE_SCHEMA = obj({
    "version": {"const": 1}, "run_id": string(32), "session_id": string(100),
    "initial": {"type": "object"},
    "phase": {"enum": ["running", "paused", "finished", "interrupted_tool"]},
    "steps": array({"type": "object"}, 15), "hypotheses": array(HYPOTHESIS, 8),
    "reviewed_step": integer(0, 15), "pending_model": {"type": "boolean"}, "pending_action": nullable({"type": "object"}),
    "transcript": array(obj({"role": {"enum": ["user", "model"]}, "text": string(250000)}), 100),
    "events": array({"type": "object"}, 300),
    "provider_failures": array({"type": "object"}, 60),
    "tool_failures": array({"type": "object"}, 15),
    "turns": integer(0, 60), "decisions": integer(0, 30), "invalid": integer(0, 30),
    "consecutive_invalid": integer(0, 3), "resume_count": integer(0, 60),
    "elapsed_seconds": {"type": "number", "minimum": 0},
    "usage": {"type": "object"}, "final": nullable(FINAL_SCHEMA),
    "stopping_reason": nullable(string(100)), "updated_at": string(100),
})

def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def run_directory(context, run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("Resume requires a run ID, not a path.")
    root = context.session_dir.resolve() / "agent-runs"
    directory = root / run_id
    if root.is_symlink() or directory.is_symlink() or directory.resolve().parent != root:
        raise ValueError("Run directory is outside this session.")
    return directory

def load_state(context, run_id):
    path = run_directory(context, run_id) / "state.json"
    if path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Invalid checkpoint file.")
    state = json.loads(path.read_text(encoding="utf-8"))
    validate(state, STATE_SCHEMA)
    if state["run_id"] != run_id or state["session_id"] != context.config["id"]:
        raise ValueError("Checkpoint belongs to another investigation or session.")
    return state

@contextmanager
def session_lock(context):
    with (context.session_dir / ".investigator.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("An investigator already owns this session.") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)

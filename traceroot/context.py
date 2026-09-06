import json
from pathlib import Path
from .repository import Repository

class Context:
    """Trusted session configuration. Not an agent-controlled tool argument."""
    def __init__(self, config: dict, session_dir: Path):
        self.config = config
        self.session_dir = session_dir
        self.repository = Repository(config["repository"], config["snapshot"], config["manifest"])

    @classmethod
    def load(cls, session_dir: Path):
        return cls(json.loads((session_dir / "session.json").read_text()), session_dir)

    def save(self):
        path = self.session_dir / "session.json"
        path.write_text(json.dumps(self.config, indent=2))
        path.chmod(0o600)

    def store_logs(self, entries: list[dict], run_id: str):
        with (self.session_dir / "application.jsonl").open("a") as stream:
            for entry in entries:
                stream.write(json.dumps({**entry, "run_id": run_id}) + "\n")

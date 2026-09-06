import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from .contracts import ToolFailure

MAX_FILE_BYTES = 128 * 1024
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
BLOCKED = {"benchmarks", ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
           ".agents", ".codex", "node_modules"}
CONFIGS = {"pytest.ini", "pyproject.toml", "setup.cfg", "requirements.txt"}

def relative_path(value: str, allow_dot: bool = False) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ToolFailure("path_denied", "Path is outside the public repository scope.")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or any(part in BLOCKED or part.startswith(".env") for part in path.parts):
        raise ToolFailure("path_denied", "Path is outside the public repository scope.")
    if str(path) == "." and not allow_dot:
        raise ToolFailure("path_denied", "A file path is required.")
    return str(path)

def public_file(relative: str) -> bool:
    path = PurePosixPath(relative)
    return relative in CONFIGS or (
        path.parts[0] in {"app", "tests"} and path.suffix == ".py"
        and not any(p in BLOCKED or p.startswith(".") for p in path.parts)
    )

def safe_bytes(root: Path, relative: str) -> bytes:
    """Open each component without following symlinks (Linux/WSL runtime)."""
    relative = relative_path(relative)
    if not public_file(relative):
        raise ToolFailure("path_denied", "File is not in the public source allowlist.")
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise ToolFailure("unsupported_host", "Repository tools require Linux or WSL.", "unavailable")
    descriptors = []
    try:
        parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(parent)
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            descriptors.append(parent)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        descriptors.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ToolFailure("path_denied", "Only regular, unlinked public files are supported.")
        if info.st_size > MAX_FILE_BYTES:
            raise ToolFailure("file_too_large", "File exceeds the 128 KiB limit.")
        chunks = bytearray()
        while chunk := os.read(fd, min(8192, MAX_FILE_BYTES + 1 - len(chunks))):
            chunks.extend(chunk)
            if len(chunks) > MAX_FILE_BYTES:
                raise ToolFailure("file_too_large", "File exceeds the 128 KiB limit.")
        if b"\x00" in chunks:
            raise ToolFailure("binary_file", "Binary files are not readable.")
        return bytes(chunks)
    except FileNotFoundError:
        raise ToolFailure("not_found", "Public file was not found.")
    except OSError:
        raise ToolFailure("path_denied", "File cannot be opened within the approved scope.")
    finally:
        for fd in reversed(descriptors):
            os.close(fd)

def public_files(root: Path) -> list[str]:
    paths = []
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in BLOCKED and not d.startswith(".")
                         and not (Path(base) / d).is_symlink())
        for name in sorted(files):
            p = Path(base) / name
            rel = p.relative_to(root).as_posix()
            if public_file(rel) and not p.is_symlink():
                paths.append(rel)
        if len(paths) > 1000:
            raise ToolFailure("repository_too_large", "Public repository exceeds 1000 files.")
    return sorted(paths)

def make_snapshot(source: Path, destination: Path) -> dict[str, str]:
    manifest = {}
    size = 0
    destination.mkdir(mode=0o700)
    for rel in public_files(source):
        content = safe_bytes(source, rel)
        size += len(content)
        if size > MAX_SNAPSHOT_BYTES:
            raise ToolFailure("repository_too_large", "Public snapshot exceeds 8 MiB.")
        content.decode("utf-8")
        path = destination / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        manifest[rel] = hashlib.sha256(content).hexdigest()
    return manifest

class Repository:
    def __init__(self, source: str, snapshot: str, manifest: dict[str, str]):
        self.source = str(Path(source).resolve())
        self.root = Path(snapshot)
        self.manifest = manifest
        digest = "\n".join(f"{p}:{h}" for p, h in sorted(manifest.items()))
        self.snapshot_id = hashlib.sha256(digest.encode()).hexdigest()

    def validate(self, repository: str):
        if not isinstance(repository, str) or str(Path(repository).resolve()) != self.source:
            raise ToolFailure("repository_denied", "Repository is not registered for this session.")

    def read(self, relative: str) -> str:
        relative = relative_path(relative)
        if relative not in self.manifest:
            raise ToolFailure("path_denied", "File is not in the approved snapshot.")
        content = safe_bytes(self.root, relative)
        if hashlib.sha256(content).hexdigest() != self.manifest[relative]:
            raise ToolFailure("snapshot_changed", "Snapshot changed; prepare a new environment.", "error")
        return content.decode("utf-8")

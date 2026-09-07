import io
import json
from pathlib import Path
import secrets
import tarfile
import time
from uuid import uuid4
from .context import Context
from .contracts import ToolFailure
from .process import run_process
from .repository import make_snapshot

def docker(context, args, timeout=30, input_bytes=None, limit=65536):
    investigation_deadline = getattr(context, "operation_deadline", None)
    if investigation_deadline is not None:
        if args[:2] == ["rm", "-f"]:
            timeout = min(timeout, 5)  # Bounded cleanup grace after cancellation.
        else:
            remaining = investigation_deadline - time.monotonic()
            if remaining <= 0:
                raise ToolFailure("investigation_timeout", "Investigation deadline reached.", "timeout")
            timeout = min(timeout, remaining)
    return run_process([context.config["docker"], *args], timeout, input_bytes, limit)

def checked(context, args, timeout=30, input_bytes=None):
    result = docker(context, args, timeout, input_bytes)
    if result.timed_out:
        raise ToolFailure("docker_timeout", "Docker operation timed out.", "timeout")
    if result.exit_code != 0:
        raise ToolFailure("docker_unavailable", "Docker operation failed; inspect the operator environment.", "unavailable")
    return result

def container_options(context, name: str) -> list[str]:
    return [
        "--name", name, "--label", f"traceroot.session={context.config['id']}",
        "--pull", "never", "--network", context.config["network"],
        "--read-only", "--user", "10001:10001", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true", "--memory", "256m",
        "--cpus", "1", "--pids-limit", "64",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--workdir", "/repo", "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--env", "PYTHONPATH=/repo:/opt/traceroot",
        "--env", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
    ]

def app_url(context):
    return f"postgresql+psycopg://application:{context.config['app_password']}@{context.config['db']}:5432/investigation"

def inspector_url(context):
    return f"postgresql://inspection:{context.config['inspector_password']}@{context.config['db']}:5432/investigation"

def image_context(context) -> bytes:
    requirements = context.repository.read("requirements.txt")
    import re
    lines = [line.strip() for line in requirements.splitlines() if line.strip() and not line.startswith("#")]
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9_.+-]+", line) for line in lines):
        raise ToolFailure("dependencies_denied", "Provisioning accepts pinned package requirements only.")
    files = {"repo/" + p: context.repository.read(p).encode() for p in context.repository.manifest}
    runtime = Path(__file__).parent / "runtime"
    for p in runtime.iterdir():
        if p.suffix in {".py", ".ini"}:
            files["runtime/" + p.name] = p.read_bytes()
    dockerfile = """FROM python:3.12-slim
WORKDIR /repo
COPY repo/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --only-binary=:all: -r /tmp/requirements.txt pytest==8.3.5 psycopg[binary]==3.2.6
COPY repo/ /repo/
COPY runtime/ /opt/traceroot/
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/repo:/opt/traceroot
USER 10001:10001
"""
    files["Dockerfile"] = dockerfile.encode()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data in sorted(files.items()):
            item = tarfile.TarInfo(name)
            item.size, item.mode, item.mtime = len(data), 0o444, 0
            archive.addfile(item, io.BytesIO(data))
    return stream.getvalue()

def cleanup(context):
    failures = []
    # Ownership labels prevent removing unrelated resources if configuration is stale.
    for name in (context.config["api"], context.config["db"]):
        found = docker(context, ["inspect", "--format", '{{index .Config.Labels "traceroot.session"}}', name])
        if found.exit_code == 0 and found.stdout.decode().strip() == context.config["id"]:
            removed = docker(context, ["rm", "-f", name])
            if removed.exit_code:
                failures.append(name)
    found = docker(context, ["network", "inspect", "--format", '{{index .Labels "traceroot.session"}}',
                             context.config["network"]])
    if found.exit_code == 0 and found.stdout.decode().strip() == context.config["id"]:
        if docker(context, ["network", "rm", context.config["network"]]).exit_code:
            failures.append("network")
    context.config["active"] = False
    context.save()
    if failures:
        raise ToolFailure("cleanup_failed", "Some session resources could not be removed.", "error")

def prepare(repository: Path, sessions: Path, docker_binary: str) -> Context:
    session_id = uuid4().hex[:12]
    session_dir = sessions / session_id
    session_dir.mkdir(parents=True, mode=0o700)
    manifest = make_snapshot(repository.resolve(), session_dir / "snapshot")
    context = Context({
        "id": session_id, "repository": str(repository.resolve()),
        "snapshot": str((session_dir / "snapshot").resolve()), "manifest": manifest,
        "docker": docker_binary, "image": f"traceroot-investigation:{session_id}",
        "network": f"traceroot-{session_id}", "db": f"traceroot-db-{session_id}",
        "api": f"traceroot-api-{session_id}", "active": False,
        "app_password": secrets.token_hex(16), "inspector_password": secrets.token_hex(16),
        "admin_password": secrets.token_hex(16),
    }, session_dir)
    context.save()
    try:
        checked(context, ["info", "--format", "{{.ServerVersion}}"], 20)
        checked(context, ["build", "--tag", context.config["image"], "-"], 300, image_context(context))
        checked(context, ["network", "create", "--internal", "--label",
                          f"traceroot.session={session_id}", context.config["network"]])
        # The database stores all state in container tmpfs, not host volumes.
        checked(context, [
            "run", "-d", "--name", context.config["db"], "--label", f"traceroot.session={session_id}",
            "--network", context.config["network"], "--read-only", "--user", "999:999",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--memory", "384m", "--cpus", "1", "--pids-limit", "100",
            "--tmpfs", "/var/lib/postgresql/data:rw,nosuid,size=256m,uid=999,gid=999",
            "--tmpfs", "/var/run/postgresql:rw,nosuid,size=4m,uid=999,gid=999",
            "--tmpfs", "/tmp:rw,nosuid,size=16m",
            "--env", "POSTGRES_DB=investigation",
            "--env", f"POSTGRES_PASSWORD={context.config['admin_password']}", "postgres:16",
        ], 120)
        for _ in range(40):
            ready = docker(context, ["exec", context.config["db"], "pg_isready", "-U", "postgres", "-d", "investigation"])
            if ready.exit_code == 0:
                break
            time.sleep(0.25)
        else:
            raise ToolFailure("database_unavailable", "Disposable PostgreSQL did not become ready.", "unavailable")
        sql = f"""
CREATE ROLE application LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD '{context.config["app_password"]}';
CREATE ROLE inspection LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD '{context.config["inspector_password"]}';
REVOKE ALL ON DATABASE investigation FROM PUBLIC;
GRANT CONNECT, CREATE ON DATABASE investigation TO application;
GRANT CONNECT ON DATABASE investigation TO inspection;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO application;
GRANT USAGE ON SCHEMA public TO inspection;
ALTER DEFAULT PRIVILEGES FOR ROLE application IN SCHEMA public GRANT SELECT ON TABLES TO inspection;
ALTER ROLE inspection SET default_transaction_read_only = on;
"""
        checked(context, ["exec", "-i", context.config["db"], "psql", "-U", "postgres",
                          "-d", "investigation", "-v", "ON_ERROR_STOP=1"], input_bytes=sql.encode())
        checked(context, ["run", "-d", *container_options(context, context.config["api"]),
                          "--env", f"DATABASE_URL={app_url(context)}", context.config["image"],
                          "python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"])
        for _ in range(30):
            result = docker(context, ["exec", context.config["api"], "python", "-c",
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"], 5)
            if result.exit_code == 0:
                break
            time.sleep(0.25)
        else:
            raise ToolFailure("application_unavailable", "Disposable application did not become ready.", "unavailable")
        context.config["active"] = True
        context.save()
        return context
    except Exception:
        cleanup(context)
        raise

def require_active(context):
    if not context.config.get("active"):
        raise ToolFailure("environment_unavailable", "Prepare a disposable environment before execution.", "unavailable")

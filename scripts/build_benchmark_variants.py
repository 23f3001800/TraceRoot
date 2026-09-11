#!/usr/bin/env python3
"""Build isolated TraceRoot benchmark patches from target-app's stable-v1 tag."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = ROOT / "benchmarks"
WORK = ROOT / ".day6-work"

BUGS = {
    "bug-002": {
        "category": "CONFIGURATION",
        "report": "Payments work locally but fail after deployment with 500 errors.",
        "expected": "Payments succeed when the deployment uses the configured payment region.",
        "actual": "A valid-looking deployed region makes payment requests return 500.",
        "root": "docker-compose supplies eu-west-1 while the local payment gateway accepts only us-east-1.",
        "subsystem": "payment configuration and runtime environment",
        "evidence": ["payment request log with configured region", "docker-compose environment", "payment gateway configuration check"],
        "remediation": "Align the deployed PAYMENTS_REGION with the gateway's supported region and make the expectation explicit.",
        "reproduction": "Run the compose deployment defaults, create an order, then post its valid payment.",
    },
    "bug-003": {
        "category": "DATA / DATABASE",
        "report": "Some users see duplicate orders after retrying a request.",
        "expected": "A repeated logical order request creates at most one order.",
        "actual": "Two requests carrying the same idempotency key create two rows.",
        "root": "Order creation stores the idempotency key but neither reuses an existing order nor enforces uniqueness.",
        "subsystem": "order request handling and orders schema",
        "evidence": ["two successful HTTP responses", "two rows with one idempotency key", "model without a unique constraint", "service without idempotency lookup"],
        "remediation": "Enforce a unique idempotency key and return the original order for a repeated request.",
        "reproduction": "Post the same order payload and idempotency_key twice, then list matching orders in PostgreSQL.",
    },
    "bug-004": {
        "category": "DEPENDENCY",
        "report": "Payment processing started failing after a dependency update.",
        "expected": "A valid payment completes and marks the order paid.",
        "actual": "The payment endpoint returns 500 after httpx 0.28 is installed.",
        "root": "The payment adapter still calls httpx.Client(proxies=...), an API removed in httpx 0.28.",
        "subsystem": "payment adapter and dependency manifest",
        "evidence": ["TypeError stack trace", "httpx 0.28 requirement", "adapter uses the removed proxies keyword", "focused payment regression"],
        "remediation": "Migrate the adapter to the supported httpx proxy configuration or pin a compatible version temporarily.",
        "reproduction": "Create an order and submit a valid payment in the patched environment.",
    },
    "bug-005": {
        "category": "RUNTIME",
        "report": "The API works initially, but after several requests, order requests become slow or fail.",
        "expected": "Repeated independent order requests remain fast and successful.",
        "actual": "The second request exhausts the small database pool and returns 500 after the timeout.",
        "root": "The order audit helper opens an engine connection for every order and never closes it.",
        "subsystem": "database connection lifecycle and order service",
        "evidence": ["first request succeeds and later request times out", "QueuePool timeout log", "connection state", "unclosed engine.connect call"],
        "remediation": "Close the audit connection or use a context manager; keep the pool size independent of request leaks.",
        "reproduction": "Create separate users and orders repeatedly until the connection-pool timeout occurs.",
    },
    "bug-006": {
        "category": "MULTI-SUBSYSTEM",
        "report": "Orders are successfully created, but some successful payments leave the order status as PENDING.",
        "expected": "A completed payment persists the matching order as paid.",
        "actual": "The payment response is completed but a fresh order read remains pending.",
        "root": "The payment is committed before the order status assignment; the later dirty order is discarded when the request session closes.",
        "subsystem": "payment service, order service, and database transaction lifecycle",
        "evidence": ["completed payment API response", "order API still reports pending", "payments row persisted", "status assignment after commit without a second commit"],
        "remediation": "Set the order status before the transaction commit or commit the status update in the same transaction.",
        "reproduction": "Create an order, submit a valid payment, then fetch the order and inspect payment and order rows.",
    },
}


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if old not in text:
        raise RuntimeError(f"Expected text missing from {path}: {old[:60]!r}")
    path.write_text(text.replace(old, new))


def add_file(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def apply_bug(name: str, tree: Path) -> None:
    services = tree / "app/services.py"
    models = tree / "app/models.py"
    schemas = tree / "app/schemas.py"
    db = tree / "app/db.py"
    compose = tree / "docker-compose.yml"
    requirements = tree / "requirements.txt"
    if name == "bug-002":
        add_file(tree, "app/payment_gateway.py", '''import os\nfrom app.core import logger\n\nSUPPORTED_REGION = "us-east-1"\n\ndef charge(amount):\n    region = os.environ.get("PAYMENTS_REGION", "us-east-1")\n    if region != SUPPORTED_REGION:\n        logger.error("Payment gateway rejected configured region", extra={"payment_region": region})\n        raise RuntimeError("Payment gateway authorization failed")\n    return {"status": "completed", "amount": str(amount)}\n''')
        replace(services, "from app.schemas import OrderCreate, PaymentCreate, UserCreate", "from app.schemas import OrderCreate, PaymentCreate, UserCreate\nfrom app.payment_gateway import charge")
        replace(services, "    payment = Payment(**data.model_dump())", "    charge(data.amount)\n    payment = Payment(**data.model_dump())")
        replace(compose, "      DATABASE_URL:", "      PAYMENTS_REGION: ${PAYMENTS_REGION:-eu-west-1}\n      DATABASE_URL:")
    elif name == "bug-003":
        replace(schemas, "    unit_price: Price\n", "    unit_price: Price\n    idempotency_key: Annotated[str | None, Field(min_length=8, max_length=100)] = None\n")
        replace(models, "    product_name: Mapped[str] = mapped_column(String(200))", "    product_name: Mapped[str] = mapped_column(String(200))\n    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)")
    elif name == "bug-004":
        add_file(tree, "app/payment_gateway.py", '''import httpx\n\ndef charge(amount):\n    # This was valid before the httpx 0.28 dependency update.\n    with httpx.Client(proxies={"https://": "http://proxy.internal:8080"}) as client:\n        return {"status": "completed", "amount": str(amount)}\n''')
        replace(services, "from app.schemas import OrderCreate, PaymentCreate, UserCreate", "from app.schemas import OrderCreate, PaymentCreate, UserCreate\nfrom app.payment_gateway import charge")
        replace(services, "    payment = Payment(**data.model_dump())", "    charge(data.amount)\n    payment = Payment(**data.model_dump())")
        replace(requirements, "httpx==0.28.1", "httpx==0.28.1  # upgraded from 0.27.2; adapter compatibility pending")
    elif name == "bug-005":
        replace(db, "from sqlalchemy import create_engine", "from sqlalchemy import create_engine, text")
        replace(db, "engine = create_engine(os.environ[\"DATABASE_URL\"], pool_pre_ping=True, hide_parameters=True)", "engine = create_engine(os.environ[\"DATABASE_URL\"], pool_pre_ping=True, hide_parameters=True, pool_size=2, max_overflow=0, pool_timeout=0.1)\n\ndef write_order_audit():\n    connection = engine.connect()\n    connection.execute(text(\"SELECT 1\"))\n    # Connection is intentionally not returned to the pool.")
        replace(services, "    order = Order(**data.model_dump(), total_amount=order_total(data.quantity, data.unit_price))", "    from app.db import write_order_audit\n    write_order_audit()\n    order = Order(**data.model_dump(), total_amount=order_total(data.quantity, data.unit_price))")
    elif name == "bug-006":
        replace(services, "    payment = Payment(**data.model_dump())\n    order.status = \"paid\"\n    db.add(payment)\n    db.commit()\n    db.refresh(payment)", "    payment = Payment(**data.model_dump())\n    db.add(payment)\n    db.commit()\n    db.refresh(payment)\n    order.status = \"paid\"")
    else:
        raise ValueError(name)
    regression = {
        "bug-002": '''def test_deployed_region_payment_completes(client, monkeypatch):
    monkeypatch.setenv("PAYMENTS_REGION", "eu-west-1")
    user = client.post("/users", json={"name": "Deploy", "email": "deploy@example.com"}).json()
    order = client.post("/orders", json={"user_id": user["id"], "product_name": "Cable", "quantity": 1, "unit_price": "9.99"}).json()
    assert client.post("/payments", json={"order_id": order["id"], "amount": "9.99"}).status_code == 201
''',
        "bug-003": '''def test_retry_returns_the_original_order(client):
    user = client.post("/users", json={"name": "Retry", "email": "retry@example.com"}).json()
    payload = {"user_id": user["id"], "product_name": "Cable", "quantity": 1, "unit_price": "9.99", "idempotency_key": "retry-key-0001"}
    first = client.post("/orders", json=payload)
    second = client.post("/orders", json=payload)
    assert first.json()["id"] == second.json()["id"]
''',
        "bug-004": '''def test_payment_after_httpx_upgrade_completes(client):
    user = client.post("/users", json={"name": "Upgrade", "email": "upgrade@example.com"}).json()
    order = client.post("/orders", json={"user_id": user["id"], "product_name": "Cable", "quantity": 1, "unit_price": "9.99"}).json()
    assert client.post("/payments", json={"order_id": order["id"], "amount": "9.99"}).status_code == 201
''',
        "bug-005": '''def test_repeated_orders_do_not_exhaust_connections(client):
    for number in range(3):
        user = client.post("/users", json={"name": f"Pool {number}", "email": f"pool{number}@example.com"}).json()
        response = client.post("/orders", json={"user_id": user["id"], "product_name": "Cable", "quantity": 1, "unit_price": "9.99"})
        assert response.status_code == 201, response.text
''',
        "bug-006": '''def test_completed_payment_persists_paid_order(client):
    user = client.post("/users", json={"name": "Payment", "email": "payment@example.com"}).json()
    order = client.post("/orders", json={"user_id": user["id"], "product_name": "Cable", "quantity": 1, "unit_price": "9.99"}).json()
    payment = client.post("/payments", json={"order_id": order["id"], "amount": "9.99"})
    assert payment.status_code == 201
    assert client.get(f"/orders/{order['id']}").json()["status"] == "paid"
''',
    }[name]
    add_file(tree, f"tests/test_{name.replace('-', '_')}.py", regression)


def command(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def build(target: Path) -> None:
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir()
    archive = WORK / "stable.tar"
    with archive.open("wb") as stream:
        subprocess.run(["git", "archive", "stable-v1"], cwd=target, stdout=stream, check=True)
    base = WORK / "stable-v1"
    with tarfile.open(archive) as tar:
        tar.extractall(base, filter="data")
    command("git", "init", "-q", cwd=base)
    command("git", "config", "user.email", "benchmark@traceroot.local", cwd=base)
    command("git", "config", "user.name", "TraceRoot Benchmark", cwd=base)
    command("git", "add", ".", cwd=base)
    command("git", "commit", "-qm", "stable-v1", cwd=base)
    for name, truth in BUGS.items():
        tree = WORK / name
        shutil.copytree(base, tree, ignore=shutil.ignore_patterns(".git"))
        shutil.copytree(base / ".git", tree / ".git")
        apply_bug(name, tree)
        command("git", "add", "-N", ".", cwd=tree)
        diff = subprocess.run(["git", "diff", "--binary", "--", "."], cwd=tree, text=True, stdout=subprocess.PIPE, check=True).stdout
        benchmark = BENCHMARKS / name
        benchmark.mkdir(parents=True, exist_ok=True)
        (benchmark / "introduced.patch").write_text(diff)
        (benchmark / "ground-truth.json").write_text(json.dumps({"bug_id": name.upper(), **truth, "verification_criteria": ["Patch applies to stable-v1", "Reproduction demonstrates the reported actual behavior", "Only the documented root cause explains all expected evidence"]}, indent=2) + "\n")
        check = subprocess.run(["git", "apply", "--check", str((benchmark / "introduced.patch").resolve())], cwd=base, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if check.returncode:
            raise RuntimeError(f"{name} patch does not apply: {check.stderr}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    build(args.target.resolve())

if __name__ == "__main__":
    main()




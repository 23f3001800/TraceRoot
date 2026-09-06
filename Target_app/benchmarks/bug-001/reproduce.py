"""Exercise the reported order-creation failure over HTTP."""
import argparse
from uuid import uuid4
import httpx

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        health = client.get("/health")
        health.raise_for_status()
        user = client.post("/users", json={
            "name": "Benchmark User", "email": f"benchmark-{uuid4().hex}@example.com",
        })
        user.raise_for_status()
        payload = {
            "user_id": user.json()["id"], "product_name": "Notebook",
            "quantity": 2, "unit_price": "19.99",
        }
        normal = client.post("/orders", json=payload)
        print(f"Normal order: {normal.status_code}", flush=True)
        if normal.status_code != 201:
            raise RuntimeError(normal.text)
        failure = False
        for attempt in range(1, 4):
            response = client.post("/orders", json={**payload, "quantity": 10})
            print(f"Bulk attempt {attempt}: HTTP {response.status_code}; "
                  f"request_id={response.headers.get('x-request-id')}; body={response.text}",
                  flush=True)
            failure |= response.status_code != 201
        recovery = client.post("/orders", json=payload)
        if recovery.status_code != 201:
            raise RuntimeError("Normal order failed after bulk requests: " + recovery.text)
        if failure:
            print("FAIL: valid bulk orders must return HTTP 201.", flush=True)
            return 1
        print("PASS: all valid orders were accepted.", flush=True)
        return 0

if __name__ == "__main__":
    raise SystemExit(main())

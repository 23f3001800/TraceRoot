# Target Commerce API

A small standalone FastAPI commerce backend for later debugging investigations.
It contains users, orders, and payments; no TraceRoot or AI components.

## Run

From this directory, using Docker Compose:

```sh
cp .env.example .env
# Edit .env and replace POSTGRES_PASSWORD with a local alphanumeric password.
docker compose up --build
```

API: http://localhost:8000 · OpenAPI: http://localhost:8000/docs
PostgreSQL data persists in the Compose volume. Configuration is supplied through
environment variables; do not commit .env. DATABASE_URL is required outside Compose.

For local Python 3.12 development with an existing PostgreSQL database:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost/DATABASE'
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Tests and reproduction

```sh
docker compose exec api pytest -q
docker compose exec api pytest -q -m "not regression"
docker compose exec api python benchmarks/bug-001/reproduce.py
docker compose logs api
```

Locally, use the same pytest commands after setting DATABASE_URL.
TEST_DATABASE_URL optionally selects a separate test database. Tests create and
drop a unique schema per test; the test role needs CREATE permission on that database.
The full suite includes a valid-input regression that intentionally fails in the
current benchmark version. The reproduction script exits nonzero when the API
violates the expected success behavior. It also accepts --base-url.

The verified stable checkpoint is stored at
benchmarks/bug-001/stable-v1.tar.gz. Extract into a separate directory to inspect
or run the complete stable source and tests. No Git commits or tags were created.
Benchmark materials contain evaluator-only information; exclude the entire
benchmarks directory from future debugging-agent access.

## API

| Method | Path | Behavior |
| --- | --- | --- |
| POST | /users | Create user (201); duplicate email (409) |
| POST | /orders | Create pending order (201); missing user (404) |
| GET | /orders/{order_id} | Retrieve order (200); missing order (404) |
| POST | /payments | Pay exact order total (201); already paid (409) |
| GET | /health | Database readiness (200 or 503) |

Requests with invalid fields return 422. Monetary values use decimal arithmetic
and serialize as strings. Payments atomically mark orders paid and serialize
concurrent payments using a database row lock.

Example order body (replace user_id with an existing user):

```json
{"user_id": 1, "product_name": "Notebook", "quantity": 2, "unit_price": "19.99"}
```

## Architecture and files

```text
app/
  main.py          HTTP endpoints, lifecycle, request logging
  core.py          JSON logger and request context
  schemas.py       Pydantic request/response validation
  services.py      Commerce operations and transactions
  models.py        Relational models and database constraints
  db.py            SQLAlchemy engine and session dependency
tests/
  conftest.py      Isolated PostgreSQL test schemas
  test_api.py      Endpoint tests and regression
benchmarks/bug-001/
  README.md        Private evaluator documentation
  reproduce.py    HTTP reproduction
  stable-v1.tar.gz Verified stable source snapshot
  introduced.patch Stable-to-current source change
Dockerfile
docker-compose.yml
requirements.txt
pytest.ini
.env.example
```

Tables initialize on startup using SQLAlchemy create_all; this small project
does not include migrations. Use one API worker for initial startup. JSON logs
include UTC timestamps, generated request IDs, method, path, HTTP status, and
exception details for failed requests. Responses do not expose database errors.
Database exceptions can include record details: keep investigation logs private.

This is a local benchmark application, without authentication or a payment
provider. Docker requires Docker Desktop WSL integration when running in WSL.

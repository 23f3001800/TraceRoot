# BUG-001 — evaluator ground truth

**Private benchmark material. Exclude this entire directory, snapshots, patches,
and verification logs from the debugging agent's filesystem and repository history
during evaluation.** Supply the public user-visible report only.

- **Bug ID:** BUG-001.
- **User-visible report:** Some users receive a 500 Internal Server Error when creating an order.
- **Expected behavior:** Valid orders persist and return 201. With the newly introduced
  bulk pricing policy, quantity 10 at 19.99 should produce total_amount 179.91.
  Stable-v1 used undiscounted pricing and returned 199.90 for that same order.
- **Actual behavior:** The bulk request returns generic HTTP 500 with a request ID.
  No order row is persisted. Normal quantity-2 orders still return 201 with 39.98.
- **Root-cause category:** Application pricing logic / relational invariant mismatch.
- **True root cause:** The changed order_total function in app/services.py applies
  a 10% discount when quantity >= 10. The unchanged PostgreSQL check constraint
  order_total_consistent, declared in app/models.py, requires total_amount =
  quantity * unit_price. Discounted totals violate that invariant during INSERT.
  SQLAlchemy raises IntegrityError wrapping psycopg CheckViolation (SQLSTATE 23514).
  The transaction rolls back when the request session closes; middleware logs the
  exception and returns a generic 500.
- **Relevant subsystem:** Order pricing, order persistence, PostgreSQL constraints.
- **Changed file:** app/services.py only. introduced.patch records the exact change.
- **Supporting files:** app/models.py, app/main.py, app/db.py, tests/test_api.py.

## Exact reproduction

From Target_app:

```sh
cp .env.example .env
# Replace POSTGRES_PASSWORD in .env.
docker compose up --build -d
docker compose exec api python benchmarks/bug-001/reproduce.py
docker compose logs api
```

Wait for /health to return 200 before running reproduction. The script creates
a unique user, sends one normal order, sends the following bulk request three
times, and verifies that another normal order still succeeds:

```json
{"user_id": "<created user ID as integer>", "product_name": "Notebook", "quantity": 10, "unit_price": "19.99"}
```

All three bulk requests return 500. The script exits **1**, asserting the expected
201 behavior instead of treating the bug as a passing result. It exits 0 when all
orders succeed. Each invocation creates a fresh user and two normal order rows
in the broken version; use a dedicated benchmark database.

## Expected supporting evidence

1. API responses contain a generic error and correlation ID, with no explanation.
2. JSON logs contain matching IDs, POST /orders, status 500, IntegrityError,
   PostgreSQL's constraint name, and traceback through create_order / commit.
3. The database definition of order_total_consistent establishes the invariant.
4. Failed bulk requests leave no order or payment rows; normal orders persist.
5. Stable snapshot comparison isolates the pricing change; Git history can be
   prepared manually from the snapshot and current source. No fabricated Git
   history, commits, or tags have been created.
6. The regression fails while health, users, normal orders, retrieval, payments,
   and validation tests pass.

Database inspection:

```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint WHERE conrelid = 'orders'::regclass;
SELECT id, user_id, quantity, unit_price, total_amount, status FROM orders;
```

## Stable checkpoint

stable-v1.tar.gz contains the stable app/ source, tests/, requirements.txt,
pytest.ini, Dockerfile, docker-compose.yml, environment/ignore examples, README,
and reproduction script. Extract it into a new empty directory:

```sh
mkdir /tmp/target-app-stable-v1
tar -xzf benchmarks/bug-001/stable-v1.tar.gz -C /tmp/target-app-stable-v1
```

Use a separate Compose project name and port if running alongside the broken
version. The archived README describes the final workflow; the archived source
is stable, so all 14 tests and the reproduction script pass there.

## Valid remediation (not implemented)

Keep the bulk-discount policy and reconcile the persisted pricing model with it:
store the applied discount explicitly and migrate the constraint to validate the
net total, or persist a consistently defined effective unit price with an explicit
rounding policy. A real migration must update existing PostgreSQL constraints;
changing SQLAlchemy metadata alone does not alter existing tables.

Reverting the pricing change restores stable-v1 behavior but removes the new
discount policy. Merely catching the exception or returning 201 without persisting
an order is not a valid fix.

## Verification criteria

- Quantity 2, price 19.99 persists with total 39.98.
- Quantity 10, price 19.99 persists with discounted total 179.91 and returns 201.
- Quantity 9 and 10 boundary cases behave consistently; test low-value rounding
  and the allowed upper quantity/price bounds.
- Retrieval returns the created order; exact-total payment succeeds and marks it paid.
- All existing tests pass, and the HTTP reproduction exits 0.
- No new unexpected 500 logs; constraints still reject inconsistent records.

## Observed verification

Python 3.12.3, PostgreSQL 16, real SQLAlchemy/psycopg connections:

- Before introducing the change: **14 passed**.
- After introducing the change: **13 passed, 1 failed**.
- Intentional failure: tests/test_api.py::test_bulk_order_is_accepted.
- Normal suite excluding regression: **13 passed, 1 deselected**.
- Live Uvicorn HTTP run: normal 201; bulk 500, 500, 500; subsequent normal 201.
- Database: two quantity-2 rows, no failed bulk rows.
- One third-party Starlette/AnyIO deprecation warning.
- Docker could not run in this WSL distro because Docker Desktop WSL integration
  is unavailable. Container startup is unverified; runtime and tests were verified
  directly against an isolated PostgreSQL 16 cluster.

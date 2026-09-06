# Environment verification

Repositories: /home/vikas/TraceRoot and /home/vikas/target-app, each with its own
Git history. The target's original two commits were extracted with git subtree
split, preserving authors, dates, messages, and changes. Hashes change when paths
are relocated to a new repository root. TraceRoot's original commits remain intact.
No remote is configured for target-app and nothing was pushed.

Target checkpoints: stable-v1 (6880b71), followed directly by
bug-001-introduced (4dc01ba). Only app/services.py differs between these tags.

Docker Desktop's Linux engine was verified through Windows docker.exe on
2026-09-06. Compose built and started Python 3.12 and PostgreSQL 16.

| Check | Stable | Bug introduced |
| --- | --- | --- |
| Full tests | 14 passed | 13 passed, 1 intentional failure |
| Normal suite | Covered by full suite | 13 passed |
| HTTP reproduction | All orders 201 | Normal 201; three bulk requests 500 |
| Host /health | 200 | 200 |

Run Windows PowerShell from the target-app directory using its WSL UNC path.
Copy .env.example to .env, set POSTGRES_PASSWORD, then run:

```powershell
docker compose up --build -d
docker compose exec api pytest -q
docker compose exec api pytest -q -m "not regression"
docker compose logs api
docker compose down
```

The full suite intentionally exits 1 at the broken checkpoint. Evaluator files
and Python caches are excluded from the image. The temporary verification
containers and their dedicated volume were removed afterward.

WSL-native Docker integration was not changed; Windows PowerShell is the verified
workflow. Compose confirms application reproducibility, but is not itself the
hardened untrusted-code sandbox specified in the input contract. No autonomous
execution or write tools have been implemented.

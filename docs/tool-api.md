# Implemented tool contracts

All six tools return ToolResult. Call to_dict() for JSON-ready output.

| Field | Meaning |
| --- | --- |
| status | ok, rejected, unavailable, timeout, or error |
| data | Structured tool-specific object, or null when no observation exists |
| error | null, or an object containing code and message |
| metadata | schema_version, tool, run_id, started_at, finished_at, duration_ms; snapshot_id when relevant |

An observed failing test returns status=ok and data.exit_code=1. Setup failures return status=error.

Durations use a monotonic clock. Wall-clock timestamps can change; correlate runs using IDs.

## Inputs

Context is trusted operator configuration, never an agent-controlled argument.

| Tool | Arguments after context |
| --- | --- |
| run_reproduction | repository_path; reproduction_command=None; timeout=60 |
| read_logs | source="application"; start_time=None; end_time=None; request_id=None; limit=20; run_id=None |
| search_code | repository; query; path_scope="."; result_limit=20 |
| read_file | repository; file_path; start_line=1; end_line=80 |
| inspect_database | operation; table=None; columns=None; filters=None; limit=20 |
| run_tests | repository; test_selector=None; timeout=60; marker=None |

Commands are argv arrays. Version 1 accepts python -m pytest or pytest, one public selector, -q, and optional -m.

Selectors support function names, file paths, and full public node IDs. Marker expressions use discovered markers and boolean operators.

Without a command, reproduction selects exactly one public regression/reproduction-marked test. Zero or multiple candidates return unavailable.

Search is literal. Repository files are restricted to app/**/*.py, tests/**/*.py, and approved public configuration files.

Configuration includes pytest.ini, pyproject.toml, setup.cfg, and requirements.txt. Discovery currently interprets pytest.ini or pyproject.toml.

Repository docs, benchmarks, Git history, environments, caches, symlinks, hardlinks, and secrets are excluded from snapshots.

## Result data

| Tool | Data fields |
| --- | --- |
| run_reproduction | Execution fields below; selection_reason, reproduced, expected, observed |
| run_tests | command, exit_code, stdout, stderr, duration_ms, collected, passed, failed, skipped, errors, failing_tests, http_observations, outcome, truncation flags |
| read_logs | source, collected_at, entries, truncated, missing_fields, collector_errors |
| search_code | query, matches, returned_matches, truncated |
| read_file | file, lines, total_lines, sha256, truncated, next_line |
| inspect_database | database, schema, role, transaction_read_only, operation, rows, truncated |

Search matches contain file, line, text, context, and text_truncated. File lines contain line and text.

reproduced is null when evidence is insufficient. HTTP values come from status_code assertions, never solely from exit codes.

Application logs are captured from pytest's actual application stderr. They are separated from reproduction stdout and registered as application.

Log entries retain application timestamps and request IDs. Each gains its execution run_id; passwords and recognized credentials are redacted.

Malformed records produce collector_error, retaining readable entries. Application IntegrityError records alone do not represent collector failures.

Database operations are list_tables, describe_table, list_constraints, and sample_rows. Sampling accepts selected columns and scalar equality filters.

Database inspection has no SQL-string argument. Identifiers are validated and quoted; filter values are parameterized.

## Limits and permissions

- Repository: 1,000 files, 128 KiB each, 8 MiB total.
- File reads: 200 lines and approximately 32 KiB output.
- Searches: 100 matches maximum and approximately 32 KiB output.
- Logs: 100 entries maximum, 32 KiB output, bounded tracebacks.
- Database: public plain tables only, 100 rows maximum, three-second statement timeout.
- Test execution: 1–120 seconds, bounded output, forced container removal afterward.
- Containers: read-only filesystem, unprivileged user, dropped capabilities, internal network, memory/CPU/process limits, scratch tmpfs.
- PostgreSQL inspection: separate role, no write grants, privilege preflight, read-only transactions.
- Test writes: disposable database and scratch only. No source edits, host mounts, published ports, or Docker socket.

The default database role is checked before every inspection. Inspection fails closed if privileges exceed the permitted scope.

The operator provisions dependencies before execution. Only pinned binary package requirements are accepted during this network-enabled build phase.

## Current scope

Linux/WSL hosts are supported. Windows Docker Desktop is accessed through its CLI executable from WSL.

Provisioning currently adapts the Python/FastAPI target app with app.main:app and requirements.txt; arbitrary project types are unsupported.

These are local prototype boundaries, not a guarantee against container-kernel vulnerabilities or deliberately falsified repository tests.

Execution reports are observations from repository code. They require corroboration; they are not trusted proof of application correctness.

Operator prepare/cleanup commands are not exposed through the six-tool registry. No agents, LLMs, or remediation tools exist.

Selectors currently identify functions or files; individual parametrization IDs are not supported.

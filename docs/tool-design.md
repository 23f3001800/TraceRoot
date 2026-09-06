# TraceRoot v1 tool design

Implementation contracts and current limits: [tool API](tool-api.md). Operator walkthrough: [your next steps](your-next-steps.md).

## run_reproduction

**Tool name:** run_reproduction

**Purpose:** Establish whether the reported failure occurs and capture a repeatable observation.

**When should the agent use it?** First, before searching implementation code. Use the optional input command when provided; otherwise run a public reproduction test selected from the repository's test configuration. If no reproduction is available, report that limitation rather than guessing success.

**Input:** An approved reproduction command or registered test selector, a bounded timeout, and an output-size limit. The runner resolves the working directory and environment from the validated repository handle; no arbitrary shell, environment overrides, or evaluator paths.

**Output:** Execution status (completed, timed_out, rejected, or unavailable), success/failure/unknown, exit code (null if none), stdout, stderr, duration_ms, output truncation flags, run ID, and observation time window. Include expected/observed HTTP status only when the test output establishes them; exit 1 alone does not establish a reproduced bug. Distinguish assertion failure from setup failure.

**Permissions:** READ ONLY investigation. Run only approved argv commands without shell expansion inside a disposable environment. Mount the source read-only; redirect caches and temporary files to scratch storage. Tests may write only to a dedicated disposable database and runtime scratch space. No host database, external services, production credentials, host filesystem writes, Docker socket, evaluator files, or persistent source edits. If isolation is unavailable, reject execution.

**Possible failures:** Missing command/test, unavailable dependencies or database, invalid selector, rejected command, setup error, timeout, output limit, nondeterminism, or failure unrelated to the report. A passing reproduction does not prove the reported bug never existed.

## read_logs

**Tool name:** read_logs

**Purpose:** Retrieve runtime evidence associated with a reproduction or failing request.

**When should the agent use it?** Immediately after reproduction, then when another hypothesis requires a narrower request or time window.

**Input:** Approved application-log source ID; optional run ID, request ID, UTC start/end times, HTTP method, path, status, or exception type; bounded maximum entries/bytes and pagination cursor. Source IDs are supplied by the trusted runner, not arbitrary host paths.

**Output:** Log source, collection time, requested window, ordered entries with timestamps and available correlation fields, pagination/truncation indicators, and explicit missing-field or redaction indicators. Preserve original exception messages and distinguish application records from collector errors.

**Permissions:** READ ONLY. Access only the selected application's logs within the investigation environment. Redact secrets before returning records. Do not read evaluator logs, unrelated services, host logs, or arbitrary files; no log deletion or service restart.

**Possible failures:** Missing source, denied access, expired/rotated logs, malformed records, clock skew, absent correlation IDs, collection delay, or truncated results. No matching entries is not proof that no error occurred.

## search_code

**Tool name:** search_code

**Purpose:** Locate relevant implementation and tests without reading the entire repository.

**When should the agent use it?** After reproduction and runtime observations suggest an endpoint, symbol, exception, or subsystem worth investigating.

**Input:** Literal query by default, optional bounded regex, optional relative directory/glob, context-line count, and maximum matches/bytes.

**Output:** Repository-relative file paths, matching line numbers, bounded surrounding context, match count, truncation flag, and repository snapshot identifier.

**Permissions:** READ ONLY. Search text files only within the approved sanitized repository. Canonicalize paths and reject traversal, absolute paths, symlink escapes, binaries, secrets, .git, and evaluator material. Apply the same exclusions to filenames, matches, context, and errors. Enforce time and output bounds.

**Possible failures:** Invalid regex, denied path, missing directory, binary/oversized file, timeout, or result truncation. Return no matches separately from search failure.

## read_file

**Tool name:** read_file

**Purpose:** Inspect selected source or test ranges with attributable locations.

**When should the agent use it?** Once search results identify a file relevant to a hypothesis; expand ranges only as needed.

**Input:** Repository-relative path, 1-based start line, and bounded line count.

**Output:** Relative path, numbered lines, file content hash, total line count when available, and truncation/continuation information.

**Permissions:** READ ONLY. Use the same sanitized root and exclusion policy as search_code. Resolve and validate the opened file against the root to prevent traversal and symlink races. Reject .git, evaluator content, secrets, binaries, and paths outside the approved snapshot.

**Possible failures:** Missing file, invalid range, access denied, unsupported encoding/binary content, file changed since search, or size limit. Denied paths must not reveal protected contents in error messages.

## inspect_database

**Tool name:** inspect_database

**Purpose:** Examine actual database schema, constraints, and bounded persisted state to test a hypothesis.

**When should the agent use it?** When logs or source suggest a persistence issue and live database evidence can confirm or falsify it.

**Input:** Approved database handle and one operation: list_tables, describe_table, list_constraints, or sample_rows. Table/schema identifiers must be allowlisted; sample_rows accepts selected columns, bounded equality filters, deterministic ordering, and a row limit. No arbitrary SQL.

**Output:** Database/schema identity without credentials, operation, observation time, column types/nullability/defaults, constraint definitions, or bounded rows as appropriate; row limits, truncation, and redactions. A failed INSERT's attempted values are not persisted rows: obtain those from request/log evidence rather than inventing database results.

**Permissions:** READ ONLY. Use a dedicated SELECT/catalog-only role, a read-only transaction, parameterized values, safely quoted allowlisted identifiers, statement/lock timeouts, and row/byte limits. No writes, DDL, arbitrary functions, stored procedures, extensions, administrative operations, or production connections. The test runner's writable disposable-database credential is never available through this tool.

**Possible failures:** Connection/authentication failure, missing schema/table, insufficient privileges, timeout/lock contention, unavailable snapshot, redacted columns, or unsupported operation. Empty rows cannot alone establish why a transaction failed.

## run_tests

**Tool name:** run_tests

**Purpose:** Gather focused evidence and establish the extent of a failure.

**When should the agent use it?** Run a specific test to evaluate a hypothesis, a file for nearby behavior, and the full suite when broader evidence is needed. Reuse existing results when code and environment have not changed.

**Input:** Scope (specific_test, test_file, or full_suite), validated public pytest node ID or relative test-file path where applicable, approved marker selection, timeout, and output-size limit. The runner constructs argv; no arbitrary flags, plugins, shell commands, or paths outside the test allowlist.

**Output:** Execution status, success/failure/unknown, exit code, stdout, stderr, duration_ms, run ID, collection/pass/fail/skip/error counts when parseable, failing node IDs, and truncation indicators. Distinguish no tests collected, collection/setup errors, timeout, and test assertion failures.

**Permissions:** READ ONLY investigation under the same disposable execution boundary as run_reproduction. Source is immutable; only isolated test state, database rows, caches, and scratch artifacts may change. Treat repository tests and configuration as untrusted executable code. No host access, evaluator material, arbitrary network, persistent modifications, or production state.

**Possible failures:** Invalid test selection, no tests collected, collection/import error, missing dependency, unavailable database, fixture failure, nondeterministic result, timeout, resource limit, or output truncation.

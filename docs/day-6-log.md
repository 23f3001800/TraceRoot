# Day 6 work log

## Benchmark design

- Kept the target's `stable-v1` Git tag untouched.
- Preserved BUG-001 as its existing isolated business-rule/database patch.
- Defined BUG-002 through BUG-006 with one intended cause per patch.

## Generator and private artifacts

- Added `scripts/build_benchmark_variants.py`.
- The generator archives `stable-v1`, creates isolated temporary variants,
  writes patches and private ground truth, then verifies every patch applies.
- Added focused failing reproduction tests to generated variants.
- Corrected BUG-003 so the idempotency key is optional for ordinary orders;
  only repeated keyed orders expose its intended duplicate-row failure.

## Evaluation status

- Patches apply cleanly to an independently archived stable baseline.
- Live single-investigator runs remain pending provider authorization.
- No multi-agent, patching agent, or target-app mutation was introduced.

## Final verification

- Regenerated every patch from an archived stable-v1 baseline.
- The generator completed its git apply --check validation for BUG-002 through BUG-006.
- TraceRoot validation passed: 97 tests passed and 4 were skipped.


## Live-run environment check

- The disposable-session runner uses the Docker CLI supplied to the WSL process.
- Docker Desktop currently reports that Docker is unavailable in this WSL distro.
- No benchmark variant was applied to the target checkout and no investigator payload was sent externally.


## Public target and BUG-001 completion

- Created a separate sanitized public target repository from stable-v1 history.
- Removed all target benchmark artifacts before publication.
- Added BUG-001's private patch and ground truth beside BUG-002 through BUG-006.


## Reproduction selection correction

- Focused reproduction tests now take priority over generic regression tests.
- This keeps BUG-001's regression test available while later variants have one deterministic reproduction target.


## Deterministic live reproduction

- Created one disposable public-target copy and Docker session per benchmark patch.
- All six focused reproductions failed as intended without target writes.
- BUG-001, 002, 004 and 005 reported expected 201 versus observed 500.
- BUG-003 and 006 reported their intended persisted-state assertion failures.
- Gemini investigator calls remain blocked by external-data approval review.


## Repository separation correction

- Removed TraceRoot's accidental origin remote to target-commerce-api.
- TraceRoot, the private target, and the public target clone now have separate Git repositories and histories.


## Published-target Gemini attempt

- Prepared BUG-001 from a fresh clone of the published target repository at stable-v1.
- Applied only its isolated private patch in a disposable directory and Docker session.
- The environment rejected sending that patched snapshot to Gemini; it distinguishes the public baseline from private benchmark changes.


## State-assertion reproduction correction

- Focused tests that fail an assertion without an HTTP status comparison now report reproduced true.
- This preserves null expected and observed fields while allowing data-state and multi-subsystem benchmarks to proceed.


## Approved Gemini live-investigation flow

- Every run clones published target-commerce-api, checks out stable-v1, applies exactly one private patch, and uses a disposable read-only Docker session.
- BUG-001: reproduction observed 201 to 500; logs found order_total_consistent CheckViolation; search and read_file linked it to bulk discount logic; evaluator returned ROOT_CAUSE_IDENTIFIED.
- BUG-001 used four tool calls and six model calls. Provider recovery resumed without rerunning reproduction.
- BUG-002 Docker setup failed transiently before Gemini. BUG-003 exposed state-assertion reproduction handling, now corrected. BUG-004 through BUG-006 remain pending.
- Full suite after correction: 97 passed, 4 skipped.


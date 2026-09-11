# Day 6: Bug benchmark

TraceRoot now has six independent benchmark variants. Each starts from the
unchanged `stable-v1` target tag. BUG-001 remains the existing
business-rule/database mismatch; BUG-002 through BUG-006 are generated as
separate patches.

## Private benchmark contract

The investigator receives only the target repository, bug report, optional
reproduction command, and read-only constraints. Ground truth is stored under
`benchmarks/` and must never be copied into an investigator task or target
runtime. TraceRoot's source tools reject any path under `benchmarks/`.

| Bug | Category | Intended root cause |
|---|---|---|
| 001 | DATABASE | Discounted total conflicts with the DB total constraint. |
| 002 | CONFIGURATION | Deployment supplies a valid but unsupported payment region. |
| 003 | DATA / DATABASE | Repeated idempotency keys create separate order rows. |
| 004 | DEPENDENCY | Payment adapter uses the removed httpx `proxies` argument. |
| 005 | RUNTIME | Order audit connections are never returned to the pool. |
| 006 | MULTI-SUBSYSTEM | Order status changes after payment commit and is not persisted. |

Each directory contains `introduced.patch` and private `ground-truth.json`.
Every patch adds one focused regression test whose expected assertion fails on
that variant. It is the deterministic reproduction command after the patch is
applied.

## Build and reset

```bash
.venv/bin/python scripts/build_benchmark_variants.py --target /home/vikas/target-app
```

The generator uses `git archive stable-v1`, so it never changes the target
checkout. It creates a temporary baseline in `.day6-work/`, produces each patch,
and runs `git apply --check` against that baseline.

For an operator evaluation, create a disposable copy of `stable-v1`, apply just
one patch, run its focused test, then discard that copy. Never apply a second
benchmark patch to the same copy.

```bash
git clone /home/vikas/target-app /tmp/traceroot-bug-004
git -C /tmp/traceroot-bug-004 checkout stable-v1
git -C /tmp/traceroot-bug-004 apply /home/vikas/TraceRoot/benchmarks/bug-004/introduced.patch
pytest -q tests/test_bug_004.py
git -C /tmp/traceroot-bug-004 apply --reverse /home/vikas/TraceRoot/benchmarks/bug-004/introduced.patch
```

## Investigator results

| Bug | Category | Reproduced | Root cause correct | Tools | Calls | Premature conclusion |
|---|---|---:|---:|---|---:|---:|
| 001 | DATABASE | Pending live-provider authorization | — | — | — | — |
| 002 | CONFIGURATION | Not run | — | — | — | — |
| 003 | DATA / DATABASE | Not run | — | — | — | — |
| 004 | DEPENDENCY | Not run | — | — | — | — |
| 005 | RUNTIME | Not run | — | — | — | — |
| 006 | MULTI-SUBSYSTEM | Not run | — | — | — | — |

A live Gemini investigation was not run because the environment requires
separate approval before target-app information can be sent to that provider.
No multi-agent system is added by Day 6.

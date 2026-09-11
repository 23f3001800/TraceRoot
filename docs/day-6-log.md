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


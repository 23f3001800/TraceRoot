# Compact benchmark report

Source: `evaluations/manifest.json`. Generated evidence: `evaluations/reports/before.json` and `after.json`.

| Run | Before | After | Gate result |
| --- | ---: | ---: | --- |
| EduForge grade-band recovery | 27.5/100 | 87.5/100 | Ineligible: clean recovery evidence incomplete |

Measured recovery evidence improved the controlled grade-band cases from 0/3 to 3/3. Focused classification tests passed 49/49 and the target unit suite passed 433 tests. Detection, diagnosis, evidence audit, approval scope, sandbox execution, original reproduction, regression checks, and production isolation have recorded evidence.

The 87.5 score is a **strong staging result**, not a production candidate. Efficiency has no complete latency/cost measurement and therefore contributes zero of five points. The later staging replay still ended `succeeded_partial`, so the mandatory `recovery_evidence_complete` gate fails and recovery is not declared.

AI-specific coverage is currently limited to overall and low-confidence controlled-case accuracy. Per-grade precision/recall/F1, confusion matrix, calibration error, fallback rate, baseline-dataset regression, and per-classification latency/cost remain `NOT_MEASURED` in the generated report.

To close those fields, record one JSON object per classification with `expected`, `predicted`, `confidence`, `low_confidence`, `fallback`, `latency_ms`, `cost_usd`, `input_tokens`, and `output_tokens`, then run `python scripts/classifier_metrics.py cases.jsonl --baseline-accuracy 0.0 --output metrics.json`. A new approved staging run can close the recovery gate only if `python scripts/recovery_receipt.py receipt.json --expected-grade-band 6-8` exits successfully.

## Interview framing

TraceRoot demonstrates a safety-gated incident loop rather than claiming autonomous production repair: automatic detection, bounded evidence collection, an independent evidence audit, exact-hash human approval, disposable execution, deterministic verification, and isolated staging delivery. The strongest evidence is the measured 0/3 to 3/3 classifier recovery with 49 focused and 433 unit tests passing. The honest limitation is equally important: the clean end-to-end staging recovery gate has not passed, so production eligibility remains false regardless of the weighted score.

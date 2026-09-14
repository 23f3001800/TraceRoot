# Day 8 — Evidence Auditor

## Flow

```text
Incident → Investigator → Evidence Auditor
  SUPPORTED     → root-cause report
  INSUFFICIENT  → Investigator with required evidence
  CONTRADICTED  → Investigator with contradictions
```

## Auditor boundary

- Receives incident, persisted observations, hypotheses, and evidence only.
- Receives no tool catalog, tool history transcript, or write capability.
- Returns `SUPPORTED`, `INSUFFICIENT`, or `CONTRADICTED` with checked claims, supporting evidence, missing evidence, contradictions, and required next evidence.
- Only `SUPPORTED` may include a final root-cause report.

## Validation

- Audit results persist in `state.audits`.
- `INSUFFICIENT` and `CONTRADICTED` are added to the Investigator’s next observation context.
- Root-cause reports remain subject to concrete citation validation.

## Current evaluation status

The single-investigator baseline is recorded in Day 7. Live A/B benchmark comparison awaits a stable provider window; existing BUG-003, BUG-005, and BUG-006 checkpoints remain resumable.

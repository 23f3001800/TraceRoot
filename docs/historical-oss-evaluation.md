# Historical Open-Source Evaluation

## Goal

Level 2 evaluates TraceRoot against unfamiliar public repositories without exposing a historical fix to the Investigator.

## Candidate gate

Each case must provide:

- an original public incident report;
- a reproducible failure on a commit before the fix;
- a bounded public test selector;
- a private record of the fixing commit and accepted remediation;
- a disposable checkout and Docker-compatible dependency profile.

The Investigator receives only the repository checkout, incident report, public reproduction command, and read-only constraints. It never receives private metadata, fixing commits, pull-request discussion, or a known solution.

## Initial screened candidates

| Case | Repository | Public report | Evaluation status |
| --- | --- | --- | --- |
| OSS-001 | pallets/flask | Issue 4170: application factory invocation regression | Screened; isolate fixing commit next. |
| OSS-002 | pallets/flask | Issue 4043: dependency compatibility regression | Screened; isolate fixing commit next. |
| OSS-003 | pytest-dev/pytest | Issue 3854: duplicate collection regression | Screened; isolate fixing commit next. |
| OSS-004 | pytest-dev/pytest | Issue 5301: last-failed behavior regression | Screened; isolate fixing commit next. |
| OSS-005 | psf/requests | Issue 5924: proxy authorization regression | Screened; isolate fixing commit next. |

Screening is not an evaluation result. A case becomes evaluable only after a clean pre-fix checkout and public reproduction succeed in a disposable environment.

## Metrics

For each eligible case, record reproduction success, root-cause category accuracy, evidence sufficiency, tool calls, model calls, provider failures, auditor verdict, and stopping reason. Provider failure remains distinct from reasoning failure.

## Provider order

Use OpenRouter free model first. Gemini is retried only after its provider health recovers. Azure remains fallback and is not used for this phase unless the first two are unavailable.

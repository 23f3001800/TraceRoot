# Day 7 — Reliability and Evidence Hardening

## Scope

- Keep investigation read-only and block benchmark-ground-truth paths.
- Separate provider failures from application and tool failures.
- Improve reproduction records and add bounded configuration and Git evidence.

## Changes

- Added `PROVIDER_FAILURE`; retryable Gemini errors checkpoint, use bounded backoff, pause after retry exhaustion, and resume at the saved graph node.
- Added `inspect_configuration`: snapshot-only, bounded, and secret-redacted.
- Added `inspect_git`: read-only bounded history, changed public files, and dependency changes. It filters protected paths.
- Extended reproduction records with selected command, requested inputs, timestamps in metadata, attempt summaries, and consistency status.
- Strengthened final validation: a root cause needs runtime/reproduction evidence and separate confirming subsystem evidence.

## Verification

Focused tests: `24 passed`.

Full-suite note: WSL has no `google.genai` package, so one pre-existing retry-options test cannot import its optional provider dependency. All remaining tests passed in the earlier run: `95 passed, 4 skipped`.

## Next

Run BUG-003 through BUG-006 against disposable patched copies of the public target repository, then record observed gaps before proposing specialist agents.

# Limitation remediation roadmap

This roadmap separates verified behavior from work that still needs evidence.

## P0 — achieve a clean staging quality result

Current evidence: the physics run completed all ten stages and produced a
package, but ended as `succeeded_partial` because generic replay responses
exercise degraded fallbacks.

Recommended fix:

1. Generate exact cassettes using the existing request hash: stage, system
   prompt, user content, and output schema.
2. Store separate schema-specific responses for every multi-call stage.
3. Replace generic fallbacks in the staging quality gate with exact cassettes;
   retain generic fallbacks only in tests that deliberately exercise recovery.
4. Add an end-to-end assertion requiring `succeeded`, ten completed stages, a
   package ID, zero degraded-fallback warnings, and the expected grade band.
5. Keep the existing baseline comparison (`0/3` to `3/3`) as an independent
   quality check rather than inferring quality from HTTP health alone.

## P0 — reconcile Azure CLI false negatives

Azure repeatedly records a successful OneDeploy operation while its CLI exits
non-zero after polling. Extend the deterministic staging deployer to query the
server-side deployment record after a CLI failure. Treat it as successful only
when the exact target reports a completed success after the approved action
started; otherwise stop staging. Record both client and server outcomes in the
deployment receipt and cover success, ambiguity, timeout, and stale-deployment
cases with tests.

## P1 — deploy the home page beyond localhost

Keep localhost as the default. For shared access:

1. Run `workspace-ui --host 0.0.0.0` behind an authenticated TLS reverse proxy.
2. Add an explicit allowlist of trusted host/origin values rather than removing
   the existing loopback check.
3. Store session state on a persistent encrypted volume.
4. Add rate limits, request-size limits, audit logs, and CSRF protection before
   accepting remote operator actions.
5. Never expose Docker's socket directly to the web container; route sandbox
   requests through the existing bounded executor service.

## P1 — complete deployed-runtime and publication adapters

The UI honestly reports no configured runtime target and no publication
destination. Add named target records containing credential references,
read-only scopes, allowed origins, and redaction rules. Bind deployment and
draft-PR actions to exact target/action hashes, then expose them only when their
capabilities pass validation.

## P2 — operational hardening

- Reconcile the monitor's Compose volume with the home-page workspace through a
  bounded event transport instead of copying files manually.
- Add retention and rotation for public event journals and screenshots.
- Add browser CI with Playwright Chromium so the currently opt-in visual test
  runs on every frontend change.
- Add backup/restore drills for incident journals and approval receipts.

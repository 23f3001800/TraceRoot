# TraceRoot input contract — v1

The caller supplies exactly four permitted top-level fields. No root-cause hint,
affected file, failing line, expected patch, evaluator notes, or preselected
subsystem is accepted.

| Field | Required | Meaning |
| --- | --- | --- |
| repository | Yes | A local repository directory reference resolved by the trusted runner to an immutable, sanitized snapshot. No arbitrary remote URL or host-wide path. |
| bug_report | Yes | Nonempty user-visible description of the failure, without designer ground truth. |
| reproduction_command | No | A public reproduction/test command, preferably an argv array. Omit when unknown. It is an untrusted proposal, not permission to execute arbitrary code or a shell. |
| constraints | Yes | Investigation restrictions. These may tighten the mandatory policy, never weaken it. |

Example input:

```yaml
repository: ../target-app
bug_report: Some users receive a 500 Internal Server Error when creating an order.
constraints:
  - benchmark ground truth inaccessible
  - read-only investigation
  - no modifications
```

If a legitimate public reproduction command is supplied, an accepted form is
an argv array such as ["python", "-m", "pytest", "-q", "tests/test_api.py"].
The runner validates commands and test selectors against its approved execution
policy; it does not pass command strings to a shell. An optional command must not
refer to benchmarks, hidden evaluator artifacts, or host utilities.

Reject unknown top-level keys, empty required values, invalid field types,
repository paths outside the configured allowlist, protected reproduction paths,
and constraints that attempt to disable mandatory restrictions. Resolve relative
repository paths against the runner's configured workspace, not arbitrary CWD.

## Mandatory isolation boundary

Before exposing a repository to the agent, the trusted runner creates a clean
snapshot without benchmarks/ (including benchmarks/bug-001/), stable archives,
patches, evaluator documentation, verification artifacts, secret files, or .git.
Filter public documentation that points at evaluator-only material. A path
denylist alone is insufficient when a copied README, container image, Git object,
or test artifact carries the same information.

The agent receives only the four input fields and subsequent permitted tool
results. Database handles, log-source handles, and executable allowlists are
runner configuration, not additional task hints. Tool errors must not reveal
protected file contents or credentials.

Source and persistent user data remain read-only. Reproduction and tests execute
untrusted repository code, so they require a disposable sandbox: immutable source,
bounded CPU/memory/time/output, isolated temporary storage, a disposable database,
and no host filesystem, Docker socket, evaluator mounts, production credentials,
or external network access. Dependencies are provisioned before investigation.
Test writes inside this disposable state are permitted execution effects; they
do not authorize source edits or modifications to user systems.

inspect_database uses a separate read-only database identity. Only the trusted
test runner can use the disposable application's writable database identity.
If this boundary cannot be enforced, return unavailable/rejected instead of
falling back to running tests directly on the host.

## Investigation behavior

Start by reproducing the symptom, then inspect logs. Use those observations to
select code and database evidence that distinguishes competing hypotheses.
Record unsupported or untested hypotheses as uncertain. Use focused and broader
test results to establish the failure's scope. Do not patch, commit, restart
services, write through database inspection, or open a PR.

Version 1 defines six investigation tools only. It adds no LLM, agent framework,
Git-history tool, write tool, or autonomous remediation.

# Day 12 - Sandbox Executor and Verifier Boundary

The executor accepts only a human-approved bounded unified diff for the registered disposable Docker session. It rejects LocalRunner, absent approval, other repositories, and invalid patches. Actual patch application remains disabled. The verifier is Docker-only and is reserved to rerun reproduction plus regression after future execution.

Verification: 2 executor-boundary tests passed.

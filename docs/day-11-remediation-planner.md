# Day 11 - Remediation Planner

The planner accepts only ROOT_CAUSE_SUPPORTED reports. It has no tools and returns a structured proposal: minimal changes, validation plan, risk, limitations, and mandatory human approval. It cannot patch files, change configuration, restart a target, or run tests. DockerRunner will be mandatory before any future executor exists.

Verification: 2 planner-boundary tests passed.

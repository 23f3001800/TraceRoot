# Day 10 - Auditor feedback loop

The Evidence Auditor returns a verdict and evidence requirements only. It cannot name a tool.

For an INSUFFICIENT verdict, LangGraph records the Auditor feedback, transitions through `investigate_missing_evidence`, and returns control to the Investigator. The Investigator selects a permitted read-only tool. New evidence then reaches the Auditor again.

For CONTRADICTED, the graph records the contradiction and returns to the Investigator to reopen hypotheses. SUPPORTED routes to the root-cause report.

The graph allows at most three audit cycles. Reaching that boundary produces `INSUFFICIENT_EVIDENCE` rather than looping indefinitely.

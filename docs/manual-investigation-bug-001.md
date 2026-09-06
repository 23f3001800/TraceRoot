# Manual investigation: BUG-001

Evaluator-only: withhold this document, its Git history, and local evidence from future debugging agents.

This is an evidence-led replay, not a blind benchmark; prior knowledge was already available.

No benchmark files were opened during this investigation. Each tool read the filtered snapshot or disposable runtime.

Initial input:

```yaml
repository: /home/vikas/target-app
bug_report: Some users receive a 500 Internal Server Error when creating an order.
constraints:
  - benchmark ground truth inaccessible
  - read-only investigation
  - no modifications
```

Snapshot: `24ad543efdd17a2901f7e83c5f98cddc61aa46c3e38174f791746da3973727ba`.

Session: `.traceroot-runs/18366a6e6bb0`. Raw input/result records remain locally under its ignored evidence directory.

The reproduction uses FastAPI TestClient inside Docker, with actual PostgreSQL transactions. It does not simulate database failures.

Database inspection targets the live application's public schema. Tests create equivalent temporary schemas and remove them afterward.

## 1. Reproduce the report

**Observation:** Only the report says some order creations return 500.

**Current hypotheses:** Intermittent application failure; database failure; dependency issue; stale report.

**Evidence needed:** A reproducible public test and its observed HTTP status.

**Tool selected:** `run_reproduction(repository_path="/home/vikas/target-app", timeout=60)`

**Why this tool:** Establish the failure before inspecting implementation.

**Tool result:** Public regression discovery selected test_bulk_order_is_accepted. Expected 201, observed 500; exit 1; 2740.29 ms.

**Hypotheses after result:** The symptom is current. The cause remains unknown.

Evidence run: `ad9627ef92b4458486dac3b9e747ffcc`.

## 2. Observe the correlated failure

**Observation:** The reproduction returned request ID 6a3a55c2-933a-4c16-81d0-ae8ceedc0f4c.

**Current hypotheses:** Application exception, persistence failure, or unavailable dependency.

**Evidence needed:** Runtime evidence for that exact request.

**Tool selected:** `read_logs(source="application", request_id="6a3a55c2-933a-4c16-81d0-ae8ceedc0f4c", run_id="ad9627ef92b4458486dac3b9e747ffcc", limit=5)`

**Why this tool:** Correlated logs distinguish the competing failure categories.

**Tool result:** POST /orders returned 500. IntegrityError wraps CheckViolation naming order_total_consistent. Collector errors: none.

**Hypotheses after result:** PostgreSQL rejected a row; network unavailability is weakened. The invariant or constructed values may be wrong.

Evidence run: `7a16fd18f8ec4fefb61dd0450a0929c7`.

## 3. Locate the endpoint

**Observation:** Logs identify POST /orders.

**Current hypotheses:** Order construction or a persisted invariant causes the rejection.

**Evidence needed:** The handler responsible for the reported endpoint.

**Tool selected:** `search_code(repository="/home/vikas/target-app", query="/orders", path_scope="app", result_limit=10)`

**Why this tool:** Locate the handler using a name supplied by runtime evidence.

**Tool result:** app/main.py:55 declares POST /orders; nearby code identifies create_order.

**Hypotheses after result:** The investigation narrows to the order-creation path.

Evidence run: `ba5f8281e5d2403e9e129076c68e53ed`.

## 4. Follow the discovered handler

**Observation:** Search identified create_order.

**Current hypotheses:** The handler delegates construction or persistence to another function.

**Evidence needed:** The function implementing order creation.

**Tool selected:** `search_code(repository="/home/vikas/target-app", query="create_order", path_scope="app", result_limit=10)`

**Why this tool:** Follow the discovered symbol rather than selecting a remembered filename.

**Tool result:** app/main.py:57 delegates to services.create_order. Its definition appears at app/services.py:33.

**Hypotheses after result:** Order construction is localized; the values require inspection.

Evidence run: `656b1d89d2794b9e8b87729f61628a32`.

## 5. Locate the logged constraint

**Observation:** PostgreSQL named order_total_consistent.

**Current hypotheses:** The deployed invariant may differ from source or conflict with application values.

**Evidence needed:** The source declaration bearing that exact name.

**Tool selected:** `search_code(repository="/home/vikas/target-app", query="order_total_consistent", path_scope="app", result_limit=10)`

**Why this tool:** Use the database's own identifier to locate relevant schema code.

**Tool result:** app/models.py:19 declares total_amount = quantity * unit_price.

**Hypotheses after result:** The source invariant expects multiplication without any additional adjustment.

Evidence run: `90525a4d9a204383b2ef02c3558461b3`.

## 6. Inspect construction

**Observation:** The handler delegates to the located service function.

**Current hypotheses:** Order construction may alter one side of the invariant.

**Evidence needed:** The assigned values and persistence operation.

**Tool selected:** `read_file(repository="/home/vikas/target-app", file_path="app/services.py", start_line=30, end_line=42)`

**Why this tool:** Inspect the small range already found by search.

**Tool result:** Line 36 assigns total_amount using order_total; line 38 commits the order.

**Hypotheses after result:** The order_total helper determines the value rejected during persistence.

Evidence run: `2fb13a6f20b346a0805bd1da326e87f3`.

## 7. Inspect the model

**Observation:** Search located the constraint and order model together.

**Current hypotheses:** Numeric types or another constraint could explain rejection.

**Evidence needed:** The surrounding model definition and numeric field types.

**Tool selected:** `read_file(repository="/home/vikas/target-app", file_path="app/models.py", start_line=14, end_line=30)`

**Why this tool:** Inspect relevant context without reading unrelated modules.

**Tool result:** Quantity is integer; prices and totals are Numeric. The named constraint requires quantity multiplied by unit_price.

**Hypotheses after result:** The named equality remains the strongest explanation; database deployment still needs confirmation.

Evidence run: `26a589bc4173448d911a110a41312ec5`.

## 8. Locate the pricing helper

**Observation:** The constructor calls order_total.

**Current hypotheses:** The helper may calculate a total incompatible with the invariant.

**Evidence needed:** The helper's exact location.

**Tool selected:** `search_code(repository="/home/vikas/target-app", query="def order_total", path_scope="app/services.py", result_limit=5)`

**Why this tool:** Follow a newly observed dependency within the already discovered file.

**Tool result:** order_total is defined at app/services.py:9.

**Hypotheses after result:** The relevant calculation can now be inspected directly.

Evidence run: `dc8c98bd16ad4ac5844d3a210e2c72c0`.

## 9. Confirm actual database enforcement

**Observation:** Source declares the invariant reported by PostgreSQL.

**Current hypotheses:** Schema drift could make source misleading.

**Evidence needed:** The live database constraint definition.

**Tool selected:** `inspect_database(operation="list_constraints", table="orders", limit=20)`

**Why this tool:** Check deployed schema through the restricted inspection identity.

**Tool result:** Role inspection, read-only transaction. PostgreSQL confirms CHECK(total_amount = quantity::numeric * unit_price).

**Hypotheses after result:** The live public schema matches the source invariant; schema drift is unsupported.

Evidence run: `19364f7c6d1d4c048430a71175fea3bb`.

## 10. Inspect the calculation

**Observation:** The constructor uses order_total; PostgreSQL enforces multiplication.

**Current hypotheses:** The helper changes totals without changing the stored quantity or price.

**Evidence needed:** The helper's arithmetic and conditional behavior.

**Tool selected:** `read_file(repository="/home/vikas/target-app", file_path="app/services.py", start_line=9, end_line=12)`

**Why this tool:** Read the specific calculation located by search.

**Tool result:** Quantity >=10 applies a 10% discount. Logs show quantity 10, price 19.99, attempted total 179.91.

**Hypotheses after result:** 179.91 differs from required 199.90. The calculation explains the exact rejected values.

Evidence run: `3c90280cf4a54da2af4b0879996aa926`.

## 11. Find comparison tests

**Observation:** The calculation changes behavior at a quantity threshold.

**Current hypotheses:** Bulk inputs fail while ordinary order creation remains operational.

**Evidence needed:** Public tests covering normal orders and related endpoints.

**Tool selected:** `search_code(repository="/home/vikas/target-app", query="def test_", path_scope="tests", result_limit=20)`

**Why this tool:** Discover comparison tests before selecting them.

**Tool result:** Found test_order_creation_and_retrieval and tests covering health, users, payments, validation, and the bulk case.

**Hypotheses after result:** The discovered tests can distinguish a conditional defect from an entirely broken endpoint.

Evidence run: `a86f77a310cd4ebba73f573fc9d0df60`.

## 12. Test ordinary behavior

**Observation:** A public normal-order test is available.

**Current hypotheses:** Ordinary order creation remains functional.

**Evidence needed:** The normal test's execution result.

**Tool selected:** `run_tests(repository="/home/vikas/target-app", test_selector="test_order_creation_and_retrieval", timeout=60)`

**Why this tool:** Test the predicted unaffected behavior with a focused execution.

**Tool result:** One passed, zero failed; exit 0; 2848.05 ms.

**Hypotheses after result:** The endpoint is not completely broken.

Evidence run: `46c3f05ec5704dd2a91ac0a008f39017`.

## 13. Measure the broader failure scope

**Observation:** The focused bulk test fails while the normal test passes.

**Current hypotheses:** The defect is localized; unrelated endpoints may remain healthy.

**Evidence needed:** The complete public suite's outcomes.

**Tool selected:** `run_tests(repository="/home/vikas/target-app", timeout=60)`

**Why this tool:** Measure affected behavior after focused evidence establishes a plausible cause.

**Tool result:** 14 collected: 13 passed, one failed, zero setup errors; exit 1; 4423.92 ms.

**Hypotheses after result:** Only test_bulk_order_is_accepted fails. Broad outage and broken test setup are weakened.

Evidence run: `124773cef5944ae7aac818a55bb7177f`.

## 14. Verify comparison inputs

**Observation:** The ordinary test passed, but its input values have not been inspected.

**Current hypotheses:** The passing case uses quantities below the discount threshold.

**Evidence needed:** The public test's request data and assertions.

**Tool selected:** `read_file(repository="/home/vikas/target-app", file_path="tests/test_api.py", start_line=1, end_line=28)`

**Why this tool:** Verify the meaning of the passing comparison rather than relying on its name.

**Tool result:** Default quantity is 2, price 19.99; the test asserts status 201, total 39.98, and successful retrieval.

**Hypotheses after result:** The passing input avoids the discount branch and satisfies the invariant.

Evidence run: `111b2377854b4ca4acafcd9da800adb8`.

## 15. Repeat the observed failure

**Observation:** Calculation, logs, live constraints, and comparison tests support the same explanation.

**Current hypotheses:** The failure should repeat with the same public regression test.

**Evidence needed:** A second focused reproduction through an explicit approved command.

**Tool selected:** `run_reproduction(repository_path="/home/vikas/target-app", reproduction_command=["python","-m","pytest","-q","tests/test_api.py::test_bulk_order_is_accepted"], timeout=60)`

**Why this tool:** Check repeatability using a test discovered during this investigation.

**Tool result:** Expected 201, observed 500; reproduced=true; exit 1; 2703.15 ms. A new request ID was returned.

**Hypotheses after result:** The conditional failure is repeatable in this snapshot. No remediation was attempted.

Evidence run: `2a7275a9a95d43c98b037c24a2c10381`.

## Evidence-backed conclusion

Bulk pricing produces a discounted total, while PostgreSQL requires the undiscounted quantity-times-price relationship.

The observed values establish the contradiction: `10 × 19.99 = 199.90`, but the attempted total is `179.91`.

Logs connect that attempted row, the named constraint, and HTTP 500 through one request ID.

Source and actual database constraints independently support the explanation. Focused and full-suite tests demonstrate conditional behavior.

No bug fix, application modification, Git-history investigation, or arbitrary agent shell was used.

## Limits and tool verification

- The initial runner omitted pytest rootdir; later calls corrected node IDs without changing the application or failure.
- Wall clocks shifted during execution. Request IDs and monotonic durations identify evidence more reliably than timestamps alone.
- This is repeated evidence for the observed inputs, not exhaustive testing of every price and quantity.
- Empty public tables cannot prove rollback: tests use separate schemas and delete them during cleanup.
- TraceRoot verification: 56 passed, including four real Docker/PostgreSQL integration tests.
- Eight write statements were rejected with SQLSTATE 42501, even after disabling transaction-level read-only defaults.
- Source writes and external connections were blocked; timed-out execution containers were removed.
- Target-app's working tree remained clean. Operator cleanup removes the disposable containers and network.

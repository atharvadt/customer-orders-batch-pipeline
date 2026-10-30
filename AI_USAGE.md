# AI Usage Disclosure — YottaFlex Customer & Orders Pipeline

## 1. AI Tools Used

ChatGPT (OpenAI) was used as a development assistant during the implementation of this project.

AI assistance was used for:
- Understanding the project requirements and breaking them into implementation tasks.
- Discussing pipeline architecture and data-quality handling.
- Assisting with Python implementation and code improvements.
- Reviewing validation, duplicate handling and idempotency logic.
- Explaining test failures and debugging issues.
- Preparing benchmark methodology and interpreting measured results.
- Improving technical documentation and setup instructions.

## 2. Where AI Accelerated Development

AI assistance helped accelerate:
- Initial project structure and implementation planning.
- Synthetic CSV data generation with deterministic edge cases.
- Validation and quarantine design.
- SQLite-based run auditing and reconciliation.
- Test-case design and review.
- Benchmark calculations and technical documentation.

Some implementation code was AI-assisted. The project should therefore be understood as AI-assisted development, not as code written entirely without AI.

## 3. Personal Review and Validation

I personally worked through the implementation and local execution process.

My review and validation activities included:

- Setting up the Python virtual environment and dependencies.
- Running the synthetic data generator with different dataset sizes.
- Executing the pipeline against generated CSV files.
- Reviewing customer and order loading results.
- Running the automated test suite and verifying that all seven tests passed.
- Re-running the same inputs to examine idempotency and replay behavior.
- Testing conflicting customer records.
- Testing schema mismatch handling and verifying failed-run audit records.
- Running performance benchmarks with small, medium, large and 100,000-order datasets.
- Checking reconciliation counts, revenue and orphan-order results.
- Reviewing and updating the project documentation.

I used actual local execution results to validate behavior rather than relying only on AI-generated explanations or code.

## 4. Representative Prompt History

The following entries summarize the main prompt themes used during development. They are representative summaries, not a verbatim export of every conversation message.

| Area | Prompt / Request Summary |
|---|---|
| Requirement analysis | Break down the YottaFlex customer and orders batch-pipeline challenge into implementation tasks and acceptance criteria. |
| Architecture | Design a reproducible Python batch pipeline with CSV ingestion, validation, transformations, curated tables and a reject path. |
| Data generation | Create a deterministic synthetic customer/order generator with configurable volumes and deliberate invalid records. |
| Validation | Implement schema validation, business-rule checks, null-key handling, duplicate handling and referential integrity. |
| Idempotency | Review rerun behavior and distinguish exact replays, intra-batch duplicates and conflicting existing records. |
| Observability | Add run IDs, status, timestamps, input/output counts, rejection counts and failure reasons. |
| Testing | Review automated tests for happy paths, empty inputs, malformed rows, null keys, duplicates and schema changes. |
| Reconciliation | Verify source-to-target accounting, revenue totals and orphan-order counts. |
| Performance | Design reproducible benchmarks and calculate throughput from measured execution times. |
| Documentation | Review the README, setup instructions, architecture, limitations and design trade-offs. |

## 5. Important Design and Validation Decisions

AI suggestions were treated as development assistance, not as proof of correctness.

Implementation behavior was checked through local execution, automated tests, repeat runs, conflict scenarios, schema-failure scenarios and reconciliation.

Performance figures in the project documentation come from actual local benchmark outputs.

## 6. Limitations and Accountability

AI assistance contributed to code and documentation development. I reviewed and executed the resulting implementation, but AI-generated code should not be assumed to be error-free.

I am responsible for understanding the submitted solution and explaining its architecture, implementation, assumptions, limitations and test results during the technical walkthrough.


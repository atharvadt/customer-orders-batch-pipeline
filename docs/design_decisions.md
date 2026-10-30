# Design Decisions and Trade-offs

1. **SQLite over a server database:** avoids credentials and external setup; supports primary keys, foreign keys, checks and transactions. PostgreSQL is a production extension.
2. **Integer cents:** avoids binary floating-point errors in currency calculations.
3. **Reject rather than drop:** preserves source filename, row number, raw record, run ID and reason.
4. **Fail-fast schema drift:** unexpected headers are operationally significant and should not be silently ignored.
5. **Insert-ignore idempotency:** safe reruns do not duplicate existing primary keys. Existing values are not overwritten; corrections require an explicit policy.
6. **Deterministic synthetic data:** fixed random seed makes test runs repeatable.
7. **CLI over dashboard:** the assignment evaluates pipeline correctness and evidence; a dashboard is not required and would consume time better spent on tests and reliability.
8. **Current limitation:** input files are loaded into memory. Chunked ingestion and bulk loading are the first optimization for larger datasets.

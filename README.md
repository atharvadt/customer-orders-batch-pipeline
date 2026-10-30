# YottaFlex AI — Customer & Orders Batch Data Pipeline

A reproducible Python batch data pipeline that ingests customer and order CSV files, validates schemas and business rules, transforms records, publishes curated SQLite tables, and quarantines rejected records with complete source traceability.

## 1. Project Overview

This project implements a local batch data engineering workflow for customer and order data.

The pipeline supports:
- CSV ingestion for customers and orders.
- Schema and business-rule validation.
- Data normalization and transformation.
- Primary-key and referential-integrity checks.
- Duplicate, replay and conflicting-record handling.
- Rejected-record quarantine with source traceability.
- Idempotent processing and run auditing.
- Operational metrics and reconciliation.
- Reproducible synthetic data generation.

**Technology stack:** Python, SQLite, CSV, pytest.

## 2. Architecture

```text
 Customer CSV                 Orders CSV
      |                            |
      +-------------+--------------+
                    |
              CSV Ingestion
                    |
             Schema Validation
                    |
          Business Rule Validation
                    |
              Transformation
                    |
             +------+------+
             |             |
       Valid Records   Invalid Records
             |             |
       Curated Tables   Reject Table
             |             |
             +------+------+
                    |
           Run Metrics & Audit
                    |
             Reconciliation
```

SQLite stores the curated customer and order tables, rejected records, and pipeline run history.

## 3. Project Structure

```text
yottaflex_customer_orders_pipeline/
│
├── data/
│   ├── customers.csv
│   ├── orders.csv
│   └── generator_manifest.json
│
├── docs/
│   ├── data_dictionary.md
│   └── design_decisions.md
│
├── outputs/
│   ├── .gitkeep
│   └── demo_execution.txt
│
├── src/
│   ├── __init__.py
│   ├── generate_data.py
│   └── pipeline.py
│
├── tests/
│   └── test_pipeline.py
│
├── .gitignore
├── README.md
└── requirements.txt
```

## 4. Source Data and Relationships

### Customers

Input file: `customers.csv`

| Column | Description |
|---|---|
| customer_id | Unique customer identifier |
| customer_name | Customer name |
| email | Customer email |
| city | Customer city |
| created_at | Customer creation timestamp |

**Grain:** One row per customer.

### Orders

Input file: `orders.csv`

| Column | Description |
|---|---|
| order_id | Unique order identifier |
| customer_id | Customer reference |
| order_date | Order timestamp |
| amount | Order amount |
| status | Order status |

**Grain:** One row per order.

**Relationship:** One customer can have multiple orders. `orders.customer_id` references `customers.customer_id`.

## 5. Business Rules and Data Quality

The pipeline applies the following rules:

- Customer and order primary keys must be non-null.
- Customer email is normalized to lowercase and must be unique.
- Order amount must be numeric, finite and non-negative.
- Monetary values are stored as integer cents to avoid floating-point currency precision errors.
- Order status must be one of `pending`, `paid`, `shipped`, or `cancelled`.
- Order customer references must exist in the curated customer table.
- Timestamps must be ISO-8601 parseable.
- Duplicate keys within a source batch are classified after the first occurrence.
- Exact replays are distinguished from conflicting records.
- Existing target records are not silently overwritten.
- Unexpected schema changes fail explicitly.
- Malformed row-width records are quarantined.

Rejected records retain the entity, source filename, source row number, run ID, raw record and rejection reason.

## 6. Setup and Installation

Requirements:
- Python 3.10 or later.
- pip.

Clone the repository:

```bash
git clone https://github.com/<your-github-username>/<your-repository-name>.git
cd <your-repository-name>
```

Create and activate a virtual environment.

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## 7. Generate Sample Data

Generate the default reproducible sample:

```bash
python -m src.generate_data --customers 100 --orders 500 --seed 42
```

The generator creates:
- `data/customers.csv`
- `data/orders.csv`
- `data/generator_manifest.json`

The generator uses a fixed random seed and deliberately injects labelled edge cases, including invalid references, negative amounts, missing values, null keys, invalid statuses and duplicate orders.

To generate clean data without deliberately injected invalid records, use:

```bash
python -m src.generate_data --customers 100 --orders 500 --seed 42 --clean
```

## 8. Execute the Pipeline

Run with the default input and output paths:

```bash
python -m src.pipeline
```

Run with custom input files and a custom database:

```bash
python -m src.pipeline --customers path/to/customers.csv --orders path/to/orders.csv --db outputs/custom.db --run-id custom-run-001
```

The pipeline prints execution metrics and reconciliation results.

Available options:

| Argument | Purpose |
|---|---|
| `--customers` | Customer CSV input path |
| `--orders` | Order CSV input path |
| `--db` | SQLite database path |
| `--log` | Log file path |
| `--run-id` | Explicit pipeline run identifier |
| `--reconcile` | Run reconciliation against the database |

## 9. Idempotency, Retry and Recovery

The pipeline uses stable primary keys and distinguishes:
- New records.
- Exact replays.
- Intra-batch duplicates.
- Conflicting existing records.

Reprocessing the same input does not create unintended duplicate target records.

Each execution has a unique run ID. Reusing an existing run ID is not permitted.

Failed runs are recorded in pipeline run history with their failure reason. After correcting the input or environment, retry using a new run ID.

Existing target records are not silently overwritten. Historical corrections and backfills should follow an explicit correction policy.

## 10. Observability and Reconciliation

The pipeline records:
- Run ID and execution status.
- Start and end timestamps.
- Customer and order input counts.
- Loaded record counts.
- Rejected record count.
- Duplicate, replay and conflict counts.
- Failure reason where applicable.

The database maintains:
- `customers`
- `orders`
- `rejects`
- `pipeline_runs`

Reconciliation reports:
- Curated customer count.
- Curated order count.
- Rejected record count.
- Total order revenue.
- Orphan order count.

The foreign-key relationship is also enforced in SQLite.

## 11. Automated Testing

Run the automated test suite:

```bash
python -m pytest -v
```

The current test suite contains seven tests covering:
1. Happy path and reconciliation.
2. Deliberate generator edge cases.
3. Idempotent reruns.
4. Empty input batches.
5. Unexpected schema changes.
6. Malformed CSV records.
7. Null customer keys.

**Latest recorded test result:** 7 passed.

## 12. Performance Benchmark

A reproducible larger dataset can be generated using:

```powershell
python -m src.generate_data --customers 10000 --orders 100000 --seed 42 --output-dir data/benchmark
```

Execute it using a separate database:

```powershell
python -m src.pipeline --customers data/benchmark/customers.csv --orders data/benchmark/orders.csv --db outputs/benchmark.db --run-id benchmark-100k
```

### Measured benchmark result

Environment: Windows, Python 3.14.4, SQLite.

| Metric | Result |
|---|---:|
| Customer input rows | 10,000 |
| Order input rows | 100,001 |
| Customers loaded | 9,999 |
| Orders loaded | 99,985 |
| Rejected records | 17 |
| Pipeline duration | 7.758899 seconds |
| Approximate throughput | 14,177 rows/second |
| Orphan orders | 0 |
| Reconciled revenue | 250,223,731.73 |

The order input contains one deliberately injected duplicate event.

Input-to-output reconciliation:

```text
Total input rows       = 110,001
Customers loaded       =   9,999
Orders loaded          =  99,985
Rejected records       =      17
--------------------------------
Total accounted rows   = 110,001
```

These are local benchmark measurements, not production performance guarantees.

### Optimization opportunity

The current implementation prioritizes clarity, validation and transactional correctness. Chunked CSV processing and batched inserts are reasonable next optimizations for larger-than-memory datasets.

## 13. Design Decisions and Trade-offs

- **SQLite:** Selected for zero-service local reproducibility. PostgreSQL would be a natural production upgrade.
- **Python standard library:** Keeps ingestion and processing dependencies minimal.
- **Integer cents:** Avoids floating-point currency precision issues.
- **Explicit quarantine:** Preserves invalid records for investigation instead of silently discarding them.
- **Conservative conflict handling:** Existing records are not overwritten without an explicit correction policy.
- **Fail-fast schema validation:** Prevents unexpected source schema changes from silently corrupting data.
- **Synthetic data:** Makes testing reproducible without exposing real customer information.

## 14. Known Limitations and Future Improvements

- The implementation is a local batch pipeline, not a streaming system.
- CSV processing currently uses an in-memory approach; chunking is a future scaling improvement.
- SQLite is intended for local execution and demonstration.
- Full change-data history and slowly changing dimensions are not implemented because source update semantics are not defined.
- Production deployment could introduce PostgreSQL, orchestration, monitoring and cloud object storage.

## 15. AI Usage and Transparency

LLM tools were used as development assistance during project implementation, debugging, documentation and test review.

A separate `AI_USAGE.md` file documents the nature of this assistance, relevant prompt history, personal review and validation activities.

The final implementation was locally executed and tested. Benchmark measurements and reconciliation results were verified through actual pipeline runs.

## 16. Documentation

Additional project documentation:

- `docs/data_dictionary.md` — field definitions and data characteristics.
- `docs/design_decisions.md` — architecture choices and trade-offs.
- `AI_USAGE.md` — AI assistance disclosure and prompt history.

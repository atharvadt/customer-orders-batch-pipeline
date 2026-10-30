# Data Dictionary

## Source entity: customers
**Grain:** one record per customer.
| Field | Type | Nullable | Rule |
|---|---|---:|---|
| customer_id | string | No | Primary key; stable source identifier |
| customer_name | string | No | Must not be blank |
| email | string | No | Lowercased; unique; basic email shape check |
| city | string | Yes | Optional descriptive attribute |
| created_at | ISO-8601 string | No | Must parse as timestamp |

## Source entity: orders
**Grain:** one record per order.
| Field | Type | Nullable | Rule |
|---|---|---:|---|
| order_id | string | No | Primary key; stable source identifier |
| customer_id | string | No | Foreign key to customers |
| order_date | ISO-8601 string | No | Must parse as timestamp |
| amount | decimal | No | Must be numeric and >= 0 |
| status | string | No | pending, paid, shipped, cancelled |

## Target tables
- `customers`: curated customer entity; primary key `customer_id`.
- `orders`: curated order fact; primary key `order_id`, FK `customer_id`; `amount` is stored as `amount_cents` integer.
- `rejects`: one row per rejected source row per run; retains raw JSON, source file, row number and reason.
- `pipeline_runs`: one operational record per run ID.

## Derived fields
- `amount_cents`: decimal amount multiplied by 100 and rounded to the nearest cent.
- `record_hash`: SHA-256 of normalized order payload, useful for audit/comparison.
- `reject_id`: deterministic SHA-256 of run ID, entity, source file and source row number.

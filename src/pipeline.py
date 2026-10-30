"""Batch ingestion, validation, transformation, quarantine and SQLite publishing."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

CUSTOMER_FIELDS = ["customer_id", "customer_name", "email", "city", "created_at"]
ORDER_FIELDS = ["order_id", "customer_id", "order_date", "amount", "status"]
VALID_STATUSES = {"pending", "paid", "shipped", "cancelled"}

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def stable_id(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()

def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )

def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS customers (
        customer_id TEXT PRIMARY KEY,
        customer_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        city TEXT,
        created_at TEXT NOT NULL,
        source_file TEXT NOT NULL,
        run_id TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL REFERENCES customers(customer_id),
        order_date TEXT NOT NULL,
        amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
        status TEXT NOT NULL CHECK(status IN ('pending','paid','shipped','cancelled')),
        source_file TEXT NOT NULL,
        run_id TEXT NOT NULL,
        record_hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS rejects (
        reject_id TEXT PRIMARY KEY,
        entity_name TEXT NOT NULL,
        source_file TEXT NOT NULL,
        source_row_number INTEGER NOT NULL,
        run_id TEXT NOT NULL,
        raw_record TEXT NOT NULL,
        rejection_reason TEXT NOT NULL,
        rejected_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        run_id TEXT PRIMARY KEY,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        status TEXT NOT NULL,
        customer_input_count INTEGER NOT NULL DEFAULT 0,
        order_input_count INTEGER NOT NULL DEFAULT 0,
        customers_loaded INTEGER NOT NULL DEFAULT 0,
        orders_loaded INTEGER NOT NULL DEFAULT 0,
        rejected_count INTEGER NOT NULL DEFAULT 0,
        duplicate_count INTEGER NOT NULL DEFAULT 0,
        replayed_count INTEGER NOT NULL DEFAULT 0,
        intra_batch_duplicate_count INTEGER NOT NULL DEFAULT 0,
        conflicting_record_count INTEGER NOT NULL DEFAULT 0,
        failure_reason TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
    CREATE INDEX IF NOT EXISTS idx_orders_order_date ON orders(order_date);
    CREATE INDEX IF NOT EXISTS idx_rejects_run_id ON rejects(run_id);
    """)
    # CREATE TABLE IF NOT EXISTS does not add columns to an existing database.
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs)")}
    for column in ("replayed_count", "intra_batch_duplicate_count", "conflicting_record_count"):
        if column not in existing_columns:
            conn.execute(
                f"ALTER TABLE pipeline_runs ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
            )

def read_csv(path: Path, expected_fields: list[str], entity: str):
    """Return (records, structural rejects, header error). Preserve malformed rows."""
    if not path.exists():
        raise FileNotFoundError(path)
    records, rejects = [], []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return [], [], f"{entity}: empty file or missing header"
        missing = sorted(set(expected_fields) - set(reader.fieldnames))
        unexpected = sorted(set(reader.fieldnames) - set(expected_fields))
        if missing or unexpected:
            return [], [], f"{entity}: schema mismatch; missing={missing}; unexpected={unexpected}"
        for row_num, row in enumerate(reader, start=2):
            raw = dict(row)
            # DictReader stores extra fields under key None; missing cells become None.
            if None in raw or any(v is None for k, v in raw.items() if k is not None):
                rejects.append((row_num, raw, "malformed_row: column count does not match header"))
                continue
            records.append((row_num, {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}))
    return records, rejects, None

def validate_customer(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    cid = row.get("customer_id", "")
    name = row.get("customer_name", "")
    email = row.get("email", "").lower()
    created = row.get("created_at", "")
    if not cid: return None, "missing_required_field: customer_id"
    if not name: return None, "missing_required_field: customer_name"
    if not email: return None, "missing_required_field: email"
    if "@" not in email or "." not in email.split("@")[-1]: return None, "invalid_email"
    if not created: return None, "missing_required_field: created_at"
    try: datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError: return None, "invalid_created_at"
    return {"customer_id": cid, "customer_name": name, "email": email,
            "city": row.get("city") or None, "created_at": created}, None

def validate_order(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    oid, cid = row.get("order_id", ""), row.get("customer_id", "")
    date, amount, status = row.get("order_date", ""), row.get("amount", ""), row.get("status", "").lower()
    if not oid: return None, "missing_required_field: order_id"
    if not cid: return None, "missing_required_field: customer_id"
    if not date: return None, "missing_required_field: order_date"
    try: datetime.fromisoformat(date.replace("Z", "+00:00"))
    except ValueError: return None, "invalid_order_date"
    if amount == "": return None, "missing_required_field: amount"
    try:
        decimal_amount = Decimal(amount)
        if not decimal_amount.is_finite(): return None, "invalid_amount"
        if decimal_amount < 0: return None, "negative_amount"
        cents = int((decimal_amount * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None, "invalid_amount"
    if status not in VALID_STATUSES: return None, "invalid_status"
    return {"order_id": oid, "customer_id": cid, "order_date": date,
            "amount_cents": cents, "status": status}, None

def add_reject(conn, entity, source, row_num, run_id, raw, reason):
    reject_id = stable_id("reject", f"{run_id}:{entity}:{source}:{row_num}")
    conn.execute("""INSERT OR IGNORE INTO rejects
        (reject_id,entity_name,source_file,source_row_number,run_id,raw_record,rejection_reason,rejected_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (reject_id, entity, source, row_num, run_id, json.dumps(raw, sort_keys=True), reason, utc_now()))

def run_pipeline(customers_csv: str | Path, orders_csv: str | Path,
                 db_path: str | Path, log_path: str | Path | None = None,
                 run_id: str | None = None) -> dict[str, Any]:
    started_clock = time.perf_counter()
    run_id = run_id or str(uuid.uuid4())
    customer_path, order_path, database = Path(customers_csv), Path(orders_csv), Path(db_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    if log_path:
        configure_logging(Path(log_path))
    logger = logging.getLogger("yottaflex")
    started_at = utc_now()
    metrics = {"run_id": run_id, "status": "failed", "customer_input_count": 0,
               "order_input_count": 0, "customers_loaded": 0, "orders_loaded": 0,
               "rejected_count": 0, "duplicate_count": 0, "replayed_count": 0,
               "intra_batch_duplicate_count": 0, "conflicting_record_count": 0}
    conn = sqlite3.connect(database)
    run_registered = False
    try:
        init_db(conn)

        # A run ID is an immutable audit identifier. Never replace an earlier run.
        existing_run = conn.execute(
            "SELECT 1 FROM pipeline_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if existing_run:
            raise ValueError(f"run_id already exists: {run_id}")
        conn.execute(
            "INSERT INTO pipeline_runs (run_id,started_at,status) VALUES (?,?,?)",
            (run_id, started_at, "running")
        )
        conn.commit()
        run_registered = True

        customers, customer_structural, customer_schema_error = read_csv(
            customer_path, CUSTOMER_FIELDS, "customers"
        )
        orders, order_structural, order_schema_error = read_csv(
            order_path, ORDER_FIELDS, "orders"
        )
        if customer_schema_error or order_schema_error:
            raise ValueError("; ".join(
                x for x in [customer_schema_error, order_schema_error] if x
            ))
        metrics["customer_input_count"] = len(customers) + len(customer_structural)
        metrics["order_input_count"] = len(orders) + len(order_structural)

        with conn:
            for row_num, raw, reason in customer_structural:
                add_reject(conn, "customer", customer_path.name, row_num, run_id, raw, reason)
                metrics["rejected_count"] += 1

            valid_customers = {}
            seen_customer_ids = set()
            seen_emails = set()
            for row_num, raw in customers:
                clean, reason = validate_customer(raw)
                if reason is None and clean["customer_id"] in seen_customer_ids:
                    reason = "duplicate_key: customer_id within input batch"
                    metrics["intra_batch_duplicate_count"] += 1
                if reason is None and clean["email"] in seen_emails:
                    reason = "duplicate_key: email within input batch"
                    metrics["intra_batch_duplicate_count"] += 1
                if reason:
                    add_reject(conn, "customer", customer_path.name, row_num, run_id, raw, reason)
                    metrics["rejected_count"] += 1
                    continue
                seen_customer_ids.add(clean["customer_id"])
                seen_emails.add(clean["email"])
                valid_customers[clean["customer_id"]] = (row_num, clean)

            # Insert new customers, count exact existing records as replays,
            # and quarantine key/email collisions whose contents differ.
            for row_num, clean in valid_customers.values():
                existing = conn.execute(
                    """SELECT customer_name,email,city,created_at
                       FROM customers WHERE customer_id=?""",
                    (clean["customer_id"],)
                ).fetchone()
                if existing:
                    existing_values = tuple(existing)
                    incoming_values = (
                        clean["customer_name"], clean["email"], clean["city"], clean["created_at"]
                    )
                    if existing_values == incoming_values:
                        metrics["replayed_count"] += 1
                    else:
                        add_reject(conn, "customer", customer_path.name, row_num, run_id,
                                   clean, "conflicting_record: customer_id exists with different data")
                        metrics["rejected_count"] += 1
                        metrics["conflicting_record_count"] += 1
                    continue

                email_owner = conn.execute(
                    "SELECT customer_id FROM customers WHERE email=?", (clean["email"],)
                ).fetchone()
                if email_owner:
                    add_reject(conn, "customer", customer_path.name, row_num, run_id,
                               clean, "conflicting_record: email already belongs to another customer_id")
                    metrics["rejected_count"] += 1
                    metrics["conflicting_record_count"] += 1
                    continue

                conn.execute(
                    """INSERT INTO customers
                       (customer_id,customer_name,email,city,created_at,source_file,run_id)
                       VALUES (?,?,?,?,?,?,?)""",
                    (clean["customer_id"], clean["customer_name"], clean["email"], clean["city"],
                     clean["created_at"], customer_path.name, run_id)
                )
                metrics["customers_loaded"] += 1

            for row_num, raw, reason in order_structural:
                add_reject(conn, "order", order_path.name, row_num, run_id, raw, reason)
                metrics["rejected_count"] += 1

            seen_order_ids = set()
            for row_num, raw in orders:
                clean, reason = validate_order(raw)
                if reason is None and clean["order_id"] in seen_order_ids:
                    reason = "duplicate_key: order_id within input batch"
                    metrics["intra_batch_duplicate_count"] += 1
                if reason is None:
                    exists = conn.execute(
                        "SELECT 1 FROM customers WHERE customer_id=?", (clean["customer_id"],)
                    ).fetchone()
                    if not exists:
                        reason = "invalid_reference: customer_id not found"
                if reason:
                    add_reject(conn, "order", order_path.name, row_num, run_id, raw, reason)
                    metrics["rejected_count"] += 1
                    continue

                seen_order_ids.add(clean["order_id"])
                record_hash = stable_id("order", json.dumps(clean, sort_keys=True))
                existing_order = conn.execute(
                    "SELECT record_hash FROM orders WHERE order_id=?", (clean["order_id"],)
                ).fetchone()
                if existing_order:
                    if existing_order[0] == record_hash:
                        metrics["replayed_count"] += 1
                    else:
                        add_reject(conn, "order", order_path.name, row_num, run_id,
                                   raw, "conflicting_record: order_id exists with different data")
                        metrics["rejected_count"] += 1
                        metrics["conflicting_record_count"] += 1
                    continue

                conn.execute(
                    """INSERT INTO orders
                       (order_id,customer_id,order_date,amount_cents,status,source_file,run_id,record_hash)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (clean["order_id"], clean["customer_id"], clean["order_date"], clean["amount_cents"],
                     clean["status"], order_path.name, run_id, record_hash)
                )
                metrics["orders_loaded"] += 1

        metrics["duplicate_count"] = (
            metrics["intra_batch_duplicate_count"] + metrics["conflicting_record_count"]
        )
        metrics["status"] = "success"
        logger.info("run_id=%s status=success metrics=%s", run_id, metrics)
    except Exception as exc:
        metrics["failure_reason"] = f"{type(exc).__name__}: {exc}"
        logger.exception("run_id=%s failed: %s", run_id, exc)
        raise
    finally:
        ended_at = utc_now()
        metrics["duration_seconds"] = round(time.perf_counter() - started_clock, 6)
        try:
            if run_registered:
                with conn:
                    conn.execute(
                        """UPDATE pipeline_runs SET ended_at=?,status=?,
                           customer_input_count=?,order_input_count=?,customers_loaded=?,orders_loaded=?,
                           rejected_count=?,duplicate_count=?,replayed_count=?,
                           intra_batch_duplicate_count=?,conflicting_record_count=?,failure_reason=?
                           WHERE run_id=?""",
                        (ended_at, metrics["status"], metrics["customer_input_count"],
                         metrics["order_input_count"], metrics["customers_loaded"],
                         metrics["orders_loaded"], metrics["rejected_count"],
                         metrics["duplicate_count"], metrics["replayed_count"],
                         metrics["intra_batch_duplicate_count"],
                         metrics["conflicting_record_count"], metrics.get("failure_reason"), run_id)
                    )
        finally:
            conn.close()
    return metrics

def reconcile(db_path: str | Path) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        orders, revenue = conn.execute("SELECT COUNT(*), COALESCE(SUM(amount_cents),0) FROM orders").fetchone()
        rejects = conn.execute("SELECT COUNT(*) FROM rejects").fetchone()[0]
        orphan_orders = conn.execute("""SELECT COUNT(*) FROM orders o
            LEFT JOIN customers c ON o.customer_id=c.customer_id WHERE c.customer_id IS NULL""").fetchone()[0]
        return {"customers": customers, "orders": orders, "rejected_records": rejects,
                "order_revenue": f"{revenue / 100:.2f}", "orphan_orders": orphan_orders}
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="YottaFlex customer/orders batch pipeline")
    parser.add_argument("--customers", default="data/customers.csv")
    parser.add_argument("--orders", default="data/orders.csv")
    parser.add_argument("--db", default="outputs/yottaflex.db")
    parser.add_argument("--log", default="outputs/pipeline.log")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--reconcile", action="store_true")
    args = parser.parse_args()
    if args.reconcile:
        print(json.dumps(reconcile(args.db), indent=2))
        return
    result = run_pipeline(args.customers, args.orders, args.db, args.log, args.run_id)
    print(json.dumps(result, indent=2))
    print("Reconciliation:")
    print(json.dumps(reconcile(args.db), indent=2))

if __name__ == "__main__":
    main()

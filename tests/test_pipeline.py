import csv
import sqlite3
from pathlib import Path
import pytest
from src.generate_data import generate
from src.pipeline import run_pipeline, reconcile

def test_happy_path_and_reconciliation(tmp_path):
    c, o = generate(tmp_path, customers=10, orders=30, include_edge_cases=False)
    result = run_pipeline(c, o, tmp_path/"test.db", run_id="run-happy")
    assert result["status"] == "success"
    assert result["customers_loaded"] == 10
    assert result["orders_loaded"] == 30
    assert reconcile(tmp_path/"test.db")["orphan_orders"] == 0

def test_generator_edge_cases_are_quarantined(tmp_path):
    c, o = generate(tmp_path, customers=10, orders=30, include_edge_cases=True)
    result = run_pipeline(c, o, tmp_path/"test.db", run_id="run-edge")
    assert result["status"] == "success"
    assert result["rejected_count"] >= 5
    conn = sqlite3.connect(tmp_path/"test.db")
    reasons = {r[0] for r in conn.execute("SELECT rejection_reason FROM rejects")}
    conn.close()
    assert "negative_amount" in reasons
    assert "invalid_reference: customer_id not found" in reasons

def test_idempotent_rerun(tmp_path):
    c, o = generate(tmp_path, customers=10, orders=30, include_edge_cases=False)
    db = tmp_path/"test.db"
    first = run_pipeline(c, o, db, run_id="run-1")
    second = run_pipeline(c, o, db, run_id="run-2")
    assert first["orders_loaded"] == 30
    assert second["orders_loaded"] == 0
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 30
    conn.close()

def test_empty_batch(tmp_path):
    c, o = generate(tmp_path, customers=2, orders=0, include_edge_cases=False)
    result = run_pipeline(c, o, tmp_path/"test.db", run_id="run-empty")
    assert result["status"] == "success"
    assert result["orders_loaded"] == 0

def test_schema_change_fails_explicitly(tmp_path):
    c, o = generate(tmp_path, customers=2, orders=2, include_edge_cases=False)
    rows = list(csv.DictReader(o.open()))
    with o.open("w", newline="", encoding="utf-8") as f:
        fields = ["order_id", "customer_id", "order_date", "amount", "status", "unexpected"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            row["unexpected"] = "extra"
            writer.writerow(row)
    with pytest.raises(ValueError, match="schema mismatch"):
        run_pipeline(c, o, tmp_path/"test.db", run_id="run-schema")

def test_malformed_row_is_rejected(tmp_path):
    c, o = generate(tmp_path, customers=2, orders=2, include_edge_cases=False)
    with o.open("a", encoding="utf-8") as f:
        f.write("O999,C000001,2025-01-01,10.00\n")
    result = run_pipeline(c, o, tmp_path/"test.db", run_id="run-malformed")
    assert result["rejected_count"] == 1

def test_null_customer_key_is_rejected(tmp_path):
    c, o = generate(tmp_path, customers=3, orders=3, include_edge_cases=False)
    rows = list(csv.DictReader(c.open()))
    rows[0]["customer_id"] = ""
    with c.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    result = run_pipeline(c, o, tmp_path/"test.db", run_id="run-null")
    assert result["rejected_count"] >= 1

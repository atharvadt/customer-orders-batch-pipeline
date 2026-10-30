"""Generate deterministic synthetic customer and order CSV files."""
from __future__ import annotations
import argparse
import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

CUSTOMER_FIELDS = ["customer_id", "customer_name", "email", "city", "created_at"]
ORDER_FIELDS = ["order_id", "customer_id", "order_date", "amount", "status"]

def generate(output_dir: str | Path, customers: int = 1000, orders: int = 5000,
             seed: int = 42, include_edge_cases: bool = True) -> tuple[Path, Path]:
    if customers < 1 or orders < 0:
        raise ValueError("customers must be >= 1 and orders must be >= 0")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    cities = ["Pune", "Mumbai", "Bengaluru", "Delhi", "Hyderabad"]
    statuses = ["pending", "paid", "shipped", "cancelled"]
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)

    customer_rows = []
    for i in range(1, customers + 1):
        customer_rows.append({
            "customer_id": f"C{i:06d}",
            "customer_name": f"Customer {i}",
            "email": f"customer{i}@example.test",
            "city": rng.choice(cities),
            "created_at": (start + timedelta(days=rng.randrange(365))).isoformat().replace("+00:00", "Z"),
        })

    order_rows = []
    for i in range(1, orders + 1):
        customer = rng.choice(customer_rows)
        order_rows.append({
            "order_id": f"O{i:07d}",
            "customer_id": customer["customer_id"],
            "order_date": (start + timedelta(days=rng.randrange(450))).isoformat().replace("+00:00", "Z"),
            "amount": f"{rng.uniform(1, 5000):.2f}",
            "status": rng.choice(statuses),
        })

    if include_edge_cases and customers >= 2 and orders >= 6:
        # Deliberate invalid/edge rows; generator labels are kept in a separate file.
        order_rows[0]["amount"] = "-10.00"                 # negative amount
        order_rows[1]["customer_id"] = "C999999"           # invalid reference
        order_rows[2]["order_id"] = ""                     # null key
        order_rows[3]["status"] = "unknown_status"         # invalid domain value
        order_rows[4]["amount"] = ""                       # missing amount
        order_rows[5] = dict(order_rows[5])                # duplicate key introduced below
        order_rows.append(dict(order_rows[5]))             # exact duplicate event
        # Customer null key
        customer_rows[-1]["customer_id"] = ""

    customer_path = out / "customers.csv"
    order_path = out / "orders.csv"
    with customer_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CUSTOMER_FIELDS)
        writer.writeheader()
        writer.writerows(customer_rows)
    with order_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ORDER_FIELDS)
        writer.writeheader()
        writer.writerows(order_rows)

    labels = {
        "seed": seed,
        "customers_requested": customers,
        "orders_requested": orders,
        "intentional_cases": [
            "negative order amount", "unknown customer reference", "null order_id",
            "invalid order status", "missing order amount", "exact duplicate order",
            "null customer_id"
        ] if include_edge_cases and customers >= 2 and orders >= 6 else []
    }
    (out / "generator_manifest.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")
    return customer_path, order_path

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic YottaFlex customer/order CSVs")
    parser.add_argument("--output-dir", default="data")
    parser.add_argument("--customers", type=int, default=100)
    parser.add_argument("--orders", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--clean", action="store_true", help="Do not inject deliberate invalid records")
    args = parser.parse_args()
    c, o = generate(args.output_dir, args.customers, args.orders, args.seed, not args.clean)
    print(f"Generated {c} and {o}")

if __name__ == "__main__":
    main()

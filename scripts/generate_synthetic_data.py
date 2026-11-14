"""Generate reproducible synthetic QuoteFlow scenarios."""

from copy import deepcopy
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "synthetic" / "scenarios.json"

SPECS = [
    ("001", "Matching documents", "match",
     "VALIDATED", [], 200),
    ("002", "Higher laptop price", "price",
     "APPROVAL_PENDING", ["PRICE_MISMATCH:LAPTOP-001"], 200),
    ("003", "Different monitor quantity", "quantity",
     "APPROVAL_PENDING", ["QUANTITY_MISMATCH:MONITOR-001"], 200),
    ("004", "Missing monitor", "missing",
     "APPROVAL_PENDING", ["MISSING_ITEM:MONITOR-001"], 200),
    ("005", "Unexpected docking station", "unexpected",
     "APPROVAL_PENDING", ["UNEXPECTED_ITEM:DOCK-001"], 200),
    ("006", "Supplier mismatch", "supplier",
     "APPROVAL_PENDING", ["SUPPLIER_MISMATCH"], 200),
    ("007", "Currency mismatch", "currency",
     "APPROVAL_PENDING", ["CURRENCY_MISMATCH"], 200),
    ("008", "Invalid quantity", "invalid_quantity",
     None, [], 422),
    ("009", "Duplicate SKU", "duplicate_sku",
     None, [], 422),
]


def make_payload(number):
    items = [
        {"sku": "LAPTOP-001", "quantity": 5,
         "unit_price": "800.00"},
        {"sku": "MONITOR-001", "quantity": 10,
         "unit_price": "200.00"},
    ]

    return {
        "purchase_order": {
            "document_id": f"PO-SYN-{number}",
            "supplier": "TechSupply Argentina",
            "currency": "USD",
            "items": deepcopy(items),
        },
        "quote": {
            "document_id": f"QT-SYN-{number}",
            "supplier": "TechSupply Argentina",
            "currency": "USD",
            "items": deepcopy(items),
        },
    }


def make_scenario(spec):
    number, description, variant, state, issues, http_status = spec
    payload = make_payload(number)
    quote = payload["quote"]
    items = quote["items"]

    if variant == "price":
        items[0]["unit_price"] = "850.00"
    elif variant == "quantity":
        items[1]["quantity"] = 9
    elif variant == "missing":
        items.pop(1)
    elif variant == "unexpected":
        items.append({
            "sku": "DOCK-001",
            "quantity": 2,
            "unit_price": "150.00",
        })
    elif variant == "supplier":
        quote["supplier"] = "Alternative Supplier"
    elif variant == "currency":
        quote["currency"] = "EUR"
    elif variant == "invalid_quantity":
        items[0]["quantity"] = 0
    elif variant == "duplicate_sku":
        items.append(deepcopy(items[0]))

    return {
        "request_id": f"QF-SYN-{number}",
        "description": description,
        "expected_http_status": http_status,
        "expected_state": state,
        "expected_issues": issues,
        "payload": payload,
    }


def main():
    scenarios = [make_scenario(spec) for spec in SPECS]

    ids = [item["request_id"] for item in scenarios]
    assert len(ids) == len(set(ids)), "Duplicate scenario IDs"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(scenarios, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Dataset created: {OUTPUT}")
    print(f"Total scenarios: {len(scenarios)}")
    print("Expected HTTP 200:", sum(
        x["expected_http_status"] == 200 for x in scenarios
    ))
    print("Expected HTTP 422:", sum(
        x["expected_http_status"] == 422 for x in scenarios
    ))


if __name__ == "__main__":
    main()
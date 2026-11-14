import sqlite3

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def example():
    item = {
        "sku": "LAPTOP-01",
        "quantity": 2,
        "unit_price": "800.00"
    }

    return {
        "purchase_order": {
            "document_id": "PO-001",
            "supplier": "Tech Supplier",
            "currency": "USD",
            "items": [item.copy()]
        },
        "quote": {
            "document_id": "Q-001",
            "supplier": "Tech Supplier",
            "currency": "USD",
            "items": [item.copy()]
        }
    }


def test_idempotency(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setenv("QUOTEFLOW_DB_PATH", str(db))

    headers = {"X-Request-ID": "REQ-001"}

    first = client.post(
        "/requests", json=example(), headers=headers
    )
    second = client.post(
        "/requests", json=example(), headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["state"] == "VALIDATED"

    retrieved = client.get("/requests/REQ-001")
    assert retrieved.json() == first.json()

    with sqlite3.connect(db) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM requests"
        ).fetchone()[0]

        events = conn.execute(
            "SELECT COUNT(*) FROM audit_events"
        ).fetchone()[0]

    assert count == 1
    assert events == 1


def test_conflicting_duplicate(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "QUOTEFLOW_DB_PATH", str(tmp_path / "test.db")
    )

    headers = {"X-Request-ID": "REQ-002"}

    first = client.post(
        "/requests", json=example(), headers=headers
    )
    assert first.status_code == 200

    changed = example()
    changed["quote"]["items"][0]["unit_price"] = "900.00"

    response = client.post(
        "/requests", json=changed, headers=headers
    )

    assert response.status_code == 409


def test_discrepancy_requires_approval(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "QUOTEFLOW_DB_PATH", str(tmp_path / "test.db")
    )

    body = example()
    body["quote"]["items"][0]["quantity"] = 3

    response = client.post(
        "/requests",
        json=body,
        headers={"X-Request-ID": "REQ-003"}
    )

    assert response.status_code == 200
    assert response.json()["state"] == "APPROVAL_PENDING"
    assert "QUANTITY_MISMATCH:LAPTOP-01" in (
        response.json()["comparison"]["issues"]
    )


def test_unknown_request(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "QUOTEFLOW_DB_PATH", str(tmp_path / "test.db")
    )

    response = client.get("/requests/UNKNOWN")
    assert response.status_code == 404
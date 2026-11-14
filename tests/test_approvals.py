import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def environment(tmp_path, monkeypatch):
    db = tmp_path / "approvals.db"
    monkeypatch.setenv("QUOTEFLOW_DB_PATH", str(db))
    monkeypatch.setenv(
        "QUOTEFLOW_APPROVAL_TOKEN", "test-only-secret"
    )
    return db


def example(price="900.00"):
    return {
        "purchase_order": {
            "document_id": "PO-001",
            "supplier": "Supplier",
            "currency": "USD",
            "items": [{
                "sku": "ITEM-1",
                "quantity": 2,
                "unit_price": "800.00"
            }]
        },
        "quote": {
            "document_id": "Q-001",
            "supplier": "Supplier",
            "currency": "USD",
            "items": [{
                "sku": "ITEM-1",
                "quantity": 2,
                "unit_price": price
            }]
        }
    }


def create_pending():
    response = client.post(
        "/requests",
        json=example(),
        headers={"X-Request-ID": "REQ-APPROVAL"}
    )
    assert response.status_code == 200
    assert response.json()["state"] == "APPROVAL_PENDING"


def decide(decision, token="test-only-secret"):
    return client.post(
        "/requests/REQ-APPROVAL/decision",
        json={
            "decision": decision,
            "actor": "Reviewer"
        },
        headers={"X-Approval-Token": token}
    )


def test_approval_and_repeated_callback(environment):
    create_pending()

    first = decide("APPROVED")
    second = decide("APPROVED")

    assert first.status_code == 200
    assert first.json()["state"] == "APPROVED"
    assert first.json()["replayed"] is False

    assert second.status_code == 200
    assert second.json()["replayed"] is True

    stored = client.get("/requests/REQ-APPROVAL")
    assert stored.json()["state"] == "APPROVED"

    with sqlite3.connect(environment) as conn:
        events = conn.execute(
            "SELECT COUNT(*) FROM audit_events"
        ).fetchone()[0]

    assert events == 2


def test_rejection_is_final(environment):
    create_pending()

    rejected = decide("REJECTED")
    assert rejected.status_code == 200
    assert rejected.json()["state"] == "REJECTED"

    attempt = decide("APPROVED")
    assert attempt.status_code == 409

    stored = client.get("/requests/REQ-APPROVAL")
    assert stored.json()["state"] == "REJECTED"


def test_invalid_token(environment):
    create_pending()

    response = decide("APPROVED", "wrong-token")
    assert response.status_code == 401

    stored = client.get("/requests/REQ-APPROVAL")
    assert stored.json()["state"] == "APPROVAL_PENDING"


def test_undisputed_request_cannot_be_manually_approved(environment):
    response = client.post(
        "/requests",
        json=example("800.00"),
        headers={"X-Request-ID": "REQ-APPROVAL"}
    )

    assert response.json()["state"] == "VALIDATED"

    attempt = decide("APPROVED")
    assert attempt.status_code == 409


def test_invalid_decision(environment):
    create_pending()

    response = decide("CANCELLED")
    assert response.status_code == 422


def test_unknown_request(environment):
    response = decide("APPROVED")
    assert response.status_code == 404
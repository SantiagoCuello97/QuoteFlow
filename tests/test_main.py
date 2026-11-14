from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def sample_request():
    item = {
        "sku": "LAPTOP-01",
        "quantity": 2,
        "unit_price": "800.00",
    }
    return {
        "purchase_order": {
            "document_id": "PO-001",
            "supplier": "Tech Supplier",
            "currency": "USD",
            "items": [item.copy()],
        },
        "quote": {
            "document_id": "Q-001",
            "supplier": "Tech Supplier",
            "currency": "USD",
            "items": [item.copy()],
        },
    }


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_matching_documents():
    response = client.post("/compare", json=sample_request())
    assert response.status_code == 200
    assert response.json()["status"] == "MATCH"
    assert response.json()["issues"] == []
    assert response.json()["quote_total"] == "1600.00"


def test_price_discrepancy():
    data = sample_request()
    data["quote"]["items"][0]["unit_price"] = "900.00"

    response = client.post("/compare", json=data)

    assert response.status_code == 200
    assert response.json()["status"] == "REVIEW_REQUIRED"
    assert "PRICE_MISMATCH:LAPTOP-01" in response.json()["issues"]


def test_invalid_quantity():
    data = sample_request()
    data["quote"]["items"][0]["quantity"] = -1

    response = client.post("/compare", json=data)
    assert response.status_code == 422
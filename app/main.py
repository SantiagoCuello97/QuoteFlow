from decimal import Decimal

from fastapi import FastAPI
from pydantic import BaseModel, Field, model_validator

app = FastAPI(title="QuoteFlow API", version="0.1.0")


class Item(BaseModel):
    sku: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0)


class Document(BaseModel):
    document_id: str = Field(min_length=1)
    supplier: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")
    items: list[Item] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_items(self):
        skus = [item.sku for item in self.items]
        if len(skus) != len(set(skus)):
            raise ValueError("Duplicate SKUs are not allowed")
        return self


class ComparisonRequest(BaseModel):
    purchase_order: Document
    quote: Document


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/compare")
def compare(request: ComparisonRequest):
    order = request.purchase_order
    quote = request.quote
    issues = []

    if order.supplier.casefold() != quote.supplier.casefold():
        issues.append("SUPPLIER_MISMATCH")

    if order.currency.upper() != quote.currency.upper():
        issues.append("CURRENCY_MISMATCH")

    order_items = {item.sku: item for item in order.items}
    quote_items = {item.sku: item for item in quote.items}

    for sku in sorted(set(order_items) | set(quote_items)):
        if sku not in order_items:
            issues.append(f"UNEXPECTED_ITEM:{sku}")
        elif sku not in quote_items:
            issues.append(f"MISSING_ITEM:{sku}")
        else:
            expected = order_items[sku]
            actual = quote_items[sku]

            if expected.quantity != actual.quantity:
                issues.append(f"QUANTITY_MISMATCH:{sku}")

            if expected.unit_price != actual.unit_price:
                issues.append(f"PRICE_MISMATCH:{sku}")

    order_total = sum(
        (i.quantity * i.unit_price for i in order.items),
        Decimal("0"),
    )
    quote_total = sum(
        (i.quantity * i.unit_price for i in quote.items),
        Decimal("0"),
    )

    return {
        "status": "MATCH" if not issues else "REVIEW_REQUIRED",
        "issues": issues,
        "purchase_order_total": str(order_total),
        "quote_total": str(quote_total),
    }

# --- Persistent request endpoints ---
from fastapi import Header, HTTPException
from app.storage import get_request, save_request


@app.post("/requests")
def create_request(
    request: ComparisonRequest,
    request_id: str = Header(alias="X-Request-ID")
):
    if not request_id.strip() or len(request_id) > 128:
        raise HTTPException(422, "Invalid X-Request-ID")

    try:
        return save_request(
            request_id,
            request.model_dump(mode="json"),
            compare(request)
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/requests/{request_id}")
def read_request(request_id: str):
    stored = get_request(request_id)

    if stored is None:
        raise HTTPException(404, "Request not found")

    return stored

# --- Approval workflow ---
import os
import secrets
from typing import Literal

from app.approvals import apply_decision, DecisionConflict


class ApprovalCommand(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    actor: str = Field(min_length=1, max_length=80)


@app.post("/requests/{request_id}/decision")
def decide_request(
    request_id: str,
    command: ApprovalCommand,
    approval_token: str | None = Header(
        default=None, alias="X-Approval-Token"
    ),
):
    configured_token = os.environ.get("QUOTEFLOW_APPROVAL_TOKEN")

    if not configured_token:
        raise HTTPException(
            status_code=503,
            detail="Approval token not configured"
        )

    if not approval_token or not secrets.compare_digest(
        approval_token, configured_token
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized"
        )

    actor = command.actor.strip()

    if not actor:
        raise HTTPException(
            status_code=422,
            detail="Actor cannot be blank"
        )

    try:
        return apply_decision(
            request_id, command.decision, actor
        )
    except KeyError:
        raise HTTPException(404, "Request not found")
    except DecisionConflict as exc:
        raise HTTPException(409, str(exc))
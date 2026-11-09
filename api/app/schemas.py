"""JSON shapes returned by the API."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

from app.extractor import ExtractedInvoice

# Amounts are sent as strings with two decimals ("84.24"), so no precision is lost in JSON.
Money = Annotated[
    Decimal, PlainSerializer(lambda value: f"{value:.2f}", return_type=str, when_used="json")
]


class ItemOut(BaseModel):
    description: str
    quantity: int
    unit_price: Money
    amount: Money


class InvoiceResult(BaseModel):
    source: str
    valid: bool
    number: str | None
    issue_date: date | None
    vendor: str | None
    customer: str | None
    items: list[ItemOut]
    subtotal: Money | None
    tax: Money | None
    total: Money | None
    warnings: list[str]


def to_result(invoice: ExtractedInvoice) -> InvoiceResult:
    return InvoiceResult(
        source=invoice.source,
        valid=invoice.is_valid,
        number=invoice.number,
        issue_date=invoice.issue_date,
        vendor=invoice.vendor,
        customer=invoice.customer,
        items=[
            ItemOut(
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                amount=item.amount,
            )
            for item in invoice.items
        ],
        subtotal=invoice.subtotal,
        tax=invoice.tax,
        total=invoice.total,
        warnings=list(invoice.warnings),
    )

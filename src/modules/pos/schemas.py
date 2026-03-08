"""
POS Schemas
-----------
Response models for POS barcode lookup.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.modules.products.models import ProductStatus
from src.modules.pos.models import PosSaleStatus


def normalize_barcode_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for entry in value:
            if isinstance(entry, str):
                items.append(entry)
                continue
            barcode = None
            if isinstance(entry, dict):
                barcode = entry.get("barcode")
            else:
                barcode = getattr(entry, "barcode", None)
            if barcode:
                items.append(barcode)
        return items
    barcode = getattr(value, "barcode", None)
    if barcode:
        return [barcode]
    return []


class PosLookupResponse(BaseModel):
    """POS lookup response (minimal product payload)."""

    model_config = ConfigDict(from_attributes=True)

    sku: str
    name: str
    unit_price: Decimal
    tax_rate: Decimal
    status: ProductStatus | None = None
    primary_barcode: str | None = None
    barcodes: list[str] = Field(default_factory=list)

    @field_validator("barcodes", mode="before")
    @classmethod
    def coerce_lookup_barcodes(cls, v):
        return normalize_barcode_list(v)


class PosCatalogProduct(BaseModel):
    """POS catalog snapshot item."""

    model_config = ConfigDict(from_attributes=True)

    sku: str
    name: str
    unit_price: Decimal
    tax_rate: Decimal
    status: ProductStatus
    primary_barcode: str | None = None
    barcodes: list[str] = Field(default_factory=list)
    updated_at: datetime

    @field_validator("barcodes", mode="before")
    @classmethod
    def coerce_barcodes(cls, v):
        return normalize_barcode_list(v)


class PosCatalogBootstrapResponse(BaseModel):
    server_time: datetime
    sync_token: str
    products: list[PosCatalogProduct]


class PosCatalogChangesResponse(BaseModel):
    server_time: datetime
    sync_token: str
    changed: list[PosCatalogProduct] = Field(default_factory=list)
    deleted_skus: list[str] = Field(default_factory=list)


class PosCheckoutLineIn(BaseModel):
    barcode: str = Field(..., min_length=1)
    qty: int = Field(..., ge=1)
    unit_price_seen: Decimal | None = None


class PosCheckoutStartRequest(BaseModel):
    location_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=8, max_length=100)
    lines: list[PosCheckoutLineIn] = Field(..., min_length=1)
    auto_create_inventory: bool = Field(default=True)


class PosCheckoutLineOut(BaseModel):
    barcode: str
    sku: str
    name: str
    qty: int
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal


class PosCheckoutTotals(BaseModel):
    subtotal: Decimal
    tax: Decimal
    total: Decimal


class PosCheckoutStartResponse(BaseModel):
    sale_id: str
    status: PosSaleStatus
    reserved_until: datetime
    lines: list[PosCheckoutLineOut]
    totals: PosCheckoutTotals


class PosCheckoutCommitRequest(BaseModel):
    sale_id: str
    idempotency_key: str = Field(..., min_length=8, max_length=100)


class PosCheckoutReceiptResponse(BaseModel):
    sale_id: str
    status: PosSaleStatus
    committed_at: datetime
    lines: list[PosCheckoutLineOut]
    totals: PosCheckoutTotals


class PosCheckoutCancelRequest(BaseModel):
    sale_id: str
    reason: str | None = Field(default=None, max_length=250)


class PosCheckoutCancelResponse(BaseModel):
    sale_id: str
    status: PosSaleStatus

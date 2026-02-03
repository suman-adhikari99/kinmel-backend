"""
Product API Schemas
-------------------
Pydantic v2 models for product request/response validation.

Design Principles:
1. SKU is immutable after creation
2. Strict validation at API boundary
3. Clear field constraints with helpful error messages
"""

from datetime import datetime
from decimal import Decimal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic import AliasChoices
from typing import Literal

from src.modules.products.models import ProductStatus

BARCODE_LENGTHS = {8, 12, 13, 14}


def normalize_barcode(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("Barcode cannot be empty")
    if not value.isalnum():
        raise ValueError("Barcode must be alphanumeric")
    if value.isdigit() and len(value) not in BARCODE_LENGTHS:
        raise ValueError("Barcode must be 8, 12, 13, or 14 digits")
    return value


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


# ═══════════════════════════════════════════════════════════════════════════
# BASE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════

class StrictModel(BaseModel):
    """Base model with strict configuration."""
    
    model_config = ConfigDict(
        strict=False,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class ProductVariantRequest(StrictModel):
    """Variant payload (not persisted yet)."""

    name: str = Field(..., min_length=1, max_length=100)
    sku: str | None = Field(default=None, max_length=50)
    price: Decimal | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)


class ProductVariantResponse(BaseModel):
    """Variant payload (placeholder)."""

    id: str | None = None
    name: str
    sku: str | None = None
    price: Decimal | None = None
    stock: int | None = None


# ═══════════════════════════════════════════════════════════════════════════
# REQUEST SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════

class CreateProductRequest(StrictModel):
    """
    Request to create a new product.
    
    Used by: Managers, Admins
    Endpoint: POST /products
    """
    
    sku: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Unique Stock Keeping Unit (e.g., 'MILK-2L-WHOLE'). Cannot be changed after creation.",
        examples=["MILK-2L-WHOLE", "BREAD-WHITE-LOAF"],
    )
    
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Product display name",
        examples=["Whole Milk 2L", "White Bread Loaf"],
    )
    
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Detailed product description",
    )
    
    category: str = Field(
        default="other",
        description="Product category",
        validation_alias=AliasChoices("category_id", "category"),
    )
    
    brand: str | None = Field(
        default=None,
        max_length=100,
        description="Brand name",
    )
    
    unit_price: Decimal = Field(
        ...,
        ge=0,
        description="Selling price per unit",
        examples=[3.99, 2.50],
        alias="price",
    )
    
    cost_price: Decimal | None = Field(
        default=None,
        ge=0,
        description="Purchase cost per unit (for margin calculation)",
    )
    
    tax_rate: Decimal = Field(
        default=Decimal("0.0"),
        ge=0,
        le=1,
        description="Tax rate as decimal (0.13 = 13%)",
        examples=[0.0, 0.13],
    )
    
    barcode: str | None = Field(
        default=None,
        max_length=50,
        description="Deprecated: use barcodes/primary_barcode",
    )

    barcodes: list[str] | None = Field(
        default=None,
        description="Additional barcodes for POS scanning",
    )

    primary_barcode: str | None = Field(
        default=None,
        description="Primary barcode (must be included in barcodes)",
    )

    subcategory: str | None = Field(
        default=None,
        max_length=100,
        description="Optional subcategory label",
    )

    image_url: str | None = Field(
        default=None,
        max_length=500,
        description="Primary product image URL",
    )

    image_file: str | None = Field(
        default=None,
        max_length=500,
        description="Stored image filename or path",
    )

    status: ProductStatus = Field(
        default=ProductStatus.ACTIVE,
        description="Product lifecycle status",
    )

    featured: bool = Field(
        default=False,
        description="Whether the product is featured",
    )

    priority: int = Field(
        default=0,
        ge=0,
        description="Sorting priority for featured products",
    )

    stock: int | None = Field(
        default=None,
        ge=0,
        description="Deprecated: ignored (use inventory module)",
    )

    variants: list[ProductVariantRequest] | None = Field(
        default=None,
        description="Variant inputs (accepted but not persisted)",
    )
    
    unit_of_measure: str = Field(
        default="each",
        max_length=20,
        description="How the product is sold (each, kg, liter, pack)",
        examples=["each", "kg", "liter", "pack"],
    )
    
    pack_size: int = Field(
        default=1,
        ge=1,
        le=1000,
        description="Units per pack",
    )
    
    is_perishable: bool = Field(
        default=False,
        description="Whether product has expiry dates",
    )
    
    shelf_life_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
        description="Expected shelf life in days (for perishables)",
    )
    
    requires_cold_storage: bool = Field(
        default=False,
        description="Whether product needs refrigeration/freezing",
    )

    @model_validator(mode="before")
    @classmethod
    def coerce_gst_to_tax_rate(cls, data):
        if not isinstance(data, dict):
            return data
        if "gst" not in data:
            return data
        gst_value = data.pop("gst")
        if "tax_rate" in data or gst_value is None:
            return data
        try:
            gst_decimal = Decimal(str(gst_value))
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError("gst must be a valid decimal") from exc
        price_value = data.get("price") or data.get("unit_price")
        if price_value is None:
            if gst_decimal <= 1:
                data["tax_rate"] = gst_decimal
                return data
            raise ValueError("gst requires price to compute tax_rate")
        price_decimal = Decimal(str(price_value))
        if price_decimal <= 0:
            raise ValueError("price must be greater than 0 when gst is provided")
        data["tax_rate"] = gst_decimal if gst_decimal <= 1 else (gst_decimal / price_decimal)
        return data
    
    @field_validator("sku")
    @classmethod
    def validate_sku_format(cls, v: str) -> str:
        """Normalize SKU to uppercase and validate format."""
        v = v.upper().strip()
        # Allow only alphanumeric and hyphens
        if not all(c.isalnum() or c == '-' for c in v):
            raise ValueError("SKU can only contain letters, numbers, and hyphens")
        return v
    
    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, v: str | None) -> str | None:
        """Validate barcode format."""
        return normalize_barcode(v)

    @field_validator("barcodes")
    @classmethod
    def validate_barcodes(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = [normalize_barcode(item) for item in v]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Barcodes must be unique")
        return cleaned

    @field_validator("primary_barcode")
    @classmethod
    def validate_primary_barcode(cls, v: str | None) -> str | None:
        return normalize_barcode(v)

    @model_validator(mode="after")
    def validate_barcode_fields(self):
        if self.barcode and self.barcodes:
            raise ValueError("Use either barcode or barcodes, not both")
        if self.barcode and self.primary_barcode:
            raise ValueError("primary_barcode cannot be used with barcode")
        if self.barcodes is not None and self.primary_barcode:
            if not self.barcodes:
                raise ValueError("primary_barcode cannot be set without barcodes")
            if self.primary_barcode not in self.barcodes:
                raise ValueError("primary_barcode must be included in barcodes")
        return self


class UpdateProductRequest(StrictModel):
    """
    Request to update a product.
    
    Note: SKU cannot be updated.
    
    Used by: Managers, Admins
    Endpoint: PUT /products/{sku}
    """
    
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Product display name",
    )

    sku: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="SKU is immutable and will be ignored if provided",
    )
    
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Detailed product description",
    )
    
    category: str | None = Field(
        default=None,
        description="Product category",
        validation_alias=AliasChoices("category_id", "category"),
    )
    
    brand: str | None = Field(
        default=None,
        max_length=100,
        description="Brand name",
    )
    
    unit_price: Decimal | None = Field(
        default=None,
        ge=0,
        description="Selling price per unit",
        alias="price",
    )
    
    cost_price: Decimal | None = Field(
        default=None,
        ge=0,
        description="Purchase cost per unit",
    )
    
    tax_rate: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Tax rate as decimal",
    )
    
    barcode: str | None = Field(
        default=None,
        max_length=50,
        description="Deprecated: use barcodes/primary_barcode",
    )

    barcodes: list[str] | None = Field(
        default=None,
        description="Additional barcodes for POS scanning",
    )

    primary_barcode: str | None = Field(
        default=None,
        description="Primary barcode (must be included in barcodes)",
    )

    subcategory: str | None = Field(
        default=None,
        max_length=100,
        description="Optional subcategory label",
    )

    image_url: str | None = Field(
        default=None,
        max_length=500,
        description="Primary product image URL",
    )

    image_file: str | None = Field(
        default=None,
        max_length=500,
        description="Stored image filename or path",
    )

    status: ProductStatus | None = Field(
        default=None,
        description="Product lifecycle status",
    )

    featured: bool | None = Field(
        default=None,
        description="Whether the product is featured",
    )

    priority: int | None = Field(
        default=None,
        ge=0,
        description="Sorting priority for featured products",
    )

    stock: int | None = Field(
        default=None,
        ge=0,
        description="Deprecated: ignored (use inventory module)",
    )

    variants: list[ProductVariantRequest] | None = Field(
        default=None,
        description="Variant inputs (accepted but not persisted)",
    )

    unit_of_measure: str | None = Field(
        default=None,
        max_length=20,
        description="How the product is sold",
    )

    pack_size: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description="Units per pack",
    )

    is_perishable: bool | None = Field(
        default=None,
        description="Whether product has expiry dates",
    )

    shelf_life_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
        description="Expected shelf life in days",
    )

    requires_cold_storage: bool | None = Field(
        default=None,
        description="Whether product needs refrigeration/freezing",
    )

    @model_validator(mode="before")
    @classmethod
    def coerce_gst_to_tax_rate(cls, data):
        if not isinstance(data, dict):
            return data
        if "gst" not in data:
            return data
        gst_value = data.pop("gst")
        if "tax_rate" in data or gst_value is None:
            return data
        try:
            gst_decimal = Decimal(str(gst_value))
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError("gst must be a valid decimal") from exc
        price_value = data.get("price") or data.get("unit_price")
        if price_value is None:
            if gst_decimal <= 1:
                data["tax_rate"] = gst_decimal
                return data
            raise ValueError("gst requires price to compute tax_rate")
        price_decimal = Decimal(str(price_value))
        if price_decimal <= 0:
            raise ValueError("price must be greater than 0 when gst is provided")
        data["tax_rate"] = gst_decimal if gst_decimal <= 1 else (gst_decimal / price_decimal)
        return data

    @field_validator("sku")
    @classmethod
    def validate_sku_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.upper().strip()
        if not all(c.isalnum() or c == '-' for c in v):
            raise ValueError("SKU can only contain letters, numbers, and hyphens")
        return v

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, v: str | None) -> str | None:
        return normalize_barcode(v)

    @field_validator("barcodes")
    @classmethod
    def validate_barcodes(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = [normalize_barcode(item) for item in v]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Barcodes must be unique")
        return cleaned

    @field_validator("primary_barcode")
    @classmethod
    def validate_primary_barcode(cls, v: str | None) -> str | None:
        return normalize_barcode(v)

    @model_validator(mode="after")
    def validate_barcode_fields(self):
        if self.barcode and self.barcodes:
            raise ValueError("Use either barcode or barcodes, not both")
        if self.barcode and self.primary_barcode:
            raise ValueError("primary_barcode cannot be used with barcode")
        if self.barcodes is not None and self.primary_barcode:
            if not self.barcodes:
                raise ValueError("primary_barcode cannot be set without barcodes")
            if self.primary_barcode not in self.barcodes:
                raise ValueError("primary_barcode must be included in barcodes")
        return self


class ProductBulkRequest(StrictModel):
    """Bulk action payload."""

    action: Literal[
        "delete",
        "archive",
        "activate",
        "feature",
        "unfeature",
        "update_priority",
    ]
    ids: list[str] = Field(..., min_length=1)
    payload: dict | None = None


class ProductBulkResponse(BaseModel):
    updated: int
    failed: list[str] = Field(default_factory=list)


class ProductImageUploadResponse(BaseModel):
    image_url: str


# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════

class ProductResponse(BaseModel):
    """Full product response."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    sku: str
    name: str
    description: str | None
    category: str
    subcategory: str | None
    brand: str | None
    unit_price: Decimal
    cost_price: Decimal | None
    tax_rate: Decimal
    barcode: str | None
    primary_barcode: str | None = None
    barcodes: list[str] = Field(default_factory=list)
    unit_of_measure: str
    pack_size: int
    is_perishable: bool
    shelf_life_days: int | None
    requires_cold_storage: bool
    status: ProductStatus
    featured: bool
    priority: int
    image_url: str | None
    stock: int = 0
    is_active: bool
    created_at: datetime
    updated_at: datetime
    variants: list[ProductVariantResponse] = Field(default_factory=list)

    @field_validator("barcodes", mode="before")
    @classmethod
    def coerce_barcodes(cls, v):
        return normalize_barcode_list(v)
    
    @computed_field
    @property
    def price_with_tax(self) -> Decimal:
        """Price including tax."""
        return round(self.unit_price * (1 + self.tax_rate), 2)

    @computed_field
    @property
    def price(self) -> Decimal:
        return self.unit_price

    @computed_field
    @property
    def gst(self) -> Decimal:
        return (self.unit_price * self.tax_rate).quantize(Decimal("0.01"))

    @computed_field
    @property
    def category_id(self) -> str:
        return self.category
    
    @computed_field
    @property
    def margin_percent(self) -> float | None:
        """Profit margin percentage."""
        if self.cost_price is None or self.cost_price == 0:
            return None
        margin = ((self.unit_price - self.cost_price) / self.cost_price) * 100
        return round(float(margin), 2)


class ProductSummaryResponse(BaseModel):
    """Summarized product response for lists."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    sku: str
    name: str
    category: str
    subcategory: str | None = None
    unit_price: Decimal
    tax_rate: Decimal
    stock: int = 0
    primary_barcode: str | None = None
    barcodes: list[str] = Field(default_factory=list)
    status: ProductStatus
    featured: bool
    priority: int
    image_url: str | None = None
    is_perishable: bool
    is_active: bool
    variants_count: int = 0
    updated_at: datetime | None = None

    @field_validator("barcodes", mode="before")
    @classmethod
    def coerce_barcodes(cls, v):
        return normalize_barcode_list(v)

    @computed_field
    @property
    def price(self) -> Decimal:
        return self.unit_price

    @computed_field
    @property
    def gst(self) -> Decimal:
        return (self.unit_price * self.tax_rate).quantize(Decimal("0.01"))

    @computed_field
    @property
    def category_id(self) -> str:
        return self.category


class ProductListResponse(BaseModel):
    """Paginated product list response."""
    
    items: list[ProductSummaryResponse]
    total: int
    limit: int
    offset: int
    
    @computed_field
    @property
    def has_more(self) -> bool:
        """Are there more products beyond this page?"""
        return (self.offset + len(self.items)) < self.total
    
    @computed_field
    @property
    def page(self) -> int:
        """Current page number (1-indexed)."""
        if self.limit == 0:
            return 1
        return (self.offset // self.limit) + 1
    
    @computed_field
    @property
    def total_pages(self) -> int:
        """Total number of pages."""
        if self.limit == 0:
            return 1
        return (self.total + self.limit - 1) // self.limit

    @computed_field
    @property
    def products(self) -> list[ProductSummaryResponse]:
        return self.items


class CategoryCreateRequest(StrictModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    status: str = Field(default="active")
    featured: bool = Field(default=False)
    priority: int = Field(default=0, ge=0)
    image_url: str | None = Field(default=None, max_length=500)
    image_file: str | None = Field(default=None, max_length=500)


class CategoryUpdateRequest(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None)
    featured: bool | None = Field(default=None)
    priority: int | None = Field(default=None, ge=0)
    image_url: str | None = Field(default=None, max_length=500)
    image_file: str | None = Field(default=None, max_length=500)


class CategorySummaryResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: str
    featured: bool
    priority: int
    image_url: str | None = None
    product_count: int
    updated_at: datetime | None = None


class CategoryDetailResponse(CategorySummaryResponse):
    created_at: datetime | None = None


class CategoryListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CategorySummaryResponse]


class CategoryImageUploadResponse(BaseModel):
    image_url: str

"""
Product Domain Models
---------------------
Product catalog entities with SKU management.

🔑 KEY CONSTRAINT: SKU is immutable after creation.
Once a product is created with a SKU, that SKU cannot change.
This ensures audit trail integrity and prevents confusion.
"""

from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import BaseModel, SoftDeleteMixin

if TYPE_CHECKING:
    from src.modules.inventory.models import InventoryItem


class ProductStatus(StrEnum):
    """Lifecycle status for products."""

    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"


DEFAULT_CATEGORY = "other"


class CategoryStatus(StrEnum):
    """Lifecycle status for categories."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class Category(BaseModel, SoftDeleteMixin):
    """Product category."""

    __tablename__ = "categories"

    __table_args__ = (
        UniqueConstraint("name", name="uq_categories_name"),
        Index("ix_categories_status", "status"),
        Index("ix_categories_featured", "featured"),
        Index("ix_categories_priority", "priority"),
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Category name",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Category description",
    )

    status: Mapped[CategoryStatus] = mapped_column(
        String(20),
        nullable=False,
        default=CategoryStatus.ACTIVE,
        doc="Category lifecycle status",
    )

    featured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether category is featured",
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Sorting priority for featured categories",
    )

    image_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Category image URL",
    )

    image_file: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Stored category image filename or path",
    )


class Product(BaseModel, SoftDeleteMixin):
    """
    Product definition with SKU.
    
    📦 PRODUCT vs INVENTORY:
    - Product: WHAT it is (name, SKU, price, category)
    - InventoryItem: WHERE and HOW MUCH (location, quantity, buffer)
    
    One Product can have multiple InventoryItem records (one per location).
    
    🔒 SKU IMMUTABILITY:
    The `sku` field cannot be changed after creation. This is enforced by:
    1. No setter method for SKU changes
    2. Application-level validation in the service layer
    3. Audit trail integrity depends on stable SKU
    
    If a SKU needs to "change", create a new product and deprecate the old one.
    
    Attributes:
        sku: Unique, human-readable identifier (e.g., "MILK-2L-WHOLE")
        name: Display name
        description: Detailed description
        category: Product category
        unit_price: Current selling price
        cost_price: Purchase cost (for margin calculation)
        unit_of_measure: How it's sold (each, kg, liter, etc.)
        is_perishable: Whether it has expiry dates
        shelf_life_days: Expected shelf life for perishables
        barcode: UPC/EAN barcode
        tax_rate: Applicable tax rate
    """
    
    __tablename__ = "products"
    
    __table_args__ = (
        # SKU must be unique
        UniqueConstraint("sku", name="uq_products_sku"),
        
        # Barcode should be unique if provided
        UniqueConstraint("barcode", name="uq_products_barcode"),
        
        # Price constraints
        CheckConstraint(
            "unit_price >= 0",
            name="ck_products_unit_price_non_negative"
        ),
        CheckConstraint(
            "cost_price >= 0 OR cost_price IS NULL",
            name="ck_products_cost_price_non_negative"
        ),
        CheckConstraint(
            "tax_rate >= 0 AND tax_rate <= 1",
            name="ck_products_tax_rate_valid"
        ),
        
        # Indexes
        Index("ix_products_sku", "sku"),
        Index("ix_products_category", "category"),
        Index("ix_products_barcode", "barcode"),
        Index("ix_products_name_search", "name"),  # For search
        Index("ix_products_status", "status"),
        Index("ix_products_featured", "featured"),
        Index("ix_products_priority", "priority"),
    )
    
    # ─────────────────────────────────────────────────────────────
    # Identification
    # ─────────────────────────────────────────────────────────────
    
    sku: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="""
        Stock Keeping Unit - unique product identifier.
        
        Format recommendations:
        - Human-readable: MILK-2L-WHOLE, BREAD-WHITE-LOAF
        - Consistent pattern: CATEGORY-SIZE-VARIANT
        - No spaces, uppercase, hyphens for separation
        
        ⚠️ IMMUTABLE: Cannot be changed after creation.
        """,
    )
    
    barcode: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="UPC/EAN barcode for scanning",
    )
    
    # ─────────────────────────────────────────────────────────────
    # Basic Info
    # ─────────────────────────────────────────────────────────────
    
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Display name shown to staff and customers",
    )
    
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Detailed product description",
    )
    
    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=DEFAULT_CATEGORY,
        doc="Product category for organization and reporting",
    )
    
    brand: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Brand name",
    )

    subcategory: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Optional subcategory label",
    )

    image_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Primary product image URL",
    )

    image_file: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Stored image file path or filename",
    )
    
    # ─────────────────────────────────────────────────────────────
    # Pricing
    # ─────────────────────────────────────────────────────────────
    
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        doc="Current selling price per unit",
    )
    
    cost_price: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        doc="Purchase cost per unit (for margin calculation)",
    )
    
    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        default=Decimal("0.0"),
        doc="Tax rate as decimal (0.13 = 13%)",
    )

    status: Mapped[ProductStatus] = mapped_column(
        String(20),
        nullable=False,
        default=ProductStatus.ACTIVE,
        doc="Product lifecycle status",
    )

    featured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether product is featured in listings",
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Sorting priority for featured products",
    )
    
    # ─────────────────────────────────────────────────────────────
    # Unit of Measure
    # ─────────────────────────────────────────────────────────────
    
    unit_of_measure: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="each",
        doc="How the product is sold (each, kg, liter, pack, etc.)",
    )
    
    pack_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        doc="Units per pack (1 for individual items)",
    )
    
    # ─────────────────────────────────────────────────────────────
    # Perishability
    # ─────────────────────────────────────────────────────────────
    
    is_perishable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether product has expiry dates",
    )
    
    shelf_life_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Expected shelf life in days (for perishables)",
    )
    
    requires_cold_storage: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether product needs refrigeration/freezing",
    )
    
    # ─────────────────────────────────────────────────────────────
    # Relationships
    # ─────────────────────────────────────────────────────────────
    
    inventory_items: Mapped[list["InventoryItem"]] = relationship(
        back_populates="product",
        lazy="noload",  # Load explicitly when needed
    )
    
    # ─────────────────────────────────────────────────────────────
    # Computed Properties
    # ─────────────────────────────────────────────────────────────
    
    @property
    def margin(self) -> Decimal | None:
        """Calculate profit margin percentage."""
        if self.cost_price is None or self.cost_price == 0:
            return None
        return ((self.unit_price - self.cost_price) / self.cost_price) * 100
    
    @property
    def price_with_tax(self) -> Decimal:
        """Calculate price including tax."""
        return self.unit_price * (1 + self.tax_rate)
    
    def __repr__(self) -> str:
        return f"<Product(sku={self.sku}, name={self.name})>"

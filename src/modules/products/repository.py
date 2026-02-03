"""
Product Repository
------------------
Data access layer for product operations.
"""

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import LoggerMixin
from src.modules.products.models import Product, ProductBarcode
from src.modules.inventory.models import InventoryItem


class ProductRepository(LoggerMixin):
    """Repository for product data access."""

    async def stock_subquery(self, session: AsyncSession):
        return (
            select(
                InventoryItem.product_id.label("product_id"),
                func.coalesce(func.sum(InventoryItem.physical_stock), 0).label("stock"),
            )
            .where(InventoryItem.is_active == True)
            .group_by(InventoryItem.product_id)
            .subquery()
        )
    
    async def get_by_id(
        self,
        session: AsyncSession,
        product_id: str,
    ) -> Product | None:
        """Get product by ID."""
        query = select(Product).where(
            Product.id == product_id,
            Product.is_active == True,
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_sku(
        self,
        session: AsyncSession,
        sku: str,
    ) -> Product | None:
        """Get product by SKU."""
        query = select(Product).where(
            Product.sku == sku,
            Product.is_active == True,
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_barcode(
        self,
        session: AsyncSession,
        barcode: str,
    ) -> Product | None:
        """Get product by barcode."""
        query = (
            select(Product)
            .join(ProductBarcode)
            .where(
                ProductBarcode.barcode == barcode,
                Product.is_active == True,
            )
        )
        result = await session.execute(query)
        product = result.scalar_one_or_none()
        if product:
            return product
        legacy_query = select(Product).where(
            Product.barcode == barcode,
            Product.is_active == True,
        )
        legacy_result = await session.execute(legacy_query)
        return legacy_result.scalar_one_or_none()

    async def get_barcodes(
        self,
        session: AsyncSession,
        barcodes: Sequence[str],
    ) -> Sequence[ProductBarcode]:
        if not barcodes:
            return []
        query = select(ProductBarcode).where(ProductBarcode.barcode.in_(barcodes))
        result = await session.execute(query)
        return result.scalars().all()
    
    async def get_all(
        self,
        session: AsyncSession,
        *,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Product]:
        """Get all products with optional filtering."""
        query = (
            select(Product)
            .where(Product.is_active == True)
            .order_by(Product.name)
            .limit(limit)
            .offset(offset)
        )
        
        if category:
            query = query.where(Product.category == category)
        
        result = await session.execute(query)
        return result.scalars().all()

    async def get_stock_by_product_id(
        self,
        session: AsyncSession,
        product_id: str,
    ) -> int:
        query = select(func.coalesce(func.sum(InventoryItem.physical_stock), 0)).where(
            InventoryItem.product_id == product_id,
            InventoryItem.is_active == True,
        )
        result = await session.execute(query)
        return int(result.scalar() or 0)

    async def list_categories(
        self,
        session: AsyncSession,
        *,
        search: str | None = None,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[str], int]:
        query = select(Product.category).where(Product.is_active == True)
        if status:
            query = query.where(Product.status == status)
        if search:
            query = query.where(Product.category.ilike(f"%{search}%"))
        query = query.distinct().order_by(Product.category)
        count_query = select(func.count()).select_from(query.subquery())

        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        result = await session.execute(query.limit(limit).offset(offset))
        categories = [row[0] for row in result.all()]
        return categories, total
    
    async def create(
        self,
        session: AsyncSession,
        **kwargs,
    ) -> Product:
        """Create a new product."""
        product = Product(**kwargs)
        session.add(product)
        await session.flush()
        
        self.logger.info(
            "Created product",
            product_id=product.id,
            sku=product.sku,
        )
        
        return product


# Singleton instance
product_repository = ProductRepository()

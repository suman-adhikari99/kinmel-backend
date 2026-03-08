"""
POS Repository
--------------
Data access for barcode lookup.
"""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from src.core.logging import LoggerMixin
from src.modules.inventory.models import InventoryItem, Location
from src.modules.products.models import Product, ProductBarcode, ProductStatus
from src.core.exceptions import AlreadyExistsError
from src.modules.pos.models import PosSale, PosSaleLine, PosSaleStatus


class PosRepository(LoggerMixin):
    def _coerce_since(self, session: AsyncSession, since_dt):
        if since_dt.tzinfo is None:
            return since_dt
        bind = session.get_bind()
        if bind is not None and bind.dialect.name == "sqlite":
            return since_dt.astimezone(UTC).replace(tzinfo=None)
        return since_dt.astimezone(UTC)

    async def get_server_time(self, session: AsyncSession) -> datetime:
        result = await session.execute(select(func.now()))
        value = result.scalar_one()
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return datetime.now(UTC)

    async def get_product_by_barcode(
        self,
        session: AsyncSession,
        barcode: str,
    ) -> Product | None:
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

    async def get_catalog_bootstrap(
        self,
        session: AsyncSession,
    ) -> list[Product]:
        query = (
            select(Product)
            .options(selectinload(Product.barcodes))
            .where(
                Product.is_active == True,
                Product.status == ProductStatus.ACTIVE,
            )
            .order_by(Product.updated_at.asc(), Product.sku.asc())
        )
        result = await session.execute(query)
        return result.scalars().all()

    async def get_catalog_changes(
        self,
        session: AsyncSession,
        since_dt,
    ) -> tuple[list[Product], list[str]]:
        since_value = self._coerce_since(session, since_dt)
        product_ids_subq = (
            select(Product.id.label("product_id"))
            .where(Product.updated_at >= since_value)
        )
        barcode_ids_subq = (
            select(ProductBarcode.product_id.label("product_id"))
            .where(ProductBarcode.updated_at >= since_value)
        )
        changed_ids = product_ids_subq.union(barcode_ids_subq).subquery()

        changed_query = (
            select(Product)
            .options(selectinload(Product.barcodes))
            .where(
                Product.id.in_(select(changed_ids.c.product_id)),
                Product.is_active == True,
                Product.status == ProductStatus.ACTIVE,
            )
            .order_by(Product.updated_at.asc(), Product.sku.asc())
        )
        changed_result = await session.execute(changed_query)
        changed_products = changed_result.scalars().all()

        deleted_query = (
            select(Product.sku)
            .where(
                Product.updated_at >= since_value,
                or_(
                    Product.is_active == False,
                    Product.status != ProductStatus.ACTIVE,
                ),
            )
            .order_by(Product.sku.asc())
        )
        deleted_result = await session.execute(deleted_query)
        deleted_skus = [row[0] for row in deleted_result.all()]

        return changed_products, deleted_skus

    async def get_inventory_item(
        self,
        session: AsyncSession,
        *,
        product_id: str,
        location_id: str,
    ) -> InventoryItem | None:
        query = select(InventoryItem).where(
            InventoryItem.product_id == product_id,
            InventoryItem.location_id == location_id,
            InventoryItem.is_active == True,
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def get_location(
        self,
        session: AsyncSession,
        location_id: str,
    ) -> Location | None:
        query = select(Location).where(
            Location.id == location_id,
            Location.is_active == True,
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def get_default_location(self, session: AsyncSession) -> Location | None:
        query = (
            select(Location)
            .where(Location.is_active == True)
            .order_by(Location.code)
            .limit(1)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def get_sale_by_idempotency_key(
        self,
        session: AsyncSession,
        key: str,
    ) -> PosSale | None:
        query = (
            select(PosSale)
            .options(selectinload(PosSale.lines))
            .where(PosSale.idempotency_key == key)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def get_sale_with_lines(
        self,
        session: AsyncSession,
        sale_id: str,
    ) -> PosSale | None:
        query = (
            select(PosSale)
            .options(selectinload(PosSale.lines))
            .where(PosSale.id == sale_id)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def create_sale(
        self,
        session: AsyncSession,
        *,
        location_id: str,
        status: PosSaleStatus,
        idempotency_key: str,
        reserved_until,
        created_by: str | None,
    ) -> PosSale:
        sale = PosSale(
            location_id=location_id,
            status=status,
            idempotency_key=idempotency_key,
            reserved_until=reserved_until,
            created_by=created_by,
        )
        session.add(sale)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            if "uq_pos_sales_idempotency_key" in str(exc):
                raise AlreadyExistsError("PosSale", idempotency_key) from exc
            raise
        return sale

    async def create_lines(
        self,
        session: AsyncSession,
        sale_id: str,
        lines: list[dict],
    ) -> list[PosSaleLine]:
        records = [PosSaleLine(sale_id=sale_id, **line) for line in lines]
        session.add_all(records)
        await session.flush()
        return records

    async def mark_status(
        self,
        session: AsyncSession,
        sale: PosSale,
        status: PosSaleStatus,
        reserved_until=None,
    ) -> PosSale:
        sale.status = status
        if reserved_until is not None:
            sale.reserved_until = reserved_until
        await session.flush()
        return sale

    async def get_products_for_barcodes(
        self,
        session: AsyncSession,
        barcodes: list[str],
    ) -> dict[str, Product]:
        if not barcodes:
            return {}
        unique = list(dict.fromkeys(barcodes))
        resolved: dict[str, Product] = {}

        query = (
            select(ProductBarcode.barcode, Product)
            .join(Product, ProductBarcode.product_id == Product.id)
            .options(selectinload(Product.barcodes))
            .where(
                ProductBarcode.barcode.in_(unique),
                Product.is_active == True,
                Product.status == ProductStatus.ACTIVE,
            )
        )
        result = await session.execute(query)
        for barcode, product in result.all():
            resolved[barcode] = product

        remaining = [barcode for barcode in unique if barcode not in resolved]
        if remaining:
            legacy_query = (
                select(Product)
                .options(selectinload(Product.barcodes))
                .where(
                Product.barcode.in_(remaining),
                Product.is_active == True,
                Product.status == ProductStatus.ACTIVE,
                )
            )
            legacy_result = await session.execute(legacy_query)
            for product in legacy_result.scalars().all():
                if product.barcode:
                    resolved[product.barcode] = product

        return resolved

    async def get_expired_sales(
        self,
        session: AsyncSession,
        now,
    ) -> list[PosSale]:
        now_value = self._coerce_since(session, now)
        query = (
            select(PosSale)
            .options(selectinload(PosSale.lines))
            .where(
                PosSale.status == PosSaleStatus.RESERVED,
                PosSale.reserved_until != None,
                PosSale.reserved_until < now_value,
            )
            .order_by(PosSale.reserved_until.asc())
        )
        result = await session.execute(query)
        return result.scalars().all()


pos_repository = PosRepository()

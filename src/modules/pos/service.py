"""
POS Service
-----------
Business logic for barcode lookup.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AlreadyExistsError, NotFoundError, ValidationError
from src.core.logging import LoggerMixin
from src.modules.pos.repository import PosRepository, pos_repository
from src.modules.pos.schemas import (
    PosCatalogBootstrapResponse,
    PosCatalogChangesResponse,
    PosCatalogProduct,
    PosCheckoutLineOut,
    PosCheckoutReceiptResponse,
    PosCheckoutStartRequest,
    PosCheckoutStartResponse,
    PosCheckoutTotals,
)
from src.modules.inventory.service import ReservationInput, inventory_service
from src.modules.pos.models import PosSaleStatus
from src.modules.products.models import ProductStatus


@dataclass
class PosLookupResult:
    sku: str
    name: str
    unit_price: Decimal
    tax_rate: Decimal
    status: ProductStatus | None
    primary_barcode: str | None
    barcodes: list[str]
    price_with_tax: Decimal
    on_hand: int
    buffer: int
    online_available: int
    location_id: str


class PosService(LoggerMixin):
    def __init__(self, repository: PosRepository | None = None) -> None:
        self.repo = repository or pos_repository

    def _resolve_barcodes(self, product) -> tuple[str | None, list[str]]:
        barcodes: list[str] = []
        primary: str | None = None

        for record in product.barcodes or []:
            barcode_value = getattr(record, "barcode", None)
            if not barcode_value:
                continue
            barcodes.append(barcode_value)
            if getattr(record, "is_primary", False):
                primary = barcode_value

        if not primary and product.barcode:
            primary = product.barcode

        if barcodes:
            unique = sorted(set(barcodes))
            if primary and primary in unique:
                unique.remove(primary)
                ordered = [primary] + unique
            else:
                ordered = unique
            return primary, ordered

        if product.barcode:
            return product.barcode, [product.barcode]

        return None, []

    def _is_uuid(self, value: str) -> bool:
        try:
            UUID(value)
            return True
        except ValueError:
            return False

    def product_to_pos_catalog_product(self, product) -> PosCatalogProduct:
        primary_barcode, barcodes = self._resolve_barcodes(product)
        return PosCatalogProduct(
            sku=product.sku,
            name=product.name,
            unit_price=product.unit_price,
            tax_rate=product.tax_rate,
            status=product.status,
            primary_barcode=primary_barcode,
            barcodes=barcodes,
            updated_at=product.updated_at,
        )

    def _build_checkout_lines(self, lines) -> list[PosCheckoutLineOut]:
        outputs: list[PosCheckoutLineOut] = []
        for line in lines:
            unit_price = line.unit_price_at_sale
            line_total = (unit_price * line.qty).quantize(Decimal("0.01"))
            outputs.append(
                PosCheckoutLineOut(
                    barcode=line.barcode,
                    sku=line.sku,
                    name=line.name_snapshot or "",
                    qty=line.qty,
                    unit_price=unit_price,
                    tax_rate=line.tax_rate_at_sale,
                    line_total=line_total,
                )
            )
        return outputs

    def _build_totals(self, lines) -> PosCheckoutTotals:
        subtotal = Decimal("0.00")
        tax = Decimal("0.00")
        for line in lines:
            line_subtotal = line.unit_price_at_sale * line.qty
            subtotal += line_subtotal
            tax += line_subtotal * line.tax_rate_at_sale
        subtotal = subtotal.quantize(Decimal("0.01"))
        tax = tax.quantize(Decimal("0.01"))
        total = (subtotal + tax).quantize(Decimal("0.01"))
        return PosCheckoutTotals(subtotal=subtotal, tax=tax, total=total)

    def _build_checkout_response(self, sale) -> PosCheckoutStartResponse:
        return PosCheckoutStartResponse(
            sale_id=sale.id,
            status=sale.status,
            reserved_until=sale.reserved_until,
            lines=self._build_checkout_lines(sale.lines),
            totals=self._build_totals(sale.lines),
        )

    async def lookup(
        self,
        session: AsyncSession,
        *,
        barcode: str,
        location_id: str | None = None,
    ) -> PosLookupResult:
        product = await self.repo.get_product_by_barcode(session, barcode)
        if not product:
            raise NotFoundError("Barcode", barcode)

        if location_id:
            location = await self.repo.get_location(session, location_id)
            if not location:
                raise NotFoundError("Location", location_id)
        else:
            location = await self.repo.get_default_location(session)
            if not location:
                raise NotFoundError("Location", "default")

        item = await self.repo.get_inventory_item(
            session,
            product_id=product.id,
            location_id=location.id,
        )

        if item:
            on_hand = item.physical_stock
            buffer = item.buffer
            online_available = item.online_available
        else:
            on_hand = 0
            buffer = 0
            online_available = 0

        price_with_tax = round(product.unit_price * (1 + product.tax_rate), 2)
        primary_barcode, barcodes = self._resolve_barcodes(product)

        return PosLookupResult(
            sku=product.sku,
            name=product.name,
            unit_price=product.unit_price,
            tax_rate=product.tax_rate,
            price_with_tax=price_with_tax,
            on_hand=on_hand,
            buffer=buffer,
            online_available=online_available,
            location_id=location.id,
            status=product.status,
            primary_barcode=primary_barcode,
            barcodes=barcodes,
        )

    async def bootstrap_catalog(
        self,
        session: AsyncSession,
    ) -> PosCatalogBootstrapResponse:
        server_time = await self.repo.get_server_time(session)
        products = await self.repo.get_catalog_bootstrap(session)
        catalog = [self.product_to_pos_catalog_product(product) for product in products]
        return PosCatalogBootstrapResponse(
            server_time=server_time,
            sync_token=server_time.isoformat(),
            products=catalog,
        )

    async def catalog_changes(
        self,
        session: AsyncSession,
        since_dt: datetime,
    ) -> PosCatalogChangesResponse:
        server_time = await self.repo.get_server_time(session)
        changed_products, deleted_skus = await self.repo.get_catalog_changes(session, since_dt)
        changed = [self.product_to_pos_catalog_product(product) for product in changed_products]
        return PosCatalogChangesResponse(
            server_time=server_time,
            sync_token=server_time.isoformat(),
            changed=changed,
            deleted_skus=deleted_skus,
        )

    async def start_checkout(
        self,
        session: AsyncSession,
        request: PosCheckoutStartRequest,
        *,
        user_id: str,
    ) -> PosCheckoutStartResponse:
        existing = await self.repo.get_sale_by_idempotency_key(session, request.idempotency_key)
        if existing:
            return self._build_checkout_response(existing)

        barcodes = [line.barcode for line in request.lines]
        products = await self.repo.get_products_for_barcodes(session, barcodes)
        for barcode in barcodes:
            if barcode not in products:
                raise NotFoundError(
                    "Product",
                    barcode,
                    staff_message="Product not found.",
                    details={"resource": "Product", "identifier": barcode},
                )

        auto_created_items: list[dict[str, str]] = []
        if request.auto_create_inventory:
            sku_totals: dict[str, int] = {}
            products_by_sku: dict[str, object] = {}
            for line in request.lines:
                product = products[line.barcode]
                sku_totals[product.sku] = sku_totals.get(product.sku, 0) + line.qty
                products_by_sku[product.sku] = product

            for sku, qty in sku_totals.items():
                product = products_by_sku[sku]
                item, created = await inventory_service.ensure_inventory_item(
                    session,
                    sku=sku,
                    location_id=request.location_id,
                    product_id=product.id,
                    initial_physical_stock=qty,
                )
                if created:
                    auto_created_items.append(
                        {
                            "sku": sku,
                            "location_id": request.location_id,
                            "inventory_item_id": item.id,
                        }
                    )

        reserved_until = datetime.now(UTC) + timedelta(minutes=2)

        created_by = user_id if self._is_uuid(user_id) else None
        try:
            sale = await self.repo.create_sale(
                session,
                location_id=request.location_id,
                status=PosSaleStatus.RESERVED,
                idempotency_key=request.idempotency_key,
                reserved_until=reserved_until,
                created_by=created_by,
            )
        except AlreadyExistsError:
            existing = await self.repo.get_sale_by_idempotency_key(session, request.idempotency_key)
            if not existing:
                raise
            return self._build_checkout_response(existing)

        if auto_created_items:
            self.logger.info(
                "POS checkout auto-created inventory items",
                sale_id=sale.id,
                location_id=request.location_id,
                items=auto_created_items,
            )

        line_payloads = []
        for line in request.lines:
            product = products[line.barcode]
            line_payloads.append(
                {
                    "barcode": line.barcode,
                    "sku": product.sku,
                    "qty": line.qty,
                    "unit_price_at_sale": product.unit_price,
                    "tax_rate_at_sale": product.tax_rate,
                    "name_snapshot": product.name,
                }
            )

        sale_lines = await self.repo.create_lines(session, sale.id, line_payloads)

        for line in sale_lines:
            await inventory_service.reserve_stock(
                session,
                ReservationInput(
                    sku=line.sku,
                    location_id=request.location_id,
                    quantity=line.qty,
                    user_id=user_id,
                    order_id=sale.id,
                    notes=None,
                ),
            )

        await session.commit()
        await session.refresh(sale)
        await session.refresh(sale, ["lines"])

        return self._build_checkout_response(sale)

    async def commit_checkout(
        self,
        session: AsyncSession,
        sale_id: str,
        *,
        idempotency_key: str,
        user_id: str,
    ) -> PosCheckoutReceiptResponse:
        sale = await self.repo.get_sale_with_lines(session, sale_id)
        if not sale:
            raise NotFoundError("PosSale", sale_id)
        if sale.idempotency_key != idempotency_key:
            raise ValidationError(
                staff_message="Idempotency key mismatch for sale",
                details={"code": "IDEMPOTENCY_MISMATCH"},
            )

        if sale.status == PosSaleStatus.COMMITTED:
            return PosCheckoutReceiptResponse(
                sale_id=sale.id,
                status=sale.status,
                committed_at=sale.updated_at,
                lines=self._build_checkout_lines(sale.lines),
                totals=self._build_totals(sale.lines),
            )
        if sale.status != PosSaleStatus.RESERVED:
            raise ValidationError(
                staff_message="Sale is not in a reservable state",
                details={"code": "SALE_NOT_RESERVED"},
            )

        now = datetime.now(UTC)
        reserved_until = sale.reserved_until
        if reserved_until is None:
            raise ValidationError(
                staff_message="Reservation has expired",
                details={"code": "RESERVATION_EXPIRED"},
            )
        if reserved_until.tzinfo is None:
            compare_now = now.replace(tzinfo=None)
        else:
            compare_now = now
        if reserved_until < compare_now:
            raise ValidationError(
                staff_message="Reservation has expired",
                details={"code": "RESERVATION_EXPIRED"},
            )

        for line in sale.lines:
            await inventory_service.fulfill_order(
                session,
                sku=line.sku,
                location_id=sale.location_id,
                quantity=line.qty,
                user_id=user_id,
                order_id=sale.id,
                notes=None,
            )

        await self.repo.mark_status(session, sale, PosSaleStatus.COMMITTED)
        await session.commit()
        await session.refresh(sale)
        await session.refresh(sale, ["lines"])

        return PosCheckoutReceiptResponse(
            sale_id=sale.id,
            status=sale.status,
            committed_at=sale.updated_at,
            lines=self._build_checkout_lines(sale.lines),
            totals=self._build_totals(sale.lines),
        )

    async def cancel_checkout(
        self,
        session: AsyncSession,
        sale_id: str,
        *,
        user_id: str,
    ) -> tuple[str, PosSaleStatus]:
        sale = await self.repo.get_sale_with_lines(session, sale_id)
        if not sale:
            raise NotFoundError("PosSale", sale_id)

        if sale.status == PosSaleStatus.COMMITTED:
            raise ValidationError(
                staff_message="Cannot cancel a committed sale",
                details={"code": "SALE_ALREADY_COMMITTED"},
            )

        if sale.status in (PosSaleStatus.CANCELLED, PosSaleStatus.EXPIRED):
            return sale.id, sale.status

        for line in sale.lines:
            await inventory_service.release_reservation(
                session,
                sku=line.sku,
                location_id=sale.location_id,
                quantity=line.qty,
                user_id=user_id,
                order_id=sale.id,
                notes=None,
            )

        await self.repo.mark_status(session, sale, PosSaleStatus.CANCELLED)
        await session.commit()
        await session.refresh(sale)
        return sale.id, sale.status

    async def get_checkout_status(
        self,
        session: AsyncSession,
        sale_id: str,
    ) -> PosCheckoutStartResponse:
        sale = await self.repo.get_sale_with_lines(session, sale_id)
        if not sale:
            raise NotFoundError("PosSale", sale_id)
        return self._build_checkout_response(sale)

    async def get_checkout_by_key(
        self,
        session: AsyncSession,
        idempotency_key: str,
    ) -> PosCheckoutStartResponse:
        sale = await self.repo.get_sale_by_idempotency_key(session, idempotency_key)
        if not sale:
            raise NotFoundError("PosSale", idempotency_key)
        return self._build_checkout_response(sale)

    async def lookup_product(
        self,
        session: AsyncSession,
        *,
        barcode: str,
    ) -> dict:
        products = await self.repo.get_products_for_barcodes(session, [barcode])
        product = products.get(barcode)
        if not product:
            raise NotFoundError("Barcode", barcode)
        primary, barcodes = self._resolve_barcodes(product)
        return {
            "sku": product.sku,
            "name": product.name,
            "unit_price": product.unit_price,
            "tax_rate": product.tax_rate,
            "status": product.status,
            "primary_barcode": primary,
            "barcodes": barcodes,
        }

    async def expire_reserved_sales(
        self,
        session: AsyncSession,
        now: datetime,
    ) -> dict:
        expired = await self.repo.get_expired_sales(session, now)
        processed = 0
        skipped = 0
        failed = 0

        for sale in expired:
            if sale.status != PosSaleStatus.RESERVED:
                skipped += 1
                continue
            try:
                for line in sale.lines:
                    try:
                        await inventory_service.release_reservation(
                            session,
                            sku=line.sku,
                            location_id=sale.location_id,
                            quantity=line.qty,
                            user_id="system",
                            order_id=sale.id,
                            notes="Reservation expired",
                        )
                    except ValidationError:
                        self.logger.warning(
                            "POS expiry release skipped - buffer mismatch",
                            sale_id=sale.id,
                            sku=line.sku,
                        )
                        continue

                await self.repo.mark_status(session, sale, PosSaleStatus.EXPIRED)
                await session.commit()
                processed += 1
            except Exception:
                await session.rollback()
                failed += 1
                self.logger.exception("Failed to expire POS reservation", sale_id=sale.id)

        return {
            "status": "completed",
            "expired": processed,
            "skipped": skipped,
            "failed": failed,
        }


pos_service = PosService()

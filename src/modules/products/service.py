"""
Product Service
---------------
Business logic for product operations.

Design Principles:
1. SKU is immutable after creation
2. Soft delete only (never hard delete)
3. Validation before database operations
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import NotFoundError, ValidationError
from src.core.logging import LoggerMixin
from src.modules.inventory.models import Location, MovementReason
from src.modules.products.models import DEFAULT_CATEGORY, Product, ProductBarcode, ProductStatus
from src.modules.products.repository import product_repository
from src.modules.products.category_repository import category_repository


@dataclass
class CreateProductInput:
    """Input data for creating a product."""
    
    sku: str
    name: str
    unit_price: Decimal
    category: str = DEFAULT_CATEGORY
    description: str | None = None
    brand: str | None = None
    cost_price: Decimal | None = None
    tax_rate: Decimal = Decimal("0.0")
    barcode: str | None = None
    barcodes: list[str] | None = None
    primary_barcode: str | None = None
    unit_of_measure: str = "each"
    pack_size: int = 1
    is_perishable: bool = False
    shelf_life_days: int | None = None
    requires_cold_storage: bool = False
    subcategory: str | None = None
    image_url: str | None = None
    image_file: str | None = None
    status: ProductStatus = ProductStatus.ACTIVE
    featured: bool = False
    priority: int = 0
    user_id: str | None = None


@dataclass
class UpdateProductInput:
    """Input data for updating a product."""
    
    name: str | None = None
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    unit_price: Decimal | None = None
    cost_price: Decimal | None = None
    tax_rate: Decimal | None = None
    barcode: str | None = None
    barcodes: list[str] | None = None
    primary_barcode: str | None = None
    unit_of_measure: str | None = None
    pack_size: int | None = None
    is_perishable: bool | None = None
    shelf_life_days: int | None = None
    requires_cold_storage: bool | None = None
    subcategory: str | None = None
    image_url: str | None = None
    image_file: str | None = None
    status: ProductStatus | None = None
    featured: bool | None = None
    priority: int | None = None
    user_id: str | None = None


class ProductService(LoggerMixin):
    """Service layer for product operations."""

    def _is_uuid(self, value: str) -> bool:
        try:
            UUID(value)
            return True
        except ValueError:
            return False

    def _dedupe_barcodes(self, barcodes: list[str]) -> list[str]:
        seen = set()
        deduped: list[str] = []
        for barcode in barcodes:
            if barcode in seen:
                raise ValidationError(
                    staff_message=f"Duplicate barcode '{barcode}' in request",
                    details={"field": "barcodes", "value": barcode},
                )
            seen.add(barcode)
            deduped.append(barcode)
        return deduped

    async def _ensure_barcodes_loaded(
        self,
        session: AsyncSession,
        product: Product,
    ) -> None:
        if "barcodes" not in product.__dict__:
            await session.refresh(product, ["barcodes"])

    def resolve_barcodes(self, product: Product) -> tuple[str | None, list[str]]:
        barcodes: list[str] = []
        primary: str | None = None

        for record in product.barcodes or []:
            if not record.barcode:
                continue
            barcodes.append(record.barcode)
            if record.is_primary:
                primary = record.barcode

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

    def _resolve_barcode_create(
        self,
        *,
        barcode: str | None,
        barcodes: list[str] | None,
        primary_barcode: str | None,
    ) -> tuple[list[str], str | None]:
        if barcode and barcodes:
            raise ValidationError(
                staff_message="Use either barcode or barcodes, not both",
                details={"field": "barcode"},
            )
        if barcode and primary_barcode:
            raise ValidationError(
                staff_message="primary_barcode cannot be used with barcode",
                details={"field": "primary_barcode"},
            )
        values = barcodes if barcodes is not None else ([barcode] if barcode else [])
        if not values:
            return [], None
        values = self._dedupe_barcodes(values)
        if primary_barcode and primary_barcode not in values:
            raise ValidationError(
                staff_message="primary_barcode must be included in barcodes",
                details={"field": "primary_barcode", "value": primary_barcode},
            )
        return values, primary_barcode or values[0]

    def _resolve_barcode_update(
        self,
        input_data: UpdateProductInput,
    ) -> tuple[list[str] | None, str | None]:
        if input_data.barcode:
            if input_data.barcodes is not None or input_data.primary_barcode is not None:
                raise ValidationError(
                    staff_message="Use either barcode or barcodes, not both",
                    details={"field": "barcode"},
                )
            return [input_data.barcode], input_data.barcode
        if input_data.barcodes is not None:
            values = self._dedupe_barcodes(input_data.barcodes)
            if input_data.primary_barcode and input_data.primary_barcode not in values:
                raise ValidationError(
                    staff_message="primary_barcode must be included in barcodes",
                    details={"field": "primary_barcode", "value": input_data.primary_barcode},
                )
            primary = input_data.primary_barcode or (values[0] if values else None)
            if primary and not values:
                raise ValidationError(
                    staff_message="primary_barcode cannot be set without barcodes",
                    details={"field": "primary_barcode", "value": primary},
                )
            return values, primary
        if input_data.primary_barcode is not None:
            return None, input_data.primary_barcode
        return None, None

    async def _reassign_barcodes(
        self,
        session: AsyncSession,
        *,
        product: Product,
        records: Sequence[ProductBarcode],
    ) -> None:
        if not records:
            return
        moved = {record.barcode for record in records}
        previous_ids = {record.product_id for record in records}

        for record in records:
            record.product = product

        if not previous_ids:
            return

        result = await session.execute(
            select(Product)
            .options(selectinload(Product.barcodes))
            .where(Product.id.in_(previous_ids))
        )
        old_products = result.scalars().all()
        for old_product in old_products:
            if old_product.barcode not in moved:
                continue
            remaining = [
                barcode for barcode in old_product.barcodes if barcode.barcode not in moved
            ]
            if remaining:
                new_primary = next((barcode for barcode in remaining if barcode.is_primary), remaining[0])
                for barcode in remaining:
                    barcode.is_primary = barcode is new_primary
                old_product.barcode = new_primary.barcode
            else:
                old_product.barcode = None
    
    async def create_product(
        self,
        session: AsyncSession,
        input_data: CreateProductInput,
    ) -> Product:
        """
        Create a new product.
        
        Args:
            session: Database session
            input_data: Product creation data
            
        Returns:
            Created product
            
        Raises:
            ValidationError: If SKU already exists or barcode conflicts
        """
        # Normalize SKU
        sku = input_data.sku.upper().strip()
        
        # Check if SKU already exists
        existing = await product_repository.get_by_sku(session, sku)
        if existing:
            raise ValidationError(
                staff_message=f"Product with SKU '{sku}' already exists",
                details={"field": "sku", "value": sku},
            )

        barcodes, primary_barcode = self._resolve_barcode_create(
            barcode=input_data.barcode,
            barcodes=input_data.barcodes,
            primary_barcode=input_data.primary_barcode,
        )
        if barcodes:
            existing_barcodes = await product_repository.get_barcodes(session, barcodes)
            if existing_barcodes:
                conflict = existing_barcodes[0].barcode
                raise ValidationError(
                    staff_message=f"Barcode '{conflict}' is already assigned to another product",
                    details={"field": "barcodes", "value": conflict},
                )
        
        # Validate perishable consistency
        if input_data.is_perishable and not input_data.shelf_life_days:
            self.logger.warning(
                "Perishable product created without shelf_life_days",
                sku=sku,
            )
        
        category_name = input_data.category.strip() if input_data.category else None
        if category_name:
            category = await category_repository.get_by_name(session, category_name)
            if not category and self._is_uuid(category_name):
                category = await category_repository.get_by_id(session, category_name)
            if not category:
                if category_name == DEFAULT_CATEGORY:
                    category = await category_repository.create(
                        session,
                        name=category_name,
                        description=None,
                        status="active",
                        featured=False,
                        priority=0,
                    )
                else:
                    raise ValidationError(
                        staff_message="Category not found",
                        details={"field": "category_id", "value": category_name},
                    )
            category_name = category.name

        # Create product
        product = await product_repository.create(
            session,
            sku=sku,
            name=input_data.name,
            description=input_data.description,
            category=category_name or DEFAULT_CATEGORY,
            brand=input_data.brand,
            subcategory=input_data.subcategory,
            image_url=input_data.image_url,
            image_file=input_data.image_file,
            unit_price=input_data.unit_price,
            cost_price=input_data.cost_price,
            tax_rate=input_data.tax_rate,
            barcode=primary_barcode,
            unit_of_measure=input_data.unit_of_measure,
            pack_size=input_data.pack_size,
            is_perishable=input_data.is_perishable,
            shelf_life_days=input_data.shelf_life_days,
            requires_cold_storage=input_data.requires_cold_storage,
            status=input_data.status,
            featured=input_data.featured,
            priority=input_data.priority,
        )
        if barcodes:
            for barcode_value in barcodes:
                session.add(
                    ProductBarcode(
                        product_id=product.id,
                        barcode=barcode_value,
                        is_primary=barcode_value == primary_barcode,
                    )
                )
            product.barcode = primary_barcode
        
        await session.commit()
        await self._ensure_barcodes_loaded(session, product)
        
        self.logger.info(
            "Product created",
            product_id=product.id,
            sku=product.sku,
            category=product.category,
        )
        
        return product
    
    async def update_product(
        self,
        session: AsyncSession,
        identifier: str,
        input_data: UpdateProductInput,
    ) -> Product:
        """
        Update an existing product.
        
        Note: SKU cannot be updated.
        
        Args:
            session: Database session
            sku: Product SKU to update
            input_data: Fields to update
            
        Returns:
            Updated product
            
        Raises:
            NotFoundError: If product doesn't exist
            ValidationError: If barcode conflicts
        """
        # Get existing product
        product = await self.get_product_by_identifier(session, identifier)
        if not product:
            raise NotFoundError(
                staff_message=f"Product not found: {identifier}",
                details={"resource": "product", "identifier": identifier},
            )
        
        barcodes_payload, primary_payload = self._resolve_barcode_update(input_data)
        conflicting_records: list[ProductBarcode] = []
        if barcodes_payload is not None:
            if not barcodes_payload and primary_payload:
                raise ValidationError(
                    staff_message="primary_barcode cannot be set without barcodes",
                    details={"field": "primary_barcode", "value": primary_payload},
                )
            if barcodes_payload:
                existing_barcodes = await product_repository.get_barcodes(session, barcodes_payload)
                conflicting_records = [
                    record for record in existing_barcodes if record.product_id != product.id
                ]
        
        # Update only provided fields
        update_fields = {}
        if input_data.category:
            category_value = input_data.category.strip()
            category = await category_repository.get_by_name(session, category_value)
            if not category and self._is_uuid(category_value):
                category = await category_repository.get_by_id(session, category_value)
            if not category:
                raise ValidationError(
                    staff_message="Category not found",
                    details={"field": "category_id", "value": category_value},
                )
            input_data.category = category.name

        for field in [
            "name", "description", "category", "brand", "unit_price",
            "cost_price", "tax_rate", "unit_of_measure", "pack_size",
            "is_perishable", "shelf_life_days", "requires_cold_storage",
            "subcategory", "image_url", "image_file", "status", "featured", "priority"
        ]:
            value = getattr(input_data, field)
            if value is not None:
                update_fields[field] = value
        
        if update_fields:
            for field, value in update_fields.items():
                setattr(product, field, value)
            
            await session.commit()
            await session.refresh(product)
            
            self.logger.info(
                "Product updated",
                product_id=product.id,
                sku=product.sku,
                updated_fields=list(update_fields.keys()),
            )

        if barcodes_payload is not None or primary_payload is not None:
            await session.refresh(product, ["barcodes"])
            if barcodes_payload and conflicting_records:
                await self._reassign_barcodes(
                    session,
                    product=product,
                    records=conflicting_records,
                )
                await session.flush()
            existing_map = {barcode.barcode: barcode for barcode in product.barcodes}
            if barcodes_payload is None:
                if not product.barcodes:
                    raise ValidationError(
                        staff_message="No existing barcodes to update",
                        details={"field": "primary_barcode"},
                    )
                if primary_payload not in existing_map:
                    raise ValidationError(
                        staff_message="primary_barcode must reference an existing barcode",
                        details={"field": "primary_barcode", "value": primary_payload},
                    )
                for barcode in product.barcodes:
                    barcode.is_primary = barcode.barcode == primary_payload
                product.barcode = primary_payload
            else:
                desired = set(barcodes_payload)
                for barcode in list(product.barcodes):
                    if barcode.barcode not in desired:
                        product.barcodes.remove(barcode)
                if not barcodes_payload:
                    product.barcode = None
                for barcode_value in barcodes_payload:
                    record = existing_map.get(barcode_value)
                    if record is None:
                        record = ProductBarcode(
                            product_id=product.id,
                            barcode=barcode_value,
                        )
                        product.barcodes.append(record)
                    record.is_primary = barcode_value == primary_payload
                product.barcode = primary_payload
            await session.commit()
            await session.refresh(product)
        
        await self._ensure_barcodes_loaded(session, product)
        return product

    async def get_product_by_identifier(
        self,
        session: AsyncSession,
        identifier: str,
    ) -> Product:
        """Get a product by SKU or UUID."""
        product = None
        if self._is_uuid(identifier):
            product = await product_repository.get_by_id(session, identifier)
        if not product:
            product = await product_repository.get_by_sku(session, identifier.upper())
        if not product:
            raise NotFoundError(
                staff_message=f"Product not found: {identifier}",
                details={"resource": "product", "identifier": identifier},
            )
        await self._ensure_barcodes_loaded(session, product)
        return product
    
    async def get_product_by_sku(
        self,
        session: AsyncSession,
        sku: str,
    ) -> Product:
        """
        Get a product by SKU.
        
        Args:
            session: Database session
            sku: Product SKU
            
        Returns:
            Product
            
        Raises:
            NotFoundError: If product doesn't exist
        """
        product = await product_repository.get_by_sku(session, sku.upper())
        if not product:
            raise NotFoundError(
                staff_message=f"Product not found: {sku}",
                details={"resource": "product", "identifier": sku},
            )
        await self._ensure_barcodes_loaded(session, product)
        return product
    
    async def get_product_by_barcode(
        self,
        session: AsyncSession,
        barcode: str,
    ) -> Product:
        """
        Get a product by barcode.
        
        Args:
            session: Database session
            barcode: Product barcode
            
        Returns:
            Product
            
        Raises:
            NotFoundError: If product doesn't exist
        """
        product = await product_repository.get_by_barcode(session, barcode)
        if not product:
            raise NotFoundError(
                staff_message=f"Product not found with barcode: {barcode}",
                details={"resource": "product", "identifier": barcode},
            )
        await self._ensure_barcodes_loaded(session, product)
        return product
    
    async def list_products(
        self,
        session: AsyncSession,
        *,
        category: str | None = None,
        subcategory: str | None = None,
        status: ProductStatus | None = None,
        featured: bool | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        in_stock: bool | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort: str = "created_at",
        order: str = "desc",
    ) -> tuple[Sequence[tuple[Product, int]], int]:
        """
        List products with optional filtering.
        
        Args:
            session: Database session
            category: Filter by category
            search: Search in name and SKU
            limit: Max products to return
            offset: Number to skip
            
        Returns:
            Tuple of (products, total_count)
        """
        stock_subq = await product_repository.stock_subquery(session)
        stock_col = func.coalesce(stock_subq.c.stock, 0)

        query = (
            select(Product, stock_col.label("stock"))
            .options(selectinload(Product.barcodes))
            .outerjoin(stock_subq, stock_subq.c.product_id == Product.id)
            .where(Product.is_active == True)
        )
        count_query = (
            select(func.count(Product.id))
            .select_from(Product)
            .outerjoin(stock_subq, stock_subq.c.product_id == Product.id)
            .where(Product.is_active == True)
        )
        
        # Apply category filter
        if category:
            category_name = category.strip()
            resolved = await category_repository.get_by_name(session, category_name)
            if not resolved and self._is_uuid(category_name):
                resolved = await category_repository.get_by_id(session, category_name)
            if resolved:
                category_name = resolved.name
            query = query.where(Product.category == category_name)
            count_query = count_query.where(Product.category == category_name)

        if subcategory:
            query = query.where(Product.subcategory == subcategory)
            count_query = count_query.where(Product.subcategory == subcategory)

        if status:
            query = query.where(Product.status == status)
            count_query = count_query.where(Product.status == status)
        else:
            query = query.where(Product.status == ProductStatus.ACTIVE)
            count_query = count_query.where(Product.status == ProductStatus.ACTIVE)

        if featured is not None:
            query = query.where(Product.featured == featured)
            count_query = count_query.where(Product.featured == featured)

        if min_price is not None:
            query = query.where(Product.unit_price >= min_price)
            count_query = count_query.where(Product.unit_price >= min_price)

        if max_price is not None:
            query = query.where(Product.unit_price <= max_price)
            count_query = count_query.where(Product.unit_price <= max_price)
        
        # Apply search filter
        if search:
            search_pattern = f"%{search}%"
            barcode_exists = exists(
                select(ProductBarcode.id).where(
                    ProductBarcode.product_id == Product.id,
                    ProductBarcode.barcode.ilike(search_pattern),
                )
            )
            query = query.where(
                (Product.name.ilike(search_pattern)) |
                (Product.sku.ilike(search_pattern)) |
                barcode_exists
            )
            count_query = count_query.where(
                (Product.name.ilike(search_pattern)) |
                (Product.sku.ilike(search_pattern)) |
                barcode_exists
            )

        if in_stock is True:
            query = query.where(stock_col > 0)
            count_query = count_query.where(stock_col > 0)
        elif in_stock is False:
            query = query.where(stock_col <= 0)
            count_query = count_query.where(stock_col <= 0)
        
        # Get total count
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0
        
        sort_map = {
            "name": Product.name,
            "price": Product.unit_price,
            "stock": stock_col,
            "updated_at": Product.updated_at,
            "created_at": Product.created_at,
            "priority": Product.priority,
        }
        sort_col = sort_map.get(sort, Product.created_at)
        if order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        query = query.limit(limit).offset(offset)
        
        # Execute query
        result = await session.execute(query)
        products = result.all()
        
        return products, total
    
    async def delete_product(
        self,
        session: AsyncSession,
        identifier: str,
    ) -> Product:
        """
        Soft delete a product.
        
        Args:
            session: Database session
            sku: Product SKU to delete
            
        Returns:
            Deleted product
            
        Raises:
            NotFoundError: If product doesn't exist
        """
        product = await self.get_product_by_identifier(session, identifier)
        
        # Soft delete
        product.is_active = False
        await session.commit()
        
        self.logger.info(
            "Product deleted (soft)",
            product_id=product.id,
            sku=product.sku,
        )
        
        await self._ensure_barcodes_loaded(session, product)
        return product
    
    async def get_products_by_category(
        self,
        session: AsyncSession,
        category: str,
        limit: int = 100,
    ) -> Sequence[Product]:
        """
        Get all products in a category.
        
        Args:
            session: Database session
            category: Product category
            limit: Max products to return
            
        Returns:
            List of products
        """
        return await product_repository.get_all(
            session,
            category=category,
            limit=limit,
        )
    
    async def list_categories(
        self,
        session: AsyncSession,
        *,
        search: str | None = None,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[str], int]:
        return await product_repository.list_categories(
            session,
            search=search,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def bulk_action(
        self,
        session: AsyncSession,
        action: str,
        ids: list[str],
        payload: dict | None = None,
    ) -> tuple[int, list[str]]:
        result = await session.execute(
            select(Product).where(Product.id.in_(ids), Product.is_active == True)
        )
        products = result.scalars().all()
        found_ids = {product.id for product in products}
        failed = [product_id for product_id in ids if product_id not in found_ids]

        if action == "delete":
            for product in products:
                product.is_active = False
        elif action == "archive":
            for product in products:
                product.status = ProductStatus.ARCHIVED
        elif action == "activate":
            for product in products:
                product.status = ProductStatus.ACTIVE
        elif action == "feature":
            for product in products:
                product.featured = True
        elif action == "unfeature":
            for product in products:
                product.featured = False
        elif action == "update_priority":
            if not payload or "priority" not in payload:
                raise ValidationError(
                    staff_message="priority is required for update_priority",
                    details={"field": "priority"},
                )
            priority_value = int(payload["priority"])
            for product in products:
                product.priority = priority_value
        else:
            raise ValidationError(
                staff_message="Invalid bulk action",
                details={"field": "action", "value": action},
            )

        await session.commit()
        return len(products), failed

    async def _seed_initial_stock(
        self,
        session: AsyncSession,
        sku: str,
        quantity: int,
        user_id: str | None,
    ) -> None:
        from src.modules.inventory.service import ReceivingInput, inventory_service
        result = await session.execute(
            select(Location).where(Location.is_active == True).order_by(Location.code).limit(1)
        )
        location = result.scalar_one_or_none()
        if not location:
            self.logger.warning("No locations available for initial stock", sku=sku)
            return
        if not user_id:
            self.logger.warning("Skipping initial stock without user_id", sku=sku)
            return
        await inventory_service.receive_stock(
            session,
            ReceivingInput(
                sku=sku,
                location_id=location.id,
                quantity=quantity,
                user_id=user_id,
                notes="Initial stock from product creation",
            ),
        )

    async def _set_stock_default_location(
        self,
        session: AsyncSession,
        sku: str,
        quantity: int,
        user_id: str | None,
    ) -> None:
        from src.modules.inventory.service import AdjustmentInput, ReceivingInput, inventory_service
        result = await session.execute(
            select(Location).where(Location.is_active == True).order_by(Location.code).limit(1)
        )
        location = result.scalar_one_or_none()
        if not location:
            self.logger.warning("No locations available to set stock", sku=sku)
            return
        if not user_id:
            self.logger.warning("Skipping stock update without user_id", sku=sku)
            return
        try:
            await inventory_service.adjust_stock(
                session,
                AdjustmentInput(
                    sku=sku,
                    location_id=location.id,
                    new_quantity=quantity,
                    user_id=user_id,
                    reason=MovementReason.SYSTEM_CORRECTION,
                    notes="Stock updated from product management",
                    skip_large_adjustment_check=True,
                ),
            )
        except NotFoundError:
            await inventory_service.receive_stock(
                session,
                ReceivingInput(
                    sku=sku,
                    location_id=location.id,
                    quantity=quantity,
                    user_id=user_id,
                    notes="Initial stock from product management",
                ),
            )


# Singleton instance
product_service = ProductService()

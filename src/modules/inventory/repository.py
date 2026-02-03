"""
Inventory Repository
--------------------
Data access layer for inventory operations.

🔒 CONCURRENCY STRATEGY:

1. OPTIMISTIC LOCKING (primary strategy)
   - Read item with current version
   - Perform business logic
   - Update with WHERE version = expected_version
   - If 0 rows affected → ConcurrencyError
   
   Best for: Most operations (low contention)

2. PESSIMISTIC LOCKING (SELECT FOR UPDATE)
   - Lock row when reading
   - Hold lock until transaction commits
   - Other transactions wait
   
   Best for: High-value operations, bulk updates

This repository uses BOTH strategies appropriately.
"""

from datetime import UTC, datetime, timedelta
from typing import Sequence

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.core.exceptions import (
    AlreadyExistsError,
    ConcurrencyError,
    NotFoundError,
)
from src.core.logging import LoggerMixin
from src.core.models import generate_uuid
from src.modules.inventory.models import (
    InventoryBatch,
    InventoryItem,
    Location,
    LocationType,
    MovementReason,
    MovementType,
    StockMovement,
)
from src.modules.products.models import Product


class InventoryRepository(LoggerMixin):
    """
    Repository for inventory data access.
    
    All methods are stateless and receive session as parameter.
    This allows for flexible transaction management at the service layer.
    """
    
    # ═══════════════════════════════════════════════════════════════════
    # INVENTORY ITEM QUERIES
    # ═══════════════════════════════════════════════════════════════════
    
    async def get_by_id(
        self,
        session: AsyncSession,
        item_id: str,
        *,
        for_update: bool = False,
    ) -> InventoryItem | None:
        """
        Get inventory item by ID.
        
        Args:
            session: Database session
            item_id: Inventory item UUID
            for_update: If True, lock the row (SELECT FOR UPDATE)
            
        Returns:
            InventoryItem or None if not found
        """
        query = (
            select(InventoryItem)
            .where(
                InventoryItem.id == item_id,
                InventoryItem.is_active == True,
            )
        )
        
        if for_update:
            # Pessimistic lock - avoid outer join locks by using selectinload
            query = query.options(
                selectinload(InventoryItem.product),
                selectinload(InventoryItem.location),
            ).with_for_update(of=InventoryItem)
        else:
            query = query.options(
                joinedload(InventoryItem.product),
                joinedload(InventoryItem.location),
            )
        
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_sku_and_location(
        self,
        session: AsyncSession,
        sku: str,
        location_id: str,
        *,
        for_update: bool = False,
        include_inactive: bool = False,
    ) -> InventoryItem | None:
        """
        Get inventory item by SKU and location.
        
        This is the most common lookup pattern:
        "How much of SKU X is at location Y?"
        
        Args:
            session: Database session
            sku: Product SKU
            location_id: Location UUID
            for_update: If True, lock the row
            
        Returns:
            InventoryItem or None
        """
        query = (
            select(InventoryItem)
            .join(InventoryItem.product)
            .where(
                Product.sku == sku,
                InventoryItem.location_id == location_id,
                Product.is_active == True,
            )
        )
        if not include_inactive:
            query = query.where(InventoryItem.is_active == True)
        
        if for_update:
            # Pessimistic lock - avoid outer join locks by using selectinload
            query = query.options(
                selectinload(InventoryItem.product),
                selectinload(InventoryItem.location),
            ).with_for_update(of=InventoryItem)
        else:
            query = query.options(
                joinedload(InventoryItem.product),
                joinedload(InventoryItem.location),
            )
        
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_all_by_sku(
        self,
        session: AsyncSession,
        sku: str,
    ) -> Sequence[InventoryItem]:
        """
        Get all inventory items for a SKU across all locations.
        
        Useful for:
        - Total stock across store
        - Finding which locations have stock
        """
        query = (
            select(InventoryItem)
            .join(InventoryItem.product)
            .options(
                joinedload(InventoryItem.product),
                joinedload(InventoryItem.location),
            )
            .where(
                Product.sku == sku,
                InventoryItem.is_active == True,
                Product.is_active == True,
            )
            .order_by(InventoryItem.location_id)
        )
        
        result = await session.execute(query)
        return result.scalars().all()
    
    async def get_total_stock_by_sku(
        self,
        session: AsyncSession,
        sku: str,
    ) -> dict[str, int]:
        """
        Get aggregated stock for a SKU across all locations.
        
        Returns:
            Dict with physical_stock, buffer, online_available totals
        """
        query = (
            select(
                func.coalesce(func.sum(InventoryItem.physical_stock), 0).label("physical_stock"),
                func.coalesce(func.sum(InventoryItem.buffer), 0).label("buffer"),
            )
            .join(InventoryItem.product)
            .where(
                Product.sku == sku,
                InventoryItem.is_active == True,
                Product.is_active == True,
            )
        )
        
        result = await session.execute(query)
        row = result.one()
        
        physical = int(row.physical_stock)
        buffer = int(row.buffer)
        
        return {
            "physical_stock": physical,
            "buffer": buffer,
            "online_available": max(physical - buffer, 0),
        }

    async def get_inventory_summary(
        self,
        session: AsyncSession,
        *,
        location_id: str | None = None,
    ) -> dict:
        query = (
            select(
                func.count(InventoryItem.id).label("total_products"),
                func.coalesce(
                    func.sum(
                        case((InventoryItem.physical_stock <= InventoryItem.reorder_point, 1), else_=0)
                    ),
                    0,
                ).label("low_stock"),
                func.coalesce(
                    func.sum(case((InventoryItem.physical_stock == 0, 1), else_=0)),
                    0,
                ).label("out_of_stock"),
                func.coalesce(
                    func.sum(case((InventoryItem.physical_stock < InventoryItem.reorder_point, 1), else_=0)),
                    0,
                ).label("below_threshold"),
                func.max(InventoryItem.updated_at).label("last_sync_at"),
            )
            .join(InventoryItem.product)
            .where(
                InventoryItem.is_active == True,
                Product.is_active == True,
            )
        )
        if location_id:
            query = query.where(InventoryItem.location_id == location_id)

        result = await session.execute(query)
        row = result.one()
        return {
            "total_products": int(row.total_products or 0),
            "low_stock": int(row.low_stock or 0),
            "out_of_stock": int(row.out_of_stock or 0),
            "below_threshold": int(row.below_threshold or 0),
            "last_sync_at": row.last_sync_at,
        }

    async def list_inventory_items(
        self,
        session: AsyncSession,
        *,
        location_id: str | None,
        search: str | None,
        category: str | None,
        status: str | None,
        low_stock_only: bool,
        out_of_stock_only: bool,
        limit: int,
        offset: int,
        sort: str,
        order: str,
    ) -> tuple[Sequence[InventoryItem], int]:
        filters = [
            InventoryItem.is_active == True,
            Product.is_active == True,
        ]
        if location_id:
            filters.append(InventoryItem.location_id == location_id)
        if search:
            like = f"%{search.lower()}%"
            filters.append(
                or_(
                    func.lower(Product.sku).like(like),
                    func.lower(Product.name).like(like),
                )
            )
        if category:
            filters.append(func.lower(Product.category) == category.lower())
        if low_stock_only:
            filters.append(InventoryItem.physical_stock <= InventoryItem.reorder_point)
        if out_of_stock_only:
            filters.append(InventoryItem.physical_stock == 0)
        if status == "in_stock":
            filters.append(InventoryItem.physical_stock > InventoryItem.reorder_point)
        elif status == "low_stock":
            filters.append(
                and_(
                    InventoryItem.physical_stock > 0,
                    InventoryItem.physical_stock <= InventoryItem.reorder_point,
                )
            )
        elif status == "out_of_stock":
            filters.append(InventoryItem.physical_stock == 0)

        sort_map = {
            "sku": Product.sku,
            "name": Product.name,
            "stock": InventoryItem.physical_stock,
            "updated_at": InventoryItem.updated_at,
            "category": Product.category,
        }
        sort_col = sort_map.get(sort, InventoryItem.updated_at)
        sort_col = sort_col.desc() if order == "desc" else sort_col.asc()

        base_query = (
            select(InventoryItem)
            .join(InventoryItem.product)
            .options(
                joinedload(InventoryItem.product),
                joinedload(InventoryItem.location),
            )
            .where(*filters)
            .order_by(sort_col)
        )

        count_query = select(func.count()).select_from(
            select(InventoryItem.id)
            .join(InventoryItem.product)
            .where(*filters)
            .subquery()
        )
        total = (await session.execute(count_query)).scalar_one()

        result = await session.execute(base_query.limit(limit).offset(offset))
        return result.scalars().all(), int(total)
    
    # ═══════════════════════════════════════════════════════════════════
    # INVENTORY ITEM MUTATIONS
    # ═══════════════════════════════════════════════════════════════════
    
    async def create(
        self,
        session: AsyncSession,
        *,
        product_id: str,
        location_id: str,
        physical_stock: int = 0,
        buffer: int = 0,
        reorder_point: int = 0,
        max_stock: int | None = None,
    ) -> InventoryItem:
        """
        Create a new inventory item.
        
        Raises:
            AlreadyExistsError: If product already exists at this location
        """
        item = InventoryItem(
            product_id=product_id,
            location_id=location_id,
            physical_stock=physical_stock,
            buffer=buffer,
            reorder_point=reorder_point,
            max_stock=max_stock,
        )
        
        session.add(item)
        
        try:
            await session.flush()
        except IntegrityError as e:
            await session.rollback()
            if "uq_inventory_product_location" in str(e):
                raise AlreadyExistsError(
                    "InventoryItem",
                    f"product={product_id}, location={location_id}",
                )
            raise
        
        self.logger.info(
            "Created inventory item",
            item_id=item.id,
            product_id=product_id,
            location_id=location_id,
        )
        
        return item

    async def create_if_missing(
        self,
        session: AsyncSession,
        *,
        product_id: str,
        location_id: str,
        physical_stock: int = 0,
        buffer: int = 0,
        reorder_point: int = 0,
        max_stock: int | None = None,
    ) -> bool:
        """
        Create an inventory item if it does not already exist.

        Uses a safe upsert to avoid raising on concurrent inserts.

        Returns:
            True if created, False if an item already exists.
        """
        values = {
            "id": generate_uuid(),
            "product_id": product_id,
            "location_id": location_id,
            "physical_stock": physical_stock,
            "buffer": buffer,
            "reorder_point": reorder_point,
            "max_stock": max_stock,
            "version": 1,
            "is_active": True,
        }
        bind = session.get_bind()
        dialect_name = bind.dialect.name if bind else "postgresql"
        if dialect_name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            stmt = sqlite_insert(InventoryItem).values(**values).on_conflict_do_nothing(
                index_elements=["product_id", "location_id"],
            )
        else:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(InventoryItem).values(**values).on_conflict_do_nothing(
                index_elements=["product_id", "location_id"],
            )

        result = await session.execute(stmt)
        return result.rowcount == 1
    
    async def update_stock_optimistic(
        self,
        session: AsyncSession,
        item_id: str,
        *,
        new_physical_stock: int,
        new_buffer: int | None = None,
        expected_version: int,
    ) -> bool:
        """
        Update stock with optimistic locking.
        
        This is the CORE method for safe concurrent updates.
        
        Args:
            session: Database session
            item_id: Inventory item ID
            new_physical_stock: New physical stock value
            new_buffer: New buffer value (optional)
            expected_version: Version the caller expects
            
        Returns:
            True if update succeeded, False if version mismatch
            
        Raises:
            ConcurrencyError: If version mismatch (another update happened)
        
        How it works:
            UPDATE inventory_items 
            SET physical_stock = ?, buffer = ?, version = version + 1
            WHERE id = ? AND version = ?
            
            If 0 rows affected → version changed → ConcurrencyError
        """
        values = {
            "physical_stock": new_physical_stock,
            "version": InventoryItem.version + 1,
            "updated_at": datetime.now(UTC),
        }
        
        if new_buffer is not None:
            values["buffer"] = new_buffer
        
        stmt = (
            update(InventoryItem)
            .where(
                InventoryItem.id == item_id,
                InventoryItem.version == expected_version,
                InventoryItem.is_active == True,
            )
            .values(**values)
        )
        
        result = await session.execute(stmt)
        
        if result.rowcount == 0:
            self.logger.warning(
                "Optimistic lock failed - concurrent modification",
                item_id=item_id,
                expected_version=expected_version,
            )
            raise ConcurrencyError("InventoryItem", item_id)
        
        self.logger.debug(
            "Stock updated via optimistic lock",
            item_id=item_id,
            new_stock=new_physical_stock,
            new_version=expected_version + 1,
        )

    async def update_reorder_point_optimistic(
        self,
        session: AsyncSession,
        item_id: str,
        *,
        new_reorder_point: int,
        expected_version: int,
    ) -> bool:
        values = {
            "reorder_point": new_reorder_point,
            "version": InventoryItem.version + 1,
            "updated_at": datetime.now(UTC),
        }
        stmt = (
            update(InventoryItem)
            .where(
                InventoryItem.id == item_id,
                InventoryItem.version == expected_version,
                InventoryItem.is_active == True,
            )
            .values(**values)
        )
        result = await session.execute(stmt)
        if result.rowcount == 0:
            self.logger.warning(
                "Optimistic lock failed - concurrent modification",
                item_id=item_id,
                expected_version=expected_version,
            )
            raise ConcurrencyError("InventoryItem", item_id)
        self.logger.debug(
            "Reorder point updated via optimistic lock",
            item_id=item_id,
            new_reorder_point=new_reorder_point,
            new_version=expected_version + 1,
        )
        
        return True
    
    # ═══════════════════════════════════════════════════════════════════
    # STOCK MOVEMENT (AUDIT)
    # ═══════════════════════════════════════════════════════════════════
    
    async def create_movement(
        self,
        session: AsyncSession,
        *,
        inventory_item_id: str,
        movement_type: MovementType,
        reason: MovementReason | None,
        quantity_delta: int,
        quantity_before: int,
        quantity_after: int,
        user_id: str,
        reference_id: str | None = None,
        reference_type: str | None = None,
        notes: str | None = None,
        batch_id: str | None = None,
    ) -> StockMovement:
        """
        Create an immutable stock movement audit record.
        
        This should be called atomically with stock updates.
        """
        movement = StockMovement(
            inventory_item_id=inventory_item_id,
            movement_type=movement_type,
            reason=reason,
            quantity_delta=quantity_delta,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            user_id=user_id,
            reference_id=reference_id,
            reference_type=reference_type,
            notes=notes,
            batch_id=batch_id,
        )
        
        session.add(movement)
        await session.flush()
        
        self.logger.info(
            "Stock movement recorded",
            movement_id=movement.id,
            type=movement_type,
            delta=quantity_delta,
            before=quantity_before,
            after=quantity_after,
        )
        
        return movement
    
    async def get_movements_for_item(
        self,
        session: AsyncSession,
        item_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[StockMovement]:
        """Get movement history for an inventory item."""
        query = (
            select(StockMovement)
            .where(StockMovement.inventory_item_id == item_id)
            .order_by(StockMovement.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        result = await session.execute(query)
        return result.scalars().all()

    async def get_movements_by_sku(
        self,
        session: AsyncSession,
        *,
        sku: str,
        location_id: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[StockMovement], int]:
        filters = [
            Product.sku == sku,
            InventoryItem.is_active == True,
            Product.is_active == True,
        ]
        if location_id:
            filters.append(InventoryItem.location_id == location_id)

        base_query = (
            select(StockMovement)
            .join(StockMovement.inventory_item)
            .join(InventoryItem.product)
            .where(*filters)
            .order_by(StockMovement.created_at.desc())
        )
        count_query = select(func.count()).select_from(
            select(StockMovement.id)
            .join(StockMovement.inventory_item)
            .join(InventoryItem.product)
            .where(*filters)
            .subquery()
        )
        total = (await session.execute(count_query)).scalar_one()
        result = await session.execute(base_query.limit(limit).offset(offset))
        return result.scalars().all(), int(total)
    
    # ═══════════════════════════════════════════════════════════════════
    # ALERT QUERIES (Low Stock, Expiring)
    # ═══════════════════════════════════════════════════════════════════
    
    async def get_low_stock_items(
        self,
        session: AsyncSession,
        *,
        location_id: str | None = None,
    ) -> Sequence[InventoryItem]:
        """
        Get items at or below reorder point.
        
        Used for:
        - Low stock alerts
        - Reorder reports
        - Manager dashboards
        """
        query = (
            select(InventoryItem)
            .options(
                joinedload(InventoryItem.product),
                joinedload(InventoryItem.location),
            )
            .where(
                InventoryItem.physical_stock <= InventoryItem.reorder_point,
                InventoryItem.is_active == True,
            )
            .order_by(
                # Most critical first (lowest stock relative to reorder)
                (InventoryItem.physical_stock - InventoryItem.reorder_point).asc()
            )
        )
        
        if location_id:
            query = query.where(InventoryItem.location_id == location_id)
        
        result = await session.execute(query)
        return result.scalars().all()
    
    async def get_out_of_stock_items(
        self,
        session: AsyncSession,
        *,
        location_id: str | None = None,
    ) -> Sequence[InventoryItem]:
        """Get items with zero physical stock."""
        query = (
            select(InventoryItem)
            .options(
                joinedload(InventoryItem.product),
                joinedload(InventoryItem.location),
            )
            .where(
                InventoryItem.physical_stock == 0,
                InventoryItem.is_active == True,
            )
        )
        
        if location_id:
            query = query.where(InventoryItem.location_id == location_id)
        
        result = await session.execute(query)
        return result.scalars().all()
    
    async def get_expiring_batches(
        self,
        session: AsyncSession,
        *,
        days_ahead: int = 7,
        location_id: str | None = None,
    ) -> Sequence[InventoryBatch]:
        """
        Get batches expiring within N days.
        
        Critical for grocery operations:
        - FIFO selling
        - Markdown decisions
        - Disposal planning
        """
        expiry_threshold = datetime.now(UTC) + timedelta(days=days_ahead)
        
        query = (
            select(InventoryBatch)
            .join(InventoryBatch.inventory_item)
            .options(
                joinedload(InventoryBatch.inventory_item).joinedload(InventoryItem.product),
                joinedload(InventoryBatch.inventory_item).joinedload(InventoryItem.location),
            )
            .where(
                InventoryBatch.expiry_date <= expiry_threshold,
                InventoryBatch.expiry_date > datetime.now(UTC),  # Not already expired
                InventoryBatch.quantity > 0,
                InventoryItem.is_active == True,
            )
            .order_by(InventoryBatch.expiry_date.asc())
        )
        
        if location_id:
            query = query.where(InventoryItem.location_id == location_id)
        
        result = await session.execute(query)
        return result.scalars().all()
    
    async def get_expired_batches(
        self,
        session: AsyncSession,
        *,
        location_id: str | None = None,
    ) -> Sequence[InventoryBatch]:
        """Get batches that have already expired (need disposal)."""
        query = (
            select(InventoryBatch)
            .join(InventoryBatch.inventory_item)
            .options(
                joinedload(InventoryBatch.inventory_item).joinedload(InventoryItem.product),
                joinedload(InventoryBatch.inventory_item).joinedload(InventoryItem.location),
            )
            .where(
                InventoryBatch.expiry_date < datetime.now(UTC),
                InventoryBatch.quantity > 0,
                InventoryItem.is_active == True,
            )
            .order_by(InventoryBatch.expiry_date.asc())
        )
        
        if location_id:
            query = query.where(InventoryItem.location_id == location_id)
        
        result = await session.execute(query)
        return result.scalars().all()
    
    # ═══════════════════════════════════════════════════════════════════
    # LOCATION QUERIES
    # ═══════════════════════════════════════════════════════════════════
    
    async def get_location_by_code(
        self,
        session: AsyncSession,
        code: str,
    ) -> Location | None:
        """Get location by its unique code."""
        query = (
            select(Location)
            .where(
                Location.code == code,
                Location.is_active == True,
            )
        )
        
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_locations_by_type(
        self,
        session: AsyncSession,
        location_type: LocationType,
    ) -> Sequence[Location]:
        """Get all locations of a specific type."""
        query = (
            select(Location)
            .where(
                Location.location_type == location_type,
                Location.is_active == True,
            )
            .order_by(Location.code)
        )
        
        result = await session.execute(query)
        return result.scalars().all()

    async def list_locations(
        self,
        session: AsyncSession,
        *,
        location_type: LocationType | None = None,
    ) -> Sequence[Location]:
        query = select(Location).where(Location.is_active == True)
        if location_type:
            query = query.where(Location.location_type == location_type)
        query = query.order_by(Location.code)
        result = await session.execute(query)
        return result.scalars().all()

    async def get_default_location_id(self, session: AsyncSession) -> str | None:
        query = (
            select(Location.id)
            .where(Location.is_active == True)
            .order_by(Location.code.asc())
            .limit(1)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    # ═══════════════════════════════════════════════════════════════════
    # BATCH OPERATIONS
    # ═══════════════════════════════════════════════════════════════════
    
    async def create_batch(
        self,
        session: AsyncSession,
        *,
        inventory_item_id: str,
        quantity: int,
        batch_number: str | None = None,
        expiry_date: datetime | None = None,
        cost_per_unit: float | None = None,
    ) -> InventoryBatch:
        """Create a new inventory batch (for perishables)."""
        from decimal import Decimal
        
        batch = InventoryBatch(
            inventory_item_id=inventory_item_id,
            quantity=quantity,
            batch_number=batch_number,
            expiry_date=expiry_date,
            cost_per_unit=Decimal(str(cost_per_unit)) if cost_per_unit else None,
            received_date=datetime.now(UTC),
        )
        
        session.add(batch)
        await session.flush()
        
        self.logger.info(
            "Created inventory batch",
            batch_id=batch.id,
            item_id=inventory_item_id,
            quantity=quantity,
            expiry=expiry_date,
        )
        
        return batch
    
    async def get_batches_for_item(
        self,
        session: AsyncSession,
        item_id: str,
        *,
        include_empty: bool = False,
    ) -> Sequence[InventoryBatch]:
        """Get batches for an inventory item, ordered by expiry (FIFO)."""
        query = (
            select(InventoryBatch)
            .where(InventoryBatch.inventory_item_id == item_id)
            .order_by(
                # FIFO: earliest expiry first, then received date
                InventoryBatch.expiry_date.asc().nulls_last(),
                InventoryBatch.received_date.asc(),
            )
        )
        
        if not include_empty:
            query = query.where(InventoryBatch.quantity > 0)
        
        result = await session.execute(query)
        return result.scalars().all()


# Singleton instance for dependency injection
inventory_repository = InventoryRepository()

# Inventory Module
# Handles: Stock levels, movements, locations, expiry tracking, alerts

from src.modules.inventory.models import (
    InventoryBatch,
    InventoryItem,
    Location,
    LocationType,
    MovementReason,
    MovementType,
    StockMovement,
)
from src.modules.inventory.repository import InventoryRepository, inventory_repository
from src.modules.inventory.router import router
from src.modules.inventory.service import (
    AdjustmentInput,
    InventoryService,
    ReceivingInput,
    ReservationInput,
    StockOperationResult,
    inventory_service,
)

__all__ = [
    # Models
    "InventoryItem",
    "InventoryBatch",
    "Location",
    "LocationType",
    "StockMovement",
    "MovementType",
    "MovementReason",
    # Repository
    "InventoryRepository",
    "inventory_repository",
    # Service
    "InventoryService",
    "inventory_service",
    "ReceivingInput",
    "AdjustmentInput",
    "ReservationInput",
    "StockOperationResult",
    # Router
    "router",
]

# Kinmel - Grocery Inventory Management System

> A **fault-tolerant, staff-proof** backend for grocery store inventory operations.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0-orange.svg)](https://www.sqlalchemy.org/)

---

## Table of Contents

- [Project Overview](#-project-overview)
- [Quick Start](#-quick-start)
- [Domain Model](#-domain-model)
- [Authentication & Authorization](#-authentication--authorization)
- [API Reference](#-api-reference)
- [Database & Migrations](#-database--migrations)
- [Inventory Actions](#-inventory-actions)
- [Background Tasks](#-background-tasks)
- [Admin & Audit System](#-admin--audit-system)
- [Testing & Development](#-testing--development)
- [Operational Tips](#-operational-tips)
- [Documentation Assets](#-documentation-assets)

---

## 📦 Project Overview

### Purpose

Kinmel is a production-grade inventory management system designed for grocery stores. It handles:

- **Stock Tracking**: Real-time inventory levels across multiple locations
- **Perishable Management**: FIFO batch tracking with expiry dates
- **Audit Trail**: Immutable log of every stock change
- **Multi-Role Access**: Granular permissions for staff, managers, and admins
- **Operational Alerts**: Automated low-stock and expiry notifications

### Tech Stack

| Component | Technology |
|-----------|------------|
| **Language** | Python 3.11+ |
| **Framework** | FastAPI 0.109 |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Database** | SQLite (aiosqlite) |
| **Migrations** | Alembic 1.13 |
| **Validation** | Pydantic v2 |
| **Background Jobs** | Celery 5.3 + Redis |
| **Auth** | JWT (PyJWT) |
| **Logging** | structlog |

### Architecture

**Modular Monolith** - Domain-driven modules with clear boundaries, ready for future microservice extraction.

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI App                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │Inventory│  │  Admin  │  │  Users  │  │Products │        │
│  │ Module  │  │ Module  │  │ Module  │  │ Module  │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
│       │            │            │            │              │
│  ┌────┴────────────┴────────────┴────────────┴────┐        │
│  │              Core Services Layer                │        │
│  │    (database, security, logging, config)       │        │
│  └─────────────────────┬───────────────────────────┘        │
└────────────────────────┼────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   ┌─────────┐     ┌─────────┐     ┌─────────┐
   │ SQLite  │     │  Redis  │     │ Celery  │
   │ Database│     │ Broker  │     │ Workers │
   └─────────┘     └─────────┘     └─────────┘
```

### Folder Structure

```
backend-kinmel/
├── src/
│   ├── main.py                 # FastAPI application entry point
│   ├── api/
│   │   ├── deps.py             # Dependency injection (auth, db)
│   │   ├── exception_handlers.py
│   │   ├── middleware.py
│   │   └── openapi.py          # OpenAPI customization
│   ├── core/
│   │   ├── config.py           # Pydantic Settings
│   │   ├── database.py         # SQLAlchemy async engine
│   │   ├── exceptions.py       # Custom exception classes
│   │   ├── logging.py          # structlog configuration
│   │   ├── models.py           # Base model mixins
│   │   └── security.py         # JWT & password utilities
│   ├── modules/
│   │   ├── inventory/
│   │   │   ├── models.py       # InventoryItem, Batch, Movement, Location
│   │   │   ├── repository.py   # Data access layer
│   │   │   ├── service.py      # Business logic
│   │   │   ├── schemas.py      # Pydantic request/response
│   │   │   └── router.py       # API endpoints
│   │   ├── products/
│   │   │   ├── models.py       # Product entity
│   │   │   └── repository.py
│   │   ├── users/
│   │   │   └── models.py       # User entity
│   │   └── admin/
│   │       ├── schemas.py      # Audit query schemas
│   │       ├── repository.py   # Audit data access
│   │       └── router.py       # Admin API endpoints
│   └── tasks/
│       ├── celery_app.py       # Celery configuration
│       ├── base.py             # Base task with retry logic
│       ├── notifications.py    # Alert dispatcher
│       ├── inventory_tasks.py  # Stock monitoring tasks
│       └── report_tasks.py     # Report generation
├── alembic/
│   ├── env.py                  # Migration environment
│   ├── versions/               # Migration files
│   └── README.md               # Migration guide
├── scripts/
│   ├── db.py                   # Database CLI helper
│   ├── seed_data.py            # Test data seeder
│   └── export_openapi.py       # OpenAPI export utility
├── tests/
│   ├── conftest.py             # Pytest fixtures
│   ├── test_inventory_api.py
│   ├── test_inventory_models.py
│   └── test_inventory_service.py
├── docs/
│   └── API.md                  # API documentation
├── requirements.txt
├── pyproject.toml              # Project config & tooling
└── alembic.ini                 # Alembic configuration
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- SQLite (included with Python; aiosqlite driver is installed via requirements)
- Redis 7+

### Setup

```bash
# Clone repository
git clone <repo-url>
cd backend-kinmel

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env if you want a custom SQLite file path (defaults to ./kinmel.db)
# Run migrations
python scripts/db.py migrate

# Seed test data
python scripts/seed_data.py

# Start the server
uvicorn src.main:app --reload
```

### Verify Installation

```bash
# Health check
curl http://localhost:8000/health

# Open API docs
open http://localhost:8000/docs
```

---

## 🧩 Domain Model

### Entity Relationship Diagram

```
┌─────────────┐       ┌─────────────────┐       ┌──────────────┐
│    User     │       │     Product     │       │   Location   │
├─────────────┤       ├─────────────────┤       ├──────────────┤
│ id (UUID)   │       │ id (UUID)       │       │ id (UUID)    │
│ email       │       │ sku (UNIQUE)    │       │ code (UNIQUE)│
│ password_hash│      │ name            │       │ name         │
│ full_name   │       │ category        │       │ location_type│
│ role        │       │ unit_price      │       │ capacity     │
│ is_verified │       │ is_perishable   │       │ temp_zone    │
│ is_active   │       │ shelf_life_days │       │ is_active    │
└──────┬──────┘       └────────┬────────┘       └──────┬───────┘
       │                       │                        │
       │              ┌────────┴────────┐              │
       │              │                 │              │
       │              ▼                 ▼              │
       │    ┌─────────────────────────────────┐       │
       │    │        InventoryItem            │◄──────┘
       │    ├─────────────────────────────────┤
       │    │ id (UUID)                       │
       │    │ product_id (FK) ────────────────┼───► Product
       │    │ location_id (FK) ───────────────┼───► Location
       │    │ physical_stock (≥0)             │
       │    │ buffer (≥0)                     │
       │    │ reorder_point (≥0)              │
       │    │ version (optimistic lock)       │
       │    └───────────┬─────────────────────┘
       │                │
       │    ┌───────────┼───────────┐
       │    │           │           │
       │    ▼           ▼           │
       │ ┌─────────┐ ┌─────────────┐│
       │ │  Batch  │ │StockMovement││
       │ ├─────────┤ ├─────────────┤│
       │ │ id      │ │ id          ││
       │ │ item_id │ │ item_id     ││
       │ │ quantity│ │ type        ││
       │ │ expiry  │ │ reason      ││
       │ │ batch_# │ │ qty_delta   ││
       └─┤         │ │ qty_before  ││
         │         │ │ qty_after   ││
         │         │ │ user_id ────┼┼───► User
         └─────────┘ │ reference   ││
                     │ notes       ││
                     │ created_at  ││
                     └─────────────┘│
                           ▲        │
                           │        │
                      (IMMUTABLE - APPEND ONLY)
```

### Core Entities

#### Product

```python
class Product(BaseModel, SoftDeleteMixin):
    """Product catalog entry with SKU management."""
    
    __tablename__ = "products"
    
    sku: str              # Unique, IMMUTABLE after creation (e.g., "MILK-2L-WHOLE")
    name: str             # Display name
    category: str         # dairy, bakery, beverages, etc.
    unit_price: Decimal   # Selling price (CHECK: >= 0)
    cost_price: Decimal   # Purchase cost (optional)
    tax_rate: Decimal     # 0.0 to 1.0 (CHECK: 0 <= x <= 1)
    barcode: str          # UPC/EAN (unique if provided)
    is_perishable: bool   # Requires expiry tracking
    shelf_life_days: int  # Default expiry period
    requires_cold_storage: bool
```

**Key Constraints:**
- `sku` is immutable - create new product if SKU needs to change
- `unit_price >= 0` enforced at database level
- Soft delete via `is_active` flag

#### InventoryItem

```python
class InventoryItem(BaseModel, SoftDeleteMixin, VersionedMixin):
    """Stock level for a product at a specific location."""
    
    __tablename__ = "inventory_items"
    
    product_id: str       # FK to Product
    location_id: str      # FK to Location
    physical_stock: int   # Actual units on hand (CHECK: >= 0)
    buffer: int           # Reserved/safety stock (CHECK: >= 0)
    reorder_point: int    # Alert threshold (CHECK: >= 0)
    max_stock: int        # Location capacity limit
    version: int          # Optimistic locking counter
```

**Key Behaviors:**
- `online_available = max(physical_stock - buffer, 0)` (computed, not stored)
- Unique constraint on `(product_id, location_id)`
- `version` increments on every update for concurrency control

#### InventoryBatch

```python
class InventoryBatch(BaseModel):
    """Batch tracking for perishables (FIFO management)."""
    
    __tablename__ = "inventory_batches"
    
    inventory_item_id: str   # FK to InventoryItem
    batch_number: str        # Supplier lot number
    quantity: int            # Units in this batch (CHECK: >= 0)
    expiry_date: datetime    # When batch expires
    received_date: datetime  # When received
    cost_per_unit: Decimal   # Batch-specific cost
```

**Key Behaviors:**
- Batches ordered by `expiry_date ASC` for FIFO selling
- Sum of batch quantities should equal parent's `physical_stock`

#### StockMovement

```python
class StockMovement(BaseModel):
    """Immutable audit record of every stock change."""
    
    __tablename__ = "stock_movements"
    
    inventory_item_id: str   # Which item changed
    movement_type: str       # receiving, sale, adjustment, etc.
    reason: str              # Detailed reason code
    quantity_delta: int      # Change amount (+/-)
    quantity_before: int     # Stock before change
    quantity_after: int      # Stock after change
    user_id: str             # Who made the change
    reference_id: str        # Order ID, PO number, etc.
    notes: str               # Staff explanation
    created_at: datetime     # When it happened
```

**Key Behaviors:**
- **IMMUTABLE** - Records are never updated or deleted
- Every stock operation creates a movement record
- Enables full audit trail reconstruction

#### Location

```python
class Location(BaseModel, SoftDeleteMixin):
    """Physical storage location in the store."""
    
    __tablename__ = "locations"
    
    code: str              # Unique identifier (e.g., "COLD-01")
    name: str              # Display name
    location_type: str     # floor, cold_storage, backroom, receiving
    capacity: int          # Max units (optional)
    temperature_zone: str  # chilled, frozen (for cold storage)
```

**Location Types:**
| Type | Description |
|------|-------------|
| `floor` | Customer-accessible shelves |
| `cold_storage` | Refrigerated/frozen storage |
| `backroom` | Back-of-store overflow |
| `receiving` | Incoming delivery staging |
| `damaged` | Damaged goods holding |

---

## 🔐 Authentication & Authorization

### JWT-Based Authentication

```
┌──────────┐     POST /auth/login      ┌──────────┐
│  Client  │ ─────────────────────────►│  Server  │
│          │  {email, password}        │          │
│          │◄───────────────────────── │          │
│          │  {access_token,           │          │
│          │   refresh_token}          │          │
└──────────┘                           └──────────┘
     │
     │  Subsequent requests:
     │  Authorization: Bearer <access_token>
     ▼
┌──────────────────────────────────────────────────┐
│            Protected Endpoint                     │
└──────────────────────────────────────────────────┘
```

### Token Structure

```json
{
  "sub": "user-uuid",           // User ID
  "role": "manager",            // User role
  "type": "access",             // Token type
  "exp": 1705123456,            // Expiration timestamp
  "iat": 1705119856             // Issued at
}
```

### Token Lifetimes

| Token Type | Lifetime | Purpose |
|------------|----------|---------|
| Access Token | 30 minutes | API authentication |
| Refresh Token | 7 days | Obtain new access tokens |

### Role Hierarchy

```
         ADMIN (100)
             │
             ▼
        MANAGER (75)
             │
             ▼
       SUPERVISOR (50)
             │
             ▼
         STAFF (25)
```

### Permission Matrix

| Action | Staff | Supervisor | Manager | Admin |
|--------|:-----:|:----------:|:-------:|:-----:|
| View stock levels | ✅ | ✅ | ✅ | ✅ |
| Receive stock | ✅ | ✅ | ✅ | ✅ |
| Reserve/Release stock | ✅ | ✅ | ✅ | ✅ |
| Fulfill orders | ✅ | ✅ | ✅ | ✅ |
| **Adjust stock** | ❌ | ❌ | ✅ | ✅ |
| **Dispose stock** | ❌ | ❌ | ✅ | ✅ |
| **View audit logs** | ❌ | ❌ | ✅ | ✅ |
| **Export audit data** | ❌ | ❌ | ✅ | ✅ |
| Manage users | ❌ | ❌ | ❌ | ✅ |

### FastAPI Dependencies

```python
from src.api.deps import (
    CurrentUser,      # Extract user from JWT
    DbSession,        # Database session
    RequireStaff,     # Minimum: Staff role
    RequireManager,   # Minimum: Manager role
    RequireAdmin,     # Minimum: Admin role
)

@router.post("/adjust", dependencies=[RequireManager])
async def adjust_stock(user: CurrentUser, db: DbSession):
    # Only Manager+ can access this endpoint
    pass
```

---

## 🔧 API Reference

### Documentation URLs

| URL | Description |
|-----|-------------|
| `http://localhost:8000/docs` | Swagger UI (Interactive) |
| `http://localhost:8000/redoc` | ReDoc (Clean) |
| `http://localhost:8000/openapi.json` | Raw OpenAPI schema |

### Authentication in Swagger UI

1. Click the **Authorize** button (🔓)
2. Enter: `Bearer <your-jwt-token>`
3. Click **Authorize**

### Example Requests

#### Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "manager@kinmel-test.local",
    "password": "TestPassword123!"
  }'
```

#### Get Stock Level

```bash
curl http://localhost:8000/api/v1/inventory/stock/MILK-2L-WHOLE \
  -H "Authorization: Bearer <token>"
```

#### Receive Stock

```bash
curl -X POST http://localhost:8000/api/v1/inventory/receive \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "sku": "MILK-2L-WHOLE",
    "location_id": "<location-uuid>",
    "quantity": 50,
    "batch_number": "BATCH-001",
    "expiry_date": "2024-02-15T00:00:00Z"
  }'
```

#### Adjust Stock (Manager+)

```bash
curl -X POST http://localhost:8000/api/v1/inventory/adjust \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "sku": "MILK-2L-WHOLE",
    "location_id": "<location-uuid>",
    "new_quantity": 45,
    "reason": "cycle_count",
    "notes": "Cycle count correction - 5 units missing"
  }'
```

#### Query Audit Log (Manager+)

```bash
curl "http://localhost:8000/api/v1/admin/audit-log?sku=MILK-2L&action_type=sale&limit=50" \
  -H "Authorization: Bearer <token>"
```

### Route Summary

#### Inventory Module (`/api/v1/inventory`)

| Method | Endpoint | Description | Min Role |
|--------|----------|-------------|----------|
| POST | `/receive` | Receive stock from supplier | Staff |
| POST | `/adjust` | Manual stock adjustment | Manager |
| POST | `/reserve` | Reserve for online order | Staff |
| POST | `/release` | Release reservation | Staff |
| POST | `/fulfill` | Fulfill order (sell) | Staff |
| POST | `/dispose` | Dispose expired/damaged | Manager |
| GET | `/stock/{sku}` | Get stock level | Staff |
| GET | `/alerts/low-stock` | Low stock items | Staff |
| GET | `/alerts/expiring` | Expiring batches | Staff |
| GET | `/history/{sku}` | Movement history | Staff |

#### Admin Module (`/api/v1/admin`)

| Method | Endpoint | Description | Min Role |
|--------|----------|-------------|----------|
| GET | `/audit-log` | Query audit trail | Manager |
| GET | `/audit-log/export.csv` | Export as CSV | Manager |
| GET | `/audit-log/stats` | Aggregated statistics | Manager |
| GET | `/audit-log/action-types` | List valid types | Any |

### Export OpenAPI

```bash
# Export JSON
python scripts/export_openapi.py -o docs/openapi.json

# Export YAML
python scripts/export_openapi.py --yaml -o docs/openapi.yaml

# Generate static HTML docs
python scripts/export_openapi.py --html --swagger
```

---

## 🗃️ Database & Migrations

### Alembic Setup

```
alembic/
├── alembic.ini          # Configuration
├── env.py               # Async SQLAlchemy setup
├── script.py.mako       # Migration template
└── versions/
    └── 20241214_0001_initial_schema.py
```

### Migration Commands

```bash
# Apply all pending migrations
python scripts/db.py migrate

# Check current status
python scripts/db.py status

# Rollback one migration
python scripts/db.py rollback

# Generate new migration (review before applying!)
python scripts/db.py generate "add_supplier_table"

# Verify models match schema
python scripts/db.py verify

# Reset database (dev only!)
python scripts/db.py reset --force
```

### Database Constraints

All critical business rules are enforced at the database level:

```sql
-- Stock cannot go negative
CHECK (physical_stock >= 0)
CHECK (buffer >= 0)
CHECK (reorder_point >= 0)

-- Batch quantity constraint
CHECK (quantity >= 0)

-- Price constraints
CHECK (unit_price >= 0)
CHECK (tax_rate >= 0 AND tax_rate <= 1)

-- Unique constraints
UNIQUE (sku)
UNIQUE (product_id, location_id)
UNIQUE (locations.code)
```

### Optimistic Locking

```python
# Read item with version
item = await repo.get_by_id(session, item_id)
print(item.version)  # 5

# Update with version check
await repo.update_stock_optimistic(
    session,
    item_id=item.id,
    new_physical_stock=45,
    expected_version=5,  # Must match current
)
# If another process updated first → ConcurrencyError
```

### Seed Data

```bash
# Seed all test data
python scripts/seed_data.py

# Seed specific entities
python scripts/seed_data.py --users
python scripts/seed_data.py --products
python scripts/seed_data.py --inventory

# Clear and reseed
python scripts/seed_data.py --clear --all
```

**Test Credentials:**
```
Password: TestPassword123!

Users:
- owner@kinmel-test.local     (Admin)
- manager@kinmel-test.local   (Manager)
- supervisor@kinmel-test.local (Supervisor)
- staff1@kinmel-test.local    (Staff)
- staff2@kinmel-test.local    (Staff)
```

---

## 🔄 Inventory Actions

### Stock Flow Diagram

```
         ┌─────────────┐
         │  Supplier   │
         └──────┬──────┘
                │
                ▼ receive_stock()
         ┌─────────────┐
         │  Backroom   │
         │   Storage   │
         └──────┬──────┘
                │
                ▼ transfer_stock()
         ┌─────────────┐
         │    Floor    │◄────── reserve_stock()
         │   Shelves   │             │
         └──────┬──────┘             │
                │                    │
    ┌───────────┼───────────┐       │
    │           │           │       │
    ▼           ▼           ▼       │
fulfill()  dispose()   release() ◄──┘
    │           │           │
    ▼           ▼           ▼
┌─────────┐ ┌─────────┐ ┌─────────┐
│ Customer│ │ Disposal│ │ Cancel  │
│  Sale   │ │ Record  │ │ Order   │
└─────────┘ └─────────┘ └─────────┘
```

### Action Details

#### `receive_stock()`

Records incoming inventory from suppliers.

```python
# Input
ReceivingInput(
    sku="MILK-2L-WHOLE",
    location_id="uuid",
    quantity=50,
    user_id="user-uuid",
    batch_number="BATCH-001",      # For perishables
    expiry_date=datetime(...),     # For perishables
    cost_per_unit=Decimal("3.20"),
    reference_id="PO-2024-001",    # Purchase order
)

# Effects
# 1. Creates InventoryItem if first time at location
# 2. Increments physical_stock by quantity
# 3. Creates InventoryBatch if expiry_date provided
# 4. Records StockMovement (type=receiving)
```

#### `adjust_stock()`

Manual stock corrections (Manager+ only).

```python
# Input
AdjustmentInput(
    sku="MILK-2L-WHOLE",
    location_id="uuid",
    new_quantity=45,               # Absolute value, not delta
    user_id="manager-uuid",
    reason=MovementReason.CYCLE_COUNT,
    notes="Cycle count found 5 missing",
    skip_large_adjustment_check=False,
)

# Effects
# 1. Calculates delta from current stock
# 2. If delta > 50% of current → requires confirmation
# 3. Updates physical_stock to new_quantity
# 4. Records StockMovement (type=adjustment)
```

**Valid Adjustment Reasons:**
- `cycle_count` - Physical count correction
- `audit_correction` - Auditor adjustment
- `system_correction` - System fix
- `shrinkage` - Unexplained loss

#### `reserve_stock()`

Holds stock for online orders.

```python
# Input
ReservationInput(
    sku="MILK-2L-WHOLE",
    location_id="uuid",
    quantity=5,
    user_id="user-uuid",
    order_id="ONLINE-001",
)

# Effects
# 1. Validates online_available >= quantity
# 2. Increments buffer by quantity
# 3. online_available decreases automatically
# 4. Records StockMovement (type=reservation)
```

#### `release_reservation()`

Cancels a reservation.

```python
# Effects
# 1. Decrements buffer by quantity
# 2. online_available increases automatically
# 3. Records StockMovement (reason=reservation_released)
```

#### `fulfill_order()`

Processes a sale.

```python
# Effects
# 1. Decrements physical_stock by quantity
# 2. Decrements buffer if was reserved
# 3. Decrements batch quantities (FIFO)
# 4. Records StockMovement (type=sale)
```

#### `dispose_stock()`

Removes expired or damaged stock (Manager+ only).

```python
# Input
reason: MovementReason  # expired, damaged, shrinkage
batch_id: str | None    # Specific batch to dispose

# Effects
# 1. Decrements physical_stock
# 2. Decrements batch quantity if specified
# 3. Records StockMovement (type=disposal)
```

### Concurrency Safety

**Optimistic Locking Pattern:**

```python
# 1. Read current state
item = await repo.get_by_id(session, item_id)
current_version = item.version

# 2. Business logic
new_stock = item.physical_stock + quantity

# 3. Atomic update with version check
# UPDATE ... WHERE id = ? AND version = ?
success = await repo.update_stock_optimistic(
    session,
    item_id=item.id,
    new_physical_stock=new_stock,
    expected_version=current_version,
)

# 4. If version mismatch → ConcurrencyError
# Caller should retry the entire operation
```

**Pessimistic Locking (for high-contention):**

```python
# SELECT ... FOR UPDATE
item = await repo.get_by_id(
    session,
    item_id,
    for_update=True,  # Lock row until commit
)
```

---

## 🔔 Background Tasks

### Celery Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Celery Beat                            │
│              (Scheduler - runs periodically)                │
└──────────────────────────┬──────────────────────────────────┘
                           │ Schedules tasks
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                        Redis                                │
│                   (Message Broker)                          │
└──────────────────────────┬──────────────────────────────────┘
                           │ Task queue
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Celery Workers                           │
│                  (Execute tasks)                            │
└──────────────────────────┬──────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌───────────┐   ┌───────────┐   ┌───────────┐
    │  Slack    │   │   Email   │   │  Webhook  │
    │  Alerts   │   │  Digest   │   │   Notify  │
    └───────────┘   └───────────┘   └───────────┘
```

### Running Celery

```bash
# Start worker (processes tasks)
celery -A src.tasks.celery_app worker --loglevel=info

# Start beat scheduler (schedules periodic tasks)
celery -A src.tasks.celery_app beat --loglevel=info

# Combined (development only)
celery -A src.tasks.celery_app worker --beat --loglevel=info

# With specific queues
celery -A src.tasks.celery_app worker -Q high_priority,default,low_priority
```

### Scheduled Tasks

| Task | Schedule | Queue | Purpose |
|------|----------|-------|---------|
| `check_critical_stock` | Every 5 min | high_priority | Out of stock alerts |
| `check_low_stock_levels` | Every 15 min | high_priority | Low stock warnings |
| `check_expiring_products` | Daily 6 AM | default | Expiry alerts |
| `generate_daily_summary` | Daily midnight | low_priority | Health report |
| `send_inventory_digest` | Daily 8 AM | low_priority | Manager digest |
| `generate_movement_report` | Monday 1 AM | low_priority | Weekly audit |
| `reconcile_batch_totals` | Sunday 2 AM | default | Data integrity |

### Notification Channels

```python
from src.tasks.notifications import send_alert, AlertSeverity, AlertCategory

# Send alert through all configured channels
send_alert(
    title="Low Stock: MILK-2L-WHOLE",
    message="Stock is at 5 units, below reorder point of 10",
    severity=AlertSeverity.WARNING,
    category=AlertCategory.LOW_STOCK,
    data={"sku": "MILK-2L", "current": 5, "reorder_point": 10},
)
```

**Configured Channels:**
- **Log** (always enabled) - Structured logging for audit
- **Slack** - Via incoming webhook
- **Email** - SMTP or transactional service
- **Webhook** - Generic HTTP POST

### Configuration

```bash
# .env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
ALERT_WEBHOOK_URL=https://your-alerting-service.com/webhook
SMTP_HOST=smtp.gmail.com
EMAIL_FROM=alerts@kinmel.local
ALERT_EMAIL_RECIPIENTS=manager1@example.com,manager2@example.com
```

### Manual Task Triggers

```python
from src.tasks import (
    trigger_low_stock_check,
    trigger_expiry_check,
    trigger_daily_summary,
)

# Trigger immediately
result = trigger_low_stock_check()
result = trigger_expiry_check(days_ahead=3)
result = trigger_daily_summary()

# Check result (if task returns one)
print(result.get())
```

### Task Features

| Feature | Implementation |
|---------|----------------|
| **Retry Logic** | Exponential backoff, max 3 retries |
| **Idempotency** | Redis-based distributed locks |
| **Deduplication** | Alert suppression for 1 hour |
| **Rate Limiting** | Per-category limits (20/hour) |
| **Logging** | Structured logs with correlation IDs |

---

## 📊 Admin & Audit System

### Audit Log Endpoint

```bash
GET /api/v1/admin/audit-log
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `sku` | string | Filter by product SKU |
| `location_code` | string | Filter by location |
| `action_type` | enum | receiving, sale, adjustment, etc. |
| `reason` | enum | Specific reason code |
| `performed_by` | string | User name (partial match) |
| `start_date` | datetime | Period start (ISO 8601) |
| `end_date` | datetime | Period end (ISO 8601) |
| `reference_id` | string | Order/PO number |
| `limit` | int | Max records (1-500, default 50) |
| `offset` | int | Skip records |

**Example:**

```bash
curl "http://localhost:8000/api/v1/admin/audit-log?\
sku=MILK-2L&\
action_type=sale&\
start_date=2024-01-01T00:00:00Z&\
limit=100" \
  -H "Authorization: Bearer <manager-token>"
```

**Response:**

```json
{
  "entries": [
    {
      "sku": "MILK-2L-WHOLE",
      "product_name": "Whole Milk 2L",
      "location_code": "FLOOR-A1",
      "location_name": "Aisle 1 - Dairy",
      "action_type": "sale",
      "reason": "customer_sale",
      "quantity_delta": -2,
      "quantity_before": 50,
      "quantity_after": 48,
      "performed_by": "John Smith",
      "timestamp": "2024-01-15T14:30:00Z",
      "reference_id": "ORD-2024-001",
      "notes": null,
      "change_direction": "decrease"
    }
  ],
  "total": 150,
  "limit": 100,
  "offset": 0,
  "has_more": true,
  "page": 1,
  "total_pages": 2
}
```

### CSV Export

```bash
GET /api/v1/admin/audit-log/export.csv?start_date=2024-01-01
```

**CSV Columns:**
```
timestamp,sku,product_name,location_code,location_name,action_type,
reason,quantity_delta,quantity_before,quantity_after,performed_by,
reference_id,reference_type,notes
```

### Statistics Endpoint

```bash
GET /api/v1/admin/audit-log/stats?start_date=2024-01-01&end_date=2024-01-31
```

**Response:**

```json
{
  "period_start": "2024-01-01T00:00:00Z",
  "period_end": "2024-01-31T23:59:59Z",
  "total_actions": 1500,
  "total_units_increased": 5000,
  "total_units_decreased": 4500,
  "net_stock_change": 500,
  "by_action_type": [
    {"action_type": "sale", "count": 1000, "total_units_affected": 3500}
  ],
  "by_day": [
    {"date": "2024-01-31", "total_actions": 50, "net_change": 20}
  ],
  "top_products": [
    {"sku": "MILK-2L", "name": "Whole Milk", "movement_count": 150}
  ],
  "top_users": [
    {"name": "John Smith", "action_count": 200}
  ]
}
```

### Privacy Considerations

The audit API intentionally:
- ✅ Uses business identifiers (SKU, location code) not UUIDs
- ✅ Shows user display name, not email
- ✅ Restricts access to Manager+ roles
- ✅ Logs all audit queries for meta-audit

---

## 🧪 Testing & Development

### Test Structure

```
tests/
├── conftest.py              # Pytest fixtures
├── test_inventory_api.py    # API endpoint tests
├── test_inventory_models.py # Model unit tests
└── test_inventory_service.py # Service layer tests
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_inventory_api.py

# Run specific test
pytest tests/test_inventory_api.py::test_receive_stock

# Skip slow tests
pytest -m "not slow"

# Run only integration tests
pytest -m integration
```

### Test Database

Tests use a separate database or SQLite in-memory:

```python
# conftest.py
@pytest.fixture
async def db_session():
    # Creates isolated test database
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSession(test_engine) as session:
        yield session
```

### Development Workflow

```bash
# 1. Start Redis (database is local SQLite file)
docker-compose up -d redis

# 2. Run migrations (creates/updates ./kinmel.db)
python scripts/db.py migrate

# 3. Seed test data
python scripts/seed_data.py

# 4. Start server with hot reload
uvicorn src.main:app --reload

# 5. Start Celery (in separate terminal)
celery -A src.tasks.celery_app worker --beat --loglevel=info

# 6. Run tests before committing
pytest
ruff check src/
mypy src/
```

### Resetting Development Data

```bash
# Clear everything and reseed
python scripts/seed_data.py --clear --force

# Or reset database completely
python scripts/db.py reset --force
python scripts/seed_data.py
```

---

## 🧰 Operational Tips

### Environment Variables

```bash
# Application
APP_ENV=development              # development, staging, production
DEBUG=true                       # Enable debug mode
SECRET_KEY=your-secret-key-here  # JWT signing key (min 32 chars)

# Database
DATABASE_URL=sqlite+aiosqlite:///./kinmel.db
DB_POOL_SIZE=10
DB_POOL_OVERFLOW=20

# Redis
REDIS_URL=redis://localhost:6379/0

# to clear ratelimit of redis:
# redis-cli DEL "otp:reset_attempts:adhikarisuman372@gmail.com"
# JWT
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Inventory Settings
LOW_STOCK_THRESHOLD_PERCENT=20
EXPIRY_WARNING_DAYS=7
MAX_STOCK_ADJUSTMENT_PERCENT=50

# Notifications
SLACK_WEBHOOK_URL=
ALERT_WEBHOOK_URL=
SMTP_HOST=
EMAIL_FROM=
ALERT_EMAIL_RECIPIENTS=
```

### CLI Tools

```bash
# Database management
python scripts/db.py migrate       # Apply migrations
python scripts/db.py status        # Show migration status
python scripts/db.py rollback      # Rollback one migration
python scripts/db.py generate "name"  # Create new migration
python scripts/db.py verify        # Check for schema drift
python scripts/db.py reset         # Reset database (dev only)

# Test data
python scripts/seed_data.py        # Seed all data
python scripts/seed_data.py --clear  # Clear all data

# Documentation
python scripts/export_openapi.py   # Export OpenAPI schema
python scripts/export_openapi.py --html  # Generate static docs
```

### Running in Production

```bash
# Use Gunicorn with Uvicorn workers
gunicorn src.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000

# Run Celery with production settings
celery -A src.tasks.celery_app worker \
  --loglevel=warning \
  --concurrency=4

celery -A src.tasks.celery_app beat \
  --loglevel=warning
```

### Health Checks

```bash
# Application health
curl http://localhost:8000/health
# {"status": "healthy", "service": "kinmel"}

# Readiness (dependencies check)
curl http://localhost:8000/ready
# {"status": "ready", "service": "kinmel"}
```

---

## 📁 Documentation Assets

### Files

| Path | Description |
|------|-------------|
| `README.md` | This document |
| `docs/API.md` | API quick reference |
| `docs/openapi.json` | OpenAPI schema (generated) |
| `docs/index.html` | Static HTML docs (generated) |
| `alembic/README.md` | Migration guide |

### Generating Documentation

```bash
# Export OpenAPI schema
python scripts/export_openapi.py -o docs/openapi.json

# Generate static HTML (Redoc)
python scripts/export_openapi.py --html

# Generate Swagger UI HTML
python scripts/export_openapi.py --swagger

# All at once
python scripts/export_openapi.py -o docs/openapi.json --html --swagger
```

### Keeping Docs Updated

1. **OpenAPI Schema**: Auto-generated from code, re-export after API changes
2. **README.md**: Update manually when adding features
3. **API.md**: Quick reference, update with new endpoints

### Sharing Documentation

- **Internal Team**: Point to `/docs` on running server
- **External Consumers**: Share `openapi.json` for Postman/Insomnia import
- **Static Hosting**: Deploy `docs/index.html` to GitHub Pages or S3

---

## 📞 Support

- **Issues**: File in GitHub repository
- **Email**: inventory-team@kinmel.local
- **Slack**: #inventory-backend

---

*Last updated: December 2024*
*Documentation version: 1.0.0*

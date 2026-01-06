/**
 * Kinmel Documentation - JavaScript
 */

// Content sections - embedded markdown content
const SECTIONS = {
    'overview': `
# Kinmel Documentation

> A **fault-tolerant, staff-proof** backend for grocery store inventory operations.

<div class="hero-badges">
    <span class="hero-badge">🐍 Python 3.11+</span>
    <span class="hero-badge">⚡ FastAPI</span>
    <span class="hero-badge">🗃️ PostgreSQL</span>
    <span class="hero-badge">📦 SQLAlchemy 2.0</span>
</div>

---

## What is Kinmel?

Kinmel is a production-grade inventory management system designed for grocery stores. It provides:

- **📦 Stock Tracking** - Real-time inventory levels across multiple locations
- **🥛 Perishable Management** - FIFO batch tracking with expiry dates
- **📝 Complete Audit Trail** - Immutable log of every stock change
- **🔐 Role-Based Access** - Granular permissions for staff, managers, and admins
- **🔔 Smart Alerts** - Automated low-stock and expiry notifications

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Language** | Python 3.11+ |
| **Framework** | FastAPI 0.109 |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Database** | PostgreSQL 15+ |
| **Migrations** | Alembic 1.13 |
| **Validation** | Pydantic v2 |
| **Background Jobs** | Celery 5.3 + Redis |
| **Auth** | JWT (PyJWT) |

## Architecture

The system follows a **Modular Monolith** architecture with domain-driven modules:

\`\`\`
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI App                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │Inventory│  │  Admin  │  │  Users  │  │Products │        │
│  │ Module  │  │ Module  │  │ Module  │  │ Module  │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
│       └────────────┴────────────┴────────────┘              │
│                    Core Services                            │
│            (database, security, logging)                    │
└─────────────────────────────────────────────────────────────┘
\`\`\`

## Quick Links

- [Quick Start Guide](#quick-start) - Get up and running in 10 minutes
- [API Reference](api-reference.html) - Full endpoint documentation
- [OpenAPI Spec](openapi.html) - Interactive API explorer
`,

    'quick-start': `
# Quick Start

Get Kinmel running locally in under 10 minutes.

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+

## Installation

\`\`\`bash
# Clone repository
git clone <repo-url>
cd backend-kinmel

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt
\`\`\`

## Configuration

\`\`\`bash
# Copy environment template
cp .env.example .env

# Edit with your database credentials
# Required: DATABASE_URL, SECRET_KEY
\`\`\`

## Database Setup

\`\`\`bash
# Run migrations
python scripts/db.py migrate

# Seed test data
python scripts/seed_data.py
\`\`\`

## Start the Server

\`\`\`bash
uvicorn src.main:app --reload
\`\`\`

## Verify Installation

\`\`\`bash
# Health check
curl http://localhost:8000/health
# Expected: {"status": "healthy", "service": "kinmel"}

# Open API docs
open http://localhost:8000/docs
\`\`\`

## Test Credentials

After seeding, you can use these accounts:

| Email | Role | Password |
|-------|------|----------|
| owner@kinmel-test.local | Admin | TestPassword123! |
| manager@kinmel-test.local | Manager | TestPassword123! |
| staff1@kinmel-test.local | Staff | TestPassword123! |

## Next Steps

1. Explore the [API Reference](api-reference.html)
2. Read the [Developer Guide](#developer-guide)
3. Review [Domain Models](#domain-model)
`,

    'developer-guide': `
# Developer Guide

Quick reference for developers working on the Kinmel backend.

## Project Structure

\`\`\`
backend-kinmel/
├── src/
│   ├── main.py                 # FastAPI app entry point
│   ├── api/                    # API layer (deps, middleware)
│   ├── core/                   # Core utilities (config, db, security)
│   ├── modules/                # Domain modules
│   │   ├── inventory/          # Stock management
│   │   ├── products/           # Product catalog
│   │   ├── users/              # User accounts
│   │   └── admin/              # Audit & admin
│   └── tasks/                  # Celery background tasks
├── alembic/                    # Database migrations
├── scripts/                    # CLI utilities
├── tests/                      # Test suite
└── docs/                       # Documentation
\`\`\`

## Key Concepts

### Stock Formula

\`\`\`
online_available = max(physical_stock - buffer, 0)
\`\`\`

- \`physical_stock\`: What's actually on the shelf
- \`buffer\`: Reserved stock (online orders, safety margin)
- \`online_available\`: What can be sold online

### Audit Trail

Every stock change creates an immutable \`StockMovement\` record:

\`\`\`python
# When you call:
await inventory_service.receive_stock(...)

# Behind the scenes:
# 1. physical_stock increases
# 2. StockMovement record created (IMMUTABLE)
# 3. Batch record created (if perishable)
\`\`\`

### Concurrency Control

\`\`\`python
# Optimistic locking prevents lost updates
item.version = 5
# UPDATE ... SET version=6 WHERE version=5
# If 0 rows affected → ConcurrencyError → retry
\`\`\`

## Common Tasks

### Add a New Endpoint

\`\`\`python
# 1. Add to router (src/modules/inventory/router.py)
@router.post("/my-action", dependencies=[RequireStaff])
async def my_action(
    request: MyRequest,
    user: CurrentUser,
    db: DbSession,
) -> MyResponse:
    result = await inventory_service.my_action(db, request, user.sub)
    return MyResponse(**result)

# 2. Add schema (src/modules/inventory/schemas.py)
class MyRequest(StrictModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)

# 3. Add service method (src/modules/inventory/service.py)
async def my_action(self, session, input, user_id):
    # Business logic here
    pass
\`\`\`

### Add a Migration

\`\`\`bash
# Modify your model, then:
python scripts/db.py generate "add_column_name"

# Review generated file, then apply:
python scripts/db.py migrate
\`\`\`

## Code Style

\`\`\`bash
# Format
ruff format src/

# Lint
ruff check src/

# Type check
mypy src/

# Run tests
pytest
\`\`\`
`,

    'domain-model': `
# Domain Model

Core entities and their relationships in the Kinmel system.

## Entity Diagram

\`\`\`
┌─────────────┐       ┌─────────────────┐       ┌──────────────┐
│    User     │       │     Product     │       │   Location   │
├─────────────┤       ├─────────────────┤       ├──────────────┤
│ id (UUID)   │       │ id (UUID)       │       │ id (UUID)    │
│ email       │       │ sku (UNIQUE)    │       │ code (UNIQUE)│
│ role        │       │ name            │       │ location_type│
│ is_active   │       │ category        │       │ capacity     │
└──────┬──────┘       └────────┬────────┘       └──────┬───────┘
       │                       │                        │
       │                       ▼                        │
       │              ┌─────────────────┐              │
       │              │  InventoryItem  │◄─────────────┘
       │              ├─────────────────┤
       │              │ physical_stock  │
       │              │ buffer          │
       │              │ version         │
       │              └────────┬────────┘
       │                       │
       │              ┌────────┴────────┐
       │              ▼                 ▼
       │         ┌─────────┐    ┌─────────────┐
       └────────►│  Batch  │    │StockMovement│
                 └─────────┘    └─────────────┘
                                 (IMMUTABLE)
\`\`\`

## Product

Product catalog entry with SKU management.

| Field | Type | Constraints |
|-------|------|-------------|
| sku | string | UNIQUE, IMMUTABLE |
| name | string | Required |
| category | enum | dairy, bakery, etc. |
| unit_price | decimal | >= 0 |
| is_perishable | boolean | Default: false |
| shelf_life_days | integer | For perishables |

## InventoryItem

Stock level for a product at a specific location.

| Field | Type | Constraints |
|-------|------|-------------|
| product_id | FK | Required |
| location_id | FK | Required |
| physical_stock | integer | >= 0 (DB enforced) |
| buffer | integer | >= 0 (DB enforced) |
| reorder_point | integer | >= 0 |
| version | integer | Optimistic lock |

**Computed:**
\`\`\`
online_available = max(physical_stock - buffer, 0)
\`\`\`

## InventoryBatch

Batch tracking for perishables (FIFO).

| Field | Type | Constraints |
|-------|------|-------------|
| inventory_item_id | FK | Required |
| batch_number | string | Supplier lot number |
| quantity | integer | >= 0 |
| expiry_date | datetime | For FIFO sorting |

## StockMovement

Immutable audit record.

| Field | Type | Description |
|-------|------|-------------|
| movement_type | enum | receiving, sale, adjustment, etc. |
| quantity_delta | integer | Change amount (+/-) |
| quantity_before | integer | Stock before |
| quantity_after | integer | Stock after |
| user_id | FK | Who made change |
| reference_id | string | Order ID, PO number |

> ⚠️ **IMMUTABLE** - Records are never updated or deleted.
`,

    'authentication': `
# Authentication & Authorization

JWT-based authentication with role-based access control.

## Authentication Flow

\`\`\`
┌──────────┐     POST /auth/login      ┌──────────┐
│  Client  │ ─────────────────────────►│  Server  │
│          │  {email, password}        │          │
│          │◄───────────────────────── │          │
│          │  {access_token,           │          │
│          │   refresh_token}          │          │
└──────────┘                           └──────────┘
     │
     │  Authorization: Bearer <access_token>
     ▼
┌──────────────────────────────────────┐
│         Protected Endpoint            │
└──────────────────────────────────────┘
\`\`\`

## Token Lifetimes

| Token | Lifetime | Purpose |
|-------|----------|---------|
| Access Token | 30 min | API authentication |
| Refresh Token | 7 days | Obtain new access tokens |

## Role Hierarchy

\`\`\`
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
\`\`\`

## Permission Matrix

| Action | Staff | Supervisor | Manager | Admin |
|--------|:-----:|:----------:|:-------:|:-----:|
| View stock | ✅ | ✅ | ✅ | ✅ |
| Receive stock | ✅ | ✅ | ✅ | ✅ |
| Reserve/Release | ✅ | ✅ | ✅ | ✅ |
| **Adjust stock** | ❌ | ❌ | ✅ | ✅ |
| **Dispose stock** | ❌ | ❌ | ✅ | ✅ |
| **View audit logs** | ❌ | ❌ | ✅ | ✅ |
| Manage users | ❌ | ❌ | ❌ | ✅ |

## Using in API Calls

\`\`\`bash
# Get token
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"email":"manager@kinmel-test.local","password":"TestPassword123!"}' \\
  | jq -r '.access_token')

# Use token
curl localhost:8000/api/v1/inventory/stock/MILK-2L \\
  -H "Authorization: Bearer $TOKEN"
\`\`\`
`,

    'database': `
# Database & Migrations

PostgreSQL with Alembic migrations.

## Migration Commands

\`\`\`bash
# Apply all pending migrations
python scripts/db.py migrate

# Check status
python scripts/db.py status

# Rollback one migration
python scripts/db.py rollback

# Generate new migration
python scripts/db.py generate "add_column"

# Verify schema matches models
python scripts/db.py verify

# Reset (dev only!)
python scripts/db.py reset --force
\`\`\`

## Database Constraints

All business rules enforced at DB level:

\`\`\`sql
-- Stock cannot go negative
CHECK (physical_stock >= 0)
CHECK (buffer >= 0)
CHECK (reorder_point >= 0)

-- Price constraints
CHECK (unit_price >= 0)
CHECK (tax_rate >= 0 AND tax_rate <= 1)

-- Unique constraints
UNIQUE (sku)
UNIQUE (product_id, location_id)
\`\`\`

## Optimistic Locking

\`\`\`python
# Read with version
item = await repo.get_by_id(session, item_id)
print(item.version)  # 5

# Update with version check
await repo.update_stock_optimistic(
    session,
    item_id=item.id,
    new_physical_stock=45,
    expected_version=5,  # Must match
)
# If version mismatch → ConcurrencyError
\`\`\`

## Seeding Data

\`\`\`bash
# Seed all test data
python scripts/seed_data.py

# Seed specific entities
python scripts/seed_data.py --users
python scripts/seed_data.py --products
python scripts/seed_data.py --inventory

# Clear and reseed
python scripts/seed_data.py --clear --all
\`\`\`
`,

    'inventory-actions': `
# Inventory Actions

Core stock operations and their effects.

## Action Summary

| Action | Effect | Min Role |
|--------|--------|----------|
| receive_stock | +physical_stock | Staff |
| adjust_stock | ±physical_stock | Manager |
| reserve_stock | +buffer | Staff |
| release_reservation | -buffer | Staff |
| fulfill_order | -physical_stock, -buffer | Staff |
| dispose_stock | -physical_stock | Manager |

## Receive Stock

Records incoming inventory from suppliers.

\`\`\`python
POST /api/v1/inventory/receive
{
    "sku": "MILK-2L-WHOLE",
    "location_id": "uuid",
    "quantity": 50,
    "batch_number": "BATCH-001",
    "expiry_date": "2024-02-15T00:00:00Z"
}
\`\`\`

**Effects:**
1. Creates InventoryItem if first time at location
2. Increments physical_stock
3. Creates Batch if expiry provided
4. Records StockMovement

## Adjust Stock

Manual corrections (Manager+ only).

\`\`\`python
POST /api/v1/inventory/adjust
{
    "sku": "MILK-2L-WHOLE",
    "location_id": "uuid",
    "new_quantity": 45,
    "reason": "cycle_count",
    "notes": "Found 5 units missing"
}
\`\`\`

> ⚠️ Adjustments >50% require \`confirm_large_adjustment: true\`

## Reserve Stock

Holds stock for online orders.

\`\`\`python
POST /api/v1/inventory/reserve
{
    "sku": "MILK-2L-WHOLE",
    "location_id": "uuid",
    "quantity": 5,
    "order_id": "ONLINE-001"
}
\`\`\`

**Effects:**
- Increments buffer
- online_available decreases
- physical_stock unchanged

## Fulfill Order

Processes a sale.

\`\`\`python
POST /api/v1/inventory/fulfill
{
    "sku": "MILK-2L-WHOLE",
    "location_id": "uuid",
    "quantity": 5,
    "order_id": "ONLINE-001"
}
\`\`\`

**Effects:**
- Decrements physical_stock
- Decrements buffer
- Decrements batch quantities (FIFO)
`,

    'background-tasks': `
# Background Tasks

Celery-based task scheduling and alerts.

## Running Celery

\`\`\`bash
# Start worker
celery -A src.tasks.celery_app worker --loglevel=info

# Start scheduler
celery -A src.tasks.celery_app beat --loglevel=info

# Combined (dev only)
celery -A src.tasks.celery_app worker --beat --loglevel=info
\`\`\`

## Scheduled Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| check_critical_stock | Every 5 min | Out of stock alerts |
| check_low_stock_levels | Every 15 min | Low stock warnings |
| check_expiring_products | Daily 6 AM | Expiry alerts |
| generate_daily_summary | Daily midnight | Health report |
| send_inventory_digest | Daily 8 AM | Manager digest |

## Notification Channels

- **Log** - Always enabled
- **Slack** - Via webhook
- **Email** - SMTP
- **Webhook** - Generic HTTP POST

## Manual Triggers

\`\`\`python
from src.tasks import (
    trigger_low_stock_check,
    trigger_expiry_check,
    trigger_daily_summary,
)

# Trigger immediately
result = trigger_low_stock_check()
result = trigger_expiry_check(days_ahead=3)
\`\`\`

## Configuration

\`\`\`bash
# .env
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
ALERT_WEBHOOK_URL=https://alerts.example.com/webhook
\`\`\`
`,

    'audit-system': `
# Admin & Audit System

Query and export the immutable audit trail.

## Audit Log Endpoint

\`\`\`bash
GET /api/v1/admin/audit-log
\`\`\`

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| sku | string | Filter by product |
| action_type | enum | sale, receiving, etc. |
| start_date | datetime | Period start |
| end_date | datetime | Period end |
| performed_by | string | User name (partial) |
| limit | int | Max records (1-500) |
| offset | int | Skip records |

## Example Query

\`\`\`bash
curl "localhost:8000/api/v1/admin/audit-log?\\
sku=MILK-2L&\\
action_type=sale&\\
start_date=2024-01-01" \\
  -H "Authorization: Bearer <manager-token>"
\`\`\`

## CSV Export

\`\`\`bash
GET /api/v1/admin/audit-log/export.csv?start_date=2024-01-01
\`\`\`

## Statistics

\`\`\`bash
GET /api/v1/admin/audit-log/stats
\`\`\`

Returns:
- Total actions
- Net stock change
- Breakdown by action type
- Daily activity
- Top products
- Top users

## Access Control

> 🔐 All audit endpoints require **Manager** or **Admin** role.
`,

    'deployment': `
# Deployment

Running Kinmel in production.

## Environment Variables

\`\`\`bash
# Required
APP_ENV=production
SECRET_KEY=<generate-secure-key>
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
REDIS_URL=redis://host:6379/0

# Optional
SLACK_WEBHOOK_URL=
ALERT_EMAIL_RECIPIENTS=admin@example.com
\`\`\`

## Production Server

\`\`\`bash
# Gunicorn with Uvicorn workers
gunicorn src.main:app \\
  --workers 4 \\
  --worker-class uvicorn.workers.UvicornWorker \\
  --bind 0.0.0.0:8000

# Celery worker
celery -A src.tasks.celery_app worker \\
  --loglevel=warning \\
  --concurrency=4

# Celery beat
celery -A src.tasks.celery_app beat \\
  --loglevel=warning
\`\`\`

## Health Checks

\`\`\`bash
# Liveness
GET /health
# {"status": "healthy"}

# Readiness
GET /ready
# {"status": "ready"}
\`\`\`

## CLI Tools

\`\`\`bash
# Database
python scripts/db.py migrate
python scripts/db.py status

# Seed data (dev only)
python scripts/seed_data.py

# Export docs
python scripts/export_openapi.py
\`\`\`
`
};

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    loadContent(getInitialSection());
    initMobileMenu();
});

// Get initial section from URL hash or default
function getInitialSection() {
    const hash = window.location.hash.slice(1);
    return hash && SECTIONS[hash] ? hash : 'overview';
}

// Initialize navigation
function initNavigation() {
    const navLinks = document.querySelectorAll('.nav-link[data-section]');
    
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const section = link.dataset.section;
            loadContent(section);
            updateActiveLink(link);
            updateURL(section);
            closeMobileMenu();
        });
    });
    
    // Handle browser back/forward
    window.addEventListener('popstate', () => {
        const section = getInitialSection();
        loadContent(section);
        updateActiveLinkBySection(section);
    });
}

// Load content for a section
function loadContent(section) {
    const content = document.getElementById('content');
    const markdown = SECTIONS[section];
    
    if (!markdown) {
        content.innerHTML = '<div class="alert alert-danger">Section not found.</div>';
        return;
    }
    
    // Configure marked options
    marked.setOptions({
        highlight: function(code, lang) {
            if (lang && hljs.getLanguage(lang)) {
                return hljs.highlight(code, { language: lang }).value;
            }
            return hljs.highlightAuto(code).value;
        },
        breaks: true,
        gfm: true
    });
    
    // Render markdown
    content.innerHTML = marked.parse(markdown);
    
    // Scroll to top
    document.getElementById('mainContent').scrollTop = 0;
    window.scrollTo(0, 0);
}

// Update active navigation link
function updateActiveLink(activeLink) {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    activeLink.classList.add('active');
}

// Update active link by section name
function updateActiveLinkBySection(section) {
    const link = document.querySelector(`.nav-link[data-section="${section}"]`);
    if (link) {
        updateActiveLink(link);
    }
}

// Update URL hash
function updateURL(section) {
    history.pushState(null, null, `#${section}`);
}

// Initialize mobile menu
function initMobileMenu() {
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    
    menuToggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        menuToggle.classList.toggle('active');
    });
    
    // Close on outside click
    document.addEventListener('click', (e) => {
        if (!sidebar.contains(e.target) && !menuToggle.contains(e.target)) {
            closeMobileMenu();
        }
    });
}

// Close mobile menu
function closeMobileMenu() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('menuToggle').classList.remove('active');
}

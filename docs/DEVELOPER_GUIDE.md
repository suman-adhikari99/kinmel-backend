# Developer Onboarding Guide

Quick reference for developers new to the Kinmel backend.

## First-Time Setup (10 minutes)

```bash
# 1. Clone & setup
git clone <repo-url> && cd backend-kinmel
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Start dependencies
docker-compose up -d postgres redis

# 3. Setup database
python scripts/db.py migrate
python scripts/seed_data.py

# 4. Run server
uvicorn src.main:app --reload
# → Open http://localhost:8000/docs
```

## Test Credentials

```
Password: TestPassword123!

Emails:
- owner@kinmel-test.local     (Admin)
- manager@kinmel-test.local   (Manager)  ← Use this for testing
- staff1@kinmel-test.local    (Staff)
```

## Key Concepts in 2 Minutes

### Stock Formula
```
online_available = max(physical_stock - buffer, 0)
```
- `physical_stock`: What's actually on the shelf
- `buffer`: Reserved stock (online orders, safety margin)
- `online_available`: What can be sold online

### Every Change = Audit Record
```python
# When you call:
await inventory_service.receive_stock(...)

# Behind the scenes:
# 1. physical_stock increases
# 2. StockMovement record created (IMMUTABLE)
# 3. Batch record created (if perishable)
```

### Concurrency Control
```python
# Optimistic locking prevents lost updates
item.version = 5
# UPDATE ... SET version=6 WHERE version=5
# If 0 rows affected → someone else changed it → retry
```

## Common Tasks

### Add a New Endpoint

```python
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
```

### Add a New Scheduled Task

```python
# 1. Create task (src/tasks/inventory_tasks.py)
@celery_app.task(base=BaseTask, bind=True)
def my_task(self):
    with TaskLock("my_task", timeout=300) as acquired:
        if not acquired:
            return {"status": "skipped"}
        return run_async(_my_task_async())

async def _my_task_async():
    async with async_session_factory() as session:
        # Query and process
        pass

# 2. Schedule it (src/tasks/celery_app.py)
beat_schedule = {
    "my-task": {
        "task": "src.tasks.inventory_tasks.my_task",
        "schedule": 900.0,  # Every 15 minutes
    },
}
```

### Add a Database Migration

```bash
# 1. Modify your model
# 2. Generate migration
python scripts/db.py generate "add_supplier_column"

# 3. REVIEW the generated file in alembic/versions/
# 4. Apply
python scripts/db.py migrate
```

## Debugging Tips

### See SQL Queries
```python
# In .env
DEBUG=true
# SQL will be logged in development mode
```

### Test Single Endpoint
```bash
# Get a token first
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"manager@kinmel-test.local","password":"TestPassword123!"}' \
  | jq -r '.access_token')

# Then test
curl localhost:8000/api/v1/inventory/stock/MILK-2L-WHOLE \
  -H "Authorization: Bearer $TOKEN"
```

### Reset Everything
```bash
python scripts/db.py reset --force
python scripts/seed_data.py
```

## Code Style

```bash
# Format code
ruff format src/

# Lint
ruff check src/

# Type check
mypy src/

# All at once before commit
ruff format src/ && ruff check src/ && mypy src/ && pytest
```

## File Quick Reference

| Need to... | Look in... |
|------------|------------|
| Add API endpoint | `src/modules/*/router.py` |
| Add business logic | `src/modules/*/service.py` |
| Add database query | `src/modules/*/repository.py` |
| Add request/response schema | `src/modules/*/schemas.py` |
| Add database model | `src/modules/*/models.py` |
| Add background task | `src/tasks/*_tasks.py` |
| Add config option | `src/core/config.py` |
| Add custom exception | `src/core/exceptions.py` |

## Getting Help

1. Check `/docs` (Swagger UI) for API examples
2. Read test files for usage patterns
3. Check `README.md` for full documentation
4. Ask in #inventory-backend Slack channel

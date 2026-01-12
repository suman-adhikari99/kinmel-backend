# Alembic Migrations

Database migration management for Kinmel Inventory System.

## Quick Reference

```bash
# Apply all pending migrations
python scripts/db.py migrate

# Show current status
python scripts/db.py status

# Generate new migration (ALWAYS REVIEW!)
python scripts/db.py generate "add_supplier_table"

# Rollback one migration
python scripts/db.py rollback

# Verify models match schema
python scripts/db.py verify

# Reset database (dev only!)
python scripts/db.py reset
```

## Migration Guidelines

### 1. Never Trust Autogenerate Blindly

Alembic's autogenerate is a **starting point**, not the final migration. Always verify:

- [ ] Table creation order respects foreign keys
- [ ] CHECK constraints have correct names and expressions
- [ ] Indexes match expected query patterns
- [ ] Downgrade properly reverses all changes
- [ ] No data loss in column type changes

### 2. CHECK Constraints for Invariants

All business invariants should be enforced at the database level:

```python
# In your migration
op.create_check_constraint(
    "ck_inventory_physical_stock_non_negative",
    "inventory_items",
    "physical_stock >= 0",
)
```

This prevents application bugs from corrupting data.

### 3. Immutable Audit Tables

`stock_movements` is an append-only audit log. **Never** add UPDATE or DELETE operations on this table.

### 4. Handling Schema Drift

Run `python scripts/db.py verify` to detect drift between models and database:

- **No drift**: Models and schema match
- **Drift detected**: Review the generated migration carefully

Common causes of drift:
- Manual database changes (avoid!)
- Missing migration after model change
- Different migration paths in environments

### 5. Safe Rollback

Every migration must have a working `downgrade()` function. Test it before committing:

```bash
# Apply migration
python scripts/db.py migrate

# Test rollback
python scripts/db.py rollback

# Re-apply
python scripts/db.py migrate
```

### 6. Data Migrations

Keep **schema** migrations separate from **data** migrations:

```python
# Schema migration: 20241214_0001_add_status_column.py
def upgrade():
    op.add_column("orders", sa.Column("status", sa.String(20)))

# Data migration: 20241214_0002_populate_status.py
def upgrade():
    op.execute("UPDATE orders SET status = 'pending' WHERE status IS NULL")
```

## Naming Conventions

Migrations follow this format:
```
YYYYMMDD_HHMM_<description>.py
```

Examples:
- `20241214_0001_initial_schema.py`
- `20241215_1430_add_supplier_table.py`
- `20241216_0900_add_index_on_sku.py`

## Constraint Naming

All constraints use explicit names (defined in `src/core/database.py`):

| Type | Pattern | Example |
|------|---------|---------|
| Primary Key | `pk_<table>` | `pk_products` |
| Foreign Key | `fk_<table>_<column>_<ref_table>` | `fk_inventory_items_product_id_products` |
| Unique | `uq_<table>_<column>` | `uq_products_sku` |
| Check | `ck_<table>_<constraint_name>` | `ck_inventory_physical_stock_non_negative` |
| Index | `ix_<column>` | `ix_products_sku` |

## Common Operations

### Add a new table

```python
def upgrade():
    op.create_table(
        "suppliers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        # ... more columns
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"])

def downgrade():
    op.drop_index("ix_suppliers_name")
    op.drop_table("suppliers")
```

### Add a column with default

```python
def upgrade():
    op.add_column(
        "products",
        sa.Column("weight_kg", sa.Numeric(10, 3), nullable=True),
    )

def downgrade():
    op.drop_column("products", "weight_kg")
```

### Add a non-nullable column to existing table

```python
def upgrade():
    # 1. Add as nullable
    op.add_column(
        "products",
        sa.Column("supplier_id", sa.String(length=36), nullable=True),
    )
    
    # 2. Populate with default (data migration)
    op.execute("UPDATE products SET supplier_id = '...' WHERE supplier_id IS NULL")
    
    # 3. Make non-nullable
    op.alter_column("products", "supplier_id", nullable=False)

def downgrade():
    op.drop_column("products", "supplier_id")
```

### Create an index

```python
from alembic import op

def upgrade():
    op.create_index("ix_stock_movements_date", "stock_movements", ["created_at"])

def downgrade():
    op.drop_index("ix_stock_movements_date", table_name="stock_movements")
```

## Environment-Specific Notes

### Development
- Use `python scripts/db.py reset` for clean slate
- Run migrations automatically on app startup (optional)

### Staging
- Apply migrations before deploying new code
- Test rollback in staging before production

### Production
- **Never** use `reset` command
- Apply migrations during maintenance window
- Have rollback plan ready
- Monitor for lock contention on large tables

## Troubleshooting

### "Target database is not up to date"

Your database has migrations that aren't in your codebase:
```bash
# Check history
python scripts/db.py status

# You might need to stamp to match
alembic stamp head
```

### "Can't locate revision"

Missing migration file. Check if:
- Migration file exists in `alembic/versions/`
- No typos in revision ID
- All team members have pulled latest code

### "Column already exists"

Migration was partially applied. Options:
1. Manually fix the database to match expected state
2. Stamp to skip: `alembic stamp <revision_id>`

### Deadlock during migration

Large table operations can cause locks. Use:
- `CREATE INDEX CONCURRENTLY` for indexes
- Batched updates for data migrations
- Off-peak hours for production migrations

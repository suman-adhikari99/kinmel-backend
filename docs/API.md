# Kinmel API Documentation

> Quick reference for API consumers. For full documentation, see [README.md](../README.md).

## Overview

The Kinmel Inventory Management System provides a REST API for managing grocery store inventory.

## Base URL

| Environment | URL |
|-------------|-----|
| Development | `http://localhost:8000` |
| Staging | `https://api-staging.kinmel.local` |
| Production | `https://api.kinmel.local` |

## Authentication

All endpoints except health checks require JWT authentication.

### Obtaining a Token

```bash
# Login to get tokens
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "manager@kinmel-test.local", "password": "TestPassword123!"}'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### Using the Token

Include the token in the `Authorization` header:

```bash
curl http://localhost:8000/api/v1/inventory/stock/MILK-2L-WHOLE \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

## Interactive Documentation

### Swagger UI (Recommended for Testing)

Available at: `http://localhost:8000/docs`

Features:
- Interactive "Try it out" functionality
- Authorize button for JWT tokens
- Request/response examples

### ReDoc (Recommended for Reading)

Available at: `http://localhost:8000/redoc`

Features:
- Clean, readable documentation
- Better for sharing with stakeholders
- Searchable content

## OpenAPI Schema

Export the schema for use with API tools:

```bash
# Download as JSON
curl http://localhost:8000/openapi.json > openapi.json

# Or use the export script
python scripts/export_openapi.py -o docs/openapi.json

# Generate static HTML docs
python scripts/export_openapi.py --html
```

## Role-Based Access

| Role | Level | Capabilities |
|------|-------|--------------|
| `admin` | 100 | Full system access, user management |
| `manager` | 75 | Inventory adjustments, reports, audit access |
| `supervisor` | 50 | Stock movements, receiving |
| `staff` | 25 | Basic operations, viewing |

### Endpoint Permissions

| Endpoint | Staff | Supervisor | Manager | Admin |
|----------|-------|------------|---------|-------|
| `GET /inventory/stock/*` | ✓ | ✓ | ✓ | ✓ |
| `POST /inventory/receive` | ✓ | ✓ | ✓ | ✓ |
| `POST /inventory/adjust` | ✗ | ✗ | ✓ | ✓ |
| `POST /inventory/dispose` | ✗ | ✗ | ✓ | ✓ |
| `GET /admin/audit-log` | ✗ | ✗ | ✓ | ✓ |

## Common Endpoints

### Stock Operations

```bash
# Get stock level
GET /api/v1/inventory/stock/{sku}

# Receive stock
POST /api/v1/inventory/receive
{
  "sku": "MILK-2L-WHOLE",
  "location_id": "uuid",
  "quantity": 50,
  "batch_number": "BATCH-001",
  "expiry_date": "2024-02-01T00:00:00Z"
}

# Adjust stock (Manager+)
POST /api/v1/inventory/adjust
{
  "sku": "MILK-2L-WHOLE",
  "location_id": "uuid",
  "new_quantity": 45,
  "reason": "cycle_count",
  "notes": "Cycle count correction"
}
```

### Audit Log (Manager+)

```bash
# Query audit log
GET /api/v1/admin/audit-log?sku=MILK-2L&action_type=sale&limit=50

# Export as CSV
GET /api/v1/admin/audit-log/export.csv?start_date=2024-01-01

# Get statistics
GET /api/v1/admin/audit-log/stats?start_date=2024-01-01&end_date=2024-01-31
```

## Error Responses

All errors follow a consistent format:

```json
{
  "detail": {
    "message": "Human-readable error message",
    "code": "ERROR_CODE",
    "field": "optional_field_name"
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `NOT_FOUND` | 404 | Resource not found |
| `INSUFFICIENT_STOCK` | 422 | Not enough stock available |
| `CONCURRENT_MODIFICATION` | 409 | Version conflict, retry |
| `INSUFFICIENT_ROLE` | 403 | Role not high enough |
| `VALIDATION_ERROR` | 422 | Invalid input data |

## Rate Limiting

- Default: 60 requests/minute per user
- Exceeded: Returns 429 Too Many Requests

## Pagination

List endpoints support pagination:

```bash
GET /api/v1/admin/audit-log?limit=50&offset=100
```

Response includes:
- `total`: Total matching records
- `limit`: Records per page
- `offset`: Records skipped
- `has_more`: Boolean indicating more pages

## Versioning

The API is versioned via URL path: `/api/v1/`

Breaking changes will increment the version number.

## Support

- **Email**: api-support@kinmel.local
- **Issues**: https://github.com/kinmel/backend/issues

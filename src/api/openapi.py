"""
OpenAPI Configuration
---------------------
Enhanced OpenAPI schema configuration for better API documentation.

Features:
- Custom tags with descriptions
- Security scheme definitions
- Example responses
- External documentation links
"""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from src.core.config import get_settings

settings = get_settings()


# ═══════════════════════════════════════════════════════════════════════════════
# TAG DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

OPENAPI_TAGS = [
    {
        "name": "Health",
        "description": "Service health and readiness checks for load balancers and orchestrators.",
    },
    {
        "name": "Inventory",
        "description": """
**Stock Management Operations**

Core inventory operations including:
- **Receiving**: Record incoming stock from suppliers
- **Adjustments**: Manual stock corrections (Manager+ only)
- **Reservations**: Reserve stock for online orders
- **Fulfillment**: Process sales and decrement stock
- **Disposal**: Remove expired or damaged stock

All operations create an immutable audit trail.
        """,
    },
    {
        "name": "Admin & Audit",
        "description": """
**Administrative APIs**

Access control: **Manager and Admin roles only**

- Query immutable audit trail
- Export audit logs as CSV
- View aggregated statistics
- Monitor stock movements
        """,
    },
    {
        "name": "Authentication",
        "description": "User authentication and token management.",
    },
    {
        "name": "Users",
        "description": "User account management (Admin only).",
    },
    {
        "name": "Products",
        "description": "Product catalog management.",
    },
    {
        "name": "Orders",
        "description": "Order management, fulfillment status, and substitutions.",
    },
    {
        "name": "Reports",
        "description": "Reporting and analytics endpoints.",
    },
    {
        "name": "Revenue",
        "description": "Revenue analytics and financial summaries.",
    },
    {
        "name": "Business",
        "description": "Business profile and compliance information.",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY SCHEMES
# ═══════════════════════════════════════════════════════════════════════════════

SECURITY_SCHEMES = {
    "BearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": """
## JWT Authentication

All protected endpoints require a valid JWT token in the Authorization header.

**Format:** `Authorization: Bearer <token>`

### Obtaining a Token

1. Call `POST /api/v1/auth/login` with email and password
2. Use the returned `access_token` for subsequent requests
3. When the access token expires, use the `refresh_token` to get a new one

### Token Claims

The JWT contains:
- `sub`: User ID
- `role`: User role (admin, manager, supervisor, staff)
- `exp`: Expiration timestamp
- `type`: Token type (access or refresh)

### Role Hierarchy

| Role | Level | Permissions |
|------|-------|-------------|
| Admin | 100 | Full system access |
| Manager | 75 | Inventory adjustments, reports |
| Supervisor | 50 | Stock movements, receiving |
| Staff | 25 | Basic operations, viewing |
        """,
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# OPENAPI SCHEMA GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def custom_openapi(app: FastAPI) -> dict:
    """
    Generate custom OpenAPI schema with enhanced documentation.
    
    This function is called once and cached by FastAPI.
    """
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=settings.app_name,
        version="1.0.0",
        description="""
# Kinmel Grocery Inventory Management System

A **fault-tolerant, staff-proof** backend for grocery inventory operations.

## Overview

This API provides comprehensive inventory management for grocery stores, including:

- 📦 **Product Management**: SKU-based product catalog with categories
- 🏪 **Multi-Location Inventory**: Track stock across store locations
- 📊 **Real-time Stock Levels**: Physical stock, buffers, and online availability
- 🔄 **Batch Tracking**: FIFO management for perishables with expiry dates
- 📝 **Complete Audit Trail**: Every change is logged and traceable
- 🔐 **Role-Based Access**: Granular permissions for staff, managers, and admins

## Key Concepts

### Stock Levels

| Field | Description |
|-------|-------------|
| `physical_stock` | Actual units on hand |
| `buffer` | Reserved/safety stock |
| `online_available` | `max(physical_stock - buffer, 0)` |
| `reorder_point` | Threshold for reorder alerts |

### Movement Types

| Type | Description | Stock Effect |
|------|-------------|--------------|
| `receiving` | Stock from suppliers | ↑ Increase |
| `sale` | Customer purchases | ↓ Decrease |
| `transfer` | Between locations | → Move |
| `adjustment` | Manual corrections | ↑↓ Varies |
| `return` | Customer returns | ↑ Increase |
| `disposal` | Expired/damaged removal | ↓ Decrease |
| `reservation` | Online order holds | Buffer ↑ |

## Authentication

All endpoints except health checks require JWT authentication.

1. Obtain a token via `/api/v1/auth/login`
2. Include in requests: `Authorization: Bearer <token>`

## Rate Limiting

- Default: 60 requests/minute per user
- Bulk operations may have lower limits

## Error Handling

All errors follow a consistent format:

```json
{
  "detail": {
    "message": "Human-readable error message",
    "code": "ERROR_CODE",
    "field": "Optional field name"
  }
}
```

## Support

- **Documentation**: [Internal Wiki](#)
- **Issues**: [GitHub Issues](#)
- **Contact**: inventory-team@kinmel.local
        """,
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = SECURITY_SCHEMES
    
    # Apply security globally (can be overridden per endpoint)
    openapi_schema["security"] = [{"BearerAuth": []}]
    
    # Add servers
    openapi_schema["servers"] = [
        {
            "url": "http://localhost:8000",
            "description": "Local Development",
        },
        {
            "url": "https://api.kinmel.local",
            "description": "Staging Environment",
        },
    ]
    
    # Add external docs
    openapi_schema["externalDocs"] = {
        "description": "Full API Documentation",
        "url": "https://docs.kinmel.local/api",
    }
    
    # Add contact and license info
    openapi_schema["info"]["contact"] = {
        "name": "Kinmel API Support",
        "email": "api-support@kinmel.local",
    }
    
    openapi_schema["info"]["license"] = {
        "name": "Proprietary",
        "url": "https://kinmel.local/license",
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


def configure_openapi(app: FastAPI) -> None:
    """
    Configure OpenAPI documentation for the FastAPI app.
    
    Call this after all routers are registered.
    """
    # Set custom OpenAPI generator
    app.openapi = lambda: custom_openapi(app)
    
    # Configure Swagger UI options
    app.swagger_ui_parameters = {
        "docExpansion": "none",  # Collapse all by default
        "filter": True,  # Enable search filter
        "tagsSorter": "alpha",  # Sort tags alphabetically
        "operationsSorter": "alpha",  # Sort operations alphabetically
        "persistAuthorization": True,  # Remember auth token
        "displayRequestDuration": True,  # Show request duration
        "tryItOutEnabled": True,  # Enable "Try it out" by default
    }

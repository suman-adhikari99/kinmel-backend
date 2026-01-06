"""
Kinmel API Integration Helper
=============================

A comprehensive reference for integrating the Kinmel Inventory Management System
with a Next.js frontend.

This document lists all API endpoints, their purposes, required authentication,
and sample data for calling each endpoint.

Base URL: http://localhost:8000
API Version: v1
API Prefix: /api/v1

Documentation URLs:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

Test Credentials:
-----------------
Password: TestPassword123!
Users:
- owner@kinmel-test.local     (Admin)
- manager@kinmel-test.local   (Manager)
- supervisor@kinmel-test.local (Supervisor)
- staff1@kinmel-test.local    (Staff)
- staff2@kinmel-test.local    (Staff)
"""

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"

# Authentication header format
def get_auth_header(access_token: str) -> dict:
    """
    Returns the authorization header for authenticated requests.
    
    Usage in Next.js:
    ```typescript
    const headers = {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
    };
    ```
    """
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

HEALTH_ENDPOINTS = {
    # ─────────────────────────────────────────────────────────────────────────────
    # Health Check
    # ─────────────────────────────────────────────────────────────────────────────
    "health_check": {
        "method": "GET",
        "endpoint": "/health",
        "purpose": "Check if the API server is running. Used by load balancers and monitoring.",
        "authentication": "Not required",
        "sample_request": {
            "url": f"{BASE_URL}/health",
            "headers": {},
        },
        "sample_response": {
            "status": "healthy",
            "service": "kinmel"
        },
        "nextjs_example": """
// Health check (no auth required)
const checkHealth = async () => {
    const response = await fetch('http://localhost:8000/health');
    return response.json();
};
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Readiness Check
    # ─────────────────────────────────────────────────────────────────────────────
    "readiness_check": {
        "method": "GET",
        "endpoint": "/ready",
        "purpose": "Check if the API is ready to serve traffic (dependencies are available).",
        "authentication": "Not required",
        "sample_request": {
            "url": f"{BASE_URL}/ready",
            "headers": {},
        },
        "sample_response": {
            "status": "ready",
            "service": "kinmel"
        },
        "nextjs_example": """
// Readiness check (no auth required)
const checkReadiness = async () => {
    const response = await fetch('http://localhost:8000/ready');
    return response.json();
};
"""
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

AUTH_ENDPOINTS = {
    # ─────────────────────────────────────────────────────────────────────────────
    # Login
    # ─────────────────────────────────────────────────────────────────────────────
    "login": {
        "method": "POST",
        "endpoint": f"{API_PREFIX}/auth/login",
        "purpose": "Authenticate user and receive JWT access and refresh tokens.",
        "authentication": "Not required",
        "request_body": {
            "email": "string (required) - User's email address",
            "password": "string (required) - User's password",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/auth/login",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": {
                "email": "manager@kinmel-test.local",
                "password": "TestPassword123!"
            }
        },
        "sample_response": {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer"
        },
        "token_info": {
            "access_token_expiry": "30 minutes",
            "refresh_token_expiry": "7 days",
        },
        "nextjs_example": """
// Login function
const login = async (email: string, password: string) => {
    const response = await fetch('http://localhost:8000/api/v1/auth/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
    });
    
    if (!response.ok) {
        throw new Error('Login failed');
    }
    
    const data = await response.json();
    // Store tokens securely (e.g., httpOnly cookies or secure storage)
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    
    return data;
};
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Refresh Token
    # ─────────────────────────────────────────────────────────────────────────────
    "refresh_token": {
        "method": "POST",
        "endpoint": f"{API_PREFIX}/auth/refresh",
        "purpose": "Get a new access token using a valid refresh token.",
        "authentication": "Refresh token required",
        "request_body": {
            "refresh_token": "string (required) - Valid refresh token",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/auth/refresh",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        },
        "sample_response": {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer"
        },
        "nextjs_example": """
// Refresh token function
const refreshAccessToken = async () => {
    const refreshToken = localStorage.getItem('refresh_token');
    
    const response = await fetch('http://localhost:8000/api/v1/auth/refresh', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
    });
    
    if (!response.ok) {
        // Refresh token expired, redirect to login
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        throw new Error('Session expired');
    }
    
    const data = await response.json();
    localStorage.setItem('access_token', data.access_token);
    
    return data.access_token;
};
"""
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# INVENTORY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

INVENTORY_ENDPOINTS = {
    # ─────────────────────────────────────────────────────────────────────────────
    # Receive Stock (POST)
    # ─────────────────────────────────────────────────────────────────────────────
    "receive_stock": {
        "method": "POST",
        "endpoint": f"{API_PREFIX}/inventory/receive",
        "purpose": "Record incoming stock from suppliers or transfers. Creates an audit trail and optionally tracks batch/expiry for perishables.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "request_body": {
            "sku": "string (required) - Product SKU (e.g., 'MILK-2L-WHOLE'). Max 50 chars.",
            "location_id": "string (required) - Target storage location UUID.",
            "quantity": "integer (required) - Number of units received. Must be > 0 and <= 10000.",
            "batch_number": "string (optional) - Supplier batch/lot number for traceability. Max 100 chars.",
            "expiry_date": "datetime (optional) - ISO 8601 format. Must be in the future for perishables.",
            "cost_per_unit": "decimal (optional) - Purchase cost per unit (2 decimal places).",
            "reference_id": "string (optional) - Purchase order or delivery note number. Max 50 chars.",
            "notes": "string (optional) - Additional notes about this delivery. Max 500 chars.",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/inventory/receive",
            "headers": {
                "Authorization": "Bearer <access_token>",
                "Content-Type": "application/json"
            },
            "body": {
                "sku": "MILK-2L-WHOLE",
                "location_id": "550e8400-e29b-41d4-a716-446655440001",
                "quantity": 50,
                "batch_number": "BATCH-2024-001",
                "expiry_date": "2024-02-15T00:00:00Z",
                "cost_per_unit": 3.20,
                "reference_id": "PO-2024-001",
                "notes": "Morning delivery from Dairy Supplier Inc."
            }
        },
        "sample_response": {
            "success": True,
            "message": "Received 50 units of MILK-2L-WHOLE",
            "item": {
                "id": "550e8400-e29b-41d4-a716-446655440010",
                "product_id": "550e8400-e29b-41d4-a716-446655440000",
                "location_id": "550e8400-e29b-41d4-a716-446655440001",
                "physical_stock": 100,
                "buffer": 10,
                "reorder_point": 20,
                "max_stock": 200,
                "version": 5,
                "is_active": True,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
                "online_available": 90,
                "is_low_stock": False,
                "is_out_of_stock": False
            },
            "movement": {
                "id": "550e8400-e29b-41d4-a716-446655440020",
                "inventory_item_id": "550e8400-e29b-41d4-a716-446655440010",
                "movement_type": "receiving",
                "reason": "supplier_delivery",
                "quantity_delta": 50,
                "quantity_before": 50,
                "quantity_after": 100,
                "user_id": "550e8400-e29b-41d4-a716-446655440099",
                "reference_id": "PO-2024-001",
                "reference_type": "purchase_order",
                "notes": "Morning delivery from Dairy Supplier Inc.",
                "created_at": "2024-01-15T10:30:00Z"
            },
            "previous_stock": 50,
            "new_stock": 100,
            "delta": 50
        },
        "nextjs_example": """
// Receive stock function
interface ReceiveStockPayload {
    sku: string;
    location_id: string;
    quantity: number;
    batch_number?: string;
    expiry_date?: string;
    cost_per_unit?: number;
    reference_id?: string;
    notes?: string;
}

const receiveStock = async (payload: ReceiveStockPayload) => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch('http://localhost:8000/api/v1/inventory/receive', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
    
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail?.message || 'Failed to receive stock');
    }
    
    return response.json();
};

// Usage example
const handleReceive = async () => {
    try {
        const result = await receiveStock({
            sku: 'MILK-2L-WHOLE',
            location_id: '550e8400-e29b-41d4-a716-446655440001',
            quantity: 50,
            batch_number: 'BATCH-2024-001',
            expiry_date: '2024-02-15T00:00:00Z',
        });
        console.log('Stock received:', result);
    } catch (error) {
        console.error('Error:', error);
    }
};
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Adjust Stock (POST) - Manager+ Only
    # ─────────────────────────────────────────────────────────────────────────────
    "adjust_stock": {
        "method": "POST",
        "endpoint": f"{API_PREFIX}/inventory/adjust",
        "purpose": "Manually adjust stock to a new quantity. Used for cycle count corrections, shrinkage recording, or audit corrections. Large adjustments (>50% of current stock) require confirmation.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "MANAGER",
        "allowed_roles": ["MANAGER", "ADMIN"],
        "request_body": {
            "sku": "string (required) - Product SKU.",
            "location_id": "string (required) - Storage location UUID.",
            "new_quantity": "integer (required) - New absolute stock quantity (not a delta). 0 to 100000.",
            "reason": "string (required) - Reason code. Must be one of: 'cycle_count', 'audit_correction', 'system_correction', 'shrinkage'.",
            "notes": "string (required) - Explanation for this adjustment. 10-500 chars.",
            "confirm_large_adjustment": "boolean (optional) - Set to true to confirm adjustments >50% of current stock.",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/inventory/adjust",
            "headers": {
                "Authorization": "Bearer <manager_access_token>",
                "Content-Type": "application/json"
            },
            "body": {
                "sku": "MILK-2L-WHOLE",
                "location_id": "550e8400-e29b-41d4-a716-446655440001",
                "new_quantity": 45,
                "reason": "cycle_count",
                "notes": "Cycle count correction - 5 units missing from shelf",
                "confirm_large_adjustment": False
            }
        },
        "sample_response": {
            "success": True,
            "message": "Stock decreased by 5 units (now 45)",
            "item": {
                "id": "550e8400-e29b-41d4-a716-446655440010",
                "product_id": "550e8400-e29b-41d4-a716-446655440000",
                "location_id": "550e8400-e29b-41d4-a716-446655440001",
                "physical_stock": 45,
                "buffer": 10,
                "reorder_point": 20,
                "max_stock": 200,
                "version": 6,
                "is_active": True,
                "online_available": 35,
                "is_low_stock": False,
                "is_out_of_stock": False
            },
            "movement": {
                "id": "550e8400-e29b-41d4-a716-446655440021",
                "movement_type": "adjustment",
                "reason": "cycle_count",
                "quantity_delta": -5,
                "quantity_before": 50,
                "quantity_after": 45
            },
            "previous_stock": 50,
            "new_stock": 45,
            "delta": -5
        },
        "valid_reasons": ["cycle_count", "audit_correction", "system_correction", "shrinkage"],
        "nextjs_example": """
// Adjust stock function (Manager+ only)
interface AdjustStockPayload {
    sku: string;
    location_id: string;
    new_quantity: number;
    reason: 'cycle_count' | 'audit_correction' | 'system_correction' | 'shrinkage';
    notes: string;
    confirm_large_adjustment?: boolean;
}

const adjustStock = async (payload: AdjustStockPayload) => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch('http://localhost:8000/api/v1/inventory/adjust', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
    
    if (response.status === 403) {
        throw new Error('Insufficient permissions. Manager role required.');
    }
    
    if (response.status === 422) {
        const error = await response.json();
        // Check if adjustment is too large
        if (error.detail?.code === 'ADJUSTMENT_TOO_LARGE') {
            // Show confirmation dialog to user
            throw new Error('Large adjustment requires confirmation');
        }
        throw new Error(error.detail?.message || 'Validation error');
    }
    
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail?.message || 'Failed to adjust stock');
    }
    
    return response.json();
};
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Reserve Stock (POST)
    # ─────────────────────────────────────────────────────────────────────────────
    "reserve_stock": {
        "method": "POST",
        "endpoint": f"{API_PREFIX}/inventory/reserve",
        "purpose": "Reserve stock for an online order. Increases buffer, reducing online_available without changing physical stock.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "request_body": {
            "sku": "string (required) - Product SKU.",
            "location_id": "string (required) - Storage location UUID.",
            "quantity": "integer (required) - Units to reserve. Must be > 0 and <= 100.",
            "order_id": "string (required) - Order reference ID. Max 50 chars.",
            "notes": "string (optional) - Additional notes. Max 500 chars.",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/inventory/reserve",
            "headers": {
                "Authorization": "Bearer <access_token>",
                "Content-Type": "application/json"
            },
            "body": {
                "sku": "MILK-2L-WHOLE",
                "location_id": "550e8400-e29b-41d4-a716-446655440001",
                "quantity": 5,
                "order_id": "ORD-2024-00123",
                "notes": "Customer online order - delivery scheduled tomorrow"
            }
        },
        "sample_response": {
            "success": True,
            "message": "Reserved 5 units for order ORD-2024-00123",
            "item": {
                "physical_stock": 100,
                "buffer": 15,
                "online_available": 85
            },
            "movement": {
                "movement_type": "reservation",
                "reason": "online_reservation",
                "quantity_delta": 0,
                "reference_id": "ORD-2024-00123"
            },
            "previous_stock": 100,
            "new_stock": 100
        },
        "nextjs_example": """
// Reserve stock for online order
interface ReserveStockPayload {
    sku: string;
    location_id: string;
    quantity: number;
    order_id: string;
    notes?: string;
}

const reserveStock = async (payload: ReserveStockPayload) => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch('http://localhost:8000/api/v1/inventory/reserve', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
    
    if (response.status === 422) {
        const error = await response.json();
        if (error.detail?.code === 'INSUFFICIENT_STOCK') {
            throw new Error(`Only ${error.detail.available} units available`);
        }
    }
    
    if (!response.ok) {
        throw new Error('Failed to reserve stock');
    }
    
    return response.json();
};
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Release Reservation (POST)
    # ─────────────────────────────────────────────────────────────────────────────
    "release_reservation": {
        "method": "POST",
        "endpoint": f"{API_PREFIX}/inventory/release",
        "purpose": "Release a stock reservation. Call when an order is cancelled or reservation expires.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "request_body": {
            "sku": "string (required) - Product SKU.",
            "location_id": "string (required) - Storage location UUID.",
            "quantity": "integer (required) - Units to release. Must be > 0.",
            "order_id": "string (required) - Original order reference.",
            "notes": "string (optional) - Additional notes. Max 500 chars.",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/inventory/release",
            "headers": {
                "Authorization": "Bearer <access_token>",
                "Content-Type": "application/json"
            },
            "body": {
                "sku": "MILK-2L-WHOLE",
                "location_id": "550e8400-e29b-41d4-a716-446655440001",
                "quantity": 5,
                "order_id": "ORD-2024-00123",
                "notes": "Order cancelled by customer"
            }
        },
        "sample_response": {
            "success": True,
            "message": "Released 5 units from order ORD-2024-00123",
            "item": {
                "physical_stock": 100,
                "buffer": 10,
                "online_available": 90
            },
            "movement": {
                "movement_type": "reservation",
                "reason": "reservation_released",
                "quantity_delta": 0,
                "reference_id": "ORD-2024-00123"
            },
            "previous_stock": 100,
            "new_stock": 100
        },
        "nextjs_example": """
// Release reservation
interface ReleaseReservationPayload {
    sku: string;
    location_id: string;
    quantity: number;
    order_id: string;
    notes?: string;
}

const releaseReservation = async (payload: ReleaseReservationPayload) => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch('http://localhost:8000/api/v1/inventory/release', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
    
    if (!response.ok) {
        throw new Error('Failed to release reservation');
    }
    
    return response.json();
};
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Fulfill Order (POST)
    # ─────────────────────────────────────────────────────────────────────────────
    "fulfill_order": {
        "method": "POST",
        "endpoint": f"{API_PREFIX}/inventory/fulfill",
        "purpose": "Fulfill an order by decrementing stock. Decreases both physical stock and buffer (if reserved).",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "request_body": {
            "sku": "string (required) - Product SKU.",
            "location_id": "string (required) - Storage location UUID.",
            "quantity": "integer (required) - Units sold. Must be > 0 and <= 1000.",
            "order_id": "string (required) - Order/transaction ID.",
            "notes": "string (optional) - Additional notes. Max 500 chars.",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/inventory/fulfill",
            "headers": {
                "Authorization": "Bearer <access_token>",
                "Content-Type": "application/json"
            },
            "body": {
                "sku": "MILK-2L-WHOLE",
                "location_id": "550e8400-e29b-41d4-a716-446655440001",
                "quantity": 5,
                "order_id": "ORD-2024-00123",
                "notes": "Pickup completed"
            }
        },
        "sample_response": {
            "success": True,
            "message": "Sold 5 units (95 remaining)",
            "item": {
                "physical_stock": 95,
                "buffer": 5,
                "online_available": 90
            },
            "movement": {
                "movement_type": "sale",
                "reason": "customer_sale",
                "quantity_delta": -5,
                "quantity_before": 100,
                "quantity_after": 95,
                "reference_id": "ORD-2024-00123"
            },
            "previous_stock": 100,
            "new_stock": 95,
            "delta": -5
        },
        "nextjs_example": """
// Fulfill order (sell stock)
interface FulfillOrderPayload {
    sku: string;
    location_id: string;
    quantity: number;
    order_id: string;
    notes?: string;
}

const fulfillOrder = async (payload: FulfillOrderPayload) => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch('http://localhost:8000/api/v1/inventory/fulfill', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
    
    if (response.status === 422) {
        const error = await response.json();
        if (error.detail?.code === 'INSUFFICIENT_STOCK') {
            throw new Error(`Insufficient stock. Available: ${error.detail.available}`);
        }
    }
    
    if (!response.ok) {
        throw new Error('Failed to fulfill order');
    }
    
    return response.json();
};
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Dispose Stock (POST) - Manager+ Only
    # ─────────────────────────────────────────────────────────────────────────────
    "dispose_stock": {
        "method": "POST",
        "endpoint": f"{API_PREFIX}/inventory/dispose",
        "purpose": "Dispose of expired or damaged stock. Creates detailed audit record for loss tracking.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "MANAGER",
        "allowed_roles": ["MANAGER", "ADMIN"],
        "request_body": {
            "sku": "string (required) - Product SKU.",
            "location_id": "string (required) - Storage location UUID.",
            "quantity": "integer (required) - Units to dispose. Must be > 0 and <= 10000.",
            "reason": "string (required) - Disposal reason. Must be one of: 'expired', 'damaged', 'shrinkage'.",
            "batch_id": "string (optional) - Specific batch being disposed.",
            "notes": "string (required) - Explanation for disposal. 10-500 chars.",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/inventory/dispose",
            "headers": {
                "Authorization": "Bearer <manager_access_token>",
                "Content-Type": "application/json"
            },
            "body": {
                "sku": "MILK-2L-WHOLE",
                "location_id": "550e8400-e29b-41d4-a716-446655440001",
                "quantity": 10,
                "reason": "expired",
                "batch_id": "550e8400-e29b-41d4-a716-446655440030",
                "notes": "Batch expired on 2024-01-14, disposal approved by manager"
            }
        },
        "sample_response": {
            "success": True,
            "message": "Disposed 10 units (expired)",
            "item": {
                "physical_stock": 90,
                "buffer": 10,
                "online_available": 80
            },
            "movement": {
                "movement_type": "disposal",
                "reason": "expired",
                "quantity_delta": -10,
                "quantity_before": 100,
                "quantity_after": 90
            },
            "previous_stock": 100,
            "new_stock": 90,
            "delta": -10
        },
        "valid_reasons": ["expired", "damaged", "shrinkage"],
        "nextjs_example": """
// Dispose stock (Manager+ only)
interface DisposeStockPayload {
    sku: string;
    location_id: string;
    quantity: number;
    reason: 'expired' | 'damaged' | 'shrinkage';
    batch_id?: string;
    notes: string;
}

const disposeStock = async (payload: DisposeStockPayload) => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch('http://localhost:8000/api/v1/inventory/dispose', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
    
    if (response.status === 403) {
        throw new Error('Insufficient permissions. Manager role required.');
    }
    
    if (!response.ok) {
        throw new Error('Failed to dispose stock');
    }
    
    return response.json();
};
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Get Stock Level (GET)
    # ─────────────────────────────────────────────────────────────────────────────
    "get_stock_level": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/inventory/stock/{{sku}}",
        "purpose": "Get current stock level for a SKU, optionally filtered by location.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "url_parameters": {
            "sku": "string (required) - Product SKU (in URL path)",
        },
        "query_parameters": {
            "location_id": "string (optional) - Filter by specific location UUID",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/inventory/stock/MILK-2L-WHOLE?location_id=550e8400-e29b-41d4-a716-446655440001",
            "headers": {
                "Authorization": "Bearer <access_token>"
            }
        },
        "sample_response": {
            "sku": "MILK-2L-WHOLE",
            "location_id": "550e8400-e29b-41d4-a716-446655440001",
            "physical_stock": 100,
            "buffer": 10,
            "online_available": 90,
            "is_low_stock": False,
            "reorder_point": 20
        },
        "nextjs_example": """
// Get stock level
const getStockLevel = async (sku: string, locationId?: string) => {
    const accessToken = localStorage.getItem('access_token');
    
    let url = `http://localhost:8000/api/v1/inventory/stock/${encodeURIComponent(sku)}`;
    if (locationId) {
        url += `?location_id=${encodeURIComponent(locationId)}`;
    }
    
    const response = await fetch(url, {
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });
    
    if (response.status === 404) {
        throw new Error('Product not found');
    }
    
    if (!response.ok) {
        throw new Error('Failed to get stock level');
    }
    
    return response.json();
};

// Usage
const stock = await getStockLevel('MILK-2L-WHOLE');
console.log(`Available: ${stock.online_available}`);
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Get Low Stock Alerts (GET)
    # ─────────────────────────────────────────────────────────────────────────────
    "get_low_stock_alerts": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/inventory/alerts/low-stock",
        "purpose": "Get all items at or below reorder point. Used for restock alerts.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "query_parameters": {
            "location_id": "string (optional) - Filter by specific location UUID",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/inventory/alerts/low-stock",
            "headers": {
                "Authorization": "Bearer <access_token>"
            }
        },
        "sample_response": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440010",
                "sku": "BREAD-WHITE-LOAF",
                "product_name": "White Bread Loaf",
                "location_code": "FLOOR-A2",
                "physical_stock": 5,
                "reorder_point": 20,
                "shortage": 15
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440011",
                "sku": "EGGS-LARGE-12",
                "product_name": "Large Eggs (12 pack)",
                "location_code": "COLD-01",
                "physical_stock": 8,
                "reorder_point": 15,
                "shortage": 7
            }
        ],
        "nextjs_example": """
// Get low stock alerts
interface LowStockAlert {
    id: string;
    sku: string;
    product_name: string;
    location_code: string;
    physical_stock: number;
    reorder_point: number;
    shortage: number;
}

const getLowStockAlerts = async (locationId?: string): Promise<LowStockAlert[]> => {
    const accessToken = localStorage.getItem('access_token');
    
    let url = 'http://localhost:8000/api/v1/inventory/alerts/low-stock';
    if (locationId) {
        url += `?location_id=${encodeURIComponent(locationId)}`;
    }
    
    const response = await fetch(url, {
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });
    
    if (!response.ok) {
        throw new Error('Failed to get low stock alerts');
    }
    
    return response.json();
};

// Usage in React component
const [alerts, setAlerts] = useState<LowStockAlert[]>([]);

useEffect(() => {
    getLowStockAlerts().then(setAlerts);
}, []);
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Get Expiring Items (GET)
    # ─────────────────────────────────────────────────────────────────────────────
    "get_expiring_items": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/inventory/alerts/expiring",
        "purpose": "Get batches expiring within N days. Used for expiry management.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "query_parameters": {
            "days_ahead": "integer (optional) - Days to look ahead. 1-90, default 7.",
            "location_id": "string (optional) - Filter by specific location UUID",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/inventory/alerts/expiring?days_ahead=7",
            "headers": {
                "Authorization": "Bearer <access_token>"
            }
        },
        "sample_response": [
            {
                "batch_id": "550e8400-e29b-41d4-a716-446655440030",
                "sku": "MILK-2L-WHOLE",
                "product_name": "Whole Milk 2L",
                "location_code": "COLD-01",
                "quantity": 15,
                "expiry_date": "2024-01-20T00:00:00Z",
                "days_until_expiry": 5,
                "batch_number": "BATCH-2024-001"
            },
            {
                "batch_id": "550e8400-e29b-41d4-a716-446655440031",
                "sku": "YOGURT-PLAIN-500G",
                "product_name": "Plain Yogurt 500g",
                "location_code": "COLD-01",
                "quantity": 8,
                "expiry_date": "2024-01-18T00:00:00Z",
                "days_until_expiry": 3,
                "batch_number": "BATCH-2024-002"
            }
        ],
        "nextjs_example": """
// Get expiring items
interface ExpiringBatch {
    batch_id: string;
    sku: string;
    product_name: string;
    location_code: string;
    quantity: number;
    expiry_date: string;
    days_until_expiry: number;
    batch_number: string | null;
}

const getExpiringItems = async (daysAhead: number = 7, locationId?: string): Promise<ExpiringBatch[]> => {
    const accessToken = localStorage.getItem('access_token');
    
    const params = new URLSearchParams({ days_ahead: daysAhead.toString() });
    if (locationId) {
        params.append('location_id', locationId);
    }
    
    const response = await fetch(`http://localhost:8000/api/v1/inventory/alerts/expiring?${params}`, {
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });
    
    if (!response.ok) {
        throw new Error('Failed to get expiring items');
    }
    
    return response.json();
};

// Usage - get items expiring in next 3 days
const expiringItems = await getExpiringItems(3);
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Get Movement History (GET)
    # ─────────────────────────────────────────────────────────────────────────────
    "get_movement_history": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/inventory/history/{{sku}}",
        "purpose": "Get stock movement audit trail for a SKU at a specific location.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "url_parameters": {
            "sku": "string (required) - Product SKU (in URL path)",
        },
        "query_parameters": {
            "location_id": "string (required) - Location UUID",
            "limit": "integer (optional) - Max records to return. 1-200, default 50.",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/inventory/history/MILK-2L-WHOLE?location_id=550e8400-e29b-41d4-a716-446655440001&limit=50",
            "headers": {
                "Authorization": "Bearer <access_token>"
            }
        },
        "sample_response": {
            "sku": "MILK-2L-WHOLE",
            "location_id": "550e8400-e29b-41d4-a716-446655440001",
            "movements": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440020",
                    "inventory_item_id": "550e8400-e29b-41d4-a716-446655440010",
                    "movement_type": "sale",
                    "reason": "customer_sale",
                    "quantity_delta": -5,
                    "quantity_before": 100,
                    "quantity_after": 95,
                    "user_id": "550e8400-e29b-41d4-a716-446655440099",
                    "reference_id": "ORD-2024-00123",
                    "reference_type": "order",
                    "notes": None,
                    "created_at": "2024-01-15T14:30:00Z"
                },
                {
                    "id": "550e8400-e29b-41d4-a716-446655440019",
                    "movement_type": "receiving",
                    "reason": "supplier_delivery",
                    "quantity_delta": 50,
                    "quantity_before": 50,
                    "quantity_after": 100,
                    "reference_id": "PO-2024-001",
                    "created_at": "2024-01-15T08:00:00Z"
                }
            ],
            "total": 2
        },
        "nextjs_example": """
// Get movement history
interface StockMovement {
    id: string;
    inventory_item_id: string;
    movement_type: string;
    reason: string | null;
    quantity_delta: number;
    quantity_before: number;
    quantity_after: number;
    user_id: string;
    reference_id: string | null;
    reference_type: string | null;
    notes: string | null;
    created_at: string;
}

interface MovementHistoryResponse {
    sku: string;
    location_id: string;
    movements: StockMovement[];
    total: number;
}

const getMovementHistory = async (
    sku: string, 
    locationId: string, 
    limit: number = 50
): Promise<MovementHistoryResponse> => {
    const accessToken = localStorage.getItem('access_token');
    
    const params = new URLSearchParams({
        location_id: locationId,
        limit: limit.toString(),
    });
    
    const response = await fetch(
        `http://localhost:8000/api/v1/inventory/history/${encodeURIComponent(sku)}?${params}`,
        {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
            },
        }
    );
    
    if (!response.ok) {
        throw new Error('Failed to get movement history');
    }
    
    return response.json();
};
"""
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

ADMIN_ENDPOINTS = {
    # ─────────────────────────────────────────────────────────────────────────────
    # Get Audit Log (GET) - Manager+ Only
    # ─────────────────────────────────────────────────────────────────────────────
    "get_audit_log": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/admin/audit-log",
        "purpose": "Query the immutable stock movement audit trail with comprehensive filters.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "MANAGER",
        "allowed_roles": ["MANAGER", "ADMIN"],
        "query_parameters": {
            "sku": "string (optional) - Filter by product SKU (case-insensitive). Max 50 chars.",
            "location_code": "string (optional) - Filter by location code. Max 50 chars.",
            "action_type": "string (optional) - Filter by action type: 'receiving', 'sale', 'transfer', 'adjustment', 'return', 'disposal', 'reservation'.",
            "reason": "string (optional) - Filter by reason code.",
            "performed_by": "string (optional) - Filter by user name (partial match). Max 100 chars.",
            "start_date": "datetime (optional) - Filter from date (ISO 8601).",
            "end_date": "datetime (optional) - Filter until date (ISO 8601).",
            "reference_id": "string (optional) - Filter by reference ID (order, PO). Max 50 chars.",
            "limit": "integer (optional) - Max records to return. 1-500, default 50.",
            "offset": "integer (optional) - Records to skip. Default 0.",
        },
        "valid_action_types": ["receiving", "sale", "transfer", "adjustment", "return", "disposal", "reservation"],
        "valid_reasons": [
            "supplier_delivery", "internal_transfer", "customer_sale", "expired", 
            "damaged", "theft", "shrinkage", "cycle_count", "audit_correction", 
            "system_correction", "customer_return", "online_reservation", "reservation_released"
        ],
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/admin/audit-log?sku=MILK-2L&action_type=sale&start_date=2024-01-01T00:00:00Z&limit=50",
            "headers": {
                "Authorization": "Bearer <manager_access_token>"
            }
        },
        "sample_response": {
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
                    "reference_type": "order",
                    "notes": None,
                    "change_direction": "decrease"
                }
            ],
            "total": 150,
            "limit": 50,
            "offset": 0,
            "filters_applied": {
                "sku": "MILK-2L",
                "action_type": "sale"
            },
            "has_more": True,
            "page": 1,
            "total_pages": 3
        },
        "nextjs_example": """
// Get audit log (Manager+ only)
interface AuditLogEntry {
    sku: string;
    product_name: string;
    location_code: string;
    location_name: string;
    action_type: string;
    reason: string | null;
    quantity_delta: number;
    quantity_before: number;
    quantity_after: number;
    performed_by: string;
    timestamp: string;
    reference_id: string | null;
    reference_type: string | null;
    notes: string | null;
    change_direction: 'increase' | 'decrease' | 'no_change';
}

interface AuditLogResponse {
    entries: AuditLogEntry[];
    total: number;
    limit: number;
    offset: number;
    filters_applied: Record<string, any>;
    has_more: boolean;
    page: number;
    total_pages: number;
}

interface AuditLogFilters {
    sku?: string;
    location_code?: string;
    action_type?: string;
    reason?: string;
    performed_by?: string;
    start_date?: string;
    end_date?: string;
    reference_id?: string;
    limit?: number;
    offset?: number;
}

const getAuditLog = async (filters: AuditLogFilters = {}): Promise<AuditLogResponse> => {
    const accessToken = localStorage.getItem('access_token');
    
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            params.append(key, String(value));
        }
    });
    
    const response = await fetch(`http://localhost:8000/api/v1/admin/audit-log?${params}`, {
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });
    
    if (response.status === 403) {
        throw new Error('Insufficient permissions. Manager role required.');
    }
    
    if (!response.ok) {
        throw new Error('Failed to get audit log');
    }
    
    return response.json();
};

// Usage with filters
const auditData = await getAuditLog({
    sku: 'MILK-2L',
    action_type: 'sale',
    start_date: '2024-01-01T00:00:00Z',
    limit: 50,
});
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Export Audit Log CSV (GET) - Manager+ Only
    # ─────────────────────────────────────────────────────────────────────────────
    "export_audit_log_csv": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/admin/audit-log/export.csv",
        "purpose": "Export audit log entries as a downloadable CSV file. Supports same filters as audit-log endpoint.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "MANAGER",
        "allowed_roles": ["MANAGER", "ADMIN"],
        "query_parameters": {
            "sku": "string (optional) - Filter by SKU.",
            "location_code": "string (optional) - Filter by location.",
            "action_type": "string (optional) - Filter by action type.",
            "reason": "string (optional) - Filter by reason.",
            "performed_by": "string (optional) - Filter by user name.",
            "start_date": "datetime (optional) - Filter from date.",
            "end_date": "datetime (optional) - Filter until date.",
            "reference_id": "string (optional) - Filter by reference ID.",
            "limit": "integer (optional) - Max records. 1-100000, default 10000.",
            "offset": "integer (optional) - Records to skip.",
        },
        "csv_columns": [
            "timestamp", "sku", "product_name", "location_code", "location_name",
            "action_type", "reason", "quantity_delta", "quantity_before",
            "quantity_after", "performed_by", "reference_id", "reference_type", "notes"
        ],
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/admin/audit-log/export.csv?start_date=2024-01-01T00:00:00Z",
            "headers": {
                "Authorization": "Bearer <manager_access_token>"
            }
        },
        "response_headers": {
            "Content-Type": "text/csv",
            "Content-Disposition": "attachment; filename=\"audit_log_export_20240115_143000.csv\""
        },
        "nextjs_example": """
// Export audit log as CSV (Manager+ only)
const exportAuditLogCsv = async (filters: AuditLogFilters = {}) => {
    const accessToken = localStorage.getItem('access_token');
    
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            params.append(key, String(value));
        }
    });
    
    const response = await fetch(`http://localhost:8000/api/v1/admin/audit-log/export.csv?${params}`, {
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });
    
    if (!response.ok) {
        throw new Error('Failed to export audit log');
    }
    
    // Get filename from Content-Disposition header
    const contentDisposition = response.headers.get('Content-Disposition');
    const filenameMatch = contentDisposition?.match(/filename="(.+)"/);
    const filename = filenameMatch ? filenameMatch[1] : 'audit_log_export.csv';
    
    // Download the file
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
};

// Usage
await exportAuditLogCsv({
    start_date: '2024-01-01T00:00:00Z',
    end_date: '2024-01-31T23:59:59Z',
});
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Get Audit Statistics (GET) - Manager+ Only
    # ─────────────────────────────────────────────────────────────────────────────
    "get_audit_stats": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/admin/audit-log/stats",
        "purpose": "Get aggregated statistics from the audit log for dashboards and reporting.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "MANAGER",
        "allowed_roles": ["MANAGER", "ADMIN"],
        "query_parameters": {
            "start_date": "datetime (optional) - Period start (default: 30 days ago).",
            "end_date": "datetime (optional) - Period end (default: now).",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/admin/audit-log/stats?start_date=2024-01-01T00:00:00Z&end_date=2024-01-31T23:59:59Z",
            "headers": {
                "Authorization": "Bearer <manager_access_token>"
            }
        },
        "sample_response": {
            "period_start": "2024-01-01T00:00:00Z",
            "period_end": "2024-01-31T23:59:59Z",
            "total_actions": 1500,
            "total_units_increased": 5000,
            "total_units_decreased": 4500,
            "net_stock_change": 500,
            "by_action_type": [
                {
                    "action_type": "sale",
                    "count": 1000,
                    "total_units_affected": 3500,
                    "average_units_per_action": 3.5
                },
                {
                    "action_type": "receiving",
                    "count": 300,
                    "total_units_affected": 4500,
                    "average_units_per_action": 15.0
                }
            ],
            "by_day": [
                {
                    "date": "2024-01-31",
                    "total_actions": 50,
                    "total_units_increased": 200,
                    "total_units_decreased": 150,
                    "net_change": 50
                }
            ],
            "top_products": [
                {"sku": "MILK-2L", "name": "Whole Milk 2L", "movement_count": 150},
                {"sku": "BREAD-WHITE", "name": "White Bread Loaf", "movement_count": 120}
            ],
            "top_users": [
                {"name": "John Smith", "action_count": 200},
                {"name": "Jane Doe", "action_count": 180}
            ]
        },
        "nextjs_example": """
// Get audit statistics (Manager+ only)
interface ActionTypeStats {
    action_type: string;
    count: number;
    total_units_affected: number;
    average_units_per_action: number;
}

interface DailyStats {
    date: string;
    total_actions: number;
    total_units_increased: number;
    total_units_decreased: number;
    net_change: number;
}

interface AuditStatsResponse {
    period_start: string;
    period_end: string;
    total_actions: number;
    total_units_increased: number;
    total_units_decreased: number;
    net_stock_change: number;
    by_action_type: ActionTypeStats[];
    by_day: DailyStats[];
    top_products: { sku: string; name: string; movement_count: number }[];
    top_users: { name: string; action_count: number }[];
}

const getAuditStats = async (startDate?: string, endDate?: string): Promise<AuditStatsResponse> => {
    const accessToken = localStorage.getItem('access_token');
    
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    
    const response = await fetch(`http://localhost:8000/api/v1/admin/audit-log/stats?${params}`, {
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });
    
    if (response.status === 403) {
        throw new Error('Insufficient permissions. Manager role required.');
    }
    
    if (!response.ok) {
        throw new Error('Failed to get audit statistics');
    }
    
    return response.json();
};

// Usage for dashboard
const stats = await getAuditStats('2024-01-01T00:00:00Z', '2024-01-31T23:59:59Z');
console.log(`Total actions: ${stats.total_actions}`);
console.log(`Net stock change: ${stats.net_stock_change}`);
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # List Action Types (GET)
    # ─────────────────────────────────────────────────────────────────────────────
    "list_action_types": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/admin/audit-log/action-types",
        "purpose": "Get list of valid action types and reasons for building filter UIs.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/admin/audit-log/action-types",
            "headers": {
                "Authorization": "Bearer <access_token>"
            }
        },
        "sample_response": {
            "action_types": [
                "receiving", "sale", "transfer", "adjustment", 
                "return", "disposal", "reservation"
            ],
            "reasons": [
                "supplier_delivery", "internal_transfer", "customer_sale", "expired",
                "damaged", "theft", "shrinkage", "cycle_count", "audit_correction",
                "system_correction", "customer_return", "online_reservation", "reservation_released"
            ]
        },
        "nextjs_example": """
// Get valid action types and reasons (for building filter dropdowns)
interface ActionTypesResponse {
    action_types: string[];
    reasons: string[];
}

const getActionTypes = async (): Promise<ActionTypesResponse> => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch('http://localhost:8000/api/v1/admin/audit-log/action-types', {
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });
    
    if (!response.ok) {
        throw new Error('Failed to get action types');
    }
    
    return response.json();
};

// Usage in a React filter component
const [filterOptions, setFilterOptions] = useState<ActionTypesResponse | null>(null);

useEffect(() => {
    getActionTypes().then(setFilterOptions);
}, []);

// Render dropdown
{filterOptions && (
    <select>
        <option value="">All Action Types</option>
        {filterOptions.action_types.map(type => (
            <option key={type} value={type}>{type}</option>
        ))}
    </select>
)}
"""
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

PRODUCT_ENDPOINTS = {
    # ─────────────────────────────────────────────────────────────────────────────
    # List Products (GET)
    # ─────────────────────────────────────────────────────────────────────────────
    "list_products": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/products",
        "purpose": "List all products with optional filtering by category and search.",
        "authentication": "Not required (Public endpoint)",
        "minimum_role": "None (Public)",
        "allowed_roles": ["Public", "STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "query_parameters": {
            "category": "string (optional) - Filter by category code (e.g., 'dairy', 'produce').",
            "search": "string (optional) - Search in product name and SKU. Max 100 chars.",
            "limit": "integer (optional) - Max products to return. 1-200, default 50.",
            "offset": "integer (optional) - Number of products to skip. Default 0.",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/products?category=dairy&limit=20",
            "headers": {
                "Authorization": "Bearer <access_token>"
            }
        },
        "sample_response": {
            "products": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "sku": "MILK-2L-WHOLE",
                    "name": "Whole Milk 2L",
                    "category": "dairy",
                    "unit_price": 3.99,
                    "is_perishable": True,
                    "is_active": True
                },
                {
                    "id": "550e8400-e29b-41d4-a716-446655440001",
                    "sku": "CHEESE-CHEDDAR-500G",
                    "name": "Cheddar Cheese 500g",
                    "category": "dairy",
                    "unit_price": 6.99,
                    "is_perishable": True,
                    "is_active": True
                }
            ],
            "total": 45,
            "limit": 20,
            "offset": 0,
            "has_more": True,
            "page": 1,
            "total_pages": 3
        },
        "nextjs_example": """
// List products with filtering
interface ProductSummary {
    id: string;
    sku: string;
    name: string;
    category: string;
    unit_price: number;
    is_perishable: boolean;
    is_active: boolean;
}

interface ProductListResponse {
    products: ProductSummary[];
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
    page: number;
    total_pages: number;
}

interface ProductFilters {
    category?: string;
    search?: string;
    limit?: number;
    offset?: number;
}

const listProducts = async (filters: ProductFilters = {}): Promise<ProductListResponse> => {
    const accessToken = localStorage.getItem('access_token');
    
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            params.append(key, String(value));
        }
    });
    
    const response = await fetch(`http://localhost:8000/api/v1/products?${params}`, {
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });
    
    if (!response.ok) {
        throw new Error('Failed to list products');
    }
    
    return response.json();
};

// Usage
const products = await listProducts({ category: 'dairy', limit: 20 });
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Get Product by SKU (GET)
    # ─────────────────────────────────────────────────────────────────────────────
    "get_product": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/products/{{sku}}",
        "purpose": "Get detailed product information by SKU.",
        "authentication": "Not required (Public endpoint)",
        "minimum_role": "None (Public)",
        "allowed_roles": ["Public", "STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "url_parameters": {
            "sku": "string (required) - Product SKU (in URL path)",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/products/MILK-2L-WHOLE",
            "headers": {
                "Authorization": "Bearer <access_token>"
            }
        },
        "sample_response": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "MILK-2L-WHOLE",
            "name": "Whole Milk 2L",
            "description": "Fresh whole milk from local farms",
            "category": "dairy",
            "brand": "Farm Fresh",
            "unit_price": 3.99,
            "cost_price": 2.50,
            "tax_rate": 0.0,
            "barcode": "4901234567890",
            "unit_of_measure": "each",
            "pack_size": 1,
            "is_perishable": True,
            "shelf_life_days": 14,
            "requires_cold_storage": True,
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-15T10:30:00Z",
            "price_with_tax": 3.99,
            "margin_percent": 59.6
        },
        "nextjs_example": """
// Get product by SKU
interface Product {
    id: string;
    sku: string;
    name: string;
    description: string | null;
    category: string;
    brand: string | null;
    unit_price: number;
    cost_price: number | null;
    tax_rate: number;
    barcode: string | null;
    unit_of_measure: string;
    pack_size: number;
    is_perishable: boolean;
    shelf_life_days: number | null;
    requires_cold_storage: boolean;
    is_active: boolean;
    created_at: string;
    updated_at: string;
    price_with_tax: number;
    margin_percent: number | null;
}

const getProduct = async (sku: string): Promise<Product> => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch(`http://localhost:8000/api/v1/products/${encodeURIComponent(sku)}`, {
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });
    
    if (response.status === 404) {
        throw new Error('Product not found');
    }
    
    if (!response.ok) {
        throw new Error('Failed to get product');
    }
    
    return response.json();
};
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Get Product by Barcode (GET)
    # ─────────────────────────────────────────────────────────────────────────────
    "get_product_by_barcode": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/products/barcode/{{barcode}}",
        "purpose": "Get product information by scanning its barcode. Useful for POS and inventory receiving.",
        "authentication": "Not required (Public endpoint)",
        "minimum_role": "None (Public)",
        "allowed_roles": ["Public", "STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "url_parameters": {
            "barcode": "string (required) - Product barcode (UPC/EAN)",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/products/barcode/4901234567890",
            "headers": {
                "Authorization": "Bearer <access_token>"
            }
        },
        "sample_response": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "MILK-2L-WHOLE",
            "name": "Whole Milk 2L",
            "category": "dairy",
            "unit_price": 3.99,
            "barcode": "4901234567890"
        },
        "nextjs_example": """
// Get product by barcode (for POS/scanning)
const getProductByBarcode = async (barcode: string): Promise<Product> => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch(`http://localhost:8000/api/v1/products/barcode/${encodeURIComponent(barcode)}`, {
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });
    
    if (response.status === 404) {
        throw new Error('Product not found for this barcode');
    }
    
    if (!response.ok) {
        throw new Error('Failed to lookup barcode');
    }
    
    return response.json();
};

// Usage for barcode scanner
const handleBarcodeScan = async (barcode: string) => {
    try {
        const product = await getProductByBarcode(barcode);
        console.log('Scanned product:', product.name);
    } catch (error) {
        console.error('Product not found');
    }
};
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Create Product (POST) - Manager+ Only
    # ─────────────────────────────────────────────────────────────────────────────
    "create_product": {
        "method": "POST",
        "endpoint": f"{API_PREFIX}/products",
        "purpose": "Create a new product in the catalog. SKU must be unique and cannot be changed after creation.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "MANAGER",
        "allowed_roles": ["MANAGER", "ADMIN"],
        "request_body": {
            "sku": "string (required) - Unique Stock Keeping Unit. Cannot be changed after creation. Max 50 chars.",
            "name": "string (required) - Product display name. Max 200 chars.",
            "description": "string (optional) - Detailed description. Max 1000 chars.",
            "category": "string (optional) - Product category. Default 'other'.",
            "brand": "string (optional) - Brand name. Max 100 chars.",
            "unit_price": "decimal (required) - Selling price. Must be >= 0.",
            "cost_price": "decimal (optional) - Purchase cost for margin calculation.",
            "tax_rate": "decimal (optional) - Tax rate as decimal (0.13 = 13%). Default 0.",
            "barcode": "string (optional) - UPC/EAN barcode. Must be unique.",
            "unit_of_measure": "string (optional) - How sold: 'each', 'kg', 'liter', 'pack'. Default 'each'.",
            "pack_size": "integer (optional) - Units per pack. Default 1.",
            "is_perishable": "boolean (optional) - Has expiry dates. Default false.",
            "shelf_life_days": "integer (optional) - Expected shelf life in days.",
            "requires_cold_storage": "boolean (optional) - Needs refrigeration. Default false.",
        },
        "valid_categories": [
            "dairy", "produce", "meat", "bakery", "frozen", "beverages",
            "snacks", "canned", "dry_goods", "household", "personal_care", "other"
        ],
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/products",
            "headers": {
                "Authorization": "Bearer <manager_access_token>",
                "Content-Type": "application/json"
            },
            "body": {
                "sku": "MILK-2L-WHOLE",
                "name": "Whole Milk 2L",
                "description": "Fresh whole milk from local farms",
                "category": "dairy",
                "brand": "Farm Fresh",
                "unit_price": 3.99,
                "cost_price": 2.50,
                "tax_rate": 0.0,
                "barcode": "4901234567890",
                "unit_of_measure": "each",
                "is_perishable": True,
                "shelf_life_days": 14,
                "requires_cold_storage": True
            }
        },
        "sample_response": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "MILK-2L-WHOLE",
            "name": "Whole Milk 2L",
            "category": "dairy",
            "unit_price": 3.99,
            "is_active": True,
            "created_at": "2024-01-15T10:30:00Z"
        },
        "nextjs_example": """
// Create product (Manager+ only)
interface CreateProductPayload {
    sku: string;
    name: string;
    unit_price: number;
    description?: string;
    category?: string;
    brand?: string;
    cost_price?: number;
    tax_rate?: number;
    barcode?: string;
    unit_of_measure?: string;
    pack_size?: number;
    is_perishable?: boolean;
    shelf_life_days?: number;
    requires_cold_storage?: boolean;
}

const createProduct = async (payload: CreateProductPayload): Promise<Product> => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch('http://localhost:8000/api/v1/products', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
    
    if (response.status === 403) {
        throw new Error('Insufficient permissions. Manager role required.');
    }
    
    if (response.status === 422) {
        const error = await response.json();
        throw new Error(error.detail?.message || 'Validation error');
    }
    
    if (!response.ok) {
        throw new Error('Failed to create product');
    }
    
    return response.json();
};

// Usage
const newProduct = await createProduct({
    sku: 'BREAD-WHOLE-WHEAT',
    name: 'Whole Wheat Bread',
    category: 'bakery',
    unit_price: 4.50,
    is_perishable: true,
    shelf_life_days: 5,
});
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Update Product (PUT) - Manager+ Only
    # ─────────────────────────────────────────────────────────────────────────────
    "update_product": {
        "method": "PUT",
        "endpoint": f"{API_PREFIX}/products/{{sku}}",
        "purpose": "Update an existing product. Note: SKU cannot be changed.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "MANAGER",
        "allowed_roles": ["MANAGER", "ADMIN"],
        "url_parameters": {
            "sku": "string (required) - Product SKU to update",
        },
        "request_body": {
            "name": "string (optional) - Product display name.",
            "description": "string (optional) - Detailed description.",
            "category": "string (optional) - Product category.",
            "brand": "string (optional) - Brand name.",
            "unit_price": "decimal (optional) - Selling price.",
            "cost_price": "decimal (optional) - Purchase cost.",
            "tax_rate": "decimal (optional) - Tax rate.",
            "barcode": "string (optional) - UPC/EAN barcode.",
            "unit_of_measure": "string (optional) - How sold.",
            "pack_size": "integer (optional) - Units per pack.",
            "is_perishable": "boolean (optional) - Has expiry dates.",
            "shelf_life_days": "integer (optional) - Expected shelf life.",
            "requires_cold_storage": "boolean (optional) - Needs refrigeration.",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/products/MILK-2L-WHOLE",
            "headers": {
                "Authorization": "Bearer <manager_access_token>",
                "Content-Type": "application/json"
            },
            "body": {
                "unit_price": 4.29,
                "description": "Premium whole milk from local organic farms"
            }
        },
        "sample_response": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "sku": "MILK-2L-WHOLE",
            "name": "Whole Milk 2L",
            "unit_price": 4.29,
            "description": "Premium whole milk from local organic farms",
            "updated_at": "2024-01-15T14:30:00Z"
        },
        "nextjs_example": """
// Update product (Manager+ only)
interface UpdateProductPayload {
    name?: string;
    description?: string;
    category?: string;
    brand?: string;
    unit_price?: number;
    cost_price?: number;
    tax_rate?: number;
    barcode?: string;
    unit_of_measure?: string;
    pack_size?: number;
    is_perishable?: boolean;
    shelf_life_days?: number;
    requires_cold_storage?: boolean;
}

const updateProduct = async (sku: string, payload: UpdateProductPayload): Promise<Product> => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch(`http://localhost:8000/api/v1/products/${encodeURIComponent(sku)}`, {
        method: 'PUT',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
    
    if (response.status === 403) {
        throw new Error('Insufficient permissions. Manager role required.');
    }
    
    if (response.status === 404) {
        throw new Error('Product not found');
    }
    
    if (!response.ok) {
        throw new Error('Failed to update product');
    }
    
    return response.json();
};

// Usage - update price
await updateProduct('MILK-2L-WHOLE', { unit_price: 4.29 });
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Delete Product (DELETE) - Admin Only
    # ─────────────────────────────────────────────────────────────────────────────
    "delete_product": {
        "method": "DELETE",
        "endpoint": f"{API_PREFIX}/products/{{sku}}",
        "purpose": "Soft delete a product (marks as inactive). Can be recovered.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "ADMIN",
        "allowed_roles": ["ADMIN"],
        "url_parameters": {
            "sku": "string (required) - Product SKU to delete",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/products/DISCONTINUED-ITEM",
            "headers": {
                "Authorization": "Bearer <admin_access_token>"
            }
        },
        "sample_response": {
            "id": "550e8400-e29b-41d4-a716-446655440099",
            "sku": "DISCONTINUED-ITEM",
            "name": "Discontinued Product",
            "is_active": False
        },
        "nextjs_example": """
// Delete product (Admin only)
const deleteProduct = async (sku: string): Promise<Product> => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch(`http://localhost:8000/api/v1/products/${encodeURIComponent(sku)}`, {
        method: 'DELETE',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });
    
    if (response.status === 403) {
        throw new Error('Insufficient permissions. Admin role required.');
    }
    
    if (response.status === 404) {
        throw new Error('Product not found');
    }
    
    if (!response.ok) {
        throw new Error('Failed to delete product');
    }
    
    return response.json();
};
"""
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORY_ENDPOINTS = {
    # ─────────────────────────────────────────────────────────────────────────────
    # List Categories (GET)
    # ─────────────────────────────────────────────────────────────────────────────
    "list_categories": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/categories",
        "purpose": "List all available product categories with descriptions.",
        "authentication": "Not required (Public endpoint)",
        "minimum_role": "None (Public)",
        "allowed_roles": ["Public", "STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/categories",
            "headers": {
            }
        },
        "sample_response": {
            "categories": [
                {
                    "code": "dairy",
                    "name": "Dairy",
                    "description": "Milk, cheese, yogurt, butter, and other dairy products"
                },
                {
                    "code": "produce",
                    "name": "Produce",
                    "description": "Fresh fruits and vegetables"
                },
                {
                    "code": "meat",
                    "name": "Meat",
                    "description": "Fresh and frozen meat, poultry, and seafood"
                },
                {
                    "code": "bakery",
                    "name": "Bakery",
                    "description": "Bread, pastries, cakes, and baked goods"
                },
                {
                    "code": "frozen",
                    "name": "Frozen",
                    "description": "Frozen foods including meals, vegetables, and desserts"
                },
                {
                    "code": "beverages",
                    "name": "Beverages",
                    "description": "Drinks including water, juice, soda, and coffee"
                },
                {
                    "code": "snacks",
                    "name": "Snacks",
                    "description": "Chips, crackers, nuts, and other snack foods"
                },
                {
                    "code": "canned",
                    "name": "Canned",
                    "description": "Canned fruits, vegetables, soups, and meals"
                },
                {
                    "code": "dry_goods",
                    "name": "Dry Goods",
                    "description": "Pasta, rice, cereals, flour, and dry ingredients"
                },
                {
                    "code": "household",
                    "name": "Household",
                    "description": "Cleaning supplies, paper products, and home essentials"
                },
                {
                    "code": "personal_care",
                    "name": "Personal Care",
                    "description": "Toiletries, hygiene products, and health items"
                },
                {
                    "code": "other",
                    "name": "Other",
                    "description": "Miscellaneous items that don't fit other categories"
                }
            ],
            "total": 12
        },
        "nextjs_example": """
// List all categories
interface Category {
    code: string;
    name: string;
    description: string | null;
}

interface CategoryListResponse {
    categories: Category[];
    total: number;
}

const listCategories = async (): Promise<CategoryListResponse> => {
    const accessToken = localStorage.getItem('access_token');
    
    const response = await fetch('http://localhost:8000/api/v1/categories', {
        headers: {
            'Authorization': `Bearer ${accessToken}`,
        },
    });
    
    if (!response.ok) {
        throw new Error('Failed to list categories');
    }
    
    return response.json();
};

// Usage in React component for category dropdown
const [categories, setCategories] = useState<Category[]>([]);

useEffect(() => {
    listCategories().then(data => setCategories(data.categories));
}, []);

// Render category selector
<select>
    <option value="">All Categories</option>
    {categories.map(cat => (
        <option key={cat.code} value={cat.code}>{cat.name}</option>
    ))}
</select>
"""
    },
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Get Products by Category (GET)
    # ─────────────────────────────────────────────────────────────────────────────
    "get_products_by_category": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/categories/{{category_code}}/products",
        "purpose": "Get all products in a specific category.",
        "authentication": "Not required (Public endpoint)",
        "minimum_role": "None (Public)",
        "allowed_roles": ["Public", "STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "url_parameters": {
            "category_code": "string (required) - Category code (e.g., 'dairy', 'produce')",
        },
        "query_parameters": {
            "limit": "integer (optional) - Max products to return. 1-200, default 50.",
            "offset": "integer (optional) - Number of products to skip. Default 0.",
        },
        "valid_category_codes": [
            "dairy", "produce", "meat", "bakery", "frozen", "beverages",
            "snacks", "canned", "dry_goods", "household", "personal_care", "other"
        ],
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/categories/dairy/products?limit=20",
            "headers": {
                "Authorization": "Bearer <access_token>"
            }
        },
        "sample_response": {
            "products": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "sku": "MILK-2L-WHOLE",
                    "name": "Whole Milk 2L",
                    "category": "dairy",
                    "unit_price": 3.99,
                    "is_perishable": True,
                    "is_active": True
                },
                {
                    "id": "550e8400-e29b-41d4-a716-446655440001",
                    "sku": "CHEESE-CHEDDAR-500G",
                    "name": "Cheddar Cheese 500g",
                    "category": "dairy",
                    "unit_price": 6.99,
                    "is_perishable": True,
                    "is_active": True
                }
            ],
            "total": 15,
            "limit": 20,
            "offset": 0,
            "has_more": False,
            "page": 1,
            "total_pages": 1
        },
        "nextjs_example": """
// Get products by category
const getProductsByCategory = async (
    categoryCode: string,
    limit: number = 50,
    offset: number = 0
): Promise<ProductListResponse> => {
    const accessToken = localStorage.getItem('access_token');
    
    const params = new URLSearchParams({
        limit: limit.toString(),
        offset: offset.toString(),
    });
    
    const response = await fetch(
        `http://localhost:8000/api/v1/categories/${encodeURIComponent(categoryCode)}/products?${params}`,
        {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
            },
        }
    );
    
    if (response.status === 404) {
        throw new Error(`Invalid category: ${categoryCode}`);
    }
    
    if (!response.ok) {
        throw new Error('Failed to get products by category');
    }
    
    return response.json();
};

// Usage
const dairyProducts = await getProductsByCategory('dairy');
console.log(`Found ${dairyProducts.total} dairy products`);
"""
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# ORDER ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

ORDER_ENDPOINTS = {
    # ─────────────────────────────────────────────────────────────────────────────
    # Order Data Model (reference)
    # ─────────────────────────────────────────────────────────────────────────────
    "order_data_model": {
        "purpose": "Core order schema used by list/detail/status/substitution endpoints.",
        "fields": {
            "id": "string - Unique order ID.",
            "type": "string - 'pickup' | 'delivery'.",
            "status": "string - 'new' | 'preparing' | 'ready' | 'out_for_delivery' | 'completed' | 'cancelled'.",
            "created_at": "string (ISO 8601 UTC).",
            "time_slot": "string (optional) - Delivery/pickup window label or start/end.",
            "customer": {
                "name": "string",
                "phone": "string",
                "email": "string",
            },
            "address": "string (optional) - Delivery address or suburb.",
            "items": "array - See item schema below.",
            "subtotal": "number",
            "gst": "number",
            "delivery_fee": "number",
            "total": "number",
            "notes": "string (optional)",
            "has_substitutions": "boolean",
            "timestamps": {
                "updated_at": "string (ISO 8601 UTC)",
                "delivered_at": "string (ISO 8601 UTC, optional)",
            },
            "status_history": "array (optional) - [{ status, at, by? }]",
        },
        "item_schema": {
            "id": "string - Item ID (order line ID or product SKU).",
            "name": "string",
            "quantity": "number",
            "price": "number",
            "checked": "boolean (optional) - Pick/pack checklist state.",
            "substitution": "object (optional) - See substitution schema.",
        },
        "substitution_schema": {
            "original_item_id": "string (optional)",
            "original_name": "string",
            "original_price": "number",
            "original_qty": "number",
            "reason": "string",
            "status": "string - 'pending' | 'approved' | 'rejected'.",
            "substitute": {
                "id": "string (optional)",
                "name": "string",
                "price": "number",
            },
            "quantity": "number",
        },
    },
    "order_response_contract": {
        "success_shape": {
            "order_id": "string",
            "status": "string",
            "timestamp": "string (ISO 8601 UTC)",
            "order": "object - Full order payload",
        },
        "error_shape": {
            "error": "string",
            "code": "number",
        },
        "notes": "Map error codes to user-friendly toasts (invalid input, auth/session expired, payment/validation failure).",
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # List Orders (GET)
    # ─────────────────────────────────────────────────────────────────────────────
    "list_orders": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/orders",
        "purpose": "List orders for the grid/tabs with filtering and search.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "query_parameters": {
            "status": "string (optional) - Filter by status.",
            "type": "string (optional) - 'pickup' | 'delivery'.",
            "search": "string (optional) - Search by order id/customer name/phone/email.",
            "limit": "integer (optional) - Max orders to return. Default 50.",
            "offset": "integer (optional) - Number of orders to skip. Default 0.",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/orders?status=preparing&type=delivery&limit=20",
            "headers": {
                "Authorization": "Bearer <access_token>",
            }
        },
        "sample_response": {
            "orders": [
                {
                    "id": "ORD-2024-00123",
                    "type": "delivery",
                    "status": "preparing",
                    "created_at": "2024-04-01T09:12:00Z",
                    "time_slot": "10:00-12:00",
                    "customer": {
                        "name": "Alex Morgan",
                        "phone": "+61 400 000 000",
                        "email": "alex@example.com"
                    },
                    "address": "Newtown, NSW",
                    "items": [
                        {
                            "id": "MILK-2L-WHOLE",
                            "name": "Whole Milk 2L",
                            "quantity": 2,
                            "price": 3.99,
                            "checked": False
                        }
                    ],
                    "subtotal": 7.98,
                    "gst": 0.0,
                    "delivery_fee": 6.0,
                    "total": 13.98,
                    "notes": "Leave at front door",
                    "has_substitutions": False,
                    "timestamps": {
                        "updated_at": "2024-04-01T09:12:00Z"
                    }
                }
            ],
            "total": 1,
            "limit": 20,
            "offset": 0,
            "has_more": False,
            "page": 1,
            "total_pages": 1
        },
        "nextjs_example": """
// List orders with filters
interface OrderListFilters {
    status?: string;
    type?: 'pickup' | 'delivery';
    search?: string;
    limit?: number;
    offset?: number;
}

const listOrders = async (filters: OrderListFilters = {}) => {
    const accessToken = localStorage.getItem('access_token');
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            params.append(key, String(value));
        }
    });
    
    const response = await fetch(`http://localhost:8000/api/v1/orders?${params}`, {
        headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    
    if (!response.ok) {
        throw new Error('Failed to list orders');
    }
    
    return response.json();
};
"""
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # Get Order Detail (GET)
    # ─────────────────────────────────────────────────────────────────────────────
    "get_order": {
        "method": "GET",
        "endpoint": f"{API_PREFIX}/orders/{{order_id}}",
        "purpose": "Fetch full order detail for the modal (including substitutions and checked flags).",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "url_parameters": {
            "order_id": "string (required) - Order ID.",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/orders/ORD-2024-00123",
            "headers": {
                "Authorization": "Bearer <access_token>",
            }
        },
        "sample_response": {
            "id": "ORD-2024-00123",
            "type": "delivery",
            "status": "preparing",
            "created_at": "2024-04-01T09:12:00Z",
            "time_slot": "10:00-12:00",
            "customer": {
                "name": "Alex Morgan",
                "phone": "+61 400 000 000",
                "email": "alex@example.com"
            },
            "address": "12 Example St, Newtown NSW 2042",
            "items": [
                {
                    "id": "MILK-2L-WHOLE",
                    "name": "Whole Milk 2L",
                    "quantity": 2,
                    "price": 3.99,
                    "checked": True,
                    "substitution": {
                        "original_name": "Whole Milk 2L",
                        "original_price": 3.99,
                        "original_qty": 2,
                        "reason": "Out of stock",
                        "status": "approved",
                        "substitute": {
                            "id": "MILK-2L-REDUCED",
                            "name": "Reduced Fat Milk 2L",
                            "price": 3.89
                        },
                        "quantity": 2
                    }
                }
            ],
            "subtotal": 7.98,
            "gst": 0.0,
            "delivery_fee": 6.0,
            "total": 13.98,
            "notes": "Leave at front door",
            "has_substitutions": True,
            "timestamps": {
                "updated_at": "2024-04-01T09:30:00Z"
            }
        },
        "nextjs_example": """
// Get order detail
const getOrder = async (orderId: string) => {
    const accessToken = localStorage.getItem('access_token');
    const response = await fetch(`http://localhost:8000/api/v1/orders/${orderId}`, {
        headers: { 'Authorization': `Bearer ${accessToken}` },
    });
    
    if (!response.ok) {
        throw new Error('Failed to get order');
    }
    
    return response.json();
};
"""
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # Update Order Status (PATCH)
    # ─────────────────────────────────────────────────────────────────────────────
    "update_order_status": {
        "method": "PATCH",
        "endpoint": f"{API_PREFIX}/orders/{{order_id}}/status",
        "purpose": "Update the order status (preparing, ready, out_for_delivery, completed, cancelled).",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "url_parameters": {
            "order_id": "string (required) - Order ID.",
        },
        "request_body": {
            "status": "string (required) - 'preparing' | 'ready' | 'out_for_delivery' | 'completed' | 'cancelled'.",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/orders/ORD-2024-00123/status",
            "headers": {
                "Authorization": "Bearer <access_token>",
                "Content-Type": "application/json"
            },
            "body": {
                "status": "ready"
            }
        },
        "sample_response": {
            "order_id": "ORD-2024-00123",
            "status": "ready",
            "timestamp": "2024-04-01T09:45:00Z",
            "order": {
                "id": "ORD-2024-00123",
                "type": "delivery",
                "status": "ready",
                "created_at": "2024-04-01T09:12:00Z",
                "customer": {
                    "name": "Alex Morgan",
                    "phone": "+61 400 000 000",
                    "email": "alex@example.com"
                },
                "items": [
                    {
                        "id": "MILK-2L-WHOLE",
                        "name": "Whole Milk 2L",
                        "quantity": 2,
                        "price": 3.99,
                        "checked": True
                    }
                ],
                "subtotal": 7.98,
                "gst": 0.0,
                "delivery_fee": 6.0,
                "total": 13.98,
                "has_substitutions": False,
                "timestamps": {
                    "updated_at": "2024-04-01T09:45:00Z"
                }
            }
        },
        "nextjs_example": """
// Update order status
const updateOrderStatus = async (orderId: string, status: string) => {
    const accessToken = localStorage.getItem('access_token');
    const response = await fetch(`http://localhost:8000/api/v1/orders/${orderId}/status`, {
        method: 'PATCH',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ status }),
    });
    
    if (!response.ok) {
        throw new Error('Failed to update order status');
    }
    
    return response.json();
};
"""
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # Update Item Checklist (PATCH)
    # ─────────────────────────────────────────────────────────────────────────────
    "update_order_item_checklist": {
        "method": "PATCH",
        "endpoint": f"{API_PREFIX}/orders/{{order_id}}/items/{{item_id}}",
        "purpose": "Update pick/pack checklist state for a single item.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "url_parameters": {
            "order_id": "string (required) - Order ID.",
            "item_id": "string (required) - Item ID.",
        },
        "request_body": {
            "checked": "boolean (required)",
        },
        "notes": "If you support batch checklist updates, consider POST /orders/{order_id}/checklist.",
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/orders/ORD-2024-00123/items/MILK-2L-WHOLE",
            "headers": {
                "Authorization": "Bearer <access_token>",
                "Content-Type": "application/json"
            },
            "body": {
                "checked": True
            }
        },
        "sample_response": {
            "order_id": "ORD-2024-00123",
            "status": "preparing",
            "timestamp": "2024-04-01T09:25:00Z",
            "item": {
                "id": "MILK-2L-WHOLE",
                "checked": True
            }
        },
        "nextjs_example": """
// Update item checklist
const updateItemChecklist = async (orderId: string, itemId: string, checked: boolean) => {
    const accessToken = localStorage.getItem('access_token');
    const response = await fetch(`http://localhost:8000/api/v1/orders/${orderId}/items/${itemId}`, {
        method: 'PATCH',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ checked }),
    });
    
    if (!response.ok) {
        throw new Error('Failed to update checklist');
    }
    
    return response.json();
};
"""
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # Create Substitution (POST)
    # ─────────────────────────────────────────────────────────────────────────────
    "create_substitution": {
        "method": "POST",
        "endpoint": f"{API_PREFIX}/orders/{{order_id}}/substitutions",
        "purpose": "Add a substitution entry to an order item.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "url_parameters": {
            "order_id": "string (required) - Order ID.",
        },
        "request_body": {
            "original_item_id": "string (required) - Item being replaced.",
            "substitute_item_id": "string (required) - Substitute item ID or SKU.",
            "quantity": "number (required)",
            "reason": "string (required)",
            "status": "string (required) - 'pending' | 'approved' | 'rejected'.",
            "price_difference": "number (optional)",
            "customer_notified": "boolean (optional)",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/orders/ORD-2024-00123/substitutions",
            "headers": {
                "Authorization": "Bearer <access_token>",
                "Content-Type": "application/json"
            },
            "body": {
                "original_item_id": "MILK-2L-WHOLE",
                "substitute_item_id": "MILK-2L-REDUCED",
                "quantity": 2,
                "reason": "Out of stock",
                "status": "pending",
                "price_difference": -0.10,
                "customer_notified": False
            }
        },
        "sample_response": {
            "order_id": "ORD-2024-00123",
            "status": "preparing",
            "timestamp": "2024-04-01T09:28:00Z",
            "order": {
                "id": "ORD-2024-00123",
                "has_substitutions": True,
                "items": [
                    {
                        "id": "MILK-2L-WHOLE",
                        "substitution": {
                            "original_name": "Whole Milk 2L",
                            "original_price": 3.99,
                            "original_qty": 2,
                            "reason": "Out of stock",
                            "status": "pending",
                            "substitute": {
                                "id": "MILK-2L-REDUCED",
                                "name": "Reduced Fat Milk 2L",
                                "price": 3.89
                            },
                            "quantity": 2
                        }
                    }
                ]
            }
        },
        "nextjs_example": """
// Create substitution
interface CreateSubstitutionPayload {
    original_item_id: string;
    substitute_item_id: string;
    quantity: number;
    reason: string;
    status: 'pending' | 'approved' | 'rejected';
    price_difference?: number;
    customer_notified?: boolean;
}

const createSubstitution = async (orderId: string, payload: CreateSubstitutionPayload) => {
    const accessToken = localStorage.getItem('access_token');
    const response = await fetch(`http://localhost:8000/api/v1/orders/${orderId}/substitutions`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
    
    if (!response.ok) {
        throw new Error('Failed to create substitution');
    }
    
    return response.json();
};
"""
    },

    # ─────────────────────────────────────────────────────────────────────────────
    # Log Contact Attempt (POST - Optional)
    # ─────────────────────────────────────────────────────────────────────────────
    "log_contact_attempt": {
        "method": "POST",
        "endpoint": f"{API_PREFIX}/orders/{{order_id}}/contact",
        "purpose": "Log a contact attempt (call/SMS/email/WhatsApp). Optional if UI uses tel/sms/mailto.",
        "authentication": "Required (JWT Bearer Token)",
        "minimum_role": "STAFF",
        "allowed_roles": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"],
        "url_parameters": {
            "order_id": "string (required) - Order ID.",
        },
        "request_body": {
            "channel": "string (required) - 'call' | 'sms' | 'email' | 'whatsapp'.",
            "template_id": "string (optional)",
            "notes": "string (optional)",
        },
        "sample_request": {
            "url": f"{BASE_URL}{API_PREFIX}/orders/ORD-2024-00123/contact",
            "headers": {
                "Authorization": "Bearer <access_token>",
                "Content-Type": "application/json"
            },
            "body": {
                "channel": "sms",
                "template_id": "substitution-pending",
                "notes": "Sent substitution request"
            }
        },
        "sample_response": {
            "order_id": "ORD-2024-00123",
            "status": "preparing",
            "timestamp": "2024-04-01T09:31:00Z",
            "contact": {
                "channel": "sms",
                "template_id": "substitution-pending",
                "notes": "Sent substitution request",
                "created_at": "2024-04-01T09:31:00Z"
            }
        },
        "nextjs_example": """
// Log contact attempt
const logContactAttempt = async (orderId: string, channel: string, notes?: string) => {
    const accessToken = localStorage.getItem('access_token');
    const response = await fetch(`http://localhost:8000/api/v1/orders/${orderId}/contact`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ channel, notes }),
    });
    
    if (!response.ok) {
        throw new Error('Failed to log contact attempt');
    }
    
    return response.json();
};
"""
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# ERROR RESPONSES
# ═══════════════════════════════════════════════════════════════════════════════

ERROR_RESPONSES = {
    "401_unauthorized": {
        "status_code": 401,
        "description": "Not authenticated - Invalid or missing JWT token.",
        "sample_response": {
            "detail": "Not authenticated"
        },
        "nextjs_handling": """
// Handle 401 errors - redirect to login or refresh token
const handleAuthError = async (response: Response) => {
    if (response.status === 401) {
        try {
            // Try to refresh token
            await refreshAccessToken();
            // Retry the original request
        } catch {
            // Redirect to login
            window.location.href = '/login';
        }
    }
};
"""
    },
    
    "403_forbidden": {
        "status_code": 403,
        "description": "Insufficient permissions - User role is not high enough.",
        "sample_response": {
            "detail": {
                "message": "This action requires Manager or Owner role.",
                "code": "INSUFFICIENT_ROLE",
                "required_role": "MANAGER",
                "your_role": "staff"
            }
        },
        "nextjs_handling": """
// Handle 403 errors - show permission denied message
if (response.status === 403) {
    const error = await response.json();
    toast.error(error.detail?.message || 'Permission denied');
}
"""
    },
    
    "404_not_found": {
        "status_code": 404,
        "description": "Resource not found - Product, location, or inventory item doesn't exist.",
        "sample_response": {
            "detail": {
                "message": "Product not found: INVALID-SKU",
                "code": "NOT_FOUND",
                "resource": "product",
                "identifier": "INVALID-SKU"
            }
        }
    },
    
    "409_conflict": {
        "status_code": 409,
        "description": "Conflict - Concurrent modification detected (optimistic locking).",
        "sample_response": {
            "detail": {
                "message": "Stock was modified by another user. Please refresh and try again.",
                "code": "CONCURRENT_MODIFICATION",
                "action": "Please refresh and try again."
            }
        },
        "nextjs_handling": """
// Handle 409 errors - prompt user to refresh
if (response.status === 409) {
    toast.warning('Data was modified by another user. Please refresh and try again.');
    // Optionally auto-refresh the data
    await refetchData();
}
"""
    },
    
    "422_validation_error": {
        "status_code": 422,
        "description": "Validation error or business rule violation.",
        "sample_responses": {
            "insufficient_stock": {
                "detail": {
                    "message": "Insufficient stock available",
                    "code": "INSUFFICIENT_STOCK",
                    "requested": 100,
                    "available": 50
                }
            },
            "adjustment_too_large": {
                "detail": {
                    "message": "Stock adjustment exceeds 50% threshold. Set confirm_large_adjustment=true to proceed.",
                    "code": "ADJUSTMENT_TOO_LARGE",
                    "adjustment": 75,
                    "threshold_percent": 50
                }
            },
            "validation_error": {
                "detail": [
                    {
                        "type": "string_too_short",
                        "loc": ["body", "notes"],
                        "msg": "String should have at least 10 characters",
                        "input": "Short"
                    }
                ]
            }
        }
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# ROLE PERMISSIONS MATRIX
# ═══════════════════════════════════════════════════════════════════════════════

ROLE_PERMISSIONS = {
    "description": "Role hierarchy and permission matrix for the Kinmel API",
    "hierarchy": {
        "ADMIN": {"level": 100, "description": "Full system access, user management"},
        "MANAGER": {"level": 75, "description": "Inventory adjustments, reports, approvals"},
        "SUPERVISOR": {"level": 50, "description": "Stock movements, receiving, audits"},
        "STAFF": {"level": 25, "description": "Basic operations, viewing, sales"},
    },
    "permissions_matrix": {
        "receive_stock": {"min_role": "STAFF", "allowed": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"]},
        "adjust_stock": {"min_role": "MANAGER", "allowed": ["MANAGER", "ADMIN"]},
        "reserve_stock": {"min_role": "STAFF", "allowed": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"]},
        "release_reservation": {"min_role": "STAFF", "allowed": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"]},
        "fulfill_order": {"min_role": "STAFF", "allowed": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"]},
        "dispose_stock": {"min_role": "MANAGER", "allowed": ["MANAGER", "ADMIN"]},
        "get_stock_level": {"min_role": "STAFF", "allowed": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"]},
        "get_low_stock_alerts": {"min_role": "STAFF", "allowed": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"]},
        "get_expiring_items": {"min_role": "STAFF", "allowed": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"]},
        "get_movement_history": {"min_role": "STAFF", "allowed": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"]},
        "get_audit_log": {"min_role": "MANAGER", "allowed": ["MANAGER", "ADMIN"]},
        "export_audit_csv": {"min_role": "MANAGER", "allowed": ["MANAGER", "ADMIN"]},
        "get_audit_stats": {"min_role": "MANAGER", "allowed": ["MANAGER", "ADMIN"]},
        "list_action_types": {"min_role": "STAFF", "allowed": ["STAFF", "SUPERVISOR", "MANAGER", "ADMIN"]},
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
# NEXTJS API CLIENT TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════════

NEXTJS_API_CLIENT_TEMPLATE = """
// ═══════════════════════════════════════════════════════════════════════════════
// Kinmel API Client for Next.js
// ═══════════════════════════════════════════════════════════════════════════════
// 
// Copy this template to your Next.js project and customize as needed.
// File: src/lib/api/kinmel-client.ts
//

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_PREFIX = '/api/v1';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface TokenPair {
    access_token: string;
    refresh_token: string;
    token_type: string;
}

interface ApiError {
    detail: {
        message?: string;
        code?: string;
        [key: string]: any;
    } | string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Token Management
// ─────────────────────────────────────────────────────────────────────────────

export const getAccessToken = (): string | null => {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('access_token');
};

export const getRefreshToken = (): string | null => {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('refresh_token');
};

export const setTokens = (tokens: TokenPair): void => {
    localStorage.setItem('access_token', tokens.access_token);
    localStorage.setItem('refresh_token', tokens.refresh_token);
};

export const clearTokens = (): void => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
};

// ─────────────────────────────────────────────────────────────────────────────
// API Client
// ─────────────────────────────────────────────────────────────────────────────

class KinmelApiClient {
    private baseUrl: string;
    
    constructor(baseUrl: string = BASE_URL) {
        this.baseUrl = baseUrl;
    }
    
    private getHeaders(includeAuth: boolean = true): HeadersInit {
        const headers: HeadersInit = {
            'Content-Type': 'application/json',
        };
        
        if (includeAuth) {
            const token = getAccessToken();
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
        }
        
        return headers;
    }
    
    private async handleResponse<T>(response: Response): Promise<T> {
        if (response.status === 401) {
            // Try to refresh token
            const refreshed = await this.refreshToken();
            if (!refreshed) {
                clearTokens();
                throw new Error('Session expired. Please log in again.');
            }
            throw new Error('RETRY'); // Signal to retry the request
        }
        
        if (!response.ok) {
            const error: ApiError = await response.json();
            const message = typeof error.detail === 'string' 
                ? error.detail 
                : error.detail?.message || 'An error occurred';
            throw new Error(message);
        }
        
        return response.json();
    }
    
    // ─────────────────────────────────────────────────────────────────────────
    // Auth Methods
    // ─────────────────────────────────────────────────────────────────────────
    
    async login(email: string, password: string): Promise<TokenPair> {
        const response = await fetch(`${this.baseUrl}${API_PREFIX}/auth/login`, {
            method: 'POST',
            headers: this.getHeaders(false),
            body: JSON.stringify({ email, password }),
        });
        
        const tokens = await this.handleResponse<TokenPair>(response);
        setTokens(tokens);
        return tokens;
    }
    
    async refreshToken(): Promise<boolean> {
        const refreshToken = getRefreshToken();
        if (!refreshToken) return false;
        
        try {
            const response = await fetch(`${this.baseUrl}${API_PREFIX}/auth/refresh`, {
                method: 'POST',
                headers: this.getHeaders(false),
                body: JSON.stringify({ refresh_token: refreshToken }),
            });
            
            if (!response.ok) return false;
            
            const data = await response.json();
            localStorage.setItem('access_token', data.access_token);
            return true;
        } catch {
            return false;
        }
    }
    
    logout(): void {
        clearTokens();
    }
    
    // ─────────────────────────────────────────────────────────────────────────
    // Inventory Methods
    // ─────────────────────────────────────────────────────────────────────────
    
    async getStockLevel(sku: string, locationId?: string) {
        const params = locationId ? `?location_id=${locationId}` : '';
        const response = await fetch(
            `${this.baseUrl}${API_PREFIX}/inventory/stock/${encodeURIComponent(sku)}${params}`,
            { headers: this.getHeaders() }
        );
        return this.handleResponse(response);
    }
    
    async receiveStock(payload: {
        sku: string;
        location_id: string;
        quantity: number;
        batch_number?: string;
        expiry_date?: string;
        cost_per_unit?: number;
        reference_id?: string;
        notes?: string;
    }) {
        const response = await fetch(`${this.baseUrl}${API_PREFIX}/inventory/receive`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify(payload),
        });
        return this.handleResponse(response);
    }
    
    async adjustStock(payload: {
        sku: string;
        location_id: string;
        new_quantity: number;
        reason: 'cycle_count' | 'audit_correction' | 'system_correction' | 'shrinkage';
        notes: string;
        confirm_large_adjustment?: boolean;
    }) {
        const response = await fetch(`${this.baseUrl}${API_PREFIX}/inventory/adjust`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify(payload),
        });
        return this.handleResponse(response);
    }
    
    async reserveStock(payload: {
        sku: string;
        location_id: string;
        quantity: number;
        order_id: string;
        notes?: string;
    }) {
        const response = await fetch(`${this.baseUrl}${API_PREFIX}/inventory/reserve`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify(payload),
        });
        return this.handleResponse(response);
    }
    
    async releaseReservation(payload: {
        sku: string;
        location_id: string;
        quantity: number;
        order_id: string;
        notes?: string;
    }) {
        const response = await fetch(`${this.baseUrl}${API_PREFIX}/inventory/release`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify(payload),
        });
        return this.handleResponse(response);
    }
    
    async fulfillOrder(payload: {
        sku: string;
        location_id: string;
        quantity: number;
        order_id: string;
        notes?: string;
    }) {
        const response = await fetch(`${this.baseUrl}${API_PREFIX}/inventory/fulfill`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify(payload),
        });
        return this.handleResponse(response);
    }
    
    async disposeStock(payload: {
        sku: string;
        location_id: string;
        quantity: number;
        reason: 'expired' | 'damaged' | 'shrinkage';
        notes: string;
        batch_id?: string;
    }) {
        const response = await fetch(`${this.baseUrl}${API_PREFIX}/inventory/dispose`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify(payload),
        });
        return this.handleResponse(response);
    }
    
    async getLowStockAlerts(locationId?: string) {
        const params = locationId ? `?location_id=${locationId}` : '';
        const response = await fetch(
            `${this.baseUrl}${API_PREFIX}/inventory/alerts/low-stock${params}`,
            { headers: this.getHeaders() }
        );
        return this.handleResponse(response);
    }
    
    async getExpiringItems(daysAhead: number = 7, locationId?: string) {
        const params = new URLSearchParams({ days_ahead: daysAhead.toString() });
        if (locationId) params.append('location_id', locationId);
        
        const response = await fetch(
            `${this.baseUrl}${API_PREFIX}/inventory/alerts/expiring?${params}`,
            { headers: this.getHeaders() }
        );
        return this.handleResponse(response);
    }
    
    async getMovementHistory(sku: string, locationId: string, limit: number = 50) {
        const params = new URLSearchParams({ location_id: locationId, limit: limit.toString() });
        const response = await fetch(
            `${this.baseUrl}${API_PREFIX}/inventory/history/${encodeURIComponent(sku)}?${params}`,
            { headers: this.getHeaders() }
        );
        return this.handleResponse(response);
    }
    
    // ─────────────────────────────────────────────────────────────────────────
    // Admin Methods
    // ─────────────────────────────────────────────────────────────────────────
    
    async getAuditLog(filters: {
        sku?: string;
        location_code?: string;
        action_type?: string;
        reason?: string;
        performed_by?: string;
        start_date?: string;
        end_date?: string;
        reference_id?: string;
        limit?: number;
        offset?: number;
    } = {}) {
        const params = new URLSearchParams();
        Object.entries(filters).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                params.append(key, String(value));
            }
        });
        
        const response = await fetch(
            `${this.baseUrl}${API_PREFIX}/admin/audit-log?${params}`,
            { headers: this.getHeaders() }
        );
        return this.handleResponse(response);
    }
    
    async getAuditStats(startDate?: string, endDate?: string) {
        const params = new URLSearchParams();
        if (startDate) params.append('start_date', startDate);
        if (endDate) params.append('end_date', endDate);
        
        const response = await fetch(
            `${this.baseUrl}${API_PREFIX}/admin/audit-log/stats?${params}`,
            { headers: this.getHeaders() }
        );
        return this.handleResponse(response);
    }
    
    async exportAuditLogCsv(filters: Record<string, any> = {}) {
        const params = new URLSearchParams();
        Object.entries(filters).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                params.append(key, String(value));
            }
        });
        
        const response = await fetch(
            `${this.baseUrl}${API_PREFIX}/admin/audit-log/export.csv?${params}`,
            { headers: this.getHeaders() }
        );
        
        if (!response.ok) {
            throw new Error('Failed to export audit log');
        }
        
        // Download the file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `audit_log_export_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }
    
    async getActionTypes() {
        const response = await fetch(
            `${this.baseUrl}${API_PREFIX}/admin/audit-log/action-types`,
            { headers: this.getHeaders() }
        );
        return this.handleResponse(response);
    }
}

// Export singleton instance
export const kinmelApi = new KinmelApiClient();
export default kinmelApi;
"""


# ═══════════════════════════════════════════════════════════════════════════════
# QUICK REFERENCE
# ═══════════════════════════════════════════════════════════════════════════════

QUICK_REFERENCE = {
    "base_url": BASE_URL,
    "api_prefix": API_PREFIX,
    "documentation": {
        "swagger": f"{BASE_URL}/docs",
        "redoc": f"{BASE_URL}/redoc",
        "openapi_json": f"{BASE_URL}/openapi.json",
    },
    "endpoints_summary": {
        "Health": [
            {"method": "GET", "path": "/health", "purpose": "Health check"},
            {"method": "GET", "path": "/ready", "purpose": "Readiness check"},
        ],
        "Authentication": [
            {"method": "POST", "path": f"{API_PREFIX}/auth/login", "purpose": "Login and get tokens"},
            {"method": "POST", "path": f"{API_PREFIX}/auth/refresh", "purpose": "Refresh access token"},
        ],
        "Products": [
            {"method": "GET", "path": f"{API_PREFIX}/products", "purpose": "List products", "role": "Public"},
            {"method": "GET", "path": f"{API_PREFIX}/products/{{sku}}", "purpose": "Get product by SKU", "role": "Public"},
            {"method": "GET", "path": f"{API_PREFIX}/products/barcode/{{barcode}}", "purpose": "Get product by barcode", "role": "Public"},
            {"method": "POST", "path": f"{API_PREFIX}/products", "purpose": "Create product", "role": "Manager+"},
            {"method": "PUT", "path": f"{API_PREFIX}/products/{{sku}}", "purpose": "Update product", "role": "Manager+"},
            {"method": "DELETE", "path": f"{API_PREFIX}/products/{{sku}}", "purpose": "Delete product", "role": "Admin"},
        ],
        "Categories": [
            {"method": "GET", "path": f"{API_PREFIX}/categories", "purpose": "List categories", "role": "Public"},
            {"method": "GET", "path": f"{API_PREFIX}/categories/{{category}}/products", "purpose": "Products by category", "role": "Public"},
        ],
        "Inventory Operations": [
            {"method": "POST", "path": f"{API_PREFIX}/inventory/receive", "purpose": "Receive stock", "role": "Staff+"},
            {"method": "POST", "path": f"{API_PREFIX}/inventory/adjust", "purpose": "Adjust stock", "role": "Manager+"},
            {"method": "POST", "path": f"{API_PREFIX}/inventory/reserve", "purpose": "Reserve stock", "role": "Staff+"},
            {"method": "POST", "path": f"{API_PREFIX}/inventory/release", "purpose": "Release reservation", "role": "Staff+"},
            {"method": "POST", "path": f"{API_PREFIX}/inventory/fulfill", "purpose": "Fulfill order", "role": "Staff+"},
            {"method": "POST", "path": f"{API_PREFIX}/inventory/dispose", "purpose": "Dispose stock", "role": "Manager+"},
        ],
        "Inventory Queries": [
            {"method": "GET", "path": f"{API_PREFIX}/inventory/stock/{{sku}}", "purpose": "Get stock level", "role": "Staff+"},
            {"method": "GET", "path": f"{API_PREFIX}/inventory/alerts/low-stock", "purpose": "Low stock alerts", "role": "Staff+"},
            {"method": "GET", "path": f"{API_PREFIX}/inventory/alerts/expiring", "purpose": "Expiring items", "role": "Staff+"},
            {"method": "GET", "path": f"{API_PREFIX}/inventory/history/{{sku}}", "purpose": "Movement history", "role": "Staff+"},
        ],
        "Orders": [
            {"method": "GET", "path": f"{API_PREFIX}/orders", "purpose": "List orders", "role": "Staff+"},
            {"method": "GET", "path": f"{API_PREFIX}/orders/{{order_id}}", "purpose": "Get order detail", "role": "Staff+"},
            {"method": "PATCH", "path": f"{API_PREFIX}/orders/{{order_id}}/status", "purpose": "Update order status", "role": "Staff+"},
            {"method": "PATCH", "path": f"{API_PREFIX}/orders/{{order_id}}/items/{{item_id}}", "purpose": "Update item checklist", "role": "Staff+"},
            {"method": "POST", "path": f"{API_PREFIX}/orders/{{order_id}}/substitutions", "purpose": "Create substitution", "role": "Staff+"},
            {"method": "POST", "path": f"{API_PREFIX}/orders/{{order_id}}/contact", "purpose": "Log contact attempt", "role": "Staff+"},
        ],
        "Admin & Audit": [
            {"method": "GET", "path": f"{API_PREFIX}/admin/audit-log", "purpose": "Query audit log", "role": "Manager+"},
            {"method": "GET", "path": f"{API_PREFIX}/admin/audit-log/export.csv", "purpose": "Export CSV", "role": "Manager+"},
            {"method": "GET", "path": f"{API_PREFIX}/admin/audit-log/stats", "purpose": "Audit statistics", "role": "Manager+"},
            {"method": "GET", "path": f"{API_PREFIX}/admin/audit-log/action-types", "purpose": "List action types", "role": "Staff+"},
        ],
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN - Print summary when run directly
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 80)
    print("KINMEL API INTEGRATION HELPER")
    print("=" * 80)
    print()
    print(f"Base URL: {BASE_URL}")
    print(f"API Prefix: {API_PREFIX}")
    print()
    print("Documentation URLs:")
    print(f"  - Swagger UI: {BASE_URL}/docs")
    print(f"  - ReDoc: {BASE_URL}/redoc")
    print(f"  - OpenAPI JSON: {BASE_URL}/openapi.json")
    print()
    print("Test Credentials:")
    print("  Password: TestPassword123!")
    print("  Users:")
    print("    - owner@kinmel-test.local (Admin)")
    print("    - manager@kinmel-test.local (Manager)")
    print("    - supervisor@kinmel-test.local (Supervisor)")
    print("    - staff1@kinmel-test.local (Staff)")
    print()
    print("Endpoints Summary:")
    print("-" * 80)
    
    for category, endpoints in QUICK_REFERENCE["endpoints_summary"].items():
        print(f"\n{category}:")
        for ep in endpoints:
            role = f" [{ep.get('role', 'Public')}]" if ep.get('role') else ""
            print(f"  {ep['method']:6} {ep['path']:45} - {ep['purpose']}{role}")
    
    print()
    print("=" * 80)
    print("See the dictionaries in this file for detailed documentation:")
    print("  - HEALTH_ENDPOINTS")
    print("  - AUTH_ENDPOINTS")
    print("  - INVENTORY_ENDPOINTS")
    print("  - ADMIN_ENDPOINTS")
    print("  - ORDER_ENDPOINTS")
    print("  - ERROR_RESPONSES")
    print("  - ROLE_PERMISSIONS")
    print("  - NEXTJS_API_CLIENT_TEMPLATE")
    print("=" * 80)

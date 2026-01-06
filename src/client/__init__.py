"""
Kinmel API Client
=================

A Python client library for interacting with the Kinmel Inventory Management API.

Usage:
    from src.client import KinmelClient
    
    client = KinmelClient(base_url="http://localhost:8000")
    
    # Login
    tokens = await client.login("manager@kinmel-test.local", "TestPassword123!")
    
    # Make authenticated requests
    stock = await client.get_stock_level("MILK-2L-WHOLE")
"""

from src.client.api_client import KinmelClient
from src.client.exceptions import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ValidationError,
    ConflictError,
    InsufficientStockError,
)

__all__ = [
    "KinmelClient",
    "APIError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "ValidationError",
    "ConflictError",
    "InsufficientStockError",
]


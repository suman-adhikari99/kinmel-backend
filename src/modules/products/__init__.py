# Products Module
# Handles: SKU management, categories, pricing, product metadata

from src.modules.products.models import Category, Product
from src.modules.products.repository import ProductRepository, product_repository
from src.modules.products.router import router, categories_router

__all__ = [
    "Category",
    "Product",
    "ProductRepository",
    "product_repository",
    "router",
    "categories_router",
]

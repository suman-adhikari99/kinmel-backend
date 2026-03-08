#!/usr/bin/env python3
"""
Database Seeder - Realistic Dummy Data
======================================
Seeds the database with realistic test data for development and testing.

Usage:
    python scripts/seed_data.py              # Full seed
    python scripts/seed_data.py --users      # Users only
    python scripts/seed_data.py --products   # Products only
    python scripts/seed_data.py --inventory  # Inventory only
    python scripts/seed_data.py --orders     # Orders only
    python scripts/seed_data.py --revenue    # Revenue only
    python scripts/seed_data.py --clear      # Clear all data first

Features:
- Idempotent: Running twice won't duplicate data
- Realistic: Uses real-world product names, SKUs, prices
- Complete: Creates full data graph (users → products → inventory → movements)
- Safe: Tagged as test data, uses known test passwords

⚠️ WARNING: This script is for DEVELOPMENT ONLY.
   Never run in production environments!
"""

import argparse
import asyncio
import sys
import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid4, uuid5

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import async_session_factory, engine
from src.core.logging import configure_logging, get_logger
from src.core.security import Role, hash_password
from src.modules.inventory.models import (
    InventoryBatch,
    InventoryItem,
    Location,
    LocationType,
    MovementReason,
    MovementType,
    StockMovement,
)
from src.modules.products.models import Category, Product
from src.modules.users.models import User
from src.modules.revenue.models import (
    AdjustmentType,
    BusinessProfile,
    PaymentMethod,
    PaymentStatus,
    PayoutStatus,
    RevenueAdjustment,
    RevenuePayment,
    RevenuePayout,
)
from src.modules.orders.models import (
    ContactChannel,
    Order,
    OrderContactAttempt,
    OrderItem,
    OrderItemSubstitution,
    OrderStatus,
    OrderStatusHistory,
    OrderType,
    SubstitutionStatus,
)

settings = get_settings()
logger = get_logger(__name__)
UTC = timezone.utc


# ═══════════════════════════════════════════════════════════════════════════════
# SEED DATA DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════


# Test password for all seed users (bcrypt hashed)
# Plain text: "TestPassword123!"
TEST_PASSWORD = "TestPassword123!"


SEED_USERS = [
    {
        "email": "owner@kinmel-test.local",
        "full_name": "Test Owner (Seed Data)",
        "role": Role.ADMIN,
        "is_verified": True,
    },
    {
        "email": "manager@kinmel-test.local",
        "full_name": "Test Manager (Seed Data)",
        "role": Role.MANAGER,
        "is_verified": True,
    },
    {
        "email": "supervisor@kinmel-test.local",
        "full_name": "Test Supervisor (Seed Data)",
        "role": Role.SUPERVISOR,
        "is_verified": True,
    },
    {
        "email": "staff1@kinmel-test.local",
        "full_name": "Test Staff One (Seed Data)",
        "role": Role.STAFF,
        "is_verified": True,
    },
    {
        "email": "staff2@kinmel-test.local",
        "full_name": "Test Staff Two (Seed Data)",
        "role": Role.STAFF,
        "is_verified": True,
    },
]


SEED_LOCATIONS = [
    {
        "code": "FLOOR-A1",
        "name": "Aisle 1 - Dairy & Refrigerated",
        "location_type": LocationType.FLOOR,
        "capacity": 500,
        "temperature_zone": None,
        "notes": "Main dairy aisle, customer accessible",
    },
    {
        "code": "FLOOR-A2",
        "name": "Aisle 2 - Bakery & Bread",
        "location_type": LocationType.FLOOR,
        "capacity": 300,
        "temperature_zone": None,
        "notes": "Fresh bread and bakery items",
    },
    {
        "code": "FLOOR-A3",
        "name": "Aisle 3 - Dry Goods & Canned",
        "location_type": LocationType.FLOOR,
        "capacity": 800,
        "temperature_zone": None,
        "notes": "Non-perishable items",
    },
    {
        "code": "COLD-01",
        "name": "Walk-in Refrigerator 1",
        "location_type": LocationType.COLD_STORAGE,
        "capacity": 1000,
        "temperature_zone": "chilled",
        "notes": "Main cold storage for dairy and produce",
    },
    {
        "code": "COLD-02",
        "name": "Freezer Unit",
        "location_type": LocationType.COLD_STORAGE,
        "capacity": 500,
        "temperature_zone": "frozen",
        "notes": "Frozen goods storage",
    },
    {
        "code": "BACK-01",
        "name": "Backroom Storage A",
        "location_type": LocationType.BACKROOM,
        "capacity": 2000,
        "temperature_zone": None,
        "notes": "Overflow and bulk storage",
    },
    {
        "code": "RECV-01",
        "name": "Receiving Dock",
        "location_type": LocationType.RECEIVING,
        "capacity": None,
        "temperature_zone": None,
        "notes": "Incoming deliveries staging area",
    },
]


SEED_PRODUCTS = [
    # Dairy Products
    {
        "sku": "MILK-2L-WHOLE",
        "name": "Whole Milk 2L",
        "category": "dairy",
        "unit_price": Decimal("4.99"),
        "cost_price": Decimal("3.20"),
        "is_perishable": True,
        "shelf_life_days": 14,
        "requires_cold_storage": True,
        "barcode": "012345678901",
        "brand": "Farm Fresh",
        "unit_of_measure": "each",
    },
    {
        "sku": "MILK-2L-SKIM",
        "name": "Skim Milk 2L",
        "category": "dairy",
        "unit_price": Decimal("4.49"),
        "cost_price": Decimal("2.90"),
        "is_perishable": True,
        "shelf_life_days": 14,
        "requires_cold_storage": True,
        "barcode": "012345678902",
        "brand": "Farm Fresh",
        "unit_of_measure": "each",
    },
    {
        "sku": "YOGURT-GRK-500",
        "name": "Greek Yogurt Plain 500g",
        "category": "dairy",
        "unit_price": Decimal("6.99"),
        "cost_price": Decimal("4.50"),
        "is_perishable": True,
        "shelf_life_days": 21,
        "requires_cold_storage": True,
        "barcode": "012345678903",
        "brand": "Olympus",
        "unit_of_measure": "each",
    },
    {
        "sku": "CHEESE-CHEDDAR-500",
        "name": "Cheddar Cheese Block 500g",
        "category": "dairy",
        "unit_price": Decimal("8.99"),
        "cost_price": Decimal("5.80"),
        "is_perishable": True,
        "shelf_life_days": 60,
        "requires_cold_storage": True,
        "barcode": "012345678904",
        "brand": "Dairy Gold",
        "unit_of_measure": "each",
    },
    {
        "sku": "BUTTER-UNSALT-250",
        "name": "Unsalted Butter 250g",
        "category": "dairy",
        "unit_price": Decimal("5.49"),
        "cost_price": Decimal("3.50"),
        "is_perishable": True,
        "shelf_life_days": 90,
        "requires_cold_storage": True,
        "barcode": "012345678905",
        "brand": "Dairy Gold",
        "unit_of_measure": "each",
    },
    # Bakery Products
    {
        "sku": "BREAD-WHITE-LOAF",
        "name": "White Bread Loaf",
        "category": "bakery",
        "unit_price": Decimal("3.49"),
        "cost_price": Decimal("1.80"),
        "is_perishable": True,
        "shelf_life_days": 5,
        "requires_cold_storage": False,
        "barcode": "012345678910",
        "brand": "Baker's Best",
        "unit_of_measure": "each",
    },
    {
        "sku": "BREAD-WHOLE-LOAF",
        "name": "Whole Wheat Bread Loaf",
        "category": "bakery",
        "unit_price": Decimal("4.29"),
        "cost_price": Decimal("2.20"),
        "is_perishable": True,
        "shelf_life_days": 5,
        "requires_cold_storage": False,
        "barcode": "012345678911",
        "brand": "Baker's Best",
        "unit_of_measure": "each",
    },
    {
        "sku": "CROISSANT-BUTTER-4",
        "name": "Butter Croissants (4 pack)",
        "category": "bakery",
        "unit_price": Decimal("5.99"),
        "cost_price": Decimal("3.20"),
        "is_perishable": True,
        "shelf_life_days": 3,
        "requires_cold_storage": False,
        "barcode": "012345678912",
        "brand": "French Delights",
        "unit_of_measure": "pack",
        "pack_size": 4,
    },
    # Beverages
    {
        "sku": "JUICE-ORANGE-1L",
        "name": "Fresh Orange Juice 1L",
        "category": "beverages",
        "unit_price": Decimal("5.99"),
        "cost_price": Decimal("3.80"),
        "is_perishable": True,
        "shelf_life_days": 10,
        "requires_cold_storage": True,
        "barcode": "012345678920",
        "brand": "Sunny Grove",
        "unit_of_measure": "each",
    },
    {
        "sku": "WATER-SPRING-500ML",
        "name": "Spring Water 500ml",
        "category": "beverages",
        "unit_price": Decimal("1.49"),
        "cost_price": Decimal("0.50"),
        "is_perishable": False,
        "shelf_life_days": None,
        "requires_cold_storage": False,
        "barcode": "012345678921",
        "brand": "Crystal Clear",
        "unit_of_measure": "each",
    },
    {
        "sku": "SODA-COLA-2L",
        "name": "Cola Soda 2L",
        "category": "beverages",
        "unit_price": Decimal("2.99"),
        "cost_price": Decimal("1.50"),
        "is_perishable": False,
        "shelf_life_days": None,
        "requires_cold_storage": False,
        "barcode": "012345678922",
        "brand": "Fizzy Pop",
        "unit_of_measure": "each",
    },
    # Canned Goods
    {
        "sku": "BEANS-BAKED-400",
        "name": "Baked Beans 400g",
        "category": "canned",
        "unit_price": Decimal("2.29"),
        "cost_price": Decimal("1.10"),
        "is_perishable": False,
        "shelf_life_days": None,
        "requires_cold_storage": False,
        "barcode": "012345678930",
        "brand": "Pantry Staples",
        "unit_of_measure": "each",
    },
    {
        "sku": "TOMATO-DICED-400",
        "name": "Diced Tomatoes 400g",
        "category": "canned",
        "unit_price": Decimal("1.99"),
        "cost_price": Decimal("0.90"),
        "is_perishable": False,
        "shelf_life_days": None,
        "requires_cold_storage": False,
        "barcode": "012345678931",
        "brand": "Pantry Staples",
        "unit_of_measure": "each",
    },
    {
        "sku": "TUNA-CHUNK-185",
        "name": "Chunk Light Tuna 185g",
        "category": "canned",
        "unit_price": Decimal("3.49"),
        "cost_price": Decimal("2.00"),
        "is_perishable": False,
        "shelf_life_days": None,
        "requires_cold_storage": False,
        "barcode": "012345678932",
        "brand": "Sea Harvest",
        "unit_of_measure": "each",
    },
    # Snacks
    {
        "sku": "CHIPS-POTATO-200",
        "name": "Classic Potato Chips 200g",
        "category": "snacks",
        "unit_price": Decimal("4.49"),
        "cost_price": Decimal("2.50"),
        "is_perishable": False,
        "shelf_life_days": None,
        "requires_cold_storage": False,
        "barcode": "012345678940",
        "brand": "Crunch Time",
        "unit_of_measure": "each",
    },
    {
        "sku": "CHOCOLATE-DARK-100",
        "name": "Dark Chocolate Bar 100g",
        "category": "snacks",
        "unit_price": Decimal("3.99"),
        "cost_price": Decimal("2.20"),
        "is_perishable": False,
        "shelf_life_days": None,
        "requires_cold_storage": False,
        "barcode": "012345678941",
        "brand": "Sweet Treats",
        "unit_of_measure": "each",
    },
    # Frozen
    {
        "sku": "PIZZA-MARG-400",
        "name": "Margherita Pizza Frozen 400g",
        "category": "frozen",
        "unit_price": Decimal("7.99"),
        "cost_price": Decimal("4.50"),
        "is_perishable": True,
        "shelf_life_days": 180,
        "requires_cold_storage": True,
        "barcode": "012345678950",
        "brand": "Quick Meals",
        "unit_of_measure": "each",
    },
    {
        "sku": "ICECREAM-VAN-1L",
        "name": "Vanilla Ice Cream 1L",
        "category": "frozen",
        "unit_price": Decimal("6.49"),
        "cost_price": Decimal("3.80"),
        "is_perishable": True,
        "shelf_life_days": 365,
        "requires_cold_storage": True,
        "barcode": "012345678951",
        "brand": "Creamy Dreams",
        "unit_of_measure": "each",
    },
    # Household
    {
        "sku": "TISSUE-TOILET-12",
        "name": "Toilet Paper 12 Roll Pack",
        "category": "household",
        "unit_price": Decimal("9.99"),
        "cost_price": Decimal("6.00"),
        "is_perishable": False,
        "shelf_life_days": None,
        "requires_cold_storage": False,
        "barcode": "012345678960",
        "brand": "Soft Touch",
        "unit_of_measure": "pack",
        "pack_size": 12,
    },
    {
        "sku": "DETERGENT-LIQUID-2L",
        "name": "Liquid Laundry Detergent 2L",
        "category": "household",
        "unit_price": Decimal("12.99"),
        "cost_price": Decimal("7.50"),
        "is_perishable": False,
        "shelf_life_days": None,
        "requires_cold_storage": False,
        "barcode": "012345678961",
        "brand": "Clean & Fresh",
        "unit_of_measure": "each",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# SEEDER CLASS
# ═══════════════════════════════════════════════════════════════════════════════


class DatabaseSeeder:
    """
    Idempotent database seeder for development/testing.
    
    Checks for existing data before inserting to prevent duplicates.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.created_users: dict[str, User] = {}
        self.created_locations: dict[str, Location] = {}
        self.created_products: dict[str, Product] = {}
        self.created_inventory: dict[str, InventoryItem] = {}
    
    async def seed_all(self) -> dict[str, int]:
        """Run all seeders and return counts."""
        results = {}
        
        results["users"] = await self.seed_users()
        results["locations"] = await self.seed_locations()
        results["products"] = await self.seed_products()
        results["orders"] = await self.seed_orders()
        results["revenue"] = await self.seed_revenue()
        results["inventory"] = await self.seed_inventory()
        results["batches"] = await self.seed_batches()
        results["movements"] = await self.seed_movements()
        
        await self.session.commit()
        
        return results
    
    async def seed_users(self) -> int:
        """Seed test users."""
        created = 0
        password_hash = hash_password(TEST_PASSWORD)
        
        for user_data in SEED_USERS:
            # Check if user exists
            result = await self.session.execute(
                select(User).where(User.email == user_data["email"])
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                self.created_users[user_data["email"]] = existing
                logger.debug(f"User already exists: {user_data['email']}")
                continue
            
            user = User(
                id=str(uuid4()),
                email=user_data["email"],
                full_name=user_data["full_name"],
                password_hash=password_hash,
                role=user_data["role"],
                is_verified=user_data["is_verified"],
                is_active=True,
            )
            
            self.session.add(user)
            self.created_users[user_data["email"]] = user
            created += 1
            logger.info(f"Created user: {user_data['email']} ({user_data['role']})")
        
        await self.session.flush()
        return created
    
    async def seed_locations(self) -> int:
        """Seed storage locations."""
        created = 0
        
        for loc_data in SEED_LOCATIONS:
            # Check if location exists
            result = await self.session.execute(
                select(Location).where(Location.code == loc_data["code"])
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                self.created_locations[loc_data["code"]] = existing
                logger.debug(f"Location already exists: {loc_data['code']}")
                continue
            
            location = Location(
                id=str(uuid4()),
                code=loc_data["code"],
                name=loc_data["name"],
                location_type=loc_data["location_type"],
                capacity=loc_data["capacity"],
                temperature_zone=loc_data["temperature_zone"],
                notes=loc_data["notes"],
                is_active=True,
            )
            
            self.session.add(location)
            self.created_locations[loc_data["code"]] = location
            created += 1
            logger.info(f"Created location: {loc_data['code']}")
        
        await self.session.flush()
        return created
    
    async def seed_products(self) -> int:
        """Seed products."""
        created = 0

        categories = sorted({prod["category"] for prod in SEED_PRODUCTS})
        image_files = {
            "dairy": "category-dairy.jpg",
            "produce": "category-produce.jpg",
            "meat": "category-meat.jpg",
            "bakery": "category-bakery.jpg",
            "frozen": "category-frozen.jpg",
            "beverages": "category-beverages.jpg",
            "snacks": "category-snacks.jpg",
            "canned": "category-canned.jpg",
            "dry_goods": "category-dry-goods.jpg",
            "household": "category-household.jpg",
            "personal_care": "category-personal-care.jpg",
            "other": "category-other.jpg",
        }
        uploads_dir = PROJECT_ROOT / "uploads" / "categories"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        placeholder_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
        )
        for category_name in categories:
            result = await self.session.execute(
                select(Category).where(Category.name == category_name)
            )
            existing_category = result.scalar_one_or_none()
            if existing_category:
                continue
            image_file = image_files.get(category_name)
            image_url = f"/uploads/categories/{image_file}" if image_file else None
            category = Category(
                id=str(uuid4()),
                name=category_name,
                description=None,
                status="active",
                featured=False,
                priority=0,
                image_url=image_url,
                image_file=image_file,
            )
            self.session.add(category)
            if image_file:
                file_path = uploads_dir / image_file
                if not file_path.exists():
                    file_path.write_bytes(placeholder_png)
        
        await self.session.flush()
        
        for prod_data in SEED_PRODUCTS:
            # Check if product exists
            result = await self.session.execute(
                select(Product).where(Product.sku == prod_data["sku"])
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                self.created_products[prod_data["sku"]] = existing
                logger.debug(f"Product already exists: {prod_data['sku']}")
                continue
            
            product = Product(
                id=str(uuid4()),
                sku=prod_data["sku"],
                name=prod_data["name"],
                category=prod_data["category"],
                unit_price=prod_data["unit_price"],
                cost_price=prod_data.get("cost_price"),
                is_perishable=prod_data["is_perishable"],
                shelf_life_days=prod_data.get("shelf_life_days"),
                requires_cold_storage=prod_data["requires_cold_storage"],
                barcode=prod_data.get("barcode"),
                brand=prod_data.get("brand"),
                unit_of_measure=prod_data.get("unit_of_measure", "each"),
                pack_size=prod_data.get("pack_size", 1),
                tax_rate=Decimal("0.0"),
                is_active=True,
            )
            
            self.session.add(product)
            self.created_products[prod_data["sku"]] = product
            created += 1
            logger.info(f"Created product: {prod_data['sku']} - {prod_data['name']}")
        
        await self.session.flush()
        return created
    
    async def seed_inventory(self) -> int:
        """Seed inventory items (product-location combinations)."""
        created = 0
        
        # Define inventory distribution
        inventory_config = [
            # SKU, Location, Physical Stock, Buffer, Reorder Point
            ("MILK-2L-WHOLE", "FLOOR-A1", 25, 5, 10),
            ("MILK-2L-WHOLE", "COLD-01", 100, 0, 20),
            ("MILK-2L-SKIM", "FLOOR-A1", 15, 3, 8),
            ("MILK-2L-SKIM", "COLD-01", 80, 0, 15),
            ("YOGURT-GRK-500", "FLOOR-A1", 30, 5, 10),
            ("YOGURT-GRK-500", "COLD-01", 60, 0, 15),
            ("CHEESE-CHEDDAR-500", "FLOOR-A1", 20, 2, 8),
            ("CHEESE-CHEDDAR-500", "COLD-01", 40, 0, 10),
            ("BUTTER-UNSALT-250", "FLOOR-A1", 25, 3, 10),
            ("BREAD-WHITE-LOAF", "FLOOR-A2", 40, 10, 15),
            ("BREAD-WHITE-LOAF", "BACK-01", 100, 0, 30),
            ("BREAD-WHOLE-LOAF", "FLOOR-A2", 30, 8, 12),
            ("CROISSANT-BUTTER-4", "FLOOR-A2", 20, 5, 8),
            ("JUICE-ORANGE-1L", "FLOOR-A1", 35, 5, 12),
            ("JUICE-ORANGE-1L", "COLD-01", 50, 0, 15),
            ("WATER-SPRING-500ML", "FLOOR-A3", 150, 20, 50),
            ("WATER-SPRING-500ML", "BACK-01", 500, 0, 100),
            ("SODA-COLA-2L", "FLOOR-A3", 60, 10, 20),
            ("BEANS-BAKED-400", "FLOOR-A3", 80, 0, 25),
            ("TOMATO-DICED-400", "FLOOR-A3", 100, 0, 30),
            ("TUNA-CHUNK-185", "FLOOR-A3", 50, 5, 15),
            ("CHIPS-POTATO-200", "FLOOR-A3", 45, 5, 15),
            ("CHOCOLATE-DARK-100", "FLOOR-A3", 60, 10, 20),
            ("PIZZA-MARG-400", "COLD-02", 40, 5, 15),
            ("ICECREAM-VAN-1L", "COLD-02", 30, 5, 10),
            ("TISSUE-TOILET-12", "FLOOR-A3", 50, 5, 20),
            ("TISSUE-TOILET-12", "BACK-01", 200, 0, 50),
            ("DETERGENT-LIQUID-2L", "FLOOR-A3", 25, 3, 10),
        ]
        
        for sku, loc_code, physical, buffer, reorder in inventory_config:
            product = self.created_products.get(sku)
            location = self.created_locations.get(loc_code)
            
            if not product or not location:
                logger.warning(f"Skipping inventory: {sku} @ {loc_code} - missing product or location")
                continue
            
            # Check if exists
            result = await self.session.execute(
                select(InventoryItem).where(
                    InventoryItem.product_id == product.id,
                    InventoryItem.location_id == location.id,
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                key = f"{sku}:{loc_code}"
                self.created_inventory[key] = existing
                logger.debug(f"Inventory already exists: {sku} @ {loc_code}")
                continue
            
            item = InventoryItem(
                id=str(uuid4()),
                product_id=product.id,
                location_id=location.id,
                physical_stock=physical,
                buffer=buffer,
                reorder_point=reorder,
                version=1,
                is_active=True,
            )
            
            self.session.add(item)
            key = f"{sku}:{loc_code}"
            self.created_inventory[key] = item
            created += 1
            logger.info(f"Created inventory: {sku} @ {loc_code} (stock: {physical})")
        
        await self.session.flush()
        return created

    async def seed_orders(self) -> int:
        """Seed sample customer orders with items, substitutions, and history."""
        created = 0
        now = datetime.now(UTC)

        if not self.created_products:
            await self.seed_products()

        if not self.created_users:
            await self.seed_users()

        product_skus = list(self.created_products.keys())
        if not product_skus:
            logger.warning("Skipping orders - no products available")
            return 0

        seed_customers = [
            {"name": "Alex Morgan", "phone": "+61 400 000 001", "email": "alex@example.com"},
            {"name": "Priya Shah", "phone": "+61 400 000 002", "email": "priya@example.com"},
            {"name": "Jordan Lee", "phone": "+61 400 000 003", "email": "jordan@example.com"},
            {"name": "Sofia Patel", "phone": "+61 400 000 004", "email": "sofia@example.com"},
            {"name": "Chris Nguyen", "phone": "+61 400 000 005", "email": "chris@example.com"},
            {"name": "Morgan Chen", "phone": "+61 400 000 006", "email": "morgan@example.com"},
            {"name": "Isla Brown", "phone": "+61 400 000 007", "email": "isla@example.com"},
            {"name": "Leo Walker", "phone": "+61 400 000 008", "email": "leo@example.com"},
            {"name": "Ava Rossi", "phone": "+61 400 000 009", "email": "ava@example.com"},
            {"name": "Noah Carter", "phone": "+61 400 000 010", "email": "noah@example.com"},
        ]

        suburbs = [
            ("Newtown", "12 Example St, Newtown NSW 2042"),
            ("Surry Hills", "48 Crown St, Surry Hills NSW 2010"),
            ("Parramatta", "5 Church St, Parramatta NSW 2150"),
            ("Bondi", "77 Beach Rd, Bondi NSW 2026"),
            ("Chatswood", "20 Pacific Hwy, Chatswood NSW 2067"),
        ]

        order_statuses = [
            OrderStatus.NEW,
            OrderStatus.PREPARING,
            OrderStatus.READY,
            OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.COMPLETED,
            OrderStatus.CANCELLED,
        ]

        order_ids = [
            str(uuid5(NAMESPACE_DNS, f"seed-order-{idx + 1}")) for idx in range(30)
        ]
        existing = await self.session.execute(
            select(Order.id).where(Order.id.in_(order_ids))
        )
        existing_ids = set(existing.scalars().all())

        staff_user = self.created_users.get("staff1@kinmel-test.local")
        changed_by = staff_user.id if staff_user else None

        for idx, order_id in enumerate(order_ids):
            if order_id in existing_ids:
                continue

            order_type = OrderType.DELIVERY if idx % 2 else OrderType.PICKUP
            status = order_statuses[idx % len(order_statuses)]
            customer = seed_customers[idx % len(seed_customers)]

            suburb, address = suburbs[idx % len(suburbs)]
            delivery_fee = Decimal("0.00") if order_type == OrderType.PICKUP else Decimal(
                "6.00" if idx % 3 else "8.00"
            )

            created_at = now - timedelta(days=30 - idx, hours=idx % 5)

            order = Order(
                id=order_id,
                order_type=order_type,
                status=status,
                time_slot="10:00-12:00" if order_type == OrderType.DELIVERY else "09:00-10:00",
                customer_name=customer["name"],
                customer_phone=customer["phone"],
                customer_email=customer["email"],
                delivery_address=address if order_type == OrderType.DELIVERY else None,
                delivery_suburb=suburb if order_type == OrderType.DELIVERY else None,
                subtotal=Decimal("0.00"),
                gst=Decimal("0.00"),
                delivery_fee=delivery_fee,
                total=Decimal("0.00"),
                notes="Seeded order for UI testing",
                has_substitutions=False,
                created_at=created_at,
                updated_at=created_at,
            )

            self.session.add(order)

            item_count = 2 + (idx % 4)
            subtotal = Decimal("0.00")

            for j in range(item_count):
                sku = product_skus[(idx + j) % len(product_skus)]
                product = self.created_products[sku]
                qty = Decimal(1 + ((idx + j) % 3))
                item = OrderItem(
                    id=str(uuid4()),
                    order_id=order.id,
                    product_sku=sku,
                    name=product.name,
                    quantity=qty,
                    price=product.unit_price,
                    checked=status in {
                        OrderStatus.READY,
                        OrderStatus.OUT_FOR_DELIVERY,
                        OrderStatus.COMPLETED,
                    },
                    created_at=created_at,
                    updated_at=created_at,
                )
                self.session.add(item)
                subtotal += product.unit_price * qty

                if j == 0 and idx % 6 == 0:
                    substitute_sku = product_skus[(idx + j + 5) % len(product_skus)]
                    substitute_product = self.created_products[substitute_sku]
                    substitution_status = (
                        SubstitutionStatus.APPROVED
                        if status in {OrderStatus.READY, OrderStatus.COMPLETED}
                        else SubstitutionStatus.PENDING
                    )
                    substitution = OrderItemSubstitution(
                        id=str(uuid4()),
                        order_item_id=item.id,
                        original_item_id=sku,
                        original_name=product.name,
                        original_price=product.unit_price,
                        original_qty=qty,
                        reason="Out of stock",
                        price_difference=(
                            substitute_product.unit_price - product.unit_price
                        ),
                        customer_notified=idx % 12 == 0,
                        status=substitution_status,
                        substitute_item_id=substitute_sku,
                        substitute_name=substitute_product.name,
                        substitute_price=substitute_product.unit_price,
                        quantity=qty,
                        created_at=created_at,
                        updated_at=created_at,
                    )
                    self.session.add(substitution)
                    order.has_substitutions = True

            gst = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
            total = (subtotal + gst + delivery_fee).quantize(Decimal("0.01"))
            order.subtotal = subtotal.quantize(Decimal("0.01"))
            order.gst = gst
            order.total = total

            if status == OrderStatus.COMPLETED:
                order.delivered_at = created_at + timedelta(hours=2)

            if status == OrderStatus.CANCELLED:
                history_steps = [OrderStatus.NEW, OrderStatus.CANCELLED]
            else:
                if order_type == OrderType.DELIVERY:
                    full_steps = [
                        OrderStatus.NEW,
                        OrderStatus.PREPARING,
                        OrderStatus.READY,
                        OrderStatus.OUT_FOR_DELIVERY,
                        OrderStatus.COMPLETED,
                    ]
                else:
                    full_steps = [
                        OrderStatus.NEW,
                        OrderStatus.PREPARING,
                        OrderStatus.READY,
                        OrderStatus.COMPLETED,
                    ]
                history_steps = full_steps[: full_steps.index(status) + 1]

            for step_idx, step_status in enumerate(history_steps):
                history = OrderStatusHistory(
                    id=str(uuid4()),
                    order_id=order.id,
                    status=step_status,
                    changed_by=changed_by,
                    created_at=created_at + timedelta(hours=step_idx),
                    updated_at=created_at + timedelta(hours=step_idx),
                )
                self.session.add(history)

            if idx % 7 == 0:
                attempt = OrderContactAttempt(
                    id=str(uuid4()),
                    order_id=order.id,
                    channel=ContactChannel.SMS if idx % 2 else ContactChannel.CALL,
                    template_id="substitution-pending" if order.has_substitutions else None,
                    notes="Seeded contact attempt",
                    created_at=created_at + timedelta(hours=1),
                    updated_at=created_at + timedelta(hours=1),
                )
                self.session.add(attempt)

            created += 1

        await self.session.flush()
        return created

    async def seed_revenue(self) -> int:
        """Seed revenue-related records."""
        created = 0
        now = datetime.now(UTC)

        # Business profile (single row)
        profile_result = await self.session.execute(select(BusinessProfile))
        profile = profile_result.scalar_one_or_none()
        if not profile:
            profile = BusinessProfile(
                id=str(uuid4()),
                legal_name="Fresh Mart Pty Ltd",
                abn="73 123 456 789",
                gst_registered=True,
                gst_rate="10%",
                store_address="12 Market Street, Sydney NSW",
                contact_email="accounts@freshmart.com.au",
                contact_phone="02 9000 1234",
                bank_masked="ANZ **** 9281",
                payout_frequency="Daily",
                processor="Stripe",
            )
            self.session.add(profile)
            created += 1

        # Revenue payments
        orders_result = await self.session.execute(select(Order))
        orders = orders_result.scalars().all()
        payment_methods = [
            PaymentMethod.CREDIT_CARD,
            PaymentMethod.DEBIT_CARD,
            PaymentMethod.CASH,
            PaymentMethod.DIGITAL_WALLET,
        ]

        for idx, order in enumerate(orders):
            existing = await self.session.execute(
                select(RevenuePayment).where(RevenuePayment.order_id == order.id)
            )
            if existing.scalar_one_or_none():
                continue
            status = (
                PaymentStatus.COMPLETED
                if order.status in {"completed", "ready", "out_for_delivery"}
                else PaymentStatus.FAILED
            )
            if order.status == "cancelled" and idx % 5 == 0:
                status = PaymentStatus.REFUNDED
            payment = RevenuePayment(
                id=str(uuid4()),
                order_id=order.id,
                method=payment_methods[idx % len(payment_methods)],
                status=status,
                amount=order.total,
                created_at=order.created_at,
                updated_at=order.updated_at,
            )
            self.session.add(payment)
            created += 1

        # Payouts
        payout_result = await self.session.execute(select(RevenuePayout))
        if not payout_result.first():
            for idx in range(7):
                payout_status = PayoutStatus.COMPLETED if idx < 5 else PayoutStatus.PENDING
                payout_at = (now - timedelta(days=idx)).strftime("%Y-%m-%dT%H:%M:%SZ")
                payout = RevenuePayout(
                    id=str(uuid4()),
                    payout_at=payout_at,
                    status=payout_status,
                    amount=Decimal("1500.00") + Decimal(idx * 50),
                )
                self.session.add(payout)
                created += 1

        # Adjustments (platform fees, refunds, disputes)
        adjustments_result = await self.session.execute(select(RevenueAdjustment))
        if not adjustments_result.first():
            adjustments = [
                (AdjustmentType.PLATFORM_FEE, Decimal("920.40")),
                (AdjustmentType.REFUND, Decimal("892.00")),
                (AdjustmentType.DISPUTE, Decimal("0.00")),
            ]
            for adj_type, amount in adjustments:
                adjustment = RevenueAdjustment(
                    id=str(uuid4()),
                    adjustment_type=adj_type,
                    amount=amount,
                    notes="Seeded adjustment",
                )
                self.session.add(adjustment)
                created += 1

        await self.session.flush()
        return created
    
    async def seed_batches(self) -> int:
        """Seed inventory batches for perishable products."""
        created = 0
        now = datetime.now(UTC)
        
        # Batch config: (SKU, Location, batches)
        # Each batch: (batch_number, quantity, days_until_expiry, days_ago_received)
        batch_config = [
            ("MILK-2L-WHOLE", "COLD-01", [
                ("BATCH-M001", 40, 10, 2),  # Expires in 10 days, received 2 days ago
                ("BATCH-M002", 35, 5, 5),   # Expires in 5 days, received 5 days ago
                ("BATCH-M003", 25, 2, 8),   # Expires in 2 days - needs attention!
            ]),
            ("YOGURT-GRK-500", "COLD-01", [
                ("BATCH-Y001", 30, 15, 3),
                ("BATCH-Y002", 30, 8, 7),
            ]),
            ("BREAD-WHITE-LOAF", "FLOOR-A2", [
                ("BATCH-B001", 25, 3, 1),
                ("BATCH-B002", 15, 1, 3),  # Expires tomorrow!
            ]),
            ("JUICE-ORANGE-1L", "COLD-01", [
                ("BATCH-J001", 30, 7, 2),
                ("BATCH-J002", 20, 4, 5),
            ]),
            ("CROISSANT-BUTTER-4", "FLOOR-A2", [
                ("BATCH-C001", 12, 2, 0),  # Fresh today
                ("BATCH-C002", 8, 1, 1),   # Expires tomorrow
            ]),
        ]
        
        for sku, loc_code, batches in batch_config:
            key = f"{sku}:{loc_code}"
            inventory_item = self.created_inventory.get(key)
            
            if not inventory_item:
                logger.warning(f"Skipping batches for {sku} @ {loc_code} - no inventory item")
                continue
            
            for batch_num, qty, days_expire, days_received in batches:
                # Check if batch exists
                result = await self.session.execute(
                    select(InventoryBatch).where(
                        InventoryBatch.inventory_item_id == inventory_item.id,
                        InventoryBatch.batch_number == batch_num,
                    )
                )
                
                if result.scalar_one_or_none():
                    logger.debug(f"Batch already exists: {batch_num}")
                    continue
                
                batch = InventoryBatch(
                    id=str(uuid4()),
                    inventory_item_id=inventory_item.id,
                    batch_number=batch_num,
                    quantity=qty,
                    expiry_date=now + timedelta(days=days_expire),
                    received_date=now - timedelta(days=days_received),
                    cost_per_unit=self.created_products[sku].cost_price,
                )
                
                self.session.add(batch)
                created += 1
                logger.info(f"Created batch: {batch_num} for {sku} (expires in {days_expire} days)")
        
        await self.session.flush()
        return created
    
    async def seed_movements(self) -> int:
        """Seed historical stock movements for audit trail."""
        created = 0
        now = datetime.now(UTC)
        
        # Get a staff user for movements
        staff_user = self.created_users.get("staff1@kinmel-test.local")
        manager_user = self.created_users.get("manager@kinmel-test.local")
        
        if not staff_user or not manager_user:
            logger.warning("Cannot seed movements - no users found")
            return 0
        
        # Movement history: (SKU, Location, movements)
        # Each movement: (type, reason, delta, days_ago, user_key, reference, notes)
        movement_config = [
            ("MILK-2L-WHOLE", "FLOOR-A1", [
                (MovementType.RECEIVING, MovementReason.SUPPLIER_DELIVERY, 50, 7, "staff1", "PO-2024-001", "Weekly delivery"),
                (MovementType.SALE, MovementReason.CUSTOMER_SALE, -10, 6, "staff1", "ORD-001", None),
                (MovementType.SALE, MovementReason.CUSTOMER_SALE, -5, 5, "staff1", "ORD-002", None),
                (MovementType.SALE, MovementReason.CUSTOMER_SALE, -8, 4, "staff1", "ORD-003", None),
                (MovementType.ADJUSTMENT, MovementReason.CYCLE_COUNT, -2, 3, "manager", None, "Cycle count correction - 2 units short"),
            ]),
            ("BREAD-WHITE-LOAF", "FLOOR-A2", [
                (MovementType.RECEIVING, MovementReason.SUPPLIER_DELIVERY, 80, 5, "staff1", "PO-2024-002", "Morning bread delivery"),
                (MovementType.SALE, MovementReason.CUSTOMER_SALE, -15, 4, "staff1", "ORD-010", None),
                (MovementType.SALE, MovementReason.CUSTOMER_SALE, -12, 3, "staff1", "ORD-011", None),
                (MovementType.DISPOSAL, MovementReason.EXPIRED, -8, 2, "manager", None, "End of day disposal - expired bread"),
                (MovementType.SALE, MovementReason.CUSTOMER_SALE, -5, 1, "staff1", "ORD-012", None),
            ]),
            ("WATER-SPRING-500ML", "FLOOR-A3", [
                (MovementType.RECEIVING, MovementReason.SUPPLIER_DELIVERY, 200, 10, "staff1", "PO-2024-003", "Bulk water delivery"),
                (MovementType.SALE, MovementReason.CUSTOMER_SALE, -30, 8, "staff1", "ORD-020", None),
                (MovementType.SALE, MovementReason.CUSTOMER_SALE, -15, 6, "staff1", "ORD-021", None),
                (MovementType.TRANSFER, MovementReason.INTERNAL_TRANSFER, -50, 4, "staff1", "TRF-001", "Transfer to backroom"),
                (MovementType.RESERVATION, MovementReason.ONLINE_RESERVATION, -20, 2, "staff1", "ONLINE-001", "Reserved for online order"),
            ]),
            ("CHEESE-CHEDDAR-500", "FLOOR-A1", [
                (MovementType.RECEIVING, MovementReason.SUPPLIER_DELIVERY, 30, 14, "staff1", "PO-2024-004", None),
                (MovementType.SALE, MovementReason.CUSTOMER_SALE, -5, 10, "staff1", "ORD-030", None),
                (MovementType.ADJUSTMENT, MovementReason.SHRINKAGE, -3, 7, "manager", None, "Shrinkage adjustment - inventory audit"),
                (MovementType.SALE, MovementReason.CUSTOMER_SALE, -2, 3, "staff1", "ORD-031", None),
            ]),
        ]
        
        for sku, loc_code, movements in movement_config:
            key = f"{sku}:{loc_code}"
            inventory_item = self.created_inventory.get(key)
            
            if not inventory_item:
                logger.warning(f"Skipping movements for {sku} @ {loc_code} - no inventory item")
                continue
            
            # Reconstruct stock history
            current_stock = inventory_item.physical_stock
            
            # Calculate starting stock (before all movements)
            total_delta = sum(m[2] for m in movements)
            starting_stock = current_stock - total_delta
            running_stock = starting_stock
            
            for move_type, reason, delta, days_ago, user_key, ref_id, notes in movements:
                user = manager_user if user_key == "manager" else staff_user
                
                qty_before = running_stock
                qty_after = running_stock + delta
                running_stock = qty_after
                
                # Check if movement exists (by reference_id and timestamp proximity)
                if ref_id:
                    result = await self.session.execute(
                        select(StockMovement).where(
                            StockMovement.inventory_item_id == inventory_item.id,
                            StockMovement.reference_id == ref_id,
                        )
                    )
                    if result.scalar_one_or_none():
                        logger.debug(f"Movement already exists: {ref_id}")
                        continue
                
                movement = StockMovement(
                    id=str(uuid4()),
                    inventory_item_id=inventory_item.id,
                    movement_type=move_type,
                    reason=reason,
                    quantity_delta=delta,
                    quantity_before=qty_before,
                    quantity_after=qty_after,
                    user_id=user.id,
                    reference_id=ref_id,
                    reference_type="order" if ref_id and ref_id.startswith("ORD") else (
                        "purchase_order" if ref_id and ref_id.startswith("PO") else (
                            "transfer" if ref_id and ref_id.startswith("TRF") else None
                        )
                    ),
                    notes=notes,
                    created_at=now - timedelta(days=days_ago),
                )
                
                self.session.add(movement)
                created += 1
                logger.info(f"Created movement: {move_type.value} {delta:+d} for {sku}")
        
        await self.session.flush()
        return created
    
    async def clear_all_data(self) -> None:
        """Clear all seeded data (DANGEROUS!)."""
        logger.warning("Clearing all data from database...")
        
        # Delete in reverse dependency order
        await self.session.execute(text("DELETE FROM order_contact_attempts"))
        await self.session.execute(text("DELETE FROM order_status_history"))
        await self.session.execute(text("DELETE FROM order_item_substitutions"))
        await self.session.execute(text("DELETE FROM order_items"))
        await self.session.execute(text("DELETE FROM order_export_jobs"))
        await self.session.execute(text("DELETE FROM notification_reads"))
        await self.session.execute(text("DELETE FROM notifications"))
        await self.session.execute(text("DELETE FROM report_exports"))
        await self.session.execute(text("DELETE FROM pos_sale_lines"))
        await self.session.execute(text("DELETE FROM pos_sales"))
        await self.session.execute(text("DELETE FROM revenue_payments"))
        await self.session.execute(text("DELETE FROM orders"))
        await self.session.execute(text("DELETE FROM revenue_payouts"))
        await self.session.execute(text("DELETE FROM revenue_adjustments"))
        await self.session.execute(text("DELETE FROM business_profile"))
        await self.session.execute(text("DELETE FROM categories"))
        await self.session.execute(text("DELETE FROM stock_movements"))
        await self.session.execute(text("DELETE FROM inventory_batches"))
        await self.session.execute(text("DELETE FROM inventory_items"))
        await self.session.execute(text("DELETE FROM product_barcodes"))
        await self.session.execute(text("DELETE FROM products"))
        await self.session.execute(text("DELETE FROM locations"))
        await self.session.execute(text("DELETE FROM users"))
        
        await self.session.commit()
        logger.info("All data cleared")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════


async def main(args: argparse.Namespace) -> int:
    """Main entry point."""
    configure_logging()
    
    # Safety check
    if settings.is_production:
        logger.error("🚫 Cannot run seeder in production environment!")
        return 1
    
    logger.info("=" * 60)
    logger.info("Kinmel Database Seeder")
    logger.info("=" * 60)
    logger.info(f"Environment: {settings.app_env}")
    db_hosts = settings.database_url.hosts()
    db_host = db_hosts[0]["host"] if db_hosts else "unknown"
    logger.info(f"Database: {db_host}{settings.database_url.path}")
    
    async with async_session_factory() as session:
        seeder = DatabaseSeeder(session)
        
        # Clear data if requested
        if args.clear:
            if not args.force:
                response = input("⚠️  This will DELETE ALL DATA. Type 'yes' to confirm: ")
                if response.lower() != "yes":
                    logger.info("Cancelled")
                    return 0
            await seeder.clear_all_data()
            if args.clear and not any([args.users, args.products, args.inventory, args.all]):
                return 0
        
        # Run seeders based on flags
        results = {}
        
        if args.all or args.users:
            results["users"] = await seeder.seed_users()
        
        if args.all or args.products:
            if not args.users and not args.all:
                # Need users first for products
                await seeder.seed_users()
            results["locations"] = await seeder.seed_locations()
            results["products"] = await seeder.seed_products()
        
        if args.all or args.inventory:
            if not args.products and not args.all:
                # Need products and locations first
                await seeder.seed_users()
                await seeder.seed_locations()
                await seeder.seed_products()
            results["inventory"] = await seeder.seed_inventory()
            results["batches"] = await seeder.seed_batches()
            results["movements"] = await seeder.seed_movements()

        if args.all or args.orders:
            if not args.products and not args.all:
                await seeder.seed_users()
                await seeder.seed_locations()
                await seeder.seed_products()
            results["orders"] = await seeder.seed_orders()

        if args.all or args.revenue:
            if not args.orders and not args.all:
                existing_orders = await session.execute(select(Order).limit(1))
                if not existing_orders.scalar_one_or_none():
                    await seeder.seed_users()
                    await seeder.seed_locations()
                    await seeder.seed_products()
                    await seeder.seed_orders()
            results["revenue"] = await seeder.seed_revenue()
        
        if args.all:
            results = await seeder.seed_all()
        
        await session.commit()
    
    # Print summary
    logger.info("=" * 60)
    logger.info("Seeding Complete!")
    logger.info("=" * 60)
    
    for entity, count in results.items():
        logger.info(f"  {entity.capitalize()}: {count} created")
    
    logger.info("")
    logger.info("📝 Test Credentials:")
    logger.info(f"   Password for all users: {TEST_PASSWORD}")
    logger.info("   Emails:")
    for user in SEED_USERS:
        logger.info(f"     - {user['email']} ({user['role'].value})")
    
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed the database with test data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/seed_data.py           # Seed everything
  python scripts/seed_data.py --users   # Seed users only
  python scripts/seed_data.py --clear   # Clear all data
  python scripts/seed_data.py --orders  # Seed orders only
  python scripts/seed_data.py --revenue # Seed revenue only
  python scripts/seed_data.py --clear --all  # Reset and reseed
        """,
    )
    
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        default=True,
        help="Seed all data (default)",
    )
    
    parser.add_argument(
        "--users", "-u",
        action="store_true",
        help="Seed users only",
    )
    
    parser.add_argument(
        "--products", "-p",
        action="store_true",
        help="Seed products and locations only",
    )
    
    parser.add_argument(
        "--inventory", "-i",
        action="store_true",
        help="Seed inventory, batches, and movements only",
    )

    parser.add_argument(
        "--orders", "-o",
        action="store_true",
        help="Seed orders only",
    )

    parser.add_argument(
        "--revenue", "-r",
        action="store_true",
        help="Seed revenue only",
    )
    
    parser.add_argument(
        "--clear", "-c",
        action="store_true",
        help="Clear all data before seeding",
    )
    
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip confirmation prompts",
    )
    
    args = parser.parse_args()
    
    # If specific flags are set, disable --all
    if args.users or args.products or args.inventory or args.orders or args.revenue:
        args.all = False
    
    sys.exit(asyncio.run(main(args)))

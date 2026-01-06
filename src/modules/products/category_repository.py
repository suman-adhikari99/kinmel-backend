"""
Category Repository
-------------------
Data access layer for category operations.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.products.models import Category, CategoryStatus, Product


class CategoryRepository:
    async def get_by_id(self, session: AsyncSession, category_id: str) -> Category | None:
        result = await session.execute(
            select(Category).where(Category.id == category_id, Category.is_active == True)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, session: AsyncSession, name: str) -> Category | None:
        result = await session.execute(
            select(Category).where(Category.name == name, Category.is_active == True)
        )
        return result.scalar_one_or_none()

    async def list_by_names(self, session: AsyncSession, names: list[str]) -> list[Category]:
        if not names:
            return []
        lowered = [name.lower() for name in names]
        result = await session.execute(
            select(Category).where(
                func.lower(Category.name).in_(lowered),
                Category.is_active == True,
            )
        )
        return result.scalars().all()

    async def list_categories(
        self,
        session: AsyncSession,
        *,
        search: str | None = None,
        status: str | None = None,
        featured: bool | None = None,
        limit: int = 20,
        offset: int = 0,
        sort: str = "name",
        order: str = "asc",
    ) -> tuple[list[Category], int]:
        query = select(Category).where(Category.is_active == True)
        count_query = select(func.count()).select_from(Category).where(Category.is_active == True)

        if status:
            query = query.where(Category.status == status)
            count_query = count_query.where(Category.status == status)

        if featured is not None:
            query = query.where(Category.featured == featured)
            count_query = count_query.where(Category.featured == featured)

        if search:
            pattern = f"%{search}%"
            query = query.where(
                (Category.name.ilike(pattern)) | (Category.description.ilike(pattern))
            )
            count_query = count_query.where(
                (Category.name.ilike(pattern)) | (Category.description.ilike(pattern))
            )

        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        sort_map = {
            "name": Category.name,
            "priority": Category.priority,
            "updated_at": Category.updated_at,
            "created_at": Category.created_at,
        }
        sort_col = sort_map.get(sort, Category.name)
        if order == "desc":
            query = query.order_by(sort_col.desc())
        else:
            query = query.order_by(sort_col.asc())

        result = await session.execute(query.limit(limit).offset(offset))
        return result.scalars().all(), total

    async def get_product_count(self, session: AsyncSession, category_name: str) -> int:
        result = await session.execute(
            select(func.count(Product.id)).where(
                Product.category == category_name,
                Product.is_active == True,
            )
        )
        return int(result.scalar() or 0)

    async def create(
        self,
        session: AsyncSession,
        *,
        name: str,
        description: str | None = None,
        status: str | CategoryStatus = CategoryStatus.ACTIVE,
        featured: bool = False,
        priority: int = 0,
        image_url: str | None = None,
        image_file: str | None = None,
    ) -> Category:
        category = Category(
            name=name,
            description=description,
            status=status,
            featured=featured,
            priority=priority,
            image_url=image_url,
            image_file=image_file,
        )
        session.add(category)
        await session.flush()
        return category


category_repository = CategoryRepository()

"""
Category Service
----------------
Business logic for category operations.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError, ValidationError
from src.modules.products.category_repository import category_repository
from src.modules.products.models import Category, CategoryStatus


@dataclass
class CreateCategoryInput:
    name: str
    description: str | None = None
    status: str = CategoryStatus.ACTIVE
    featured: bool = False
    priority: int = 0
    image_url: str | None = None
    image_file: str | None = None


@dataclass
class UpdateCategoryInput:
    name: str | None = None
    description: str | None = None
    status: str | None = None
    featured: bool | None = None
    priority: int | None = None
    image_url: str | None = None
    image_file: str | None = None


class CategoryService:
    def _validate_status(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.lower()
        if normalized not in {CategoryStatus.ACTIVE, CategoryStatus.ARCHIVED}:
            raise ValidationError(
                staff_message="Invalid status",
                details={"field": "status", "value": value},
            )
        return normalized

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
        return await category_repository.list_categories(
            session,
            search=search,
            status=status,
            featured=featured,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
        )

    async def get_category(
        self,
        session: AsyncSession,
        category_id: str,
    ) -> Category:
        category = await category_repository.get_by_id(session, category_id)
        if not category:
            raise NotFoundError(
                staff_message=f"Category not found: {category_id}",
                details={"resource": "category", "identifier": category_id},
            )
        return category

    async def create_category(
        self,
        session: AsyncSession,
        input_data: CreateCategoryInput,
    ) -> Category:
        status = self._validate_status(input_data.status) or CategoryStatus.ACTIVE
        name = input_data.name.strip()
        existing = await category_repository.get_by_name(session, name)
        if existing:
            raise ValidationError(
                staff_message="Category name already exists",
                details={"field": "name", "value": name},
            )
        category = await category_repository.create(
            session,
            name=name,
            description=input_data.description,
            status=status,
            featured=input_data.featured,
            priority=input_data.priority,
            image_url=input_data.image_url,
            image_file=input_data.image_file,
        )
        await session.commit()
        return category

    async def update_category(
        self,
        session: AsyncSession,
        category_id: str,
        input_data: UpdateCategoryInput,
    ) -> Category:
        category = await self.get_category(session, category_id)

        if input_data.status is not None:
            input_data.status = self._validate_status(input_data.status)

        if input_data.name and input_data.name.strip() != category.name:
            input_data.name = input_data.name.strip()
            existing = await category_repository.get_by_name(session, input_data.name)
            if existing and existing.id != category.id:
                raise ValidationError(
                    staff_message="Category name already exists",
                    details={"field": "name", "value": input_data.name},
                )

        update_fields = {}
        for field in [
            "name",
            "description",
            "status",
            "featured",
            "priority",
            "image_url",
            "image_file",
        ]:
            value = getattr(input_data, field)
            if value is not None:
                update_fields[field] = value

        for field, value in update_fields.items():
            setattr(category, field, value)

        await session.commit()
        await session.refresh(category)
        return category

    async def delete_category(
        self,
        session: AsyncSession,
        category_id: str,
    ) -> Category:
        category = await self.get_category(session, category_id)
        category.status = CategoryStatus.ARCHIVED
        category.is_active = False
        await session.commit()
        return category

    async def get_product_count(
        self,
        session: AsyncSession,
        category_name: str,
    ) -> int:
        return await category_repository.get_product_count(session, category_name)


category_service = CategoryService()

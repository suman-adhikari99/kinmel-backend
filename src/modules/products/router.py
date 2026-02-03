"""
Product API Router
------------------
REST endpoints for product and category operations.

🔐 ACCESS CONTROL:

| Endpoint              | PUBLIC | STAFF | MANAGER | ADMIN |
|-----------------------|--------|-------|---------|-------|
| list_products         | ✓      | ✓     | ✓       | ✓     |
| get_product           | ✓      | ✓     | ✓       | ✓     |
| get_product_by_barcode| ✓      | ✓     | ✓       | ✓     |
| list_categories       | ✓      | ✓     | ✓       | ✓     |
| get_products_by_cat   | ✓      | ✓     | ✓       | ✓     |
| create_product        | ✗      | ✗     | ✓       | ✓     |
| update_product        | ✗      | ✗     | ✓       | ✓     |
| delete_product        | ✗      | ✗     | ✗       | ✓     |
"""

from typing import Annotated
from pathlib import Path
import uuid
from decimal import Decimal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from starlette.requests import Request

from src.api.deps import (
    CurrentUser,
    DbSession,
)
from src.core.exceptions import NotFoundError, ValidationError
from src.core.logging import get_logger
from src.core.security import Role, has_role_or_higher
from src.modules.products.models import ProductStatus
from src.modules.products.schemas import (
    CategoryCreateRequest,
    CategoryDetailResponse,
    CategoryImageUploadResponse,
    CategoryListResponse,
    CategorySummaryResponse,
    CategoryUpdateRequest,
    CreateProductRequest,
    ProductBulkRequest,
    ProductBulkResponse,
    ProductImageUploadResponse,
    ProductListResponse,
    ProductResponse,
    ProductSummaryResponse,
    UpdateProductRequest,
)
from src.modules.products.service import (
    CreateProductInput,
    UpdateProductInput,
    product_service,
)
from src.modules.products.category_service import (
    CreateCategoryInput,
    UpdateCategoryInput,
    category_service,
)
from src.modules.products.repository import product_repository

logger = get_logger(__name__)

PRODUCT_IMAGE_DIR = Path("uploads/products")
ALLOWED_PRODUCT_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
PRODUCT_IMAGE_MAX_SIZE = 5 * 1024 * 1024

CATEGORY_IMAGE_DIR = Path("uploads/categories")
ALLOWED_CATEGORY_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
CATEGORY_IMAGE_MAX_SIZE = 5 * 1024 * 1024

router = APIRouter(
    prefix="/products",
    tags=["Products"],
    responses={
        404: {"description": "Product not found"},
        422: {"description": "Validation error"},
    },
)

categories_router = APIRouter(
    prefix="/categories",
    tags=["Categories"],
)


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def require_manager_or_admin(user: CurrentUser) -> None:
    """Verify user has manager or admin role."""
    if not has_role_or_higher(user.role, Role.MANAGER):
        logger.warning(
            "Access denied - insufficient role for product management",
            user_id=user.sub,
            user_role=user.role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Product management requires Manager or Admin role.",
                "code": "INSUFFICIENT_ROLE",
                "required_role": "MANAGER",
                "your_role": user.role.value,
            },
        )


def require_admin(user: CurrentUser) -> None:
    """Verify user has admin role."""
    if not has_role_or_higher(user.role, Role.ADMIN):
        logger.warning(
            "Access denied - insufficient role for product deletion",
            user_id=user.sub,
            user_role=user.role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Product deletion requires Admin role.",
                "code": "INSUFFICIENT_ROLE",
                "required_role": "ADMIN",
                "your_role": user.role.value,
            },
        )


def handle_service_error(e: Exception) -> None:
    """Convert service exceptions to HTTP exceptions."""
    if isinstance(e, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": e.staff_message,
                "code": "NOT_FOUND",
                "resource": e.details.get("resource"),
                "identifier": e.details.get("identifier"),
            },
        )
    elif isinstance(e, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": e.staff_message,
                "code": "VALIDATION_ERROR",
                "field": e.details.get("field"),
                "value": e.details.get("value"),
            },
        )
    else:
        logger.exception("Unexpected error in product operation")
        raise


def parse_category(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip()


def parse_status(value: str | None) -> ProductStatus | None:
    if not value:
        return None
    try:
        return ProductStatus(value.lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": f"Invalid status: {value}",
                "code": "INVALID_STATUS",
                "valid_statuses": [s.value for s in ProductStatus],
            },
        ) from exc


def parse_category_status(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.lower()
    if normalized not in {"active", "archived"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": f"Invalid status: {value}",
                "code": "INVALID_STATUS",
                "valid_statuses": ["active", "archived"],
            },
        )
    return normalized


def resolve_product_image_url(request: Request, image_url: str | None, image_file: str | None) -> str | None:
    url = image_url or ""
    if url:
        if url.startswith(("http://", "https://")):
            return url
        if not url.startswith("/"):
            if "uploads/" in url:
                url = f"/{url.lstrip('/')}"
            else:
                url = f"/uploads/products/{url}"
    elif image_file:
        url = f"/uploads/products/{image_file}"
    if url.startswith("/"):
        return f"{str(request.base_url).rstrip('/')}{url}"
    return url or None


def apply_barcodes(response: ProductResponse, product) -> None:
    primary_barcode, barcodes = product_service.resolve_barcodes(product)
    response.primary_barcode = primary_barcode
    response.barcodes = barcodes


def build_summary(request: Request, product, stock: int) -> ProductSummaryResponse:
    primary_barcode, barcodes = product_service.resolve_barcodes(product)
    return ProductSummaryResponse(
        id=product.id,
        sku=product.sku,
        name=product.name,
        category=product.category,
        subcategory=product.subcategory,
        unit_price=product.unit_price,
        tax_rate=product.tax_rate,
        stock=stock,
        primary_barcode=primary_barcode,
        barcodes=barcodes,
        status=product.status,
        featured=product.featured,
        priority=product.priority,
        image_url=resolve_product_image_url(request, product.image_url, product.image_file),
        is_perishable=product.is_perishable,
        is_active=product.is_active,
        variants_count=0,
        updated_at=product.updated_at,
    )


def resolve_image_url(request: Request, image_url: str | None, image_file: str | None) -> str | None:
    url = image_url or ""
    if url:
        if url.startswith(("http://", "https://")):
            return url
        if not url.startswith("/"):
            if "uploads/" in url:
                url = f"/{url.lstrip('/')}"
            else:
                url = f"/uploads/categories/{url}"
    elif image_file:
        url = f"/uploads/categories/{image_file}"
    if url.startswith("/"):
        return f"{str(request.base_url).rstrip('/')}{url}"
    return url or None


async def build_category_summary(
    db: DbSession,
    category,
    request: Request,
) -> CategorySummaryResponse:
    product_count = await category_service.get_product_count(db, category.name)
    image_url = resolve_image_url(request, category.image_url, category.image_file)
    return CategorySummaryResponse(
        id=category.id,
        name=category.name,
        description=category.description,
        status=category.status,
        featured=category.featured,
        priority=category.priority,
        image_url=image_url,
        product_count=product_count,
        updated_at=category.updated_at,
    )


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "",
    response_model=ProductListResponse,
    summary="List products",
    description="""
    List all products with optional filtering and pagination.
    
    **Who can use:** Public (no authentication required)
    
    **Filters:**
    - `category`: Filter by product category
    - `search`: Search in product name and SKU
    
    **Pagination:**
    - `limit`: Max products to return (default 50, max 200)
    - `offset`: Number of products to skip
    """,
)
async def list_products(
    db: DbSession,
    request: Request,
    category: Annotated[
        str | None,
        Query(description="Filter by category")
    ] = None,
    subcategory: Annotated[
        str | None,
        Query(description="Filter by subcategory")
    ] = None,
    status: Annotated[
        str | None,
        Query(description="Filter by status")
    ] = None,
    featured: Annotated[
        bool | None,
        Query(description="Filter by featured flag")
    ] = None,
    min_price: Annotated[
        Decimal | None,
        Query(ge=0, description="Minimum unit price")
    ] = None,
    max_price: Annotated[
        Decimal | None,
        Query(ge=0, description="Maximum unit price")
    ] = None,
    in_stock: Annotated[
        bool | None,
        Query(description="Filter by stock availability")
    ] = None,
    search: Annotated[
        str | None,
        Query(max_length=100, description="Search in name and SKU")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Annotated[
        str,
        Query(description="Sort field", pattern="^(name|price|stock|updated_at|created_at|priority)$"),
    ] = "created_at",
    order: Annotated[
        str,
        Query(description="Sort order", pattern="^(asc|desc)$"),
    ] = "desc",
) -> ProductListResponse:
    """List products with optional filtering. Public endpoint."""
    category_enum = parse_category(category)
    status_enum = parse_status(status)
    products, total = await product_service.list_products(
        db,
        category=category_enum,
        subcategory=subcategory,
        status=status_enum,
        featured=featured,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        search=search,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )
    
    return ProductListResponse(
        items=[build_summary(request, product, int(stock or 0)) for product, stock in products],
        total=total,
        limit=limit,
        offset=offset,
    )




@router.get(
    "/{identifier}",
    response_model=ProductResponse,
    summary="Get product by SKU or ID",
    description="""
    Get detailed product information by SKU or UUID.
    
    **Who can use:** Public (no authentication required)
    """,
)
async def get_product(
    identifier: str,
    db: DbSession,
    request: Request,
) -> ProductResponse:
    """Get a product by SKU or UUID. Public endpoint."""
    try:
        product = await product_service.get_product_by_identifier(db, identifier)
        stock = await product_repository.get_stock_by_product_id(db, product.id)
        response = ProductResponse.model_validate(product)
        response.stock = stock
        response.variants = []
        response.image_url = resolve_product_image_url(request, product.image_url, product.image_file)
        apply_barcodes(response, product)
        return response
    except Exception as e:
        handle_service_error(e)
        raise


@router.get(
    "/barcode/{barcode}",
    response_model=ProductResponse,
    summary="Get product by barcode",
    description="""
    Get product information by scanning its barcode.
    
    **Who can use:** Public (no authentication required)
    
    Useful for:
    - Point of sale scanning
    - Inventory receiving
    - Quick product lookup
    """,
)
async def get_product_by_barcode(
    barcode: str,
    db: DbSession,
    request: Request,
) -> ProductResponse:
    """Get a product by barcode. Public endpoint."""
    try:
        product = await product_service.get_product_by_barcode(db, barcode)
        stock = await product_repository.get_stock_by_product_id(db, product.id)
        response = ProductResponse.model_validate(product)
        response.stock = stock
        response.variants = []
        response.image_url = resolve_product_image_url(request, product.image_url, product.image_file)
        apply_barcodes(response, product)
        return response
    except Exception as e:
        handle_service_error(e)
        raise


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create product",
    description="""
    Create a new product in the catalog.
    
    **Who can use:** Managers and Admins only
    
    **Important:**
    - SKU must be unique and cannot be changed after creation
    - Barcode must be unique if provided
    """,
)
async def create_product(
    request: CreateProductRequest,
    user: CurrentUser,
    db: DbSession,
    req: Request,
) -> ProductResponse:
    """Create a new product."""
    require_manager_or_admin(user)
    
    logger.info(
        "Creating product",
        sku=request.sku,
        name=request.name,
        category=request.category,
        user=user.sub,
    )
    
    try:
        product = await product_service.create_product(
            db,
            CreateProductInput(
                sku=request.sku,
                name=request.name,
                description=request.description,
                category=request.category,
                brand=request.brand,
                subcategory=request.subcategory,
                image_url=request.image_url,
                image_file=request.image_file,
                unit_price=request.unit_price,
                cost_price=request.cost_price,
                tax_rate=request.tax_rate,
                barcode=request.barcode,
                barcodes=request.barcodes,
                primary_barcode=request.primary_barcode,
                unit_of_measure=request.unit_of_measure,
                pack_size=request.pack_size,
                is_perishable=request.is_perishable,
                shelf_life_days=request.shelf_life_days,
                requires_cold_storage=request.requires_cold_storage,
                status=request.status,
                featured=request.featured,
                priority=request.priority,
                user_id=user.sub,
            ),
        )
        response = ProductResponse.model_validate(product)
        response.stock = await product_repository.get_stock_by_product_id(db, product.id)
        response.image_url = resolve_product_image_url(req, product.image_url, product.image_file)
        apply_barcodes(response, product)
        return response
    except Exception as e:
        handle_service_error(e)
        raise


@router.put(
    "/{identifier}",
    response_model=ProductResponse,
    summary="Update product",
    description="""
    Update an existing product.
    
    **Who can use:** Managers and Admins only
    
    **Note:** SKU cannot be changed. Only provided fields will be updated.
    """,
)
async def update_product(
    identifier: str,
    request: UpdateProductRequest,
    user: CurrentUser,
    db: DbSession,
    req: Request,
) -> ProductResponse:
    """Update a product."""
    require_manager_or_admin(user)
    
    logger.info(
        "Updating product",
        identifier=identifier,
        user=user.sub,
    )
    
    try:
        product = await product_service.update_product(
            db,
            identifier,
            UpdateProductInput(
                name=request.name,
                description=request.description,
                category=request.category,
                brand=request.brand,
                subcategory=request.subcategory,
                image_url=request.image_url,
                image_file=request.image_file,
                unit_price=request.unit_price,
                cost_price=request.cost_price,
                tax_rate=request.tax_rate,
                barcode=request.barcode,
                barcodes=request.barcodes,
                primary_barcode=request.primary_barcode,
                unit_of_measure=request.unit_of_measure,
                pack_size=request.pack_size,
                is_perishable=request.is_perishable,
                shelf_life_days=request.shelf_life_days,
                requires_cold_storage=request.requires_cold_storage,
                status=request.status,
                featured=request.featured,
                priority=request.priority,
                user_id=user.sub,
            ),
        )
        response = ProductResponse.model_validate(product)
        response.stock = await product_repository.get_stock_by_product_id(db, product.id)
        response.image_url = resolve_product_image_url(req, product.image_url, product.image_file)
        apply_barcodes(response, product)
        return response
    except Exception as e:
        handle_service_error(e)
        raise


@router.patch(
    "/{identifier}",
    response_model=ProductResponse,
    summary="Update product (partial)",
    description="Partially update a product.",
)
async def patch_product(
    identifier: str,
    request: UpdateProductRequest,
    user: CurrentUser,
    db: DbSession,
    req: Request,
) -> ProductResponse:
    return await update_product(identifier, request, user, db, req)


@router.delete(
    "/{identifier}",
    response_model=ProductResponse,
    summary="Delete product",
    description="""
    Soft delete a product (marks as inactive).
    
    **Who can use:** Admins only
    
    **Note:** Products are soft-deleted and can be recovered.
    Inventory items associated with this product remain in the system.
    """,
)
async def delete_product(
    identifier: str,
    user: CurrentUser,
    db: DbSession,
    req: Request,
) -> ProductResponse:
    """Delete (soft) a product."""
    require_admin(user)
    
    logger.info(
        "Deleting product",
        identifier=identifier,
        user=user.sub,
    )
    
    try:
        product = await product_service.delete_product(db, identifier)
        response = ProductResponse.model_validate(product)
        response.image_url = resolve_product_image_url(req, product.image_url, product.image_file)
        apply_barcodes(response, product)
        return response
    except Exception as e:
        handle_service_error(e)
        raise


@router.post(
    "/bulk",
    response_model=ProductBulkResponse,
    summary="Bulk product actions",
    description="Perform bulk actions on products.",
)
async def bulk_products(
    request: ProductBulkRequest,
    user: CurrentUser,
    db: DbSession,
) -> ProductBulkResponse:
    require_manager_or_admin(user)
    if request.action == "delete":
        require_admin(user)

    updated, failed = await product_service.bulk_action(
        db,
        request.action,
        request.ids,
        request.payload,
    )
    return ProductBulkResponse(updated=updated, failed=failed)


@router.post(
    "/{identifier}/image",
    response_model=ProductImageUploadResponse,
    summary="Upload product image",
    description="Upload a product image (max 5MB, jpg/png/webp).",
)
async def upload_product_image(
    identifier: str,
    user: CurrentUser,
    db: DbSession,
    request: Request,
    file: UploadFile = File(...),
) -> ProductImageUploadResponse:
    require_manager_or_admin(user)

    if file.content_type not in ALLOWED_PRODUCT_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_PRODUCT_IMAGE_TYPES)}",
        )

    contents = await file.read()
    if len(contents) > PRODUCT_IMAGE_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {PRODUCT_IMAGE_MAX_SIZE // (1024 * 1024)}MB",
        )

    product = await product_service.get_product_by_identifier(db, identifier)

    ext = file.filename.split(".")[-1] if file.filename else "jpg"
    filename = f"{product.id}-{uuid.uuid4().hex[:8]}.{ext}"

    PRODUCT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    file_path = PRODUCT_IMAGE_DIR / filename
    with open(file_path, "wb") as handler:
        handler.write(contents)

    image_url = f"/uploads/products/{filename}"
    product.image_url = image_url
    product.image_file = filename
    await db.commit()

    return ProductImageUploadResponse(
        image_url=resolve_product_image_url(request, image_url, filename)
    )


@router.get(
    "/export.csv",
    summary="Export products CSV",
)
async def export_products(
    db: DbSession,
    category: Annotated[str | None, Query(description="Filter by category")] = None,
    subcategory: Annotated[str | None, Query(description="Filter by subcategory")] = None,
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    featured: Annotated[bool | None, Query(description="Filter by featured flag")] = None,
    min_price: Annotated[Decimal | None, Query(ge=0, description="Minimum unit price")] = None,
    max_price: Annotated[Decimal | None, Query(ge=0, description="Maximum unit price")] = None,
    in_stock: Annotated[bool | None, Query(description="Filter by stock availability")] = None,
    search: Annotated[str | None, Query(max_length=100, description="Search in name and SKU")] = None,
    sort: Annotated[
        str,
        Query(description="Sort field", pattern="^(name|price|stock|updated_at|created_at|priority)$"),
    ] = "created_at",
    order: Annotated[
        str,
        Query(description="Sort order", pattern="^(asc|desc)$"),
    ] = "desc",
    limit: Annotated[int, Query(ge=1, le=5000)] = 5000,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    from starlette.responses import StreamingResponse
    import csv
    import io

    category_enum = parse_category(category)
    status_enum = parse_status(status)
    products, _ = await product_service.list_products(
        db,
        category=category_enum,
        subcategory=subcategory,
        status=status_enum,
        featured=featured,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        search=search,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "sku",
            "name",
            "category",
            "subcategory",
            "price",
            "gst",
            "stock",
            "status",
            "featured",
            "priority",
            "image_url",
            "image_file",
            "updated_at",
        ]
    )
    for product, stock in products:
        gst_amount = (product.unit_price * product.tax_rate).quantize(Decimal("0.01"))
        writer.writerow(
            [
                product.id,
                product.sku,
                product.name,
                product.category,
                product.subcategory or "",
                str(product.unit_price),
                str(gst_amount),
                int(stock or 0),
                product.status.value,
                product.featured,
                product.priority,
                product.image_url or "",
                product.image_file or "",
                product.updated_at.isoformat() if product.updated_at else "",
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="products_export.csv"'},
    )


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@categories_router.get(
    "",
    response_model=CategoryListResponse,
    summary="List categories",
    description="""
    List all available product categories.
    
    **Who can use:** Public (no authentication required)
    
    Returns the category code, display name, and description for each category.
    """,
)
async def list_categories(
    db: DbSession,
    request: Request,
    search: Annotated[str | None, Query(description="Search categories")] = None,
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    featured: Annotated[bool | None, Query(description="Filter by featured flag")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Annotated[
        str,
        Query(description="Sort field", pattern="^(name|priority|updated_at|created_at)$"),
    ] = "name",
    order: Annotated[
        str,
        Query(description="Sort order", pattern="^(asc|desc)$"),
    ] = "asc",
) -> CategoryListResponse:
    """List all product categories. Public endpoint."""
    status_value = parse_category_status(status)
    categories, total = await category_service.list_categories(
        db,
        search=search,
        status=status_value,
        featured=featured,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )
    items = [await build_category_summary(db, category, request) for category in categories]
    return CategoryListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@categories_router.get(
    "/{category_id}",
    response_model=CategoryDetailResponse,
    summary="Get category detail",
)
async def get_category_detail(
    category_id: str,
    db: DbSession,
    request: Request,
) -> CategoryDetailResponse:
    category = await category_service.get_category(db, category_id)
    summary = await build_category_summary(db, category, request)
    return CategoryDetailResponse(
        **summary.model_dump(),
        created_at=category.created_at,
    )


@categories_router.post(
    "",
    response_model=CategoryDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create category",
)
async def create_category(
    request: CategoryCreateRequest,
    user: CurrentUser,
    db: DbSession,
    req: Request,
) -> CategoryDetailResponse:
    require_manager_or_admin(user)
    category = await category_service.create_category(
        db,
        CreateCategoryInput(
            name=request.name,
            description=request.description,
            status=request.status,
            featured=request.featured,
            priority=request.priority,
            image_url=request.image_url,
            image_file=request.image_file,
        ),
    )
    summary = await build_category_summary(db, category, req)
    return CategoryDetailResponse(
        **summary.model_dump(),
        created_at=category.created_at,
    )


@categories_router.patch(
    "/{category_id}",
    response_model=CategoryDetailResponse,
    summary="Update category",
)
async def update_category(
    category_id: str,
    request: CategoryUpdateRequest,
    user: CurrentUser,
    db: DbSession,
    req: Request,
) -> CategoryDetailResponse:
    require_manager_or_admin(user)
    category = await category_service.update_category(
        db,
        category_id,
        UpdateCategoryInput(
            name=request.name,
            description=request.description,
            status=request.status,
            featured=request.featured,
            priority=request.priority,
            image_url=request.image_url,
            image_file=request.image_file,
        ),
    )
    summary = await build_category_summary(db, category, req)
    return CategoryDetailResponse(
        **summary.model_dump(),
        created_at=category.created_at,
    )


@categories_router.delete(
    "/{category_id}",
    summary="Delete category",
)
async def delete_category(
    category_id: str,
    user: CurrentUser,
    db: DbSession,
):
    require_admin(user)
    await category_service.delete_category(db, category_id)
    return {"message": "Category deleted"}


@categories_router.post(
    "/{category_id}/image",
    response_model=CategoryImageUploadResponse,
    summary="Upload category image",
)
async def upload_category_image(
    category_id: str,
    user: CurrentUser,
    db: DbSession,
    request: Request,
    file: UploadFile = File(...),
) -> CategoryImageUploadResponse:
    require_manager_or_admin(user)

    content_type = (file.content_type or "").lower()
    ext = (file.filename.split(".")[-1].lower() if file.filename else "")
    allowed_ext = {"jpg", "jpeg", "png", "webp"}
    if content_type not in ALLOWED_CATEGORY_IMAGE_TYPES and ext not in allowed_ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_CATEGORY_IMAGE_TYPES)}",
        )

    contents = await file.read()
    if len(contents) > CATEGORY_IMAGE_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {CATEGORY_IMAGE_MAX_SIZE // (1024 * 1024)}MB",
        )

    category = await category_service.get_category(db, category_id)
    ext = ext or "jpg"
    filename = f"{category.id}-{uuid.uuid4().hex[:8]}.{ext}"
    CATEGORY_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    file_path = CATEGORY_IMAGE_DIR / filename
    with open(file_path, "wb") as handler:
        handler.write(contents)

    image_url = f"{str(request.base_url).rstrip('/')}/uploads/categories/{filename}"
    await category_service.update_category(
        db,
        category.id,
        UpdateCategoryInput(image_url=image_url, image_file=filename),
    )
    return CategoryImageUploadResponse(image_url=image_url)


@categories_router.get(
    "/{category_code}/products",
    response_model=ProductListResponse,
    summary="Get products by category",
    description="""
    Get all products in a specific category.
    
    **Who can use:** Public (no authentication required)
    """,
)
async def get_products_by_category(
    category_code: str,
    db: DbSession,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductListResponse:
    """Get products in a category. Public endpoint."""
    category_value = category_code.strip()
    category = category_value
    if category_value:
        try:
            category_obj = await category_service.get_category(db, category_value)
            category = category_obj.name
        except Exception:
            category = category_value
    
    products, total = await product_service.list_products(
        db,
        category=category,
        limit=limit,
        offset=offset,
    )
    
    return ProductListResponse(
        items=[build_summary(request, product, int(stock or 0)) for product, stock in products],
        total=total,
        limit=limit,
        offset=offset,
    )

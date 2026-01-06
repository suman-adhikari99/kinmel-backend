"""
Business Profile Router
-----------------------
Business profile endpoints.
"""

from fastapi import APIRouter

from src.api.deps import RequireStaff, CurrentUser, DbSession
from src.modules.revenue.schemas import BusinessProfileResponse
from src.modules.revenue.service import revenue_service

router = APIRouter(
    prefix="/business",
    tags=["Business"],
    dependencies=[RequireStaff],
)


@router.get(
    "/profile",
    response_model=BusinessProfileResponse,
    summary="Business profile",
)
async def get_business_profile(
    user: CurrentUser,
    db: DbSession,
) -> BusinessProfileResponse:
    profile = await revenue_service.get_business_profile(db)
    if not profile:
        return BusinessProfileResponse(
            legalName="",
            abn="",
            gstRegistered=False,
            gstRate="",
            storeAddress="",
            contactEmail="",
            contactPhone="",
            bankMasked="",
        )
    return BusinessProfileResponse(
        legalName=profile.legal_name,
        abn=profile.abn,
        gstRegistered=profile.gst_registered,
        gstRate=profile.gst_rate,
        storeAddress=profile.store_address,
        contactEmail=profile.contact_email,
        contactPhone=profile.contact_phone,
        bankMasked=profile.bank_masked,
    )

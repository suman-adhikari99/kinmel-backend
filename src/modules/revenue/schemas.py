"""
Revenue API Schemas
-------------------
Pydantic models for revenue reporting endpoints.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        from_attributes=True,
    )


class RevenueTotals(StrictModel):
    revenue: Decimal
    expenses: Decimal
    profit: Decimal


class RevenueComparisons(StrictModel):
    revenueChangePct: Decimal
    expensesChangePct: Decimal
    profitChangePct: Decimal


class RevenueSummaryResponse(StrictModel):
    currency: str
    range: str
    from_: str = Field(..., alias="from")
    to: str
    totals: RevenueTotals
    comparisons: RevenueComparisons
    lastUpdated: datetime


class RevenueTrendPoint(StrictModel):
    label: str
    startDate: str
    revenue: Decimal
    expenses: Decimal
    profit: Decimal


class RevenueTrendResponse(StrictModel):
    currency: str
    interval: Literal["day", "week", "month"]
    series: list[RevenueTrendPoint]


class RevenueDailyByTypePoint(StrictModel):
    label: str
    date: str
    pickup: Decimal
    delivery: Decimal


class RevenueDailyByTypeResponse(StrictModel):
    currency: str
    series: list[RevenueDailyByTypePoint]


class RevenuePaymentMethod(StrictModel):
    name: str
    value: Decimal
    amount: Decimal


class RevenuePaymentMethodsResponse(StrictModel):
    currency: str
    methods: list[RevenuePaymentMethod]
    total: Decimal


class RevenueCategoryItem(StrictModel):
    category: str
    revenue: Decimal
    percentage: Decimal


class RevenueCategoryOthers(StrictModel):
    revenue: Decimal
    percentage: Decimal


class RevenueCategoriesResponse(StrictModel):
    currency: str
    categories: list[RevenueCategoryItem]
    others: RevenueCategoryOthers


class RevenueTransaction(StrictModel):
    id: str
    customer: str
    amount: Decimal
    method: str
    time: datetime
    status: str


class RevenueTransactionsResponse(StrictModel):
    currency: str
    transactions: list[RevenueTransaction]


class BusinessProfileResponse(StrictModel):
    legalName: str
    abn: str
    gstRegistered: bool
    gstRate: str
    storeAddress: str
    contactEmail: str
    contactPhone: str
    bankMasked: str


class RevenuePayoutSummaryResponse(StrictModel):
    nextPayout: datetime
    lastPayout: datetime
    pendingAmount: Decimal
    completedThisMonth: int
    payoutFrequency: str
    processor: str


class RevenueTaxesFeesResponse(StrictModel):
    gstCollected: Decimal
    gstDue: str
    platformFees: Decimal
    refunds: Decimal
    disputes: Decimal

"""
Customers Repository
--------------------
Mock data access for customers endpoints.

No customers table exists yet, so this repository returns in-memory data.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.customers.schemas import ActionStatus, CustomerSegment, CustomerStatus
from src.modules.customers.seed_data import EXTRA_CUSTOMERS


_CUSTOMERS: list[dict] = [
    {
        "id": "CUST-1045",
        "name": "Asha Rai",
        "email": "asha.rai@email.com",
        "phone": "+61 412 334 882",
        "status": "active",
        "segment": "VIP",
        "location": "Sydney",
        "owner": {"id": "USER-1", "name": "Nisha"},
        "lifetime_value": 6280.0,
        "orders_count": 34,
        "avg_order_value": 184.0,
        "last_order_at": datetime(2024, 6, 12, 10, 5, tzinfo=UTC),
        "last_contact_at": datetime(2024, 6, 13, 2, 15, tzinfo=UTC),
        "next_action": "Confirm monthly wholesale schedule",
        "loyalty_tier": "Gold",
        "tags": ["Wholesale", "Cafe"],
        "risk_score": 12,
        "created_at": datetime(2024, 1, 14, 8, 30, tzinfo=UTC),
        "notes": "Prefers early morning delivery, high repeat rate.",
        "invite_status": "accepted",
        "invite_sent_at": datetime(2024, 1, 14, 9, 0, tzinfo=UTC),
        "invite_accepted_at": datetime(2024, 1, 14, 9, 30, tzinfo=UTC),
        "invite_token": None,
        "invite_expires_at": None,
    },
    {
        "id": "CUST-1102",
        "name": "Milan Thapa",
        "email": "milan.thapa@email.com",
        "phone": "+61 409 112 500",
        "status": "at_risk",
        "segment": "Local",
        "location": "Melbourne",
        "owner": {"id": "USER-2", "name": "Amit"},
        "lifetime_value": 2120.0,
        "orders_count": 11,
        "avg_order_value": 193.0,
        "last_order_at": datetime(2024, 5, 20, 6, 40, tzinfo=UTC),
        "last_contact_at": datetime(2024, 6, 2, 1, 20, tzinfo=UTC),
        "next_action": "Offer seasonal bundle and check satisfaction",
        "loyalty_tier": "Silver",
        "tags": ["Cafe"],
        "risk_score": 58,
        "created_at": datetime(2023, 11, 2, 9, 10, tzinfo=UTC),
        "notes": "Price-sensitive. Responds to short promos.",
        "invite_status": "sent",
        "invite_sent_at": datetime(2024, 6, 2, 3, 0, tzinfo=UTC),
        "invite_accepted_at": None,
        "invite_token": "INVITE-1102",
        "invite_expires_at": datetime(2024, 6, 9, 3, 0, tzinfo=UTC),
    },
    {
        "id": "CUST-1207",
        "name": "Rajan Koirala",
        "email": "rajan.koirala@email.com",
        "phone": "+61 431 778 990",
        "status": "active",
        "segment": "Wholesale",
        "location": "Brisbane",
        "owner": {"id": "USER-3", "name": "Sasha"},
        "lifetime_value": 11420.0,
        "orders_count": 54,
        "avg_order_value": 211.0,
        "last_order_at": datetime(2024, 6, 14, 12, 0, tzinfo=UTC),
        "last_contact_at": datetime(2024, 6, 15, 2, 5, tzinfo=UTC),
        "next_action": "Review quarterly volume rebate",
        "loyalty_tier": "Platinum",
        "tags": ["Wholesale"],
        "risk_score": 8,
        "created_at": datetime(2023, 7, 22, 3, 40, tzinfo=UTC),
        "notes": "High volume account. Prefers consolidated invoices.",
        "invite_status": "accepted",
        "invite_sent_at": datetime(2023, 7, 22, 4, 0, tzinfo=UTC),
        "invite_accepted_at": datetime(2023, 7, 22, 6, 0, tzinfo=UTC),
        "invite_token": None,
        "invite_expires_at": None,
    },
    {
        "id": "CUST-1310",
        "name": "Kiran Lama",
        "email": "kiran.lama@email.com",
        "phone": "+61 428 551 304",
        "status": "new",
        "segment": "Online",
        "location": "Perth",
        "owner": {"id": "USER-1", "name": "Nisha"},
        "lifetime_value": 340.0,
        "orders_count": 2,
        "avg_order_value": 170.0,
        "last_order_at": datetime(2024, 6, 10, 4, 20, tzinfo=UTC),
        "last_contact_at": None,
        "next_action": "Welcome call and onboarding",
        "loyalty_tier": None,
        "tags": ["Online"],
        "risk_score": 22,
        "created_at": datetime(2024, 6, 1, 1, 0, tzinfo=UTC),
        "notes": "First-time online shopper.",
        "invite_status": "sent",
        "invite_sent_at": datetime(2024, 6, 1, 1, 10, tzinfo=UTC),
        "invite_accepted_at": None,
        "invite_token": "INVITE-1310",
        "invite_expires_at": datetime(2024, 6, 8, 1, 10, tzinfo=UTC),
    },
    {
        "id": "CUST-1422",
        "name": "Sita Gurung",
        "email": "sita.gurung@email.com",
        "phone": "+61 401 991 877",
        "status": "inactive",
        "segment": "Lapsed",
        "location": "Adelaide",
        "owner": {"id": "USER-4", "name": "Priya"},
        "lifetime_value": 980.0,
        "orders_count": 6,
        "avg_order_value": 163.0,
        "last_order_at": datetime(2024, 2, 18, 9, 5, tzinfo=UTC),
        "last_contact_at": datetime(2024, 3, 1, 0, 15, tzinfo=UTC),
        "next_action": "Send win-back offer",
        "loyalty_tier": None,
        "tags": ["Retail"],
        "risk_score": 76,
        "created_at": datetime(2023, 8, 10, 11, 35, tzinfo=UTC),
        "notes": "Hasn't reordered since February.",
        "invite_status": "not_sent",
        "invite_sent_at": None,
        "invite_accepted_at": None,
        "invite_token": None,
        "invite_expires_at": None,
    },
    {
        "id": "CUST-1503",
        "name": "Deepak Shrestha",
        "email": "deepak.shrestha@email.com",
        "phone": "+61 410 331 991",
        "status": "active",
        "segment": "Local",
        "location": "Sydney",
        "owner": {"id": "USER-2", "name": "Amit"},
        "lifetime_value": 4520.0,
        "orders_count": 29,
        "avg_order_value": 156.0,
        "last_order_at": datetime(2024, 6, 11, 7, 45, tzinfo=UTC),
        "last_contact_at": datetime(2024, 6, 12, 3, 30, tzinfo=UTC),
        "next_action": "Check in about summer menu",
        "loyalty_tier": "Gold",
        "tags": ["Cafe", "Local"],
        "risk_score": 18,
        "created_at": datetime(2023, 9, 30, 6, 15, tzinfo=UTC),
        "notes": "Prefers deliveries before noon.",
        "invite_status": "accepted",
        "invite_sent_at": datetime(2023, 9, 30, 7, 0, tzinfo=UTC),
        "invite_accepted_at": datetime(2023, 10, 1, 3, 0, tzinfo=UTC),
        "invite_token": None,
        "invite_expires_at": None,
    },
    {
        "id": "CUST-1628",
        "name": "Anita Sherpa",
        "email": "anita.sherpa@email.com",
        "phone": "+61 409 551 728",
        "status": "active",
        "segment": "VIP",
        "location": "Melbourne",
        "owner": {"id": "USER-3", "name": "Sasha"},
        "lifetime_value": 7740.0,
        "orders_count": 40,
        "avg_order_value": 194.0,
        "last_order_at": datetime(2024, 6, 9, 11, 20, tzinfo=UTC),
        "last_contact_at": datetime(2024, 6, 10, 2, 40, tzinfo=UTC),
        "next_action": "Schedule quarterly feedback call",
        "loyalty_tier": "Gold",
        "tags": ["Wholesale", "VIP"],
        "risk_score": 14,
        "created_at": datetime(2023, 6, 4, 5, 0, tzinfo=UTC),
        "notes": "High-margin orders, quick responses.",
        "invite_status": "accepted",
        "invite_sent_at": datetime(2023, 6, 4, 6, 0, tzinfo=UTC),
        "invite_accepted_at": datetime(2023, 6, 4, 8, 0, tzinfo=UTC),
        "invite_token": None,
        "invite_expires_at": None,
    },
    {
        "id": "CUST-1739",
        "name": "Nabin Basnet",
        "email": "nabin.basnet@email.com",
        "phone": "+61 422 662 111",
        "status": "at_risk",
        "segment": "Online",
        "location": "Canberra",
        "owner": {"id": "USER-4", "name": "Priya"},
        "lifetime_value": 1560.0,
        "orders_count": 9,
        "avg_order_value": 173.0,
        "last_order_at": datetime(2024, 4, 12, 2, 10, tzinfo=UTC),
        "last_contact_at": datetime(2024, 5, 2, 0, 55, tzinfo=UTC),
        "next_action": "Review churn risk and offer reorder",
        "loyalty_tier": None,
        "tags": ["Online"],
        "risk_score": 64,
        "created_at": datetime(2023, 10, 18, 7, 25, tzinfo=UTC),
        "notes": "Drop in order frequency over last 60 days.",
        "invite_status": "not_sent",
        "invite_sent_at": None,
        "invite_accepted_at": None,
        "invite_token": None,
        "invite_expires_at": None,
    },
]

_CUSTOMERS.extend(EXTRA_CUSTOMERS)

_ACTIONS: list[dict] = [
    {
        "id": "ACT-402",
        "customer_id": "CUST-1102",
        "customer_name": "Milan Thapa",
        "title": "Offer seasonal bundle and check satisfaction",
        "due_at": datetime(2024, 6, 15, 8, 0, tzinfo=UTC),
        "priority": "high",
        "status": "open",
        "last_order_at": datetime(2024, 5, 20, 6, 40, tzinfo=UTC),
        "owner_id": "USER-2",
    },
    {
        "id": "ACT-403",
        "customer_id": "CUST-1422",
        "customer_name": "Sita Gurung",
        "title": "Send win-back offer",
        "due_at": datetime(2024, 6, 20, 6, 0, tzinfo=UTC),
        "priority": "medium",
        "status": "snoozed",
        "last_order_at": datetime(2024, 2, 18, 9, 5, tzinfo=UTC),
        "owner_id": "USER-4",
    },
    {
        "id": "ACT-404",
        "customer_id": "CUST-1310",
        "customer_name": "Kiran Lama",
        "title": "Welcome call and onboarding",
        "due_at": datetime(2024, 6, 16, 4, 0, tzinfo=UTC),
        "priority": "low",
        "status": "open",
        "last_order_at": datetime(2024, 6, 10, 4, 20, tzinfo=UTC),
        "owner_id": "USER-1",
    },
]


class CustomersRepository:
    """Repository for customers with mock data."""

    def _resolve_owner(self, owner_id: str | None) -> dict | None:
        if not owner_id:
            return None
        for customer in _CUSTOMERS:
            owner = customer.get("owner")
            if owner and owner.get("id") == owner_id:
                return owner
        return {"id": owner_id, "name": "Owner"}

    def _generate_customer_id(self) -> str:
        return f"CUST-{uuid4().hex[:4].upper()}"

    def _build_invite(
        self,
        *,
        send: bool,
        note: str | None,
    ) -> dict:
        if not send:
            return {
                "invite_status": "not_sent",
                "invite_sent_at": None,
                "invite_accepted_at": None,
                "invite_token": None,
                "invite_expires_at": None,
                "next_action": None,
            }
        token = f"INVITE-{uuid4().hex}"
        sent_at = datetime.now(UTC)
        return {
            "invite_status": "sent",
            "invite_sent_at": sent_at,
            "invite_accepted_at": None,
            "invite_token": token,
            "invite_expires_at": sent_at + timedelta(days=1),
            "next_action": "Await portal setup",
            "invite_note": note,
        }

    def _matches_search(self, customer: dict, query: str) -> bool:
        value = query.lower()
        haystack = " ".join(
            [
                str(customer.get("id", "")),
                str(customer.get("name", "")),
                str(customer.get("email", "")),
                str(customer.get("phone", "")),
            ]
        ).lower()
        return value in haystack

    def _filter_by_date(
        self,
        customer: dict,
        *,
        before: date | None,
        after: date | None,
    ) -> bool:
        last_order = customer.get("last_order_at")
        if last_order is None:
            return False if (before or after) else True
        last_date = last_order.date()
        if before and last_date >= before:
            return False
        if after and last_date <= after:
            return False
        return True

    def _sort_customers(
        self,
        customers: list[dict],
        *,
        sort_by: str,
        sort_dir: str,
    ) -> list[dict]:
        reverse = sort_dir == "desc"

        def _key(item: dict):
            value = item.get(sort_by)
            if value is None:
                if sort_by in {"last_order_at", "created_at"}:
                    return datetime.min.replace(tzinfo=UTC)
                if sort_by in {"lifetime_value", "orders_count"}:
                    return 0
                return ""
            return value

        return sorted(customers, key=_key, reverse=reverse)

    def _status_counts(self, customers: Iterable[dict]) -> dict[str, int]:
        counts = {"active": 0, "at_risk": 0}
        for customer in customers:
            status = customer.get("status")
            if status in counts:
                counts[status] += 1
        return counts

    def _serialize_customer(self, customer: dict, *, include_notes: bool) -> dict:
        data = {
            "id": customer.get("id"),
            "name": customer.get("name"),
            "email": customer.get("email"),
            "phone": customer.get("phone"),
            "status": customer.get("status"),
            "segment": customer.get("segment"),
            "location": customer.get("location"),
            "owner": customer.get("owner"),
            "lifetime_value": customer.get("lifetime_value", 0),
            "orders_count": customer.get("orders_count", 0),
            "avg_order_value": customer.get("avg_order_value", 0),
            "last_order_at": customer.get("last_order_at"),
            "last_contact_at": customer.get("last_contact_at"),
            "next_action": customer.get("next_action"),
            "loyalty_tier": customer.get("loyalty_tier"),
            "tags": customer.get("tags", []),
            "risk_score": customer.get("risk_score", 0),
            "invite_status": customer.get("invite_status"),
        }
        if include_notes:
            data["notes"] = customer.get("notes")
        return data

    async def list_customers(
        self,
        db: AsyncSession,
        *,
        limit: int,
        offset: int,
        search: str | None,
        status: CustomerStatus | None,
        segment: CustomerSegment | None,
        owner_id: str | None,
        min_ltv: float | None,
        max_ltv: float | None,
        last_order_before: date | None,
        last_order_after: date | None,
        sort_by: str,
        sort_dir: str,
    ) -> tuple[list[dict], int, dict[str, int]]:
        filtered = []
        for customer in _CUSTOMERS:
            if search and not self._matches_search(customer, search):
                continue
            if status and customer.get("status") != status:
                continue
            if segment and customer.get("segment") != segment:
                continue
            if owner_id:
                owner = customer.get("owner") or {}
                if owner.get("id") != owner_id:
                    continue
            if min_ltv is not None and customer.get("lifetime_value", 0) < min_ltv:
                continue
            if max_ltv is not None and customer.get("lifetime_value", 0) > max_ltv:
                continue
            if not self._filter_by_date(
                customer,
                before=last_order_before,
                after=last_order_after,
            ):
                continue
            filtered.append(customer)

        total = len(filtered)
        ordered = self._sort_customers(filtered, sort_by=sort_by, sort_dir=sort_dir)
        paged = [self._serialize_customer(c, include_notes=False) for c in ordered[offset : offset + limit]]
        meta_counts = self._status_counts(filtered)
        return paged, total, meta_counts

    async def get_summary(self, db: AsyncSession) -> dict:
        total_customers = len(_CUSTOMERS)
        active_customers = len([c for c in _CUSTOMERS if c.get("status") == "active"])
        at_risk_customers = len([c for c in _CUSTOMERS if c.get("status") == "at_risk"])
        ltv_total = sum(c.get("lifetime_value", 0) for c in _CUSTOMERS)
        orders_total = sum(c.get("orders_count", 0) for c in _CUSTOMERS)
        avg_order_value = (
            (ltv_total / orders_total) if orders_total else 0
        )
        return {
            "total_customers": total_customers,
            "active_customers": active_customers,
            "at_risk_customers": at_risk_customers,
            "average_order_value": round(avg_order_value, 2),
            "ltv_total": round(ltv_total, 2),
            "retention_rate": 0.61,
        }

    async def get_spotlight(self, db: AsyncSession) -> dict:
        spotlight = max(_CUSTOMERS, key=lambda c: c.get("lifetime_value", 0))
        return {
            "customer": {
                "id": spotlight["id"],
                "name": spotlight["name"],
                "segment": spotlight["segment"],
                "loyalty_tier": spotlight.get("loyalty_tier"),
                "lifetime_value": spotlight.get("lifetime_value", 0),
                "notes": spotlight.get("notes"),
            },
            "goal_ltv": 8000.0,
            "progress_pct": 78,
        }

    async def list_actions(
        self,
        db: AsyncSession,
        *,
        limit: int,
        offset: int,
        owner_id: str | None,
        status: ActionStatus | None,
    ) -> tuple[list[dict], int]:
        filtered = []
        for action in _ACTIONS:
            if owner_id and action.get("owner_id") != owner_id:
                continue
            if status and action.get("status") != status:
                continue
            filtered.append(action)
        total = len(filtered)
        paged = filtered[offset : offset + limit]
        return paged, total

    async def get_experience(self, db: AsyncSession) -> dict:
        return {
            "metrics": [
                {"key": "on_time_delivery", "label": "On-time delivery", "value": 94},
                {"key": "response_within_4h", "label": "Response within 4 hours", "value": 88},
                {"key": "repeat_purchase_rate", "label": "Repeat purchase rate", "value": 61},
                {"key": "subscription_renewal", "label": "Subscription renewal", "value": 76},
            ]
        }

    async def get_segments(self, db: AsyncSession) -> dict:
        focus_map = {
            "VIP": "Protect high value relationships and expand share of wallet.",
            "Wholesale": "Optimize contract volume and reduce service friction.",
            "Local": "Build routine reorders and deepen local ties.",
            "Online": "Improve digital reorders and reduce churn risk.",
            "Lapsed": "Win back dormant customers with targeted offers.",
        }
        counts: dict[str, int] = {}
        for customer in _CUSTOMERS:
            segment = customer.get("segment")
            counts[segment] = counts.get(segment, 0) + 1
        items = []
        for segment, count in counts.items():
            items.append(
                {
                    "segment": segment,
                    "count": count,
                    "focus": focus_map.get(segment, ""),
                }
            )
        return {"items": items}

    async def get_opportunities(self, db: AsyncSession) -> dict:
        return {
            "upsell": [
                {"label": "Wholesale add-ons", "count": 6, "progress_pct": 62},
                {"label": "Subscription upgrades", "count": 4, "progress_pct": 48},
            ],
            "impact": [
                {"label": "Revenue protected", "value": 14600},
                {"label": "At-risk value", "value": 4820},
                {"label": "Projected retention lift", "value": "4.2"},
            ],
        }

    async def get_customer(self, db: AsyncSession, customer_id: str) -> dict | None:
        customer = self._get_customer_record(customer_id)
        if not customer:
            return None
        return self._serialize_customer(customer, include_notes=True)

    def _get_customer_record(self, customer_id: str) -> dict | None:
        for customer in _CUSTOMERS:
            if customer.get("id") == customer_id:
                return customer
        return None

    async def create_customer(
        self,
        db: AsyncSession,
        *,
        name: str,
        email: str | None,
        phone: str | None,
        location: str | None,
        segment: CustomerSegment,
        status: CustomerStatus,
        owner_id: str | None,
        next_action: str | None,
        notes: str | None,
        tags: list[str],
        invite_send: bool,
        invite_note: str | None,
    ) -> dict:
        now = datetime.now(UTC)
        invite_fields = self._build_invite(send=invite_send, note=invite_note)
        customer = {
            "id": self._generate_customer_id(),
            "name": name,
            "email": email,
            "phone": phone,
            "status": status,
            "segment": segment,
            "location": location,
            "owner": self._resolve_owner(owner_id),
            "lifetime_value": 0.0,
            "orders_count": 0,
            "avg_order_value": 0.0,
            "last_order_at": None,
            "last_contact_at": now,
            "next_action": next_action or invite_fields.get("next_action"),
            "loyalty_tier": "Starter",
            "tags": tags,
            "risk_score": 0,
            "created_at": now,
            "notes": notes,
        }
        customer.update(invite_fields)
        _CUSTOMERS.append(customer)
        return self._serialize_customer(customer, include_notes=True)

    async def send_invite(
        self,
        db: AsyncSession,
        *,
        customer_id: str,
        note: str | None,
    ) -> dict | None:
        customer = self._get_customer_record(customer_id)
        if not customer:
            return None
        invite_fields = self._build_invite(send=True, note=note)
        customer.update(invite_fields)
        return {
            "status": customer.get("invite_status", "sent"),
            "sent_at": customer.get("invite_sent_at"),
        }

    async def get_invite_status(
        self,
        db: AsyncSession,
        customer_id: str,
    ) -> dict | None:
        customer = self._get_customer_record(customer_id)
        if not customer:
            return None
        return {
            "status": customer.get("invite_status", "not_sent"),
            "sent_at": customer.get("invite_sent_at"),
            "accepted_at": customer.get("invite_accepted_at"),
        }

    async def verify_invite_token(self, db: AsyncSession, token: str) -> dict:
        now = datetime.now(UTC)
        for customer in _CUSTOMERS:
            if customer.get("invite_token") == token:
                expires_at = customer.get("invite_expires_at")
                if expires_at and expires_at < now:
                    return {"valid": False, "expires_at": expires_at, "customer_email": None}
                return {
                    "valid": True,
                    "expires_at": expires_at,
                    "customer_email": customer.get("email"),
                }
        return {"valid": False, "expires_at": None, "customer_email": None}

    async def accept_invite(
        self,
        db: AsyncSession,
        *,
        token: str,
    ) -> dict | None:
        now = datetime.now(UTC)
        for customer in _CUSTOMERS:
            if customer.get("invite_token") == token:
                expires_at = customer.get("invite_expires_at")
                if expires_at and expires_at < now:
                    return None
                customer["invite_status"] = "accepted"
                customer["invite_accepted_at"] = now
                customer["invite_token"] = None
                customer["invite_expires_at"] = None
                if customer.get("status") == "new":
                    customer["status"] = "active"
                return {"message": "Account activated", "customer_id": customer["id"]}
        return None

    async def log_contact(
        self,
        db: AsyncSession,
        *,
        customer_id: str,
        channel: str,
        note: str | None,
    ) -> dict | None:
        customer = self._get_customer_record(customer_id)
        if not customer:
            return None
        customer["last_contact_at"] = datetime.now(UTC)
        if note:
            customer["notes"] = note
        return {
            "ok": True,
            "channel": channel,
            "noted_at": customer["last_contact_at"],
        }


customers_repository = CustomersRepository()

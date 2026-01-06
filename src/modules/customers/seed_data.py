"""
Customers Seed Data
-------------------
Generated mock data for customer UI previews.
"""

from datetime import UTC, datetime, timedelta


def _owner(owner_id: str, name: str) -> dict:
    return {"id": owner_id, "name": name}


def _base_date(days_ago: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days_ago)


NAMES = [
    "Aarav Shrestha",
    "Maya Karki",
    "Rina Adhikari",
    "Suresh Rana",
    "Kunal Joshi",
    "Priyanka Thapa",
    "Bikram Tamang",
    "Elina Poudel",
    "Nishan Lama",
    "Sabin Gurung",
    "Ashmita Rai",
    "Raju Basnet",
    "Sangita Bista",
    "Prakash KC",
    "Srijana Pandey",
    "Kiran Shahi",
    "Ujjwal Koirala",
    "Sonam Sherpa",
    "Krishna Ghimire",
    "Bina Bhatt",
    "Dinesh Dhakal",
    "Shreya Luitel",
    "Bibek Rijal",
    "Alisha Sapkota",
    "Nirajan Bohara",
    "Rashmi Magar",
    "Prabin Chaudhary",
    "Sita Maharjan",
    "Rabin Shrestha",
    "Kabita Shakya",
    "Hari Rokka",
    "Deepa Acharya",
]

SEGMENTS = ["VIP", "Wholesale", "Local", "Online", "Lapsed"]
STATUSES = ["new", "active", "at_risk", "inactive"]
LOCATIONS = ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Canberra"]
OWNERS = [
    _owner("USER-1", "Nisha"),
    _owner("USER-2", "Amit"),
    _owner("USER-3", "Sasha"),
    _owner("USER-4", "Priya"),
]
TAGS = [
    ["Wholesale", "Cafe"],
    ["Local"],
    ["Online"],
    ["Retail"],
    ["VIP", "Wholesale"],
    ["Cafe", "Local"],
]


def _invite_fields(status: str, index: int) -> dict:
    if status == "new":
        sent_at = _base_date(1 + index)
        return {
            "invite_status": "sent",
            "invite_sent_at": sent_at,
            "invite_accepted_at": None,
            "invite_token": f"INVITE-{2000 + index}",
            "invite_expires_at": sent_at + timedelta(days=1),
        }
    if status == "active":
        sent_at = _base_date(30 + index)
        return {
            "invite_status": "accepted",
            "invite_sent_at": sent_at,
            "invite_accepted_at": sent_at + timedelta(hours=3),
            "invite_token": None,
            "invite_expires_at": None,
        }
    if status == "at_risk":
        sent_at = _base_date(10 + index)
        return {
            "invite_status": "sent",
            "invite_sent_at": sent_at,
            "invite_accepted_at": None,
            "invite_token": f"INVITE-{3000 + index}",
            "invite_expires_at": sent_at + timedelta(days=1),
        }
    return {
        "invite_status": "not_sent",
        "invite_sent_at": None,
        "invite_accepted_at": None,
        "invite_token": None,
        "invite_expires_at": None,
    }


def build_extra_customers() -> list[dict]:
    customers = []
    for i, name in enumerate(NAMES, start=1):
        segment = SEGMENTS[i % len(SEGMENTS)]
        status = STATUSES[i % len(STATUSES)]
        location = LOCATIONS[i % len(LOCATIONS)]
        owner = OWNERS[i % len(OWNERS)]
        orders_count = (i * 3) % 55
        lifetime_value = round(orders_count * (110 + (i % 7) * 12), 2)
        avg_order_value = round((lifetime_value / orders_count), 2) if orders_count else 0.0
        last_order_at = _base_date(2 + i) if orders_count else None
        last_contact_at = _base_date(1 + i)
        created_at = _base_date(120 + i)
        next_action = (
            "Schedule welcome call"
            if status == "new"
            else "Review retention plan" if status == "at_risk" else None
        )
        loyalty_tier = "Gold" if lifetime_value > 5000 else "Silver" if lifetime_value > 2500 else "Starter"
        tags = TAGS[i % len(TAGS)]
        risk_score = 10 + (i * 3) % 80
        customer = {
            "id": f"CUST-{1600 + i}",
            "name": name,
            "email": f"{name.lower().replace(' ', '.')}@email.com",
            "phone": f"+61 4{10 + i:02d} {300 + i:03d} {500 + i:03d}",
            "status": status,
            "segment": segment,
            "location": location,
            "owner": owner,
            "lifetime_value": lifetime_value,
            "orders_count": orders_count,
            "avg_order_value": avg_order_value,
            "last_order_at": last_order_at,
            "last_contact_at": last_contact_at,
            "next_action": next_action,
            "loyalty_tier": loyalty_tier,
            "tags": tags,
            "risk_score": risk_score,
            "created_at": created_at,
            "notes": f"{segment} customer based in {location}.",
        }
        customer.update(_invite_fields(status, i))
        customers.append(customer)
    return customers


EXTRA_CUSTOMERS = build_extra_customers()

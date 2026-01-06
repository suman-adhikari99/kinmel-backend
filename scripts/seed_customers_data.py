#!/usr/bin/env python3
"""
Generate seed data for customer UI previews.

Writes a JSON snapshot to scripts/customers_seed.json.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.modules.customers.repository import _CUSTOMERS  # noqa: E402


def _serialize(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def main() -> None:
    payload = []
    for customer in _CUSTOMERS:
        payload.append({key: _serialize(value) for key, value in customer.items()})

    output_path = ROOT / "scripts" / "customers_seed.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(payload)} customers to {output_path}")


if __name__ == "__main__":
    main()

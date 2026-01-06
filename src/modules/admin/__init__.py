"""
Admin Module
============
Administrative APIs for audit, reporting, and system management.

Endpoints:
- /admin/audit-log - Query immutable stock movement audit trail
- /admin/audit-log/export.csv - Export audit log as CSV
- /admin/audit-log/stats - Aggregated statistics

Access Control:
- All endpoints require MANAGER or ADMIN role
- Audit logs are read-only (immutable by design)
"""

from src.modules.admin.router import router

__all__ = ["router"]

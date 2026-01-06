"""
Dashboard Module
----------------
Provides aggregated dashboard statistics and metrics.
"""

from src.modules.dashboard.router import router
from src.modules.dashboard.schemas import DashboardResponse

__all__ = ["router", "DashboardResponse"]


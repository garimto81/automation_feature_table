"""Dashboard module for monitoring (PRD-0008)."""

from src.dashboard.monitoring_service import (
    Alert,
    AlertType,
    MonitoringIntegration,
    MonitoringService,
)
from src.dashboard.websocket_server import DashboardWebSocket

__all__ = [
    "DashboardWebSocket",
    "MonitoringService",
    "MonitoringIntegration",
    "Alert",
    "AlertType",
]

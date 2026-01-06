"""
Notification Dispatcher
-----------------------
Flexible notification system for alerting users about:
- Low stock conditions
- Expiring inventory
- Daily reports
- System alerts

Channels Supported:
1. Log (always enabled - for audit)
2. Email (via SMTP or transactional service)
3. Webhook (HTTP POST to external endpoint)
4. Slack (via incoming webhook)

Design Principles:
- Channel-agnostic alert creation
- Graceful degradation (log if other channels fail)
- Rate limiting to prevent alert fatigue
- Deduplication of identical alerts
"""

import hashlib
import json
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx
from redis import Redis

from src.core.config import get_settings
from src.tasks.email_tasks import send_notification_email_task
from src.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# ALERT MODELS
# ═══════════════════════════════════════════════════════════════════════════


class AlertSeverity(StrEnum):
    """Alert severity levels."""
    
    INFO = "info"          # Informational, no action required
    WARNING = "warning"    # Attention needed, not urgent
    CRITICAL = "critical"  # Immediate action required
    

class AlertCategory(StrEnum):
    """Categories of alerts for filtering/routing."""
    
    LOW_STOCK = "low_stock"
    EXPIRY = "expiry"
    OUT_OF_STOCK = "out_of_stock"
    SYSTEM = "system"
    REPORT = "report"


@dataclass
class Alert:
    """
    Represents a notification to be sent.
    
    Attributes:
        title: Short summary (used in email subject, Slack header)
        message: Detailed message body
        severity: How urgent is this?
        category: What type of alert?
        data: Structured data for rich formatting
        dedup_key: Key for deduplication (auto-generated if not provided)
    """
    
    title: str
    message: str
    severity: AlertSeverity = AlertSeverity.INFO
    category: AlertCategory = AlertCategory.SYSTEM
    data: dict[str, Any] = field(default_factory=dict)
    dedup_key: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    
    def __post_init__(self):
        if self.dedup_key is None:
            # Generate dedup key from title + category
            key_data = f"{self.category}:{self.title}"
            self.dedup_key = hashlib.md5(key_data.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "data": self.data,
            "dedup_key": self.dedup_key,
            "created_at": self.created_at.isoformat(),
        }


# ═══════════════════════════════════════════════════════════════════════════
# NOTIFICATION CHANNELS
# ═══════════════════════════════════════════════════════════════════════════


class NotificationChannel(ABC):
    """Base class for notification channels."""
    
    @abstractmethod
    def send(self, alert: Alert) -> bool:
        """
        Send an alert through this channel.
        
        Returns True if sent successfully, False otherwise.
        """
        ...
    
    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if this channel is configured and enabled."""
        ...


class LogChannel(NotificationChannel):
    """
    Log channel - always enabled for audit trail.
    
    Logs alerts using structured logging, making them
    searchable in log aggregation systems.
    """
    
    def send(self, alert: Alert) -> bool:
        log_method = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.CRITICAL: logger.error,
        }.get(alert.severity, logger.info)
        
        log_method(
            alert.title,
            alert_category=alert.category,
            alert_severity=alert.severity,
            alert_message=alert.message,
            alert_data=alert.data,
            dedup_key=alert.dedup_key,
        )
        return True
    
    def is_enabled(self) -> bool:
        return True  # Always enabled


class WebhookChannel(NotificationChannel):
    """
    Generic webhook channel.
    
    Sends alerts as JSON POST to configured endpoint.
    Compatible with most alerting systems.
    """
    
    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url
    
    def send(self, alert: Alert) -> bool:
        if not self.is_enabled():
            return False
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    self.webhook_url,  # type: ignore
                    json=alert.to_dict(),
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                
            logger.debug(
                "Webhook notification sent",
                webhook_url=self.webhook_url,
                alert_title=alert.title,
            )
            return True
            
        except httpx.HTTPError as e:
            logger.error(
                "Webhook notification failed",
                webhook_url=self.webhook_url,
                error=str(e),
            )
            return False
    
    def is_enabled(self) -> bool:
        return bool(self.webhook_url)


class SlackChannel(NotificationChannel):
    """
    Slack notification channel via incoming webhook.
    
    Formats alerts as rich Slack messages with:
    - Color-coded severity (red/yellow/green)
    - Structured fields for data
    - Links to dashboard (if configured)
    """
    
    SEVERITY_COLORS = {
        AlertSeverity.INFO: "#36a64f",      # Green
        AlertSeverity.WARNING: "#ffc107",   # Yellow
        AlertSeverity.CRITICAL: "#dc3545",  # Red
    }
    
    SEVERITY_EMOJI = {
        AlertSeverity.INFO: "ℹ️",
        AlertSeverity.WARNING: "⚠️",
        AlertSeverity.CRITICAL: "🚨",
    }
    
    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url
    
    def send(self, alert: Alert) -> bool:
        if not self.is_enabled():
            return False
        
        try:
            payload = self._format_slack_message(alert)
            
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    self.webhook_url,  # type: ignore
                    json=payload,
                )
                response.raise_for_status()
            
            logger.debug(
                "Slack notification sent",
                alert_title=alert.title,
            )
            return True
            
        except httpx.HTTPError as e:
            logger.error(
                "Slack notification failed",
                error=str(e),
            )
            return False
    
    def _format_slack_message(self, alert: Alert) -> dict[str, Any]:
        """Format alert as Slack Block Kit message."""
        emoji = self.SEVERITY_EMOJI.get(alert.severity, "ℹ️")
        color = self.SEVERITY_COLORS.get(alert.severity, "#36a64f")
        
        # Build fields from alert data
        fields = []
        for key, value in alert.data.items():
            fields.append({
                "title": key.replace("_", " ").title(),
                "value": str(value),
                "short": True,
            })
        
        return {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"{emoji} {alert.title}",
                                "emoji": True,
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": alert.message,
                            },
                        },
                    ],
                    "fields": fields,
                    "footer": f"Kinmel Inventory | {alert.category.value}",
                    "ts": int(alert.created_at.timestamp()),
                }
            ]
        }
    
    def is_enabled(self) -> bool:
        return bool(self.webhook_url)


class EmailChannel(NotificationChannel):
    """
    Email notification channel.
    
    Sends alerts via SMTP or transactional email service.
    For production, consider using SendGrid, SES, or similar.
    
    Note: This is a placeholder - implement actual SMTP logic
    or integrate with your email service provider.
    """
    
    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int = 587,
        from_email: str | None = None,
        to_emails: list[str] | None = None,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_email = from_email
        self.to_emails = to_emails or []
    
    def send(self, alert: Alert) -> bool:
        if not self.is_enabled():
            return False
        
        # TODO: Implement actual email sending
        # For now, just log that we would send an email
        logger.info(
            "Email notification (simulated)",
            to=self.to_emails,
            subject=alert.title,
            alert_category=alert.category,
        )
        
        # In production, uncomment and implement:
        # import smtplib
        # from email.message import EmailMessage
        # 
        # msg = EmailMessage()
        # msg["Subject"] = f"[{alert.severity.value.upper()}] {alert.title}"
        # msg["From"] = self.from_email
        # msg["To"] = ", ".join(self.to_emails)
        # msg.set_content(self._format_email_body(alert))
        # 
        # with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
        #     server.starttls()
        #     server.login(username, password)
        #     server.send_message(msg)
        
        return True
    
    def is_enabled(self) -> bool:
        return bool(self.smtp_host and self.from_email and self.to_emails)


# ═══════════════════════════════════════════════════════════════════════════
# NOTIFICATION DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════


class NotificationDispatcher:
    """
    Central dispatcher for all notifications.
    
    Features:
    - Multi-channel dispatch
    - Deduplication (suppress duplicate alerts within window)
    - Rate limiting per category
    - Graceful degradation (always logs, even if other channels fail)
    
    Usage:
        dispatcher = NotificationDispatcher()
        dispatcher.send(Alert(
            title="Low Stock Alert",
            message="MILK-2L is below reorder point",
            severity=AlertSeverity.WARNING,
            category=AlertCategory.LOW_STOCK,
        ))
    """
    
    # Deduplication window (don't send same alert within this period)
    DEDUP_WINDOW_SECONDS = 3600  # 1 hour
    
    # Rate limits per category (max alerts per hour)
    CATEGORY_RATE_LIMITS = {
        AlertCategory.LOW_STOCK: 20,
        AlertCategory.EXPIRY: 20,
        AlertCategory.OUT_OF_STOCK: 10,
        AlertCategory.SYSTEM: 50,
        AlertCategory.REPORT: 5,
    }
    
    def __init__(
        self,
        slack_webhook: str | None = None,
        alert_webhook: str | None = None,
        email_config: dict[str, Any] | None = None,
    ):
        self.channels: list[NotificationChannel] = [
            LogChannel(),  # Always enabled
        ]
        
        if slack_webhook:
            self.channels.append(SlackChannel(slack_webhook))
        
        if alert_webhook:
            self.channels.append(WebhookChannel(alert_webhook))
        
        if email_config:
            self.channels.append(EmailChannel(**email_config))
        
        self._redis: Redis | None = None
    
    @property
    def redis(self) -> Redis:
        """Lazy Redis connection."""
        if self._redis is None:
            self._redis = Redis.from_url(str(settings.redis_url))
        return self._redis
    
    def send(self, alert: Alert) -> dict[str, bool]:
        """
        Send alert through all enabled channels.
        
        Returns dict of channel -> success status.
        """
        # Check deduplication
        if self._is_duplicate(alert):
            logger.debug(
                "Alert suppressed (duplicate)",
                dedup_key=alert.dedup_key,
                title=alert.title,
            )
            return {"suppressed": True, "reason": "duplicate"}
        
        # Check rate limit
        if self._is_rate_limited(alert.category):
            logger.warning(
                "Alert suppressed (rate limited)",
                category=alert.category,
                title=alert.title,
            )
            return {"suppressed": True, "reason": "rate_limited"}
        
        # Send through all channels
        results: dict[str, bool] = {}
        
        for channel in self.channels:
            if channel.is_enabled():
                channel_name = type(channel).__name__
                try:
                    results[channel_name] = channel.send(alert)
                except Exception as e:
                    logger.error(
                        "Channel send failed",
                        channel=channel_name,
                        error=str(e),
                    )
                    results[channel_name] = False
        
        # Mark as sent for deduplication
        self._mark_sent(alert)
        self._increment_rate_counter(alert.category)
        
        return results
    
    def send_batch(self, alerts: list[Alert]) -> list[dict[str, bool]]:
        """Send multiple alerts."""
        return [self.send(alert) for alert in alerts]
    
    def _is_duplicate(self, alert: Alert) -> bool:
        """Check if this alert was recently sent."""
        key = f"alert_sent:{alert.dedup_key}"
        return bool(self.redis.exists(key))
    
    def _mark_sent(self, alert: Alert) -> None:
        """Mark alert as sent for deduplication."""
        key = f"alert_sent:{alert.dedup_key}"
        self.redis.setex(key, self.DEDUP_WINDOW_SECONDS, "1")
    
    def _is_rate_limited(self, category: AlertCategory) -> bool:
        """Check if category has exceeded rate limit."""
        key = f"alert_rate:{category.value}"
        count = int(self.redis.get(key) or 0)
        limit = self.CATEGORY_RATE_LIMITS.get(category, 50)
        return count >= limit
    
    def _increment_rate_counter(self, category: AlertCategory) -> None:
        """Increment rate limit counter for category."""
        key = f"alert_rate:{category.value}"
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 3600)  # Reset every hour
        pipe.execute()


# ═══════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════


# Singleton dispatcher (configure in app startup)
_dispatcher: NotificationDispatcher | None = None


def get_dispatcher() -> NotificationDispatcher:
    """Get the configured notification dispatcher."""
    global _dispatcher
    if _dispatcher is None:
        # Initialize with environment-based config
        _dispatcher = NotificationDispatcher(
            slack_webhook=getattr(settings, "slack_webhook_url", None),
            alert_webhook=getattr(settings, "alert_webhook_url", None),
        )
    return _dispatcher


def send_alert(
    title: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.INFO,
    category: AlertCategory = AlertCategory.SYSTEM,
    data: dict[str, Any] | None = None,
) -> dict[str, bool]:
    """
    Convenience function to send an alert.
    
    Usage:
        send_alert(
            "Low Stock: MILK-2L",
            "Stock is at 5 units, below reorder point of 10",
            severity=AlertSeverity.WARNING,
            category=AlertCategory.LOW_STOCK,
            data={"sku": "MILK-2L", "current": 5, "reorder_point": 10},
        )
    """
    alert = Alert(
        title=title,
        message=message,
        severity=severity,
        category=category,
        data=data or {},
    )
    results = get_dispatcher().send(alert)
    if not results.get("suppressed"):
        _record_notification(alert)
        if category in {AlertCategory.LOW_STOCK, AlertCategory.OUT_OF_STOCK}:
            text_body = f"{title}\n\n{message}"
            html_body = f"<h3>{title}</h3><p>{message.replace(chr(10), '<br>')}</p>"
            send_notification_email_task.delay(
                settings.alert_email_recipients,
                title,
                text_body,
                html_body,
            )
    return results


def _notification_type(category: AlertCategory) -> str:
    if category in {AlertCategory.LOW_STOCK, AlertCategory.OUT_OF_STOCK}:
        return "stock"
    if category == AlertCategory.REPORT:
        return "success"
    return "alert"


def _record_notification(alert: Alert) -> None:
    async def _persist() -> None:
        from src.core.database import async_session_factory
        from src.modules.notifications.service import notifications_service

        source_label = alert.data.get("source_label")
        source_href = alert.data.get("source_href")

        async with async_session_factory() as session:
            await notifications_service.create_notification(
                session,
                notif_type=_notification_type(alert.category),
                title=alert.title,
                message=alert.message,
                source_label=source_label,
                source_href=source_href,
            )
            await session.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_persist())
    finally:
        loop.close()


def send_low_stock_alert(
    sku: str,
    product_name: str,
    current_stock: int,
    reorder_point: int,
    location: str,
) -> dict[str, bool]:
    """Send a low stock alert for a specific product."""
    return send_alert(
        title=f"Low Stock: {sku}",
        message=(
            f"**{product_name}** at {location} is below reorder point.\n"
            f"Current: {current_stock} | Reorder Point: {reorder_point}"
        ),
        severity=AlertSeverity.WARNING,
        category=AlertCategory.LOW_STOCK,
        data={
            "sku": sku,
            "product_name": product_name,
            "current_stock": current_stock,
            "reorder_point": reorder_point,
            "location": location,
            "source_label": "Open inventory",
            "source_href": f"/dashboard/inventory?sku={sku}",
        },
    )


def send_expiry_alert(
    sku: str,
    product_name: str,
    batch_number: str | None,
    quantity: int,
    days_until_expiry: int,
    expiry_date: str,
) -> dict[str, bool]:
    """Send an expiry warning alert."""
    severity = (
        AlertSeverity.CRITICAL if days_until_expiry <= 1
        else AlertSeverity.WARNING
    )
    
    return send_alert(
        title=f"Expiry Alert: {sku}",
        message=(
            f"**{product_name}** (Batch: {batch_number or 'N/A'}) "
            f"expires in {days_until_expiry} day(s).\n"
            f"Quantity: {quantity} | Expiry: {expiry_date}"
        ),
        severity=severity,
        category=AlertCategory.EXPIRY,
        data={
            "sku": sku,
            "product_name": product_name,
            "batch_number": batch_number,
            "quantity": quantity,
            "days_until_expiry": days_until_expiry,
            "expiry_date": expiry_date,
            "source_label": "Open inventory",
            "source_href": f"/dashboard/inventory?sku={sku}",
        },
    )

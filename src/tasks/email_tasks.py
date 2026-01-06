"""
Email Tasks
-----------
Celery tasks for sending emails.
"""

from typing import Iterable

from src.core.config import get_settings
from src.core.email import get_email_service
from src.core.logging import get_logger
from src.tasks.celery_app import celery_app

logger = get_logger(__name__)
settings = get_settings()


@celery_app.task(name="src.tasks.email_tasks.send_otp_email")
def send_otp_email_task(to_email: str, otp: str, expires_minutes: int = 30) -> bool:
    service = get_email_service()
    if not service.is_configured():
        logger.warning("Email not configured, skipping send", to=to_email)
        return False
    logger.info("Sending OTP email", to=to_email, expires_minutes=expires_minutes)
    return service.send_otp_email(to_email=to_email, otp=otp, expires_minutes=expires_minutes)


@celery_app.task(name="src.tasks.email_tasks.send_notification_email")
def send_notification_email_task(
    to_emails: Iterable[str] | None,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> int:
    service = get_email_service()
    recipients = list(to_emails or settings.alert_email_recipients or [])
    if not recipients:
        logger.info("No alert email recipients configured; skipping notification email")
        return 0
    if not service.is_configured():
        logger.warning("Email not configured, skipping notification email")
        return 0

    sent = 0
    for email in recipients:
        if service.send_email(email, subject, html_body or text_body, text_body):
            sent += 1
    logger.info("Notification email sent", subject=subject, recipients=sent)
    return sent

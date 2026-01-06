"""
Email Service
-------------
SMTP-based email sending for OTP and notifications.
"""

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.core.config import get_settings
from src.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


class EmailService:
    """
    Simple SMTP email service.
    
    Supports Gmail, SendGrid, AWS SES, or any SMTP provider.
    """

    def __init__(self):
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_username = settings.smtp_username
        self.smtp_password = settings.smtp_password
        self.from_email = settings.email_from or settings.smtp_username

    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        return bool(
            self.smtp_host
            and self.smtp_username
            and self.smtp_password
        )

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
    ) -> bool:
        """
        Send an email via SMTP.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML content
            text_body: Plain text fallback (optional)
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured():
            logger.warning("Email not configured, skipping send")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            # Add plain text part
            if text_body:
                msg.attach(MIMEText(text_body, "plain"))

            # Add HTML part
            msg.attach(MIMEText(html_body, "html"))

            # Connect and send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.sendmail(self.from_email, to_email, msg.as_string())

            logger.info("Email sent successfully", to=to_email, subject=subject)
            return True

        except Exception as e:
            logger.error("Failed to send email", to=to_email, error=str(e))
            return False

    def send_email_with_attachment(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str | None,
        *,
        filename: str,
        content: bytes,
        mime_type: str = "text/csv",
    ) -> bool:
        """
        Send an email with a single attachment via SMTP.
        """
        if not self.is_configured():
            logger.warning("Email not configured, skipping send")
            return False

        try:
            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            alt = MIMEMultipart("alternative")
            if text_body:
                alt.attach(MIMEText(text_body, "plain"))
            alt.attach(MIMEText(html_body, "html"))
            msg.attach(alt)

            attachment = MIMEApplication(content, _subtype=mime_type.split("/")[-1])
            attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=filename,
            )
            msg.attach(attachment)

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.sendmail(self.from_email, to_email, msg.as_string())

            logger.info("Email sent successfully", to=to_email, subject=subject)
            return True
        except Exception as e:
            logger.error("Failed to send email", to=to_email, error=str(e))
            return False

    def send_otp_email(self, to_email: str, otp: str, expires_minutes: int = 30) -> bool:
        """
        Send OTP email for password change.
        
        Args:
            to_email: User's email address
            otp: The 6-digit OTP code
            expires_minutes: OTP expiry time in minutes
            
        Returns:
            True if sent successfully
        """
        subject = "Password Change OTP - Kinmel"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .otp-box {{ 
                    background: #f5f5f5; 
                    padding: 20px; 
                    text-align: center; 
                    font-size: 32px; 
                    font-weight: bold; 
                    letter-spacing: 8px;
                    margin: 20px 0;
                    border-radius: 8px;
                }}
                .warning {{ color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Password Change Request</h2>
                <p>You requested to change your password. Use the OTP below to proceed:</p>
                
                <div class="otp-box">{otp}</div>
                
                <p class="warning">
                    This OTP expires in <strong>{expires_minutes} minutes</strong>.<br>
                    If you didn't request this, please ignore this email.
                </p>
                
                <p>— Kinmel Team</p>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
Password Change Request

Your OTP code is: {otp}

This code expires in {expires_minutes} minutes.

If you didn't request this, please ignore this email.

— Kinmel Team
        """

        return self.send_email(to_email, subject, html_body, text_body)


# Singleton instance
_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    """Get the email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service

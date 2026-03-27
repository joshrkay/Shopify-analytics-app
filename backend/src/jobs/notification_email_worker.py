"""
Notification Email Worker for Story 9.1.

Background worker that processes queued notification emails:
- Picks up notifications with email_queued_at set but email_sent_at null
- Sends emails via configured email provider
- Records success/failure status

Run as a cron job or background worker:
    python -m src.jobs.notification_email_worker

Configuration:
- NOTIFICATION_EMAIL_BATCH_SIZE: Number of emails to process per batch (default: 50)
- NOTIFICATION_EMAIL_PROVIDER: Email provider (sendgrid, smtp, mock)

SECURITY:
- All operations are tenant-scoped
- No PII logged

Story 9.1 - Notification Framework (Events → Channels)
"""

import os
import sys
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid

import httpx
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.session import get_db_session_sync
from src.models.notification import (
    Notification,
    NotificationImportance,
    NotificationEventType,
)
from src.models.tenant import Tenant
from src.models.store import ShopifyStore
from src.services.email_sender import EmailMessage, EmailSender, get_email_sender


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

NOTIFICATION_EMAIL_BATCH_SIZE = int(os.getenv("NOTIFICATION_EMAIL_BATCH_SIZE", "50"))


def validate_worker_environment() -> None:
    """Validate required worker environment configuration."""
    clerk_secret = os.getenv("CLERK_SECRET_KEY", "").strip()
    if not clerk_secret:
        raise RuntimeError("CLERK_SECRET_KEY is required for notification email worker")


# Email templates by event type
EMAIL_SUBJECTS = {
    NotificationEventType.CONNECTOR_FAILED: "Action Required: Data Sync Failed",
    NotificationEventType.ACTION_REQUIRES_APPROVAL: "Action Requires Your Approval",
    NotificationEventType.INCIDENT_DECLARED: "Alert: Data Quality Incident Detected",
    NotificationEventType.ACTION_FAILED: "Action Execution Failed",
    NotificationEventType.SYNC_COMPLETED: "Data Sync Completed Successfully",
    NotificationEventType.ACTION_EXECUTED: "AI Action Executed Successfully",
    NotificationEventType.ALERT_TRIGGERED: "Alert: Metric Threshold Exceeded",
    NotificationEventType.INSIGHT_GENERATED: "New AI Insight Available",
    NotificationEventType.RECOMMENDATION_CREATED: "New AI Recommendation",
    NotificationEventType.INCIDENT_RESOLVED: "Incident Resolved",
}


def _resolve_tenant_branding(db_session, tenant_id: str) -> dict:
    """Resolve tenant branding with fallbacks: custom config -> Shopify store name -> MarkInsight."""
    branding = {}
    try:
        tenant = db_session.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant and tenant.settings:
            branding = tenant.settings.get("branding", {})

        brand_name = branding.get("brand_name") or None

        # Fallback to Shopify store name
        if not brand_name and tenant:
            store = (
                db_session.query(ShopifyStore)
                .filter(ShopifyStore.tenant_id == tenant.id)
                .first()
            )
            if store and store.shop_name:
                brand_name = store.shop_name
    except Exception as exc:
        logger.warning("Failed to resolve tenant branding", extra={"tenant_id": tenant_id, "error": str(exc)})
        brand_name = None

    return {
        "brand_name": brand_name or "MarkInsight",
        "logo_url": branding.get("logo_url") or None,
        "accent_color": branding.get("accent_color") or "#4CAF50",
        "email_footer_text": branding.get("email_footer_text") or None,
    }


def _build_email_html(notification: Notification, branding: dict | None = None) -> str:
    """Build branded HTML email body from notification."""
    brand = branding or {"brand_name": "MarkInsight", "accent_color": "#4CAF50"}
    brand_name = brand.get("brand_name", "MarkInsight")
    accent_color = brand.get("accent_color", "#4CAF50")
    logo_url = brand.get("logo_url")
    footer_text = brand.get("email_footer_text") or f"This is an automated notification from {brand_name}."

    action_link = ""
    if notification.action_url:
        base_url = os.getenv("APP_BASE_URL", "")
        if not base_url:
            logger.warning("APP_BASE_URL not set — email links will be broken")
            base_url = "https://app.example.com"
        full_url = f"{base_url}{notification.action_url}"
        action_link = f'<p><a href="{full_url}" style="display: inline-block; padding: 10px 20px; background-color: {accent_color}; color: white; text-decoration: none; border-radius: 4px;">View Details</a></p>'

    # Header: show logo if available, otherwise brand name text
    if logo_url:
        header_content = f'<img src="{logo_url}" alt="{brand_name}" style="max-height: 40px; max-width: 200px;" />'
    else:
        header_content = f'<h1 style="margin: 0; color: #212529; font-size: 20px;">{brand_name}</h1>'

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="padding: 20px; border-bottom: 3px solid {accent_color}; border-radius: 8px 8px 0 0; background-color: #f8f9fa;">
                {header_content}
            </div>
            <div style="background-color: #ffffff; padding: 20px; border: 1px solid #e9ecef; border-top: none;">
                <h2 style="margin: 0 0 12px 0; color: #212529; font-size: 18px;">{notification.title}</h2>
                <p style="margin: 0 0 16px 0; color: #495057;">{notification.message}</p>
                {action_link}
            </div>
            <div style="border: 1px solid #e9ecef; border-top: none; border-radius: 0 0 8px 8px; background-color: #f8f9fa; padding: 16px 20px;">
                <p style="margin: 0 0 4px 0; font-size: 12px; color: #6c757d;">{footer_text}</p>
                <p style="margin: 0; font-size: 12px; color: #6c757d;">You can manage your notification preferences in settings.</p>
            </div>
        </div>
    </body>
    </html>
    """


def _build_email_text(notification: Notification, branding: dict | None = None) -> str:
    """Build branded plain text email body from notification."""
    brand = branding or {"brand_name": "MarkInsight"}
    brand_name = brand.get("brand_name", "MarkInsight")
    footer_text = brand.get("email_footer_text") or f"This is an automated notification from {brand_name}."

    text = f"{notification.title}\n\n{notification.message}"
    if notification.action_url:
        base_url = os.getenv("APP_BASE_URL", "")
        if not base_url:
            logger.warning("APP_BASE_URL not set — email links will be broken")
            base_url = "https://app.example.com"
        text += f"\n\nView details: {base_url}{notification.action_url}"
    text += f"\n\n---\n{footer_text}"
    return text


class NotificationEmailWorker:
    """
    Background worker for processing notification emails.

    Processes queued emails across all tenants.
    """

    def __init__(
        self,
        db_session: Session,
        email_sender: Optional[EmailSender] = None,
    ):
        """
        Initialize notification email worker.

        Args:
            db_session: Database session
            email_sender: Email sender (optional, uses default if not provided)
        """
        self.db = db_session
        self.email_sender = email_sender or get_email_sender()
        self.clerk_secret_key = os.getenv("CLERK_SECRET_KEY", "").strip()
        self.clerk_api_base_url = os.getenv("CLERK_API_BASE_URL", "https://api.clerk.com").rstrip("/")
        self.missing_email_policy = os.getenv("NOTIFICATION_MISSING_EMAIL_POLICY", "fail").lower()
        self.run_id = str(uuid.uuid4())
        self.stats = {
            "processed": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
        }

    def _get_pending_emails(self, limit: int = 50) -> List[Notification]:
        """Get notifications pending email delivery."""
        return (
            self.db.query(Notification)
            .filter(
                Notification.importance == NotificationImportance.IMPORTANT,
                Notification.email_queued_at.isnot(None),
                Notification.email_sent_at.is_(None),
                Notification.email_failed_at.is_(None),
            )
            .order_by(Notification.email_queued_at.asc())
            .limit(limit)
            .all()
        )

    def _get_user_email(self, user_id: str) -> Optional[str]:
        """
        Get primary verified user email address from Clerk Users API.

        Returns:
            Primary verified email if available, else first verified email.
            Returns None if user not found or no verified email exists.
        """
        if not self.clerk_secret_key:
            logger.error("CLERK_SECRET_KEY missing; cannot resolve user email")
            return None

        user_url = f"{self.clerk_api_base_url}/v1/users/{user_id}"
        headers = {"Authorization": f"Bearer {self.clerk_secret_key}"}

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(user_url, headers=headers)

            if response.status_code == 404:
                logger.warning(
                    "Clerk user not found",
                    extra={"user_id": user_id},
                )
                return None

            response.raise_for_status()
            clerk_user = response.json()

            primary_email_id = clerk_user.get("primary_email_address_id")
            email_addresses = clerk_user.get("email_addresses", [])

            primary_verified_email = next(
                (
                    item.get("email_address")
                    for item in email_addresses
                    if item.get("id") == primary_email_id
                    and item.get("verification", {}).get("status") == "verified"
                    and item.get("email_address")
                ),
                None,
            )
            if primary_verified_email:
                return primary_verified_email

            return next(
                (
                    item.get("email_address")
                    for item in email_addresses
                    if item.get("verification", {}).get("status") == "verified"
                    and item.get("email_address")
                ),
                None,
            )

        except Exception as exc:
            logger.error(
                "Failed to fetch user from Clerk",
                extra={"user_id": user_id, "error": str(exc)},
            )
            return None

    async def process_notification(self, notification: Notification) -> bool:
        """
        Process a single notification email.

        Args:
            notification: Notification to send email for

        Returns:
            True if successful, False otherwise
        """
        self.stats["processed"] += 1

        if not notification.user_id:
            logger.warning(
                "No user_id for notification, skipping email",
                extra={
                    "notification_id": notification.id,
                    "tenant_id": notification.tenant_id,
                },
            )
            self.stats["skipped"] += 1
            return False

        # Get user email from Clerk Users API
        user_email = self._get_user_email(notification.user_id)

        if not user_email:
            if self.missing_email_policy == "skip":
                logger.warning(
                    "User email not found; skipping email delivery per policy",
                    extra={
                        "notification_id": notification.id,
                        "user_id": notification.user_id,
                        "policy": self.missing_email_policy,
                    },
                )
                self.stats["skipped"] += 1
                return False

            logger.warning(
                "User email not found; marking delivery as failed",
                extra={
                    "notification_id": notification.id,
                    "user_id": notification.user_id,
                    "policy": self.missing_email_policy,
                },
            )
            notification.mark_email_failed("User email not found or not verified in Clerk")
            self.stats["failed"] += 1
            return False

        try:
            # Resolve tenant branding for this notification
            branding = _resolve_tenant_branding(self.db, notification.tenant_id)
            brand_name = branding.get("brand_name", "MarkInsight")

            base_subject = EMAIL_SUBJECTS.get(
                notification.event_type,
                "New Notification"
            )
            subject = f"[{brand_name}] {base_subject}"

            message = EmailMessage(
                to_email=user_email,
                to_name=None,
                subject=subject,
                html_body=_build_email_html(notification, branding),
                text_body=_build_email_text(notification, branding),
                from_name=brand_name,
                tags=[
                    f"notification:{notification.event_type.value}",
                    f"tenant:{notification.tenant_id}",
                ],
            )

            success = await self.email_sender.send(message)

            if success:
                notification.mark_email_sent()
                self.stats["sent"] += 1
                logger.info(
                    "Notification email sent",
                    extra={
                        "notification_id": notification.id,
                        "event_type": notification.event_type.value,
                    },
                )
                return True
            else:
                notification.mark_email_failed("Email send returned False")
                self.stats["failed"] += 1
                return False

        except Exception as e:
            notification.mark_email_failed(str(e))
            self.stats["failed"] += 1
            self.stats["errors"] += 1
            logger.error(
                "Failed to send notification email",
                extra={
                    "notification_id": notification.id,
                    "error": str(e),
                },
                exc_info=True,
            )
            return False

    async def run(self) -> Dict:
        """
        Run the notification email worker.

        Processes all pending emails.

        Returns:
            Run statistics
        """
        start_time = datetime.now(timezone.utc)
        logger.info(
            "Starting notification email worker",
            extra={"run_id": self.run_id},
        )

        try:
            pending = self._get_pending_emails(limit=NOTIFICATION_EMAIL_BATCH_SIZE)
            logger.info(
                f"Found {len(pending)} pending notification emails",
                extra={"run_id": self.run_id},
            )

            for notification in pending:
                await self.process_notification(notification)
                self.db.commit()

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(
                "Notification email worker failed",
                extra={
                    "run_id": self.run_id,
                    "error": str(e),
                },
                exc_info=True,
            )

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        self.stats["duration_seconds"] = duration
        self.stats["run_id"] = self.run_id

        logger.info(
            "Notification email worker completed",
            extra={
                "run_id": self.run_id,
                "duration_seconds": duration,
                **self.stats,
            },
        )

        return self.stats


async def main():
    """Main entry point for notification email worker."""
    logger.info("Notification Email Worker starting")

    try:
        validate_worker_environment()
        for session in get_db_session_sync():
            worker = NotificationEmailWorker(session)
            stats = await worker.run()
            logger.info("Notification Email Worker stats", extra=stats)
    except Exception as e:
        logger.error("Notification Email Worker failed", extra={"error": str(e)}, exc_info=True)
        sys.exit(1)

    logger.info("Notification Email Worker finished")


if __name__ == "__main__":
    asyncio.run(main())

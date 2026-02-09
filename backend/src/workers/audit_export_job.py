"""
Async audit export worker.

Handles large exports (>10K rows) that would block the API.
Runs as a polling worker that picks up queued export jobs from the DB.

LOCKED RULES:
- Export respects tenant scoping
- Large exports do not block API
- Export attempts are audited
"""

import logging
import os
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.services.audit_exporter import AuditExporterService, ExportFormat

logger = logging.getLogger(__name__)

# Poll interval (seconds)
POLL_INTERVAL = int(os.getenv("AUDIT_EXPORT_POLL_INTERVAL", "30"))


class AuditExportJob:
    """
    Processes a single async audit export job.

    In GA scope, the job reads from the ga_audit_logs table,
    formats the output, and stores it for download.
    """

    def __init__(self, db: Session):
        self.db = db
        self._exporter = AuditExporterService(db)

    def execute(
        self,
        export_id: str,
        tenant_id: str,
        fmt: ExportFormat,
        is_super_admin: bool = False,
        event_type: str | None = None,
        dashboard_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """
        Execute an async export job.

        Args:
            export_id: Unique export identifier
            tenant_id: Tenant to scope export
            fmt: CSV or JSON
            is_super_admin: Global scope if True
            event_type: Optional event type filter
            dashboard_id: Optional dashboard filter
            start_date: Optional start date
            end_date: Optional end date

        Returns:
            Dict with export result metadata
        """
        start_time = time.monotonic()
        logger.info(
            "audit_export_job_started",
            extra={
                "export_id": export_id,
                "tenant_id": tenant_id,
                "format": fmt.value,
            },
        )

        try:
            result = self._exporter.export(
                tenant_id=tenant_id,
                fmt=fmt,
                is_super_admin=is_super_admin,
                event_type=event_type,
                dashboard_id=dashboard_id,
                start_date=start_date,
                end_date=end_date,
            )

            elapsed = time.monotonic() - start_time

            if result.success:
                logger.info(
                    "audit_export_job_completed",
                    extra={
                        "export_id": export_id,
                        "record_count": result.record_count,
                        "elapsed_seconds": round(elapsed, 2),
                    },
                )
            else:
                logger.warning(
                    "audit_export_job_failed",
                    extra={
                        "export_id": export_id,
                        "error": result.error,
                        "elapsed_seconds": round(elapsed, 2),
                    },
                )

            return {
                "export_id": export_id,
                "success": result.success,
                "record_count": result.record_count,
                "format": result.format.value,
                "elapsed_seconds": round(elapsed, 2),
                "error": result.error,
            }

        except Exception as exc:
            elapsed = time.monotonic() - start_time
            logger.error(
                "audit_export_job_exception",
                extra={
                    "export_id": export_id,
                    "error": str(exc),
                    "elapsed_seconds": round(elapsed, 2),
                },
                exc_info=True,
            )
            return {
                "export_id": export_id,
                "success": False,
                "record_count": 0,
                "format": fmt.value,
                "elapsed_seconds": round(elapsed, 2),
                "error": str(exc),
            }


class AuditExportWorker:
    """
    Polling worker that picks up and processes async export jobs.

    In the GA phase, this worker runs as a long-lived process that
    periodically checks for queued export jobs. In production, this
    would be backed by a job queue table.
    """

    def __init__(self, db_session_factory):
        self._db_session_factory = db_session_factory
        self._running = True

    def stop(self):
        """Signal the worker to stop after the current iteration."""
        self._running = False

    def run(self):
        """Main polling loop."""
        logger.info("audit_export_worker_started")
        while self._running:
            try:
                self._poll_and_process()
            except Exception:
                logger.error(
                    "audit_export_worker_poll_error",
                    exc_info=True,
                )
            time.sleep(POLL_INTERVAL)
        logger.info("audit_export_worker_stopped")

    def _poll_and_process(self):
        """
        Poll for queued export jobs and process them.

        In GA scope, this is a placeholder that demonstrates the pattern.
        Production implementation would query a job table.
        """
        # GA: No persistent job table yet.
        # This worker exists to handle the async export pattern.
        # Jobs are dispatched directly in the API layer for now.
        pass

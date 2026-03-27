"""
Async audit export worker.

Handles large exports (>10K rows) that would block the API.
Runs as a polling worker that picks up queued export jobs from the DB.

LOCKED RULES:
- Export respects tenant scoping
- Large exports do not block API
- Export attempts are audited
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.services.audit_exporter import AuditExporterService, ExportFormat

logger = logging.getLogger(__name__)

# Poll interval (seconds)
POLL_INTERVAL = int(os.getenv("AUDIT_EXPORT_POLL_INTERVAL", "30"))
MAX_RETRIES = int(os.getenv("AUDIT_EXPORT_MAX_RETRIES", "3"))
CLAIM_BATCH_SIZE = int(os.getenv("AUDIT_EXPORT_CLAIM_BATCH_SIZE", "10"))
RETRY_BACKOFF_SECONDS = int(os.getenv("AUDIT_EXPORT_RETRY_BACKOFF_SECONDS", "60"))


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
                "artifact_location": None,
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
                "artifact_location": None,
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

    def _claim_queued_jobs(self, db: Session, limit: int) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        dialect = db.bind.dialect.name if db.bind is not None else ""

        if dialect == "postgresql":
            result = db.execute(
                text(
                    """
                    WITH claimable AS (
                        SELECT id
                        FROM audit_export_jobs
                        WHERE status = 'queued'
                          AND (next_retry_at IS NULL OR next_retry_at <= :now)
                        ORDER BY created_at ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT :limit
                    )
                    UPDATE audit_export_jobs j
                    SET status = 'in_progress',
                        started_at = COALESCE(j.started_at, :now),
                        claimed_at = :now,
                        updated_at = :now
                    FROM claimable c
                    WHERE j.id = c.id
                    RETURNING
                        j.id,
                        j.tenant_id,
                        j.filters,
                        j.format,
                        j.retries,
                        j.max_retries
                    """
                ),
                {"limit": limit, "now": now},
            )
            return [dict(row._mapping) for row in result.fetchall()]

        rows = db.execute(
            text(
                """
                SELECT id, tenant_id, filters, format, retries, max_retries
                FROM audit_export_jobs
                WHERE status = 'queued'
                  AND (next_retry_at IS NULL OR next_retry_at <= :now)
                ORDER BY created_at ASC
                LIMIT :limit
                """
            ),
            {"limit": limit, "now": now},
        ).fetchall()

        claimed: list[dict[str, Any]] = []
        for row in rows:
            row_data = dict(row._mapping)
            updated = db.execute(
                text(
                    """
                    UPDATE audit_export_jobs
                    SET status = 'in_progress',
                        started_at = COALESCE(started_at, :now),
                        claimed_at = :now,
                        updated_at = :now
                    WHERE id = :job_id
                      AND status = 'queued'
                    """
                ),
                {"job_id": row_data["id"], "now": now},
            )
            if updated.rowcount:
                claimed.append(row_data)

        return claimed

    def _poll_and_process(self):
        """
        Poll for queued export jobs and process them.

        Claims queued jobs atomically, executes export, and persists
        success/failure metadata with retry handling.
        """
        now = datetime.now(timezone.utc)
        with self._db_session_factory() as db:
            jobs = self._claim_queued_jobs(db, CLAIM_BATCH_SIZE)
            if not jobs:
                db.commit()
                logger.debug("audit_export_worker_poll: no queued jobs")
                return

            executor = AuditExportJob(db)

            for job in jobs:
                filters = job.get("filters") or {}
                if isinstance(filters, str):
                    filters = json.loads(filters)

                fmt = ExportFormat(filters.get("format") or job["format"])

                result = executor.execute(
                    export_id=job["id"],
                    tenant_id=job["tenant_id"],
                    fmt=fmt,
                    is_super_admin=bool(filters.get("is_super_admin", False)),
                    event_type=filters.get("event_type"),
                    dashboard_id=filters.get("dashboard_id"),
                    start_date=filters.get("start_date"),
                    end_date=filters.get("end_date"),
                )

                if result.get("success"):
                    db.execute(
                        text(
                            """
                            UPDATE audit_export_jobs
                            SET status = 'completed',
                                completed_at = :now,
                                updated_at = :now,
                                record_count = :record_count,
                                error = NULL,
                                artifact_location = COALESCE(:artifact_location, artifact_location),
                                result_metadata = :result_metadata
                            WHERE id = :job_id
                            """
                        ),
                        {
                            "job_id": job["id"],
                            "now": now,
                            "record_count": result.get("record_count", 0),
                            "artifact_location": result.get("artifact_location"),
                            "result_metadata": json.dumps(result),
                        },
                    )
                    continue

                retries = int(job.get("retries", 0)) + 1
                max_retries = int(job.get("max_retries", MAX_RETRIES) or MAX_RETRIES)
                can_retry = retries <= max_retries

                if can_retry:
                    retry_at = now + timedelta(seconds=RETRY_BACKOFF_SECONDS * retries)
                    db.execute(
                        text(
                            """
                            UPDATE audit_export_jobs
                            SET status = 'queued',
                                retries = :retries,
                                next_retry_at = :next_retry_at,
                                error = :error,
                                updated_at = :now,
                                result_metadata = :result_metadata
                            WHERE id = :job_id
                            """
                        ),
                        {
                            "job_id": job["id"],
                            "retries": retries,
                            "next_retry_at": retry_at,
                            "error": result.get("error", "export_failed"),
                            "now": now,
                            "result_metadata": json.dumps(result),
                        },
                    )
                else:
                    db.execute(
                        text(
                            """
                            UPDATE audit_export_jobs
                            SET status = 'failed',
                                retries = :retries,
                                completed_at = :now,
                                error = :error,
                                updated_at = :now,
                                result_metadata = :result_metadata
                            WHERE id = :job_id
                            """
                        ),
                        {
                            "job_id": job["id"],
                            "retries": retries,
                            "error": result.get("error", "export_failed"),
                            "now": now,
                            "result_metadata": json.dumps(result),
                        },
                    )

            db.commit()

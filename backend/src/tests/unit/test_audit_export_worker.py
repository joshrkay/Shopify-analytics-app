from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import text

from src.workers.audit_export_job import AuditExportWorker


def _create_audit_export_jobs_table(db_session):
    db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS audit_export_jobs (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                filters TEXT NOT NULL DEFAULT '{}',
                format TEXT NOT NULL,
                retries INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                next_retry_at TIMESTAMP,
                claimed_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                artifact_location TEXT,
                record_count INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                result_metadata TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
    )
    db_session.commit()


def _insert_job(
    db_session,
    *,
    job_id: str,
    status: str = "queued",
    retries: int = 0,
    max_retries: int = 3,
):
    now = datetime.now(timezone.utc)
    db_session.execute(
        text(
            """
            INSERT INTO audit_export_jobs (
                id, tenant_id, status, filters, format, retries, max_retries,
                created_at, updated_at
            ) VALUES (
                :id, :tenant_id, :status, :filters, :format, :retries, :max_retries,
                :created_at, :updated_at
            )
            """
        ),
        {
            "id": job_id,
            "tenant_id": "tenant-1",
            "status": status,
            "filters": '{"event_type": "dashboard.viewed"}',
            "format": "csv",
            "retries": retries,
            "max_retries": max_retries,
            "created_at": now,
            "updated_at": now,
        },
    )
    db_session.commit()


def test_poll_claims_job_and_marks_completed(db_session):
    _create_audit_export_jobs_table(db_session)
    _insert_job(db_session, job_id="job-success")

    worker = AuditExportWorker(lambda: db_session)

    def _execute_side_effect(**kwargs):
        status = db_session.execute(
            text("SELECT status FROM audit_export_jobs WHERE id = :id"),
            {"id": kwargs["export_id"]},
        ).scalar_one()
        assert status == "in_progress"
        return {
            "export_id": kwargs["export_id"],
            "success": True,
            "record_count": 42,
            "format": "csv",
            "elapsed_seconds": 1.2,
            "error": None,
            "artifact_location": "s3://exports/job-success.csv",
        }

    with patch("src.workers.audit_export_job.AuditExportJob.execute", side_effect=_execute_side_effect):
        worker._poll_and_process()

    row = db_session.execute(
        text(
            """
            SELECT status, record_count, artifact_location, error, completed_at
            FROM audit_export_jobs
            WHERE id = :id
            """
        ),
        {"id": "job-success"},
    ).mappings().one()

    assert row["status"] == "completed"
    assert row["record_count"] == 42
    assert row["artifact_location"] == "s3://exports/job-success.csv"
    assert row["error"] is None
    assert row["completed_at"] is not None


def test_poll_requeues_failed_job_when_retries_remaining(db_session):
    _create_audit_export_jobs_table(db_session)
    _insert_job(db_session, job_id="job-retry", retries=1, max_retries=3)

    worker = AuditExportWorker(lambda: db_session)

    with patch(
        "src.workers.audit_export_job.AuditExportJob.execute",
        return_value={
            "export_id": "job-retry",
            "success": False,
            "record_count": 0,
            "format": "csv",
            "elapsed_seconds": 0.4,
            "error": "temporary error",
            "artifact_location": None,
        },
    ):
        worker._poll_and_process()

    row = db_session.execute(
        text(
            """
            SELECT status, retries, next_retry_at, completed_at, error
            FROM audit_export_jobs
            WHERE id = :id
            """
        ),
        {"id": "job-retry"},
    ).mappings().one()

    assert row["status"] == "queued"
    assert row["retries"] == 2
    assert row["next_retry_at"] is not None
    assert row["completed_at"] is None
    assert row["error"] == "temporary error"


def test_poll_marks_terminal_failure_after_max_retries(db_session):
    _create_audit_export_jobs_table(db_session)
    _insert_job(db_session, job_id="job-failed", retries=3, max_retries=3)

    worker = AuditExportWorker(lambda: db_session)

    with patch(
        "src.workers.audit_export_job.AuditExportJob.execute",
        return_value={
            "export_id": "job-failed",
            "success": False,
            "record_count": 0,
            "format": "json",
            "elapsed_seconds": 0.7,
            "error": "permanent error",
            "artifact_location": None,
        },
    ):
        worker._poll_and_process()

    row = db_session.execute(
        text(
            """
            SELECT status, retries, next_retry_at, completed_at, error
            FROM audit_export_jobs
            WHERE id = :id
            """
        ),
        {"id": "job-failed"},
    ).mappings().one()

    assert row["status"] == "failed"
    assert row["retries"] == 4
    assert row["next_retry_at"] is None
    assert row["completed_at"] is not None
    assert row["error"] == "permanent error"

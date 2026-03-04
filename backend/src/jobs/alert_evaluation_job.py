"""
Alert evaluation background job.

Iterates all tenants with enabled alert rules and evaluates each rule.
Per-tenant error isolation — one tenant's failure doesn't block others.
"""

import logging
from sqlalchemy import text
from src.services.alert_rule_service import AlertRuleService

logger = logging.getLogger(__name__)


class AlertEvaluationWorker:

    def __init__(self, db_session):
        self.db = db_session

    def run(self) -> dict:
        """Evaluate all enabled alert rules across all tenants."""
        stats = {"tenants": 0, "evaluated": 0, "triggered": 0, "errors": 0}

        try:
            tenant_rows = self.db.execute(text(
                "SELECT DISTINCT tenant_id FROM alert_rules WHERE enabled = true"
            )).fetchall()
        except Exception as exc:
            logger.error("Failed to query tenant list for alert evaluation: %s", exc)
            return stats

        for row in tenant_rows:
            tenant_id = row.tenant_id
            stats["tenants"] += 1
            try:
                svc = AlertRuleService(self.db, tenant_id)
                result = svc.evaluate_rules()
                stats["evaluated"] += result.get("evaluated", 0)
                stats["triggered"] += result.get("triggered", 0)
                stats["errors"] += result.get("errors", 0)
            except Exception as exc:
                stats["errors"] += 1
                logger.error(
                    "Alert evaluation failed for tenant %s: %s",
                    tenant_id, exc,
                )

        logger.info(
            "Alert evaluation complete",
            extra=stats,
        )
        return stats


def main():
    """Entry point for the alert evaluation worker."""
    from src.database.session import get_db_session_sync
    db_gen = get_db_session_sync()
    db = next(db_gen)
    try:
        worker = AlertEvaluationWorker(db)
        result = worker.run()
        logger.info("Alert evaluation finished: %s", result)
    finally:
        db.close()


if __name__ == "__main__":
    main()

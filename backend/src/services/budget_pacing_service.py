"""Budget pacing service — CRUD for budgets + spend pacing calculations."""

import calendar
import logging
import uuid
from datetime import date
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.models.ad_budget import AdBudget

logger = logging.getLogger(__name__)


class BudgetPacingService:

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def list_budgets(self) -> List[AdBudget]:
        return (
            self.db.query(AdBudget)
            .filter(AdBudget.tenant_id == self.tenant_id)
            .order_by(AdBudget.source_platform)
            .all()
        )

    def create_budget(
        self, source_platform: str, budget_monthly_cents: int,
        start_date: date, end_date: Optional[date] = None,
    ) -> AdBudget:
        budget = AdBudget(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            source_platform=source_platform,
            budget_monthly_cents=budget_monthly_cents,
            start_date=start_date,
            end_date=end_date,
        )
        self.db.add(budget)
        self.db.commit()
        self.db.refresh(budget)
        return budget

    def update_budget(self, budget_id: str, **kwargs) -> Optional[AdBudget]:
        budget = (
            self.db.query(AdBudget)
            .filter(AdBudget.id == budget_id, AdBudget.tenant_id == self.tenant_id)
            .first()
        )
        if not budget:
            return None
        for key, value in kwargs.items():
            if hasattr(budget, key):
                setattr(budget, key, value)
        self.db.commit()
        self.db.refresh(budget)
        return budget

    def delete_budget(self, budget_id: str) -> bool:
        budget = (
            self.db.query(AdBudget)
            .filter(AdBudget.id == budget_id, AdBudget.tenant_id == self.tenant_id)
            .first()
        )
        if not budget:
            return False
        self.db.delete(budget)
        self.db.commit()
        return True

    def get_pacing(self) -> list[dict]:
        """Get current month pacing data per platform.

        Queries analytics.marketing_spend which has columns:
          tenant_id, date, source_platform, spend (decimal, NOT cents)
        """
        budgets = self.list_budgets()
        if not budgets:
            return []

        # Query MTD spend per platform from marketing_spend
        # NOTE: marketing_spend.spend is in dollars (decimal), not cents
        try:
            rows = self.db.execute(text("""
                SELECT source_platform, SUM(spend) as total_spend
                FROM analytics.marketing_spend
                WHERE tenant_id = :tenant_id
                  AND date >= date_trunc('month', current_date)::date
                  AND date <= current_date
                GROUP BY source_platform
            """), {"tenant_id": self.tenant_id}).fetchall()

            # Convert spend (dollars) to cents for comparison with budget_monthly_cents
            spend_by_platform = {r.source_platform: int(float(r.total_spend) * 100) for r in rows}
        except Exception as exc:
            logger.warning("Failed to query marketing_spend: %s", exc)
            spend_by_platform = {}

        today = date.today()
        day_of_month = today.day
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        pct_time = round(day_of_month / days_in_month, 4)

        results = []
        for b in budgets:
            if not b.enabled:
                continue
            spent = spend_by_platform.get(b.source_platform, 0)
            pct_spent = round(spent / b.budget_monthly_cents, 4) if b.budget_monthly_cents > 0 else 0
            pace_ratio = round(pct_spent / pct_time, 2) if pct_time > 0 else 0
            projected = int(spent / pct_time) if pct_time > 0 else 0

            if pace_ratio <= 1.1:
                pacing_status = "on_pace"
            elif pace_ratio <= 1.3:
                pacing_status = "slightly_over"
            else:
                pacing_status = "over_budget"

            results.append({
                "platform": b.source_platform,
                "budget_cents": b.budget_monthly_cents,
                "spent_cents": spent,
                "pct_spent": pct_spent,
                "pct_time": pct_time,
                "pace_ratio": pace_ratio,
                "projected_total_cents": projected,
                "status": pacing_status,
                "budget_id": b.id,
            })

        return results

"""
Budget Pacing API — ad spend budget tracking and pacing.

Provides:
  GET    /api/budgets         — list budgets
  POST   /api/budgets         — create budget
  PUT    /api/budgets/{id}    — update budget
  DELETE /api/budgets/{id}    — delete budget
  GET    /api/budget-pacing   — current month pacing data

Queries: ad_budgets table + analytics.marketing_spend
Tenant isolation: WHERE tenant_id = :tenant_id on every query.
"""

import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.platform.tenant_context import get_tenant_context
from src.services.budget_pacing_service import BudgetPacingService
from src.api.dependencies.entitlements import check_budget_pacing_entitlement

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["budget_pacing"])


# Request/Response models
class BudgetCreate(BaseModel):
    source_platform: str
    budget_monthly_cents: int
    start_date: date
    end_date: Optional[date] = None


class BudgetUpdate(BaseModel):
    source_platform: Optional[str] = None
    budget_monthly_cents: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    enabled: Optional[bool] = None


class BudgetResponse(BaseModel):
    id: str
    source_platform: str
    budget_monthly_cents: int
    start_date: date
    end_date: Optional[date]
    enabled: bool


class PacingItem(BaseModel):
    platform: str
    budget_cents: int
    spent_cents: int
    pct_spent: float
    pct_time: float
    pace_ratio: float
    projected_total_cents: int
    status: str
    budget_id: str


class PacingResponse(BaseModel):
    pacing: List[PacingItem]


@router.get("/budgets", response_model=List[BudgetResponse])
async def list_budgets(request: Request, db: Session = Depends(check_budget_pacing_entitlement)):
    tenant_ctx = get_tenant_context(request)
    svc = BudgetPacingService(db, tenant_ctx.tenant_id)
    budgets = svc.list_budgets()
    return [
        BudgetResponse(
            id=b.id,
            source_platform=b.source_platform,
            budget_monthly_cents=b.budget_monthly_cents,
            start_date=b.start_date,
            end_date=b.end_date,
            enabled=b.enabled,
        )
        for b in budgets
    ]


@router.post("/budgets", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget(request: Request, body: BudgetCreate, db: Session = Depends(check_budget_pacing_entitlement)):
    tenant_ctx = get_tenant_context(request)
    svc = BudgetPacingService(db, tenant_ctx.tenant_id)
    budget = svc.create_budget(
        source_platform=body.source_platform,
        budget_monthly_cents=body.budget_monthly_cents,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    return BudgetResponse(
        id=budget.id,
        source_platform=budget.source_platform,
        budget_monthly_cents=budget.budget_monthly_cents,
        start_date=budget.start_date,
        end_date=budget.end_date,
        enabled=budget.enabled,
    )


@router.put("/budgets/{budget_id}", response_model=BudgetResponse)
async def update_budget(request: Request, budget_id: str, body: BudgetUpdate, db: Session = Depends(check_budget_pacing_entitlement)):
    tenant_ctx = get_tenant_context(request)
    svc = BudgetPacingService(db, tenant_ctx.tenant_id)
    updates = body.model_dump(exclude_unset=True)
    budget = svc.update_budget(budget_id, **updates)
    if not budget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return BudgetResponse(
        id=budget.id,
        source_platform=budget.source_platform,
        budget_monthly_cents=budget.budget_monthly_cents,
        start_date=budget.start_date,
        end_date=budget.end_date,
        enabled=budget.enabled,
    )


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(request: Request, budget_id: str, db: Session = Depends(check_budget_pacing_entitlement)):
    tenant_ctx = get_tenant_context(request)
    svc = BudgetPacingService(db, tenant_ctx.tenant_id)
    if not svc.delete_budget(budget_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")


@router.get("/budget-pacing", response_model=PacingResponse)
async def get_budget_pacing(request: Request, db: Session = Depends(check_budget_pacing_entitlement)):
    tenant_ctx = get_tenant_context(request)
    svc = BudgetPacingService(db, tenant_ctx.tenant_id)
    pacing = svc.get_pacing()
    return PacingResponse(pacing=[PacingItem(**p) for p in pacing])

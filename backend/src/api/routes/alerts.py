"""
Alerts API — alert rule CRUD and execution history.

Provides:
  GET    /api/alerts/rules              — list rules
  POST   /api/alerts/rules              — create rule
  PUT    /api/alerts/rules/{rule_id}    — update rule
  DELETE /api/alerts/rules/{rule_id}    — delete rule
  PATCH  /api/alerts/rules/{rule_id}/toggle — enable/disable
  GET    /api/alerts/history            — paginated execution log
  GET    /api/alerts/rules/{rule_id}/history — execution history for rule

Tenant isolation: WHERE tenant_id = :tenant_id on every query.
"""

import logging
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from src.platform.tenant_context import get_tenant_context
from src.services.alert_rule_service import AlertRuleService
from src.api.dependencies.entitlements import check_alerts_entitlement

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# Request/Response models
class AlertRuleCreate(BaseModel):
    name: str
    metric_name: str
    comparison_operator: Literal["gt", "lt", "eq", "gte", "lte"]
    threshold_value: float
    evaluation_period: Literal["daily", "weekly", "monthly"]
    severity: Literal["info", "warning", "critical"] = "warning"
    description: Optional[str] = None


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    metric_name: Optional[str] = None
    comparison_operator: Optional[Literal["gt", "lt", "eq", "gte", "lte"]] = None
    threshold_value: Optional[float] = None
    evaluation_period: Optional[Literal["daily", "weekly", "monthly"]] = None
    severity: Optional[Literal["info", "warning", "critical"]] = None
    description: Optional[str] = None


class AlertRuleToggle(BaseModel):
    enabled: bool


class AlertRuleResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    metric_name: str
    comparison_operator: str
    threshold_value: float
    evaluation_period: str
    severity: str
    enabled: bool


class AlertExecutionResponse(BaseModel):
    id: str
    alert_rule_id: str
    fired_at: datetime
    metric_value: float
    threshold_value: float
    resolved_at: Optional[datetime]


class RulesListResponse(BaseModel):
    rules: List[AlertRuleResponse]
    count: int
    limit: int


@router.get("/rules", response_model=RulesListResponse)
async def list_rules(request: Request, db=Depends(check_alerts_entitlement)):
    tenant_ctx = get_tenant_context(request)
    svc = AlertRuleService(db, tenant_ctx.tenant_id)
    rules = svc.list_rules()
    count = svc.get_rule_count()
    return RulesListResponse(
        rules=[
            AlertRuleResponse(
                id=r.id, name=r.name, description=r.description,
                metric_name=r.metric_name,
                comparison_operator=r.comparison_operator if isinstance(r.comparison_operator, str) else r.comparison_operator.value,
                threshold_value=r.threshold_value,
                evaluation_period=r.evaluation_period if isinstance(r.evaluation_period, str) else r.evaluation_period.value,
                severity=r.severity if isinstance(r.severity, str) else r.severity.value,
                enabled=r.enabled,
            )
            for r in rules
        ],
        count=count,
        limit=-1,  # Current limit from billing; -1 = unlimited
    )


@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(request: Request, body: AlertRuleCreate, db=Depends(check_alerts_entitlement)):
    tenant_ctx = get_tenant_context(request)
    svc = AlertRuleService(db, tenant_ctx.tenant_id)
    rule = svc.create_rule(
        name=body.name,
        metric_name=body.metric_name,
        comparison_operator=body.comparison_operator,
        threshold_value=body.threshold_value,
        evaluation_period=body.evaluation_period,
        severity=body.severity,
        description=body.description,
        user_id=tenant_ctx.user_id,
    )
    return AlertRuleResponse(
        id=rule.id, name=rule.name, description=rule.description,
        metric_name=rule.metric_name,
        comparison_operator=rule.comparison_operator if isinstance(rule.comparison_operator, str) else rule.comparison_operator.value,
        threshold_value=rule.threshold_value,
        evaluation_period=rule.evaluation_period if isinstance(rule.evaluation_period, str) else rule.evaluation_period.value,
        severity=rule.severity if isinstance(rule.severity, str) else rule.severity.value,
        enabled=rule.enabled,
    )


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_rule(request: Request, rule_id: str, body: AlertRuleUpdate, db=Depends(check_alerts_entitlement)):
    tenant_ctx = get_tenant_context(request)
    svc = AlertRuleService(db, tenant_ctx.tenant_id)
    updates = body.model_dump(exclude_unset=True)
    rule = svc.update_rule(rule_id, **updates)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return AlertRuleResponse(
        id=rule.id, name=rule.name, description=rule.description,
        metric_name=rule.metric_name,
        comparison_operator=rule.comparison_operator if isinstance(rule.comparison_operator, str) else rule.comparison_operator.value,
        threshold_value=rule.threshold_value,
        evaluation_period=rule.evaluation_period if isinstance(rule.evaluation_period, str) else rule.evaluation_period.value,
        severity=rule.severity if isinstance(rule.severity, str) else rule.severity.value,
        enabled=rule.enabled,
    )


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(request: Request, rule_id: str, db=Depends(check_alerts_entitlement)):
    tenant_ctx = get_tenant_context(request)
    svc = AlertRuleService(db, tenant_ctx.tenant_id)
    if not svc.delete_rule(rule_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")


@router.patch("/rules/{rule_id}/toggle", response_model=AlertRuleResponse)
async def toggle_rule(request: Request, rule_id: str, body: AlertRuleToggle, db=Depends(check_alerts_entitlement)):
    tenant_ctx = get_tenant_context(request)
    svc = AlertRuleService(db, tenant_ctx.tenant_id)
    rule = svc.toggle_rule(rule_id, body.enabled)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return AlertRuleResponse(
        id=rule.id, name=rule.name, description=rule.description,
        metric_name=rule.metric_name,
        comparison_operator=rule.comparison_operator if isinstance(rule.comparison_operator, str) else rule.comparison_operator.value,
        threshold_value=rule.threshold_value,
        evaluation_period=rule.evaluation_period if isinstance(rule.evaluation_period, str) else rule.evaluation_period.value,
        severity=rule.severity if isinstance(rule.severity, str) else rule.severity.value,
        enabled=rule.enabled,
    )


@router.get("/history", response_model=List[AlertExecutionResponse])
async def list_history(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(check_alerts_entitlement),
):
    tenant_ctx = get_tenant_context(request)
    svc = AlertRuleService(db, tenant_ctx.tenant_id)
    executions = svc.list_executions(limit=limit, offset=offset)
    return [
        AlertExecutionResponse(
            id=e.id, alert_rule_id=e.alert_rule_id,
            fired_at=e.fired_at, metric_value=e.metric_value,
            threshold_value=e.threshold_value, resolved_at=e.resolved_at,
        )
        for e in executions
    ]


@router.get("/rules/{rule_id}/history", response_model=List[AlertExecutionResponse])
async def rule_history(
    request: Request,
    rule_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(check_alerts_entitlement),
):
    tenant_ctx = get_tenant_context(request)
    svc = AlertRuleService(db, tenant_ctx.tenant_id)
    executions = svc.list_executions(rule_id=rule_id, limit=limit, offset=offset)
    return [
        AlertExecutionResponse(
            id=e.id, alert_rule_id=e.alert_rule_id,
            fired_at=e.fired_at, metric_value=e.metric_value,
            threshold_value=e.threshold_value, resolved_at=e.resolved_at,
        )
        for e in executions
    ]

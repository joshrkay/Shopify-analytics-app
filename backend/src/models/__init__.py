"""
Database models for billing, subscriptions, and entitlements.

All models follow strict tenant isolation patterns.
Tenant-scoped models inherit from TenantScopedMixin.
"""

from src.models.base import TimestampMixin, TenantScopedMixin
# Identity models (Epic 1.1)
from src.models.organization import Organization
from src.models.tenant import Tenant, TenantStatus
from src.models.user import User
from src.models.user_tenant_roles import UserTenantRole
from src.models.store import ShopifyStore
from src.models.plan import Plan, PlanFeature
from src.models.subscription import Subscription
from src.models.usage import UsageRecord, UsageAggregate
from src.models.billing_event import BillingEvent
from src.models.airbyte_connection import TenantAirbyteConnection, ConnectionStatus, ConnectionType
from src.models.backfill import BackfillExecution, BackfillStatus
from src.models.dq_models import (
    DQCheck, DQResult, DQIncident, SyncRun, BackfillJob,
    DQCheckType, DQSeverity, DQResultStatus, DQIncidentStatus,
    SyncRunStatus, ConnectorSourceType, BackfillJobStatus,
    FRESHNESS_THRESHOLDS, get_freshness_threshold, is_critical_source,
    MAX_MERCHANT_BACKFILL_DAYS,
)
from src.models.ai_insight import AIInsight, InsightType, InsightSeverity
from src.models.insight_job import InsightJob, InsightJobStatus, InsightJobCadence
from src.models.ai_recommendation import (
    AIRecommendation,
    RecommendationType,
    RecommendationPriority,
    EstimatedImpact,
    RiskLevel,
    AffectedEntityType,
)
from src.models.recommendation_job import (
    RecommendationJob,
    RecommendationJobStatus,
    RecommendationJobCadence,
)
from src.models.action_proposal import (
    ActionProposal,
    ActionType,
    ActionStatus,
    TargetPlatform,
    TargetEntityType,
    MAX_SCOPE_RULES,
    DEFAULT_PROPOSAL_TTL_DAYS,
)
from src.models.action_approval_audit import (
    ActionApprovalAudit,
    AuditAction,
)
from src.models.action_proposal_job import (
    ActionProposalJob,
    ActionProposalJobStatus,
    ActionProposalJobCadence,
)
from src.models.notification import (
    Notification,
    NotificationEventType,
    NotificationImportance,
    NotificationStatus,
    EVENT_IMPORTANCE_MAP,
)
from src.models.notification_preference import NotificationPreference
from src.models.llm_routing import (
    LLMModelRegistry,
    LLMOrgConfig,
    LLMPromptTemplate,
    LLMUsageLog,
    LLMResponseStatus,
)
from src.models.changelog_entry import (
    ChangelogEntry,
    ReleaseType,
    FEATURE_AREAS,
)
from src.models.changelog_read_status import ChangelogReadStatus
from src.models.data_change_event import (
    DataChangeEvent,
    DataChangeEventType,
    AFFECTED_METRICS,
)
from src.models.dashboard_metric_binding import DashboardMetricBinding
from src.models.data_availability import (
    DataAvailability,
    AvailabilityState,
    AvailabilityReason,
)
# region agent log
# Debug instrumentation for module resolution (Debug Mode)
# Hypotheses:
# A) backend/src is missing from sys.path during regression runs
# B) merchant_data_health.py not visible at runtime
# C) working directory impacts resolution
try:
    import json
    import os
    import sys
    import time

    # Derive repo root for CI environments (repo root = parents[3])
    from pathlib import Path

    _log_path = str(Path(__file__).resolve().parents[3] / ".cursor" / "debug.log")
    _now = int(time.time() * 1000)
    _entries = [
        {
            "sessionId": "debug-session",
            "runId": "baseline",
            "hypothesisId": "A",
            "location": "src/models/__init__.py:agent-log-1",
            "message": "sys.path snapshot",
            "data": {"sys_path": sys.path, "cwd": os.getcwd()},
            "timestamp": _now,
        },
        {
            "sessionId": "debug-session",
            "runId": "baseline",
            "hypothesisId": "B",
            "location": "src/models/__init__.py:agent-log-2",
            "message": "merchant_data_health existence",
            "data": {
                "file_exists": os.path.exists(os.path.join(os.path.dirname(__file__), "merchant_data_health.py")),
                "file_dir": os.path.dirname(__file__),
            },
            "timestamp": _now + 1,
        },
        {
            "sessionId": "debug-session",
            "runId": "baseline",
            "hypothesisId": "C",
            "location": "src/models/__init__.py:agent-log-3",
            "message": "__file__ resolution",
            "data": {
                "init_file": __file__,
                "dir_contents_sample": sorted(os.listdir(os.path.dirname(__file__)))[:10],
            },
            "timestamp": _now + 2,
        },
    ]
    with open(_log_path, "a", encoding="utf-8") as _f:
        for _e in _entries:
            _f.write(json.dumps(_e) + "\n")
except Exception:
    # Do not break imports during debugging
    pass
# endregion

from src.models.merchant_data_health import (
    MerchantHealthState,
    MerchantDataHealthResponse,
)

__all__ = [
    "TimestampMixin",
    "TenantScopedMixin",
    # Identity models (Epic 1.1)
    "Organization",
    "Tenant",
    "TenantStatus",
    "User",
    "UserTenantRole",
    "ShopifyStore",
    "Plan",
    "PlanFeature",
    "Subscription",
    "UsageRecord",
    "UsageAggregate",
    "BillingEvent",
    "TenantAirbyteConnection",
    "ConnectionStatus",
    "ConnectionType",
    "BackfillExecution",
    "BackfillStatus",
    # Data Quality models
    "DQCheck",
    "DQResult",
    "DQIncident",
    "SyncRun",
    "BackfillJob",
    "DQCheckType",
    "DQSeverity",
    "DQResultStatus",
    "DQIncidentStatus",
    "SyncRunStatus",
    "ConnectorSourceType",
    "BackfillJobStatus",
    "FRESHNESS_THRESHOLDS",
    "get_freshness_threshold",
    "is_critical_source",
    "MAX_MERCHANT_BACKFILL_DAYS",
    # AI Insight models
    "AIInsight",
    "InsightType",
    "InsightSeverity",
    "InsightJob",
    "InsightJobStatus",
    "InsightJobCadence",
    # AI Recommendation models
    "AIRecommendation",
    "RecommendationType",
    "RecommendationPriority",
    "EstimatedImpact",
    "RiskLevel",
    "AffectedEntityType",
    "RecommendationJob",
    "RecommendationJobStatus",
    "RecommendationJobCadence",
    # AI Action models (Story 8.5)
    "AIAction",
    "ActionType",
    "ActionStatus",
    "ActionTargetEntityType",
    "ActionExecutionLog",
    "ActionLogEventType",
    "ActionJob",
    "ActionJobStatus",
    # Action Proposal models (Story 8.4)
    "ActionProposal",
    "ActionType",
    "ActionStatus",
    "TargetPlatform",
    "TargetEntityType",
    "MAX_SCOPE_RULES",
    "DEFAULT_PROPOSAL_TTL_DAYS",
    "ActionApprovalAudit",
    "AuditAction",
    "ActionProposalJob",
    "ActionProposalJobStatus",
    "ActionProposalJobCadence",
    # Notification models (Story 9.1)
    "Notification",
    "NotificationEventType",
    "NotificationImportance",
    "NotificationStatus",
    "EVENT_IMPORTANCE_MAP",
    "NotificationPreference",
    # LLM Routing models (Story 8.8)
    "LLMModelRegistry",
    "LLMOrgConfig",
    "LLMPromptTemplate",
    "LLMUsageLog",
    "LLMResponseStatus",
    # Changelog models (Story 9.7)
    "ChangelogEntry",
    "ReleaseType",
    "FEATURE_AREAS",
    "ChangelogReadStatus",
    # Data Change Event models (Story 9.8)
    "DataChangeEvent",
    "DataChangeEventType",
    "AFFECTED_METRICS",
    # Dashboard Metric Binding models (Story 2.3)
    "DashboardMetricBinding",
    # Data Availability state machine
    "DataAvailability",
    "AvailabilityState",
    "AvailabilityReason",
    # Merchant Data Health (Story 4.3)
    "MerchantHealthState",
    "MerchantDataHealthResponse",
]

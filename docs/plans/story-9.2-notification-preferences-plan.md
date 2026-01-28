# Implementation Plan: Story 9.2 — Notification Preferences

**Created:** 2026-01-28
**Branch:** `claude/plan-notification-preferences-5j9hf`

---

## Executive Summary

This plan builds on the Notification Framework (Story 9.1) to implement user notification preferences. Story 9.1 already created the database schema and model for `notification_preferences`, as well as the preference lookup logic in `NotificationService._should_send_email()`. This plan focuses on the missing components: CRUD API, role-based defaults, default seeding logic, and UI-safe endpoints.

---

## Part 1: Codebase Analysis — What Already Exists

### Existing Infrastructure from Story 9.1

| Component | Location | Status |
|-----------|----------|--------|
| `notification_preferences` table | `migrations/notifications_schema.sql` | ✅ Exists |
| `NotificationPreference` model | `src/models/notification_preference.py` | ✅ Exists |
| Email preference lookup | `src/services/notification_service.py:_should_send_email()` | ✅ Exists |
| Event type enum | `src/models/notification.py:NotificationEventType` | ✅ Exists (9 types) |
| Tenant isolation | `TenantScopedMixin` | ✅ Exists |

### Existing Preference Model

```python
class NotificationPreference(Base, TimestampMixin, TenantScopedMixin):
    id = Column(String(255), primary_key=True)
    user_id = Column(String(255), nullable=True)  # NULL = tenant default
    event_type = Column(Enum(NotificationEventType), nullable=False)
    in_app_enabled = Column(Boolean, default=True)
    email_enabled = Column(Boolean, default=True)

    # Unique constraint: (tenant_id, user_id, event_type)
```

### Existing Preference Lookup Logic

```
Lookup Order (from notification_service.py):
1. User-specific preference (user_id + tenant_id + event_type)
2. Tenant default (user_id=NULL + tenant_id + event_type)
3. System default (True)
```

---

## Part 2: Gap Analysis — What's Missing

### Gaps in Original Prompt

| Gap | Description | Impact |
|-----|-------------|--------|
| No CRUD API | Only preference lookup exists, no way to create/update/delete | Users cannot manage preferences |
| No role-based defaults | Prompt mentions "merchant vs agency" but no implementation spec | Defaults won't vary by role |
| No default seeding | No logic to seed preferences for new tenants/users | New users get no preferences |
| No in_app preference check | Only `_should_send_email()` exists, no `_should_show_in_app()` | In-app notifications ignore preferences |
| No bulk operations | No way to update all preferences at once | Poor UX for preference management |
| No permission model | Who can update tenant defaults vs user preferences? | Security gap |
| No preference reset | No way to restore defaults | Poor UX |
| No API schema validation | Event types not validated | API errors |

### Additional Tasks Beyond Original Prompt

| # | Task | Why It's Needed |
|---|------|-----------------|
| 1 | Permission model for preferences | Security - who can modify what |
| 2 | In-app preference checking | Complete feature - not just email |
| 3 | Bulk preference operations | UX - update all at once |
| 4 | Preference reset to defaults | UX - restore system defaults |
| 5 | Preference migration for existing users | Data integrity |
| 6 | Unit & integration tests | Quality assurance |
| 7 | API documentation/schemas | Developer experience |

---

## Part 3: Enhanced Implementation Plan

### SECTION 1: ROLE-BASED DEFAULTS CONFIGURATION

**Create:** `src/config/notification_defaults.py`

```python
"""
Default notification preferences by role category.

Merchants: All notifications enabled (single tenant, want visibility)
Agency: Email disabled for routine events (multi-tenant, less noise)
"""

from src.constants.permissions import RoleCategory
from src.models.notification import NotificationEventType, NotificationImportance, EVENT_IMPORTANCE_MAP


# Role-based default preferences
# Key: RoleCategory
# Value: dict[event_type -> (in_app_enabled, email_enabled)]
ROLE_DEFAULT_PREFERENCES = {
    RoleCategory.MERCHANT: {
        # Merchants get all notifications by default
        NotificationEventType.CONNECTOR_FAILED: (True, True),
        NotificationEventType.ACTION_REQUIRES_APPROVAL: (True, True),
        NotificationEventType.ACTION_EXECUTED: (True, False),  # No email for routine
        NotificationEventType.ACTION_FAILED: (True, True),
        NotificationEventType.INCIDENT_DECLARED: (True, True),
        NotificationEventType.INCIDENT_RESOLVED: (True, False),
        NotificationEventType.SYNC_COMPLETED: (True, False),
        NotificationEventType.INSIGHT_GENERATED: (True, False),
        NotificationEventType.RECOMMENDATION_CREATED: (True, False),
    },
    RoleCategory.AGENCY: {
        # Agency users get fewer emails (they manage many stores)
        NotificationEventType.CONNECTOR_FAILED: (True, True),  # Always important
        NotificationEventType.ACTION_REQUIRES_APPROVAL: (True, True),  # Always important
        NotificationEventType.ACTION_EXECUTED: (True, False),
        NotificationEventType.ACTION_FAILED: (True, True),
        NotificationEventType.INCIDENT_DECLARED: (True, True),  # Always important
        NotificationEventType.INCIDENT_RESOLVED: (True, False),
        NotificationEventType.SYNC_COMPLETED: (False, False),  # Noise for agency
        NotificationEventType.INSIGHT_GENERATED: (True, False),
        NotificationEventType.RECOMMENDATION_CREATED: (True, False),
    },
    RoleCategory.PLATFORM: {
        # Platform/legacy roles - same as merchant
        NotificationEventType.CONNECTOR_FAILED: (True, True),
        NotificationEventType.ACTION_REQUIRES_APPROVAL: (True, True),
        NotificationEventType.ACTION_EXECUTED: (True, False),
        NotificationEventType.ACTION_FAILED: (True, True),
        NotificationEventType.INCIDENT_DECLARED: (True, True),
        NotificationEventType.INCIDENT_RESOLVED: (True, False),
        NotificationEventType.SYNC_COMPLETED: (True, False),
        NotificationEventType.INSIGHT_GENERATED: (True, False),
        NotificationEventType.RECOMMENDATION_CREATED: (True, False),
    },
}


def get_default_preference(
    role_category: RoleCategory,
    event_type: NotificationEventType,
) -> tuple[bool, bool]:
    """
    Get default preference for role category and event type.

    Returns:
        Tuple of (in_app_enabled, email_enabled)
    """
    role_defaults = ROLE_DEFAULT_PREFERENCES.get(
        role_category,
        ROLE_DEFAULT_PREFERENCES[RoleCategory.PLATFORM]
    )
    return role_defaults.get(event_type, (True, True))


def get_all_defaults_for_role(
    role_category: RoleCategory,
) -> dict[NotificationEventType, tuple[bool, bool]]:
    """Get all default preferences for a role category."""
    return ROLE_DEFAULT_PREFERENCES.get(
        role_category,
        ROLE_DEFAULT_PREFERENCES[RoleCategory.PLATFORM]
    )
```

---

### SECTION 2: NOTIFICATION PREFERENCE SERVICE

**Create:** `src/services/notification_preference_service.py`

```python
"""
Service for managing notification preferences.

Handles CRUD operations, role-based defaults, and seeding logic.

SECURITY:
- Users can only modify their own preferences
- Admin roles can modify tenant defaults (user_id=NULL)
- tenant_id from JWT only
"""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.models.notification_preference import NotificationPreference
from src.models.notification import NotificationEventType
from src.constants.permissions import RoleCategory, get_primary_role_category
from src.config.notification_defaults import (
    get_default_preference,
    get_all_defaults_for_role,
)


class NotificationPreferenceService:
    """
    Service for notification preference management.
    """

    def __init__(
        self,
        db_session: Session,
        tenant_id: str,
        user_id: str,
        roles: list[str],
    ):
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if not user_id:
            raise ValueError("user_id is required")

        self.db = db_session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.roles = roles
        self.role_category = get_primary_role_category(roles)

    # ─────────────────────────────────────────────────────────────────
    # READ OPERATIONS
    # ─────────────────────────────────────────────────────────────────

    def get_preferences(self) -> list[dict]:
        """
        Get all preferences for current user with defaults applied.

        Returns list of preferences for all event types, with user preferences
        taking precedence over tenant defaults over role defaults.
        """
        result = []

        # Get user preferences
        user_prefs = self._get_user_preferences()
        user_pref_map = {p.event_type: p for p in user_prefs}

        # Get tenant defaults
        tenant_defaults = self._get_tenant_defaults()
        tenant_default_map = {p.event_type: p for p in tenant_defaults}

        # Get role defaults
        role_defaults = get_all_defaults_for_role(self.role_category)

        # Build response for all event types
        for event_type in NotificationEventType:
            if event_type in user_pref_map:
                # User has explicit preference
                pref = user_pref_map[event_type]
                result.append({
                    "event_type": event_type.value,
                    "in_app_enabled": pref.in_app_enabled,
                    "email_enabled": pref.email_enabled,
                    "source": "user",
                })
            elif event_type in tenant_default_map:
                # Tenant has default
                pref = tenant_default_map[event_type]
                result.append({
                    "event_type": event_type.value,
                    "in_app_enabled": pref.in_app_enabled,
                    "email_enabled": pref.email_enabled,
                    "source": "tenant",
                })
            else:
                # Use role default
                in_app, email = role_defaults.get(event_type, (True, True))
                result.append({
                    "event_type": event_type.value,
                    "in_app_enabled": in_app,
                    "email_enabled": email,
                    "source": "default",
                })

        return result

    def get_preference(self, event_type: NotificationEventType) -> dict:
        """
        Get preference for a specific event type.

        Returns resolved preference with source indicator.
        """
        # Check user preference first
        user_pref = self._get_preference(event_type, self.user_id)
        if user_pref:
            return {
                "event_type": event_type.value,
                "in_app_enabled": user_pref.in_app_enabled,
                "email_enabled": user_pref.email_enabled,
                "source": "user",
            }

        # Check tenant default
        tenant_pref = self._get_preference(event_type, None)
        if tenant_pref:
            return {
                "event_type": event_type.value,
                "in_app_enabled": tenant_pref.in_app_enabled,
                "email_enabled": tenant_pref.email_enabled,
                "source": "tenant",
            }

        # Return role default
        in_app, email = get_default_preference(self.role_category, event_type)
        return {
            "event_type": event_type.value,
            "in_app_enabled": in_app,
            "email_enabled": email,
            "source": "default",
        }

    def get_tenant_defaults(self) -> list[dict]:
        """
        Get tenant default preferences (admin only).

        Returns tenant-level defaults, not user-specific.
        """
        tenant_defaults = self._get_tenant_defaults()
        tenant_default_map = {p.event_type: p for p in tenant_defaults}
        role_defaults = get_all_defaults_for_role(self.role_category)

        result = []
        for event_type in NotificationEventType:
            if event_type in tenant_default_map:
                pref = tenant_default_map[event_type]
                result.append({
                    "event_type": event_type.value,
                    "in_app_enabled": pref.in_app_enabled,
                    "email_enabled": pref.email_enabled,
                    "is_customized": True,
                })
            else:
                in_app, email = role_defaults.get(event_type, (True, True))
                result.append({
                    "event_type": event_type.value,
                    "in_app_enabled": in_app,
                    "email_enabled": email,
                    "is_customized": False,
                })

        return result

    # ─────────────────────────────────────────────────────────────────
    # WRITE OPERATIONS
    # ─────────────────────────────────────────────────────────────────

    def update_preference(
        self,
        event_type: NotificationEventType,
        in_app_enabled: Optional[bool] = None,
        email_enabled: Optional[bool] = None,
    ) -> dict:
        """
        Update preference for current user.

        Creates preference if it doesn't exist.
        """
        pref = self._get_preference(event_type, self.user_id)

        if pref:
            # Update existing
            if in_app_enabled is not None:
                pref.in_app_enabled = in_app_enabled
            if email_enabled is not None:
                pref.email_enabled = email_enabled
        else:
            # Get defaults to fill in missing values
            default_in_app, default_email = get_default_preference(
                self.role_category, event_type
            )

            pref = NotificationPreference(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                event_type=event_type,
                in_app_enabled=in_app_enabled if in_app_enabled is not None else default_in_app,
                email_enabled=email_enabled if email_enabled is not None else default_email,
            )
            self.db.add(pref)

        self.db.flush()

        return {
            "event_type": event_type.value,
            "in_app_enabled": pref.in_app_enabled,
            "email_enabled": pref.email_enabled,
            "source": "user",
        }

    def update_preferences_bulk(
        self,
        preferences: list[dict],
    ) -> list[dict]:
        """
        Update multiple preferences at once.

        Args:
            preferences: List of {event_type, in_app_enabled, email_enabled}

        Returns:
            Updated preferences
        """
        results = []
        for pref_data in preferences:
            event_type = NotificationEventType(pref_data["event_type"])
            result = self.update_preference(
                event_type=event_type,
                in_app_enabled=pref_data.get("in_app_enabled"),
                email_enabled=pref_data.get("email_enabled"),
            )
            results.append(result)

        return results

    def reset_preference(self, event_type: NotificationEventType) -> dict:
        """
        Reset preference for event type to default.

        Deletes user-specific preference, falling back to tenant/role default.
        """
        pref = self._get_preference(event_type, self.user_id)
        if pref:
            self.db.delete(pref)
            self.db.flush()

        # Return the effective preference after reset
        return self.get_preference(event_type)

    def reset_all_preferences(self) -> list[dict]:
        """
        Reset all user preferences to defaults.

        Deletes all user-specific preferences.
        """
        self.db.query(NotificationPreference).filter(
            NotificationPreference.tenant_id == self.tenant_id,
            NotificationPreference.user_id == self.user_id,
        ).delete(synchronize_session=False)

        self.db.flush()

        return self.get_preferences()

    # ─────────────────────────────────────────────────────────────────
    # TENANT DEFAULT OPERATIONS (Admin only)
    # ─────────────────────────────────────────────────────────────────

    def update_tenant_default(
        self,
        event_type: NotificationEventType,
        in_app_enabled: Optional[bool] = None,
        email_enabled: Optional[bool] = None,
    ) -> dict:
        """
        Update tenant default preference.

        Admin only - affects all users without explicit preferences.
        """
        pref = self._get_preference(event_type, None)  # NULL user_id = tenant default

        if pref:
            if in_app_enabled is not None:
                pref.in_app_enabled = in_app_enabled
            if email_enabled is not None:
                pref.email_enabled = email_enabled
        else:
            default_in_app, default_email = get_default_preference(
                self.role_category, event_type
            )

            pref = NotificationPreference(
                tenant_id=self.tenant_id,
                user_id=None,  # NULL = tenant default
                event_type=event_type,
                in_app_enabled=in_app_enabled if in_app_enabled is not None else default_in_app,
                email_enabled=email_enabled if email_enabled is not None else default_email,
            )
            self.db.add(pref)

        self.db.flush()

        return {
            "event_type": event_type.value,
            "in_app_enabled": pref.in_app_enabled,
            "email_enabled": pref.email_enabled,
            "is_customized": True,
        }

    def reset_tenant_default(self, event_type: NotificationEventType) -> dict:
        """
        Reset tenant default to system default.
        """
        pref = self._get_preference(event_type, None)
        if pref:
            self.db.delete(pref)
            self.db.flush()

        in_app, email = get_default_preference(self.role_category, event_type)
        return {
            "event_type": event_type.value,
            "in_app_enabled": in_app,
            "email_enabled": email,
            "is_customized": False,
        }

    # ─────────────────────────────────────────────────────────────────
    # SEEDING OPERATIONS
    # ─────────────────────────────────────────────────────────────────

    def seed_user_defaults(self) -> list[dict]:
        """
        Seed default preferences for current user based on role.

        Called when user first accesses preferences.
        Only creates if no preferences exist.
        """
        existing = self._get_user_preferences()
        if existing:
            return self.get_preferences()  # Already seeded

        role_defaults = get_all_defaults_for_role(self.role_category)

        for event_type, (in_app, email) in role_defaults.items():
            pref = NotificationPreference(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                event_type=event_type,
                in_app_enabled=in_app,
                email_enabled=email,
            )
            self.db.add(pref)

        self.db.flush()

        return self.get_preferences()

    @classmethod
    def seed_tenant_defaults(
        cls,
        db_session: Session,
        tenant_id: str,
        role_category: RoleCategory,
    ) -> None:
        """
        Seed default preferences for a tenant.

        Called during tenant onboarding.
        Creates tenant-level defaults (user_id=NULL).
        """
        role_defaults = get_all_defaults_for_role(role_category)

        for event_type, (in_app, email) in role_defaults.items():
            pref = NotificationPreference(
                tenant_id=tenant_id,
                user_id=None,  # Tenant default
                event_type=event_type,
                in_app_enabled=in_app,
                email_enabled=email,
            )
            try:
                db_session.add(pref)
                db_session.flush()
            except IntegrityError:
                db_session.rollback()  # Already exists

    # ─────────────────────────────────────────────────────────────────
    # PRIVATE HELPERS
    # ─────────────────────────────────────────────────────────────────

    def _get_preference(
        self,
        event_type: NotificationEventType,
        user_id: Optional[str],
    ) -> Optional[NotificationPreference]:
        """Get specific preference by event type and user."""
        query = self.db.query(NotificationPreference).filter(
            NotificationPreference.tenant_id == self.tenant_id,
            NotificationPreference.event_type == event_type,
        )

        if user_id is None:
            query = query.filter(NotificationPreference.user_id.is_(None))
        else:
            query = query.filter(NotificationPreference.user_id == user_id)

        return query.first()

    def _get_user_preferences(self) -> list[NotificationPreference]:
        """Get all user-specific preferences."""
        return self.db.query(NotificationPreference).filter(
            NotificationPreference.tenant_id == self.tenant_id,
            NotificationPreference.user_id == self.user_id,
        ).all()

    def _get_tenant_defaults(self) -> list[NotificationPreference]:
        """Get all tenant default preferences."""
        return self.db.query(NotificationPreference).filter(
            NotificationPreference.tenant_id == self.tenant_id,
            NotificationPreference.user_id.is_(None),
        ).all()
```

---

### SECTION 3: API SCHEMAS

**Create:** `src/api/schemas/notification_preferences.py`

```python
"""
Pydantic schemas for notification preference API.

UI-safe response models with proper typing.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field

from src.models.notification import NotificationEventType


class PreferenceBase(BaseModel):
    """Base preference fields."""
    event_type: str = Field(..., description="Event type identifier")
    in_app_enabled: bool = Field(..., description="Whether in-app notifications are enabled")
    email_enabled: bool = Field(..., description="Whether email notifications are enabled")


class PreferenceResponse(PreferenceBase):
    """Single preference response with source indicator."""
    source: Literal["user", "tenant", "default"] = Field(
        ...,
        description="Where this preference comes from"
    )


class TenantDefaultResponse(PreferenceBase):
    """Tenant default preference response."""
    is_customized: bool = Field(
        ...,
        description="Whether this differs from system default"
    )


class PreferenceListResponse(BaseModel):
    """List of preferences."""
    preferences: list[PreferenceResponse]


class TenantDefaultListResponse(BaseModel):
    """List of tenant defaults."""
    defaults: list[TenantDefaultResponse]


class PreferenceUpdateRequest(BaseModel):
    """Request to update a single preference."""
    event_type: str = Field(..., description="Event type to update")
    in_app_enabled: Optional[bool] = Field(None, description="Set in-app enabled state")
    email_enabled: Optional[bool] = Field(None, description="Set email enabled state")


class PreferenceBulkUpdateRequest(BaseModel):
    """Request to update multiple preferences."""
    preferences: list[PreferenceUpdateRequest] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="List of preferences to update"
    )


class PreferenceResetRequest(BaseModel):
    """Request to reset preference to default."""
    event_type: str = Field(..., description="Event type to reset")


# Valid event types for API validation
VALID_EVENT_TYPES = [e.value for e in NotificationEventType]


def validate_event_type(event_type: str) -> NotificationEventType:
    """Validate and convert event type string."""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event_type. Must be one of: {VALID_EVENT_TYPES}")
    return NotificationEventType(event_type)
```

---

### SECTION 4: API ENDPOINTS

**Create:** `src/api/routes/notification_preferences.py`

```python
"""
API routes for notification preference management.

Story 9.2 - Notification Preferences

ENDPOINTS:
- GET  /api/notifications/preferences           - Get all preferences
- GET  /api/notifications/preferences/{type}    - Get single preference
- PATCH /api/notifications/preferences/{type}   - Update single preference
- POST /api/notifications/preferences/bulk      - Update multiple preferences
- POST /api/notifications/preferences/reset     - Reset single preference
- POST /api/notifications/preferences/reset-all - Reset all preferences
- GET  /api/notifications/preferences/defaults  - Get tenant defaults (admin)
- PATCH /api/notifications/preferences/defaults/{type} - Update tenant default (admin)

SECURITY:
- All endpoints require authentication
- Users can only modify their own preferences
- Tenant default modification requires SETTINGS_MANAGE permission
"""

import logging
from fastapi import APIRouter, Request, HTTPException, status, Depends

from src.db import get_db
from src.platform.tenant_context import get_tenant_context
from src.platform.rbac import require_permission, has_permission
from src.constants.permissions import Permission
from src.services.notification_preference_service import NotificationPreferenceService
from src.api.schemas.notification_preferences import (
    PreferenceResponse,
    PreferenceListResponse,
    TenantDefaultResponse,
    TenantDefaultListResponse,
    PreferenceUpdateRequest,
    PreferenceBulkUpdateRequest,
    PreferenceResetRequest,
    validate_event_type,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications/preferences", tags=["notification-preferences"])


def get_preference_service(request: Request, db=Depends(get_db)) -> NotificationPreferenceService:
    """Create preference service with tenant context."""
    ctx = get_tenant_context(request)
    return NotificationPreferenceService(
        db_session=db,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        roles=ctx.roles,
    )


# ─────────────────────────────────────────────────────────────────
# USER PREFERENCE ENDPOINTS
# ─────────────────────────────────────────────────────────────────

@router.get("", response_model=PreferenceListResponse)
async def get_preferences(
    request: Request,
    service: NotificationPreferenceService = Depends(get_preference_service),
):
    """
    Get all notification preferences for current user.

    Returns preferences for all event types, with source indicator
    showing whether preference is user-specific, tenant default, or system default.
    """
    preferences = service.get_preferences()
    return PreferenceListResponse(preferences=preferences)


@router.get("/{event_type}", response_model=PreferenceResponse)
async def get_preference(
    event_type: str,
    request: Request,
    service: NotificationPreferenceService = Depends(get_preference_service),
):
    """
    Get preference for a specific event type.
    """
    try:
        validated_type = validate_event_type(event_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return service.get_preference(validated_type)


@router.patch("/{event_type}", response_model=PreferenceResponse)
async def update_preference(
    event_type: str,
    body: PreferenceUpdateRequest,
    request: Request,
    service: NotificationPreferenceService = Depends(get_preference_service),
):
    """
    Update preference for a specific event type.

    Only updates fields that are provided (partial update).
    """
    try:
        validated_type = validate_event_type(event_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = service.update_preference(
        event_type=validated_type,
        in_app_enabled=body.in_app_enabled,
        email_enabled=body.email_enabled,
    )

    ctx = get_tenant_context(request)
    logger.info(
        "Preference updated",
        extra={
            "tenant_id": ctx.tenant_id,
            "user_id": ctx.user_id,
            "event_type": event_type,
        },
    )

    return PreferenceResponse(**result)


@router.post("/bulk", response_model=PreferenceListResponse)
async def update_preferences_bulk(
    body: PreferenceBulkUpdateRequest,
    request: Request,
    service: NotificationPreferenceService = Depends(get_preference_service),
):
    """
    Update multiple preferences at once.
    """
    # Validate all event types first
    for pref in body.preferences:
        try:
            validate_event_type(pref.event_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    results = service.update_preferences_bulk(
        [p.model_dump() for p in body.preferences]
    )

    ctx = get_tenant_context(request)
    logger.info(
        "Preferences updated in bulk",
        extra={
            "tenant_id": ctx.tenant_id,
            "user_id": ctx.user_id,
            "count": len(results),
        },
    )

    return PreferenceListResponse(preferences=results)


@router.post("/reset", response_model=PreferenceResponse)
async def reset_preference(
    body: PreferenceResetRequest,
    request: Request,
    service: NotificationPreferenceService = Depends(get_preference_service),
):
    """
    Reset a single preference to default.

    Removes user-specific preference, falling back to tenant or system default.
    """
    try:
        validated_type = validate_event_type(body.event_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = service.reset_preference(validated_type)

    ctx = get_tenant_context(request)
    logger.info(
        "Preference reset",
        extra={
            "tenant_id": ctx.tenant_id,
            "user_id": ctx.user_id,
            "event_type": body.event_type,
        },
    )

    return PreferenceResponse(**result)


@router.post("/reset-all", response_model=PreferenceListResponse)
async def reset_all_preferences(
    request: Request,
    service: NotificationPreferenceService = Depends(get_preference_service),
):
    """
    Reset all user preferences to defaults.

    Removes all user-specific preferences.
    """
    results = service.reset_all_preferences()

    ctx = get_tenant_context(request)
    logger.info(
        "All preferences reset",
        extra={
            "tenant_id": ctx.tenant_id,
            "user_id": ctx.user_id,
        },
    )

    return PreferenceListResponse(preferences=results)


# ─────────────────────────────────────────────────────────────────
# TENANT DEFAULT ENDPOINTS (Admin only)
# ─────────────────────────────────────────────────────────────────

@router.get("/defaults", response_model=TenantDefaultListResponse)
@require_permission(Permission.SETTINGS_MANAGE)
async def get_tenant_defaults(
    request: Request,
    service: NotificationPreferenceService = Depends(get_preference_service),
):
    """
    Get tenant default preferences.

    Requires SETTINGS_MANAGE permission.
    Returns defaults that apply to all users without explicit preferences.
    """
    defaults = service.get_tenant_defaults()
    return TenantDefaultListResponse(defaults=defaults)


@router.patch("/defaults/{event_type}", response_model=TenantDefaultResponse)
@require_permission(Permission.SETTINGS_MANAGE)
async def update_tenant_default(
    event_type: str,
    body: PreferenceUpdateRequest,
    request: Request,
    service: NotificationPreferenceService = Depends(get_preference_service),
):
    """
    Update tenant default preference.

    Requires SETTINGS_MANAGE permission.
    Affects all users without explicit preferences for this event type.
    """
    try:
        validated_type = validate_event_type(event_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = service.update_tenant_default(
        event_type=validated_type,
        in_app_enabled=body.in_app_enabled,
        email_enabled=body.email_enabled,
    )

    ctx = get_tenant_context(request)
    logger.info(
        "Tenant default updated",
        extra={
            "tenant_id": ctx.tenant_id,
            "user_id": ctx.user_id,
            "event_type": event_type,
        },
    )

    return TenantDefaultResponse(**result)


@router.post("/defaults/{event_type}/reset", response_model=TenantDefaultResponse)
@require_permission(Permission.SETTINGS_MANAGE)
async def reset_tenant_default(
    event_type: str,
    request: Request,
    service: NotificationPreferenceService = Depends(get_preference_service),
):
    """
    Reset tenant default to system default.

    Requires SETTINGS_MANAGE permission.
    """
    try:
        validated_type = validate_event_type(event_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = service.reset_tenant_default(validated_type)

    ctx = get_tenant_context(request)
    logger.info(
        "Tenant default reset",
        extra={
            "tenant_id": ctx.tenant_id,
            "user_id": ctx.user_id,
            "event_type": event_type,
        },
    )

    return TenantDefaultResponse(**result)
```

---

### SECTION 5: UPDATE NOTIFICATION SERVICE

**Update:** `src/services/notification_service.py`

Add in-app preference checking alongside email preference checking:

```python
# Add method for in-app preference checking
def _should_show_in_app(
    self,
    event_type: NotificationEventType,
    user_id: Optional[str],
) -> bool:
    """
    Check if notification should be shown in-app based on preferences.

    Args:
        event_type: Event type to check
        user_id: User to check preferences for

    Returns:
        True if in-app notification should be shown
    """
    # First check user-specific preference
    if user_id:
        pref = (
            self.db.query(NotificationPreference)
            .filter(
                NotificationPreference.tenant_id == self.tenant_id,
                NotificationPreference.user_id == user_id,
                NotificationPreference.event_type == event_type,
            )
            .first()
        )
        if pref:
            return pref.in_app_enabled

    # Check tenant default (user_id is NULL)
    tenant_pref = (
        self.db.query(NotificationPreference)
        .filter(
            NotificationPreference.tenant_id == self.tenant_id,
            NotificationPreference.user_id.is_(None),
            NotificationPreference.event_type == event_type,
        )
        .first()
    )

    if tenant_pref:
        return tenant_pref.in_app_enabled

    # Default: show in-app notifications
    return True


# Update notify() method to check in-app preferences:
def notify(self, ...):
    # ... existing code ...

    # Check if user has disabled in-app for this event
    if not self._should_show_in_app(event_type, user_id):
        logger.info(
            "In-app notification skipped per preferences",
            extra={
                "tenant_id": self.tenant_id,
                "event_type": event_type.value,
                "user_id": user_id,
            },
        )
        # Still create record for audit but don't mark as delivered
        # Or skip entirely based on business requirements
        pass

    # ... rest of method ...
```

---

### SECTION 6: REGISTER ROUTES

**Update:** `backend/main.py`

```python
# Add import
from src.api.routes.notification_preferences import router as notification_preferences_router

# Add router registration
app.include_router(notification_preferences_router)
```

---

### SECTION 7: TESTING REQUIREMENTS

**Create tests in:** `backend/src/tests/`

#### Unit Tests

**File:** `tests/unit/test_notification_preference_service.py`

```python
"""
Unit tests for NotificationPreferenceService.

Story 9.2 - Notification Preferences
"""

import pytest
from unittest.mock import MagicMock, patch

from src.services.notification_preference_service import NotificationPreferenceService
from src.models.notification import NotificationEventType
from src.constants.permissions import RoleCategory


class TestNotificationPreferenceService:
    """Tests for preference service."""

    def test_init_requires_tenant_id(self):
        """Service requires tenant_id."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            NotificationPreferenceService(
                db_session=MagicMock(),
                tenant_id="",
                user_id="user-123",
                roles=["merchant_admin"],
            )

    def test_init_requires_user_id(self):
        """Service requires user_id."""
        with pytest.raises(ValueError, match="user_id is required"):
            NotificationPreferenceService(
                db_session=MagicMock(),
                tenant_id="tenant-123",
                user_id="",
                roles=["merchant_admin"],
            )

    def test_get_preferences_returns_all_event_types(self):
        """get_preferences returns entry for every event type."""
        # ... test implementation

    def test_get_preferences_user_overrides_tenant(self):
        """User preferences take precedence over tenant defaults."""
        # ... test implementation

    def test_get_preferences_tenant_overrides_role(self):
        """Tenant defaults take precedence over role defaults."""
        # ... test implementation

    def test_update_preference_creates_if_not_exists(self):
        """update_preference creates new preference if none exists."""
        # ... test implementation

    def test_update_preference_partial_update(self):
        """update_preference only updates provided fields."""
        # ... test implementation

    def test_reset_preference_removes_user_pref(self):
        """reset_preference deletes user-specific preference."""
        # ... test implementation

    def test_role_defaults_merchant_vs_agency(self):
        """Different defaults for merchant vs agency roles."""
        # ... test implementation
```

**File:** `tests/unit/test_notification_defaults.py`

```python
"""
Unit tests for notification default configuration.

Story 9.2 - Notification Preferences
"""

import pytest

from src.config.notification_defaults import (
    get_default_preference,
    get_all_defaults_for_role,
    ROLE_DEFAULT_PREFERENCES,
)
from src.models.notification import NotificationEventType
from src.constants.permissions import RoleCategory


class TestNotificationDefaults:
    """Tests for default configuration."""

    def test_all_event_types_have_defaults(self):
        """Every event type has a default for every role category."""
        for role_cat in RoleCategory:
            for event_type in NotificationEventType:
                in_app, email = get_default_preference(role_cat, event_type)
                assert isinstance(in_app, bool)
                assert isinstance(email, bool)

    def test_important_events_email_enabled_by_default(self):
        """Important events have email enabled by default."""
        important_events = [
            NotificationEventType.CONNECTOR_FAILED,
            NotificationEventType.ACTION_REQUIRES_APPROVAL,
            NotificationEventType.ACTION_FAILED,
            NotificationEventType.INCIDENT_DECLARED,
        ]

        for event_type in important_events:
            for role_cat in RoleCategory:
                _, email = get_default_preference(role_cat, event_type)
                assert email is True, f"{event_type} should have email enabled for {role_cat}"

    def test_agency_has_sync_completed_disabled(self):
        """Agency users have sync_completed disabled (too much noise)."""
        in_app, email = get_default_preference(
            RoleCategory.AGENCY,
            NotificationEventType.SYNC_COMPLETED
        )
        assert in_app is False
        assert email is False
```

#### Integration Tests

**File:** `tests/integration/test_notification_preferences_api.py`

```python
"""
Integration tests for notification preferences API.

Story 9.2 - Notification Preferences
"""

import pytest
from fastapi.testclient import TestClient


class TestNotificationPreferencesAPI:
    """Integration tests for preference endpoints."""

    def test_get_preferences_returns_all_types(self, client, auth_headers):
        """GET /preferences returns all event types."""
        response = client.get(
            "/api/notifications/preferences",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "preferences" in data
        assert len(data["preferences"]) == 9  # All event types

    def test_update_preference_persists(self, client, auth_headers):
        """PATCH /preferences/{type} persists change."""
        # Update
        response = client.patch(
            "/api/notifications/preferences/connector_failed",
            json={"email_enabled": False},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["email_enabled"] is False

        # Verify persisted
        response = client.get(
            "/api/notifications/preferences/connector_failed",
            headers=auth_headers,
        )
        assert response.json()["email_enabled"] is False

    def test_reset_preference_removes_customization(self, client, auth_headers):
        """POST /preferences/reset removes user customization."""
        # ... test implementation

    def test_tenant_defaults_require_permission(self, client, viewer_auth_headers):
        """Tenant default endpoints require SETTINGS_MANAGE."""
        response = client.get(
            "/api/notifications/preferences/defaults",
            headers=viewer_auth_headers,
        )
        assert response.status_code == 403

    def test_invalid_event_type_returns_400(self, client, auth_headers):
        """Invalid event type returns 400."""
        response = client.patch(
            "/api/notifications/preferences/invalid_type",
            json={"email_enabled": False},
            headers=auth_headers,
        )
        assert response.status_code == 400
```

---

### SECTION 8: IMPLEMENTATION ORDER

1. **Create configuration** (`src/config/notification_defaults.py`)
   - Define role-based defaults
   - Helper functions for default lookup

2. **Create service** (`src/services/notification_preference_service.py`)
   - CRUD operations
   - Role-based default resolution
   - Seeding logic

3. **Create API schemas** (`src/api/schemas/notification_preferences.py`)
   - Request/response models
   - Validation helpers

4. **Create API routes** (`src/api/routes/notification_preferences.py`)
   - User preference endpoints
   - Tenant default endpoints (admin)

5. **Update notification service** (`src/services/notification_service.py`)
   - Add `_should_show_in_app()` method
   - Update `notify()` to check in-app preferences

6. **Register routes** (`backend/main.py`)
   - Include router

7. **Write unit tests**
   - Service tests
   - Default config tests

8. **Write integration tests**
   - API endpoint tests

---

## Part 4: Summary of Additional Tasks

### Tasks Beyond Original Prompt

| # | Task | Why It's Needed |
|---|------|-----------------|
| 1 | Permission model (SETTINGS_MANAGE for tenant defaults) | Security |
| 2 | In-app preference checking (`_should_show_in_app`) | Feature completeness |
| 3 | Bulk preference update endpoint | UX |
| 4 | Preference reset endpoints | UX |
| 5 | Source indicator in responses (`user`/`tenant`/`default`) | UI clarity |
| 6 | Event type validation | API robustness |
| 7 | Pydantic schemas for UI-safe API | Developer experience |
| 8 | Comprehensive unit/integration tests | Quality assurance |

### Original vs Enhanced Requirements

| Original Requirement | Enhanced Implementation |
|---------------------|------------------------|
| Per event type | All 9 event types covered |
| Per channel (in-app, email) | Both channels with preference checking |
| Role-based defaults (merchant vs agency) | 3 role categories with different defaults |
| UI-safe API | Pydantic schemas, proper HTTP status codes, validation |
| Preferences table | Already exists from Story 9.1 |
| CRUD API | Full CRUD + bulk + reset operations |
| Default seeding logic | `seed_user_defaults()` and `seed_tenant_defaults()` |

---

## Part 5: File Inventory

### New Files to Create

| File | Purpose |
|------|---------|
| `src/config/notification_defaults.py` | Role-based default configuration |
| `src/services/notification_preference_service.py` | Preference management service |
| `src/api/schemas/notification_preferences.py` | API request/response models |
| `src/api/routes/notification_preferences.py` | API endpoints |
| `tests/unit/test_notification_preference_service.py` | Service unit tests |
| `tests/unit/test_notification_defaults.py` | Config unit tests |
| `tests/integration/test_notification_preferences_api.py` | API integration tests |

### Existing Files to Update

| File | Changes |
|------|---------|
| `src/services/notification_service.py` | Add `_should_show_in_app()` |
| `backend/main.py` | Register new router |

---

## Part 6: Acceptance Criteria Mapping

| Acceptance Criteria | Implementation |
|---------------------|----------------|
| Users can enable/disable per event + channel | CRUD API with `in_app_enabled` and `email_enabled` |
| Defaults applied correctly | Role-based defaults in `notification_defaults.py`, cascade: user > tenant > role default |
| Preferences respected by notification engine | `_should_send_email()` (exists) + `_should_show_in_app()` (new) |

---

## Part 7: Dependencies

```
Story 9.1 (Notification Framework)
─────────────────────────────────
        │
        ├── notification_preferences table ──┐
        │                                    │
        ├── NotificationPreference model ────┼──► Story 9.2 (Preferences)
        │                                    │
        └── _should_send_email() ────────────┘
```

**Story 9.2 depends on Story 9.1 being complete (which it is).**

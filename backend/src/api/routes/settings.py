"""Settings routes for API key management and AI insights configuration."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.constants.permissions import Permission
from src.database.session import get_db_session
from src.models.api_key import ApiKey
from src.models.tenant import Tenant
from src.platform.rbac import check_permission_or_raise
from src.platform.tenant_context import get_tenant_context
from src.services.billing_entitlements import BillingEntitlementsService, BillingFeature
from src.models.store import ShopifyStore
from src.api.schemas.settings import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeySummary,
    AiInsightsSettings,
    AiInsightsSettingsResponse,
    BrandingSettings,
    BrandingSettingsResponse,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _to_api_key_summary(record: ApiKey) -> ApiKeySummary:
    return ApiKeySummary(
        id=record.id,
        name=record.name,
        key_prefix=record.key_prefix,
        created_at=record.created_at,
        last_used_at=record.last_used_at,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
        is_active=record.is_active,
    )


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(request: Request, db_session=Depends(get_db_session)):
    tenant_ctx = get_tenant_context(request)
    check_permission_or_raise(tenant_ctx, Permission.SETTINGS_MANAGE, request)

    keys = (
        db_session.query(ApiKey)
        .filter(ApiKey.tenant_id == tenant_ctx.tenant_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )

    return ApiKeyListResponse(keys=[_to_api_key_summary(key) for key in keys])


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: Request,
    payload: ApiKeyCreateRequest,
    db_session=Depends(get_db_session),
):
    tenant_ctx = get_tenant_context(request)
    check_permission_or_raise(tenant_ctx, Permission.SETTINGS_MANAGE, request)

    raw_key = f"mi_{secrets.token_urlsafe(32)}"
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None

    api_key = ApiKey(
        tenant_id=tenant_ctx.tenant_id,
        name=payload.name,
        key_prefix=raw_key[:12],
        key_hash=_hash_key(raw_key),
        created_by_user_id=tenant_ctx.user_id,
        expires_at=expires_at,
        is_active=True,
    )
    db_session.add(api_key)
    db_session.commit()
    db_session.refresh(api_key)

    return ApiKeyCreateResponse(
        key=_to_api_key_summary(api_key),
        plaintext_key=raw_key,
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(key_id: str, request: Request, db_session=Depends(get_db_session)):
    tenant_ctx = get_tenant_context(request)
    check_permission_or_raise(tenant_ctx, Permission.SETTINGS_MANAGE, request)

    api_key = (
        db_session.query(ApiKey)
        .filter(ApiKey.id == key_id, ApiKey.tenant_id == tenant_ctx.tenant_id)
        .first()
    )

    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    api_key.is_active = False
    api_key.revoked_at = datetime.now(UTC)
    db_session.commit()


@router.get("/ai-insights", response_model=AiInsightsSettingsResponse)
async def get_ai_settings(request: Request, db_session=Depends(get_db_session)):
    tenant_ctx = get_tenant_context(request)
    check_permission_or_raise(tenant_ctx, Permission.AI_CONFIG_MANAGE, request)

    tenant = db_session.query(Tenant).filter(Tenant.id == tenant_ctx.tenant_id).first()
    settings = (tenant.settings or {}).get("ai_insights_settings", {}) if tenant else {}

    entitlement_result = BillingEntitlementsService(db_session, tenant_ctx.tenant_id).check_feature_entitlement(
        BillingFeature.AI_INSIGHTS
    )

    return AiInsightsSettingsResponse(
        settings=AiInsightsSettings(**settings),
        entitled=entitlement_result.is_entitled,
        entitlement_reason=entitlement_result.reason,
    )


@router.put("/ai-insights", response_model=AiInsightsSettingsResponse)
async def update_ai_settings(
    payload: AiInsightsSettings,
    request: Request,
    db_session=Depends(get_db_session),
):
    tenant_ctx = get_tenant_context(request)
    check_permission_or_raise(tenant_ctx, Permission.AI_CONFIG_MANAGE, request)

    entitlement_result = BillingEntitlementsService(db_session, tenant_ctx.tenant_id).check_feature_entitlement(
        BillingFeature.AI_INSIGHTS
    )
    if not entitlement_result.is_entitled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=entitlement_result.reason or "Current plan does not include AI Insights.",
        )

    tenant = db_session.query(Tenant).filter(Tenant.id == tenant_ctx.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    current_settings = tenant.settings or {}
    current_settings["ai_insights_settings"] = payload.model_dump()
    tenant.settings = current_settings
    db_session.commit()

    return AiInsightsSettingsResponse(
        settings=payload,
        entitled=True,
        entitlement_reason=None,
    )


def _resolve_branding(tenant: Tenant | None, db_session) -> BrandingSettingsResponse:
    """Resolve branding with fallbacks: custom config -> Shopify store name -> MarkInsight."""
    branding = {}
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

    return BrandingSettingsResponse(
        brand_name=brand_name or "MarkInsight",
        logo_url=branding.get("logo_url") or None,
        accent_color=branding.get("accent_color") or "#4CAF50",
        email_footer_text=branding.get("email_footer_text") or None,
    )


@router.get("/branding", response_model=BrandingSettingsResponse)
async def get_branding_settings(request: Request, db_session=Depends(get_db_session)):
    """Get tenant branding configuration with smart fallbacks."""
    tenant_ctx = get_tenant_context(request)

    tenant = db_session.query(Tenant).filter(Tenant.id == tenant_ctx.tenant_id).first()
    return _resolve_branding(tenant, db_session)


@router.put("/branding", response_model=BrandingSettingsResponse)
async def update_branding_settings(
    payload: BrandingSettings,
    request: Request,
    db_session=Depends(get_db_session),
):
    """Update tenant branding configuration."""
    tenant_ctx = get_tenant_context(request)

    tenant = db_session.query(Tenant).filter(Tenant.id == tenant_ctx.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    current_settings = tenant.settings or {}
    current_settings["branding"] = {
        k: v for k, v in payload.model_dump().items() if v is not None
    }
    tenant.settings = current_settings
    db_session.commit()

    return _resolve_branding(tenant, db_session)

"""
Shopify OAuth installation routes.

Handles:
- GET /api/auth/install: Initiate OAuth flow
- GET /api/auth/callback: Complete OAuth flow

SECURITY: These routes bypass tenant context middleware (no JWT required).
OAuth state provides CSRF protection.
"""

import os
import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, status, Depends, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from src.services.oauth_service import (
    OAuthService,
    OAuthError,
    InvalidShopDomainError,
    InvalidStateError,
    HMACVerificationError,
    TokenExchangeError
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# Dependency to get database session
async def get_db_session():
    """
    Get database session for OAuth processing.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured"
        )

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_oauth_service() -> OAuthService:
    """Get OAuth service instance."""
    return OAuthService()


def render_error_page(title: str, message: str, details: Optional[str] = None) -> HTMLResponse:
    """Render user-friendly error page."""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            .error-box {{
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #d72c0d;
                margin-top: 0;
            }}
            .details {{
                margin-top: 20px;
                padding: 15px;
                background: #f9f9f9;
                border-radius: 4px;
                font-size: 14px;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div class="error-box">
            <h1>{title}</h1>
            <p>{message}</p>
            {f'<div class="details">{details}</div>' if details else ''}
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)


@router.get("/install")
async def install(
    shop: str = Query(..., description="Shopify shop domain"),
    session: Session = Depends(get_db_session),
    oauth_service: OAuthService = Depends(get_oauth_service)
):
    """
    Initiate Shopify OAuth installation flow.
    
    Validates shop domain, creates OAuth state, and redirects to Shopify.
    
    Args:
        shop: Shopify shop domain (e.g., "mystore.myshopify.com")
        
    Returns:
        Redirect to Shopify OAuth authorization page
    """
    try:
        # Validate shop domain
        if not oauth_service.validate_shop_domain(shop):
            logger.warning("Invalid shop domain", extra={"shop": shop})
            return render_error_page(
                "Invalid Shop Domain",
                f"The shop domain '{shop}' is not valid.",
                "Shop domains must be in the format: yourstore.myshopify.com"
            )
        
        # Create authorization URL with state
        auth_url = oauth_service.create_authorization_url(shop, session)
        
        logger.info("Redirecting to Shopify OAuth", extra={"shop": shop})
        
        # Redirect to Shopify
        return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
        
    except Exception as e:
        logger.error("OAuth install error", extra={"shop": shop, "error": str(e)})
        return render_error_page(
            "Installation Error",
            "An error occurred while starting the installation process.",
            f"Error: {str(e)}"
        )


@router.get("/callback")
async def callback(
    request: Request,
    code: Optional[str] = Query(None, description="Authorization code"),
    state: Optional[str] = Query(None, description="OAuth state parameter"),
    shop: Optional[str] = Query(None, description="Shop domain"),
    hmac: Optional[str] = Query(None, description="HMAC signature"),
    timestamp: Optional[str] = Query(None, description="Request timestamp"),
    session: Session = Depends(get_db_session),
    oauth_service: OAuthService = Depends(get_oauth_service)
):
    """
    Complete Shopify OAuth installation flow.
    
    Verifies HMAC, validates state, exchanges code for token,
    and creates/updates store record.
    
    Args:
        code: Authorization code from Shopify
        state: State parameter for CSRF protection
        shop: Shop domain
        hmac: HMAC signature
        timestamp: Request timestamp
        
    Returns:
        Redirect to embedded app or error page
    """
    try:
        # Collect all query parameters for HMAC verification
        params = dict(request.query_params)
        
        # Validate required parameters
        if not code:
            return render_error_page(
                "Missing Authorization Code",
                "The OAuth callback is missing the authorization code.",
                "Please try installing the app again."
            )
        
        if not state:
            return render_error_page(
                "Missing State Parameter",
                "The OAuth callback is missing the state parameter.",
                "This may indicate a security issue. Please try installing again."
            )
        
        if not shop:
            return render_error_page(
                "Missing Shop Domain",
                "The OAuth callback is missing the shop domain.",
                "Please try installing the app again."
            )
        
        # Normalize shop domain
        shop = shop.replace("https://", "").replace("http://", "").rstrip("/").lower()
        
        # Complete OAuth flow
        store = await oauth_service.complete_oauth(
            shop=shop,
            code=code,
            state=state,
            params=params,
            session=session
        )
        
        # Redirect to embedded app
        app_handle = oauth_service.app_handle
        embedded_url = f"https://{shop}/admin/apps/{app_handle}"
        
        logger.info("OAuth callback successful, redirecting to app", extra={
            "shop_domain": shop,
            "tenant_id": store.tenant_id
        })
        
        return RedirectResponse(url=embedded_url, status_code=status.HTTP_302_FOUND)
        
    except HMACVerificationError as e:
        logger.warning("HMAC verification failed", extra={"shop": shop, "error": str(e)})
        return render_error_page(
            "Security Verification Failed",
            "The OAuth callback could not be verified.",
            "This may indicate a security issue. Please try installing the app again."
        )
    
    except InvalidStateError as e:
        logger.warning("Invalid OAuth state", extra={"shop": shop, "error": str(e)})
        return render_error_page(
            "Invalid OAuth State",
            "The OAuth state is invalid, expired, or has already been used.",
            "Please try installing the app again."
        )
    
    except TokenExchangeError as e:
        logger.error("Token exchange failed", extra={"shop": shop, "error": str(e)})
        return render_error_page(
            "Token Exchange Failed",
            "Failed to exchange authorization code for access token.",
            f"Error: {str(e)}. Please try installing the app again."
        )
    
    except InvalidShopDomainError as e:
        logger.warning("Invalid shop domain in callback", extra={"shop": shop, "error": str(e)})
        return render_error_page(
            "Invalid Shop Domain",
            f"The shop domain '{shop}' is not valid.",
            "Please try installing the app again."
        )
    
    except Exception as e:
        logger.error("OAuth callback error", extra={"shop": shop, "error": str(e)})
        return render_error_page(
            "Installation Error",
            "An unexpected error occurred during installation.",
            f"Error: {str(e)}. Please contact support if this persists."
        )

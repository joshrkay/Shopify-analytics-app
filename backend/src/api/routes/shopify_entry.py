"""
Shopify embedded app entry point route.

When a merchant opens the app from Shopify Admin, Shopify navigates the iframe
to the application_url (GET /) with authentication query parameters:
  - hmac: HMAC-SHA256 signature of query params (hex)
  - shop: e.g. myshop.myshopify.com
  - host: Base64-encoded Shopify Admin host
  - timestamp: Unix timestamp

This route:
1. Validates the Shopify HMAC to confirm the request is from Shopify Admin
2. Serves an HTML bootstrap page that loads the React SPA with App Bridge

This route MUST be exempt from Clerk JWT and TenantContext middleware because
Shopify sends auth as query params, not Bearer tokens.
"""

import hashlib
import hmac as hmac_mod
import logging
import os
from urllib.parse import urlencode

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["shopify-entry"])


def verify_shopify_query_hmac(query_params: dict, api_secret: str) -> bool:
    """
    Verify the HMAC signature on Shopify query-string authentication.

    Shopify signs query params differently from webhooks:
    - Remove the ``hmac`` key from the params
    - Sort remaining keys alphabetically
    - Encode as ``key=value`` joined by ``&``
    - HMAC-SHA256 with the app API secret (hex digest)

    Args:
        query_params: Full query string parameters as a dict.
        api_secret: SHOPIFY_API_SECRET.

    Returns:
        True if signature is valid.
    """
    if not api_secret:
        logger.error("SHOPIFY_API_SECRET not configured")
        return False

    hmac_value = query_params.get("hmac")
    if not hmac_value:
        return False

    # Build message: sorted params excluding hmac
    filtered = {k: v for k, v in query_params.items() if k != "hmac"}
    sorted_params = urlencode(sorted(filtered.items()))

    computed = hmac_mod.new(
        api_secret.encode("utf-8"),
        sorted_params.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac_mod.compare_digest(computed, hmac_value)


@router.get("/", response_class=HTMLResponse)
async def shopify_app_entry(request: Request):
    """
    Root route handler for Shopify Admin iframe entry point.

    Shopify navigates here with ``?hmac=...&shop=...&host=...&timestamp=...``.
    Validates the HMAC and serves an HTML page that bootstraps the React SPA.
    """
    query_params = dict(request.query_params)

    # If no Shopify params at all, return a basic redirect to the frontend
    if not query_params.get("shop") and not query_params.get("hmac"):
        return HTMLResponse(
            content=_build_redirect_html(),
            status_code=200,
        )

    # Validate HMAC
    api_secret = os.getenv("SHOPIFY_API_SECRET", "")
    if not verify_shopify_query_hmac(query_params, api_secret):
        logger.warning(
            "Shopify entry HMAC verification failed",
            extra={
                "shop": query_params.get("shop"),
                "has_hmac": bool(query_params.get("hmac")),
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid HMAC signature",
        )

    shop = query_params.get("shop", "")
    host = query_params.get("host", "")
    api_key = os.getenv("SHOPIFY_API_KEY", "")

    logger.info(
        "Shopify Admin app entry",
        extra={"shop": shop, "has_host": bool(host)},
    )

    return HTMLResponse(
        content=_build_app_html(api_key=api_key, host=host, shop=shop),
        status_code=200,
        headers={
            "Content-Security-Policy": (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.shopify.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.shopify.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' data: https:; "
                "connect-src 'self' https://api.shopify.com https://admin.shopify.com; "
                "frame-ancestors 'self' https://admin.shopify.com https://*.myshopify.com; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            ),
            "X-Frame-Options": "ALLOW-FROM https://admin.shopify.com",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _build_app_html(api_key: str, host: str, shop: str) -> str:
    """Build the HTML bootstrap page that loads the React SPA inside Shopify Admin."""
    frontend_origin = os.getenv("FRONTEND_URL", "")
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="shopify-api-key" content="{api_key}" />
  <title>Signals AI</title>
  <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>
</head>
<body>
  <div id="root"></div>
  <script>
    // Pass Shopify params to the frontend SPA
    window.__SHOPIFY_CONFIG__ = {{
      apiKey: "{api_key}",
      host: "{host}",
      shop: "{shop}",
    }};
  </script>
  {f'<script type="module" src="{frontend_origin}/src/main.tsx"></script>' if frontend_origin else '<script type="module" src="/src/main.tsx"></script>'}
</body>
</html>"""


def _build_redirect_html() -> str:
    """Build a simple redirect page for non-Shopify requests to /."""
    frontend_url = os.getenv("FRONTEND_URL", "/analytics")
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="refresh" content="0;url={frontend_url}" />
  <title>Signals AI</title>
</head>
<body>
  <p>Redirecting...</p>
</body>
</html>"""

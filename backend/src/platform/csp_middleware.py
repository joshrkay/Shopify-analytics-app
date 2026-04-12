"""
Content Security Policy (CSP) Middleware for Shopify Admin Embedding.

Ensures Superset dashboards work safely within Shopify's security constraints.
Enforces strict CSP headers to prevent unauthorized embedding.

Security Requirements:
- Only allow framing from https://admin.shopify.com
- Block all other embedding attempts
- Enforce strict CSP headers
"""

import os
import logging
from typing import Optional, Callable
from urllib.parse import urlparse

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class CSPConfig:
    """
    CSP configuration for Shopify Admin embedding.

    All configuration can be overridden via environment variables.
    """

    def __init__(self):
        # Allowed frame ancestors (who can embed our content)
        self.frame_ancestors = self._get_frame_ancestors()

        # CSP directives
        self.default_src = "'self'"
        self.script_src = "'self' 'unsafe-inline' 'unsafe-eval' https://cdn.shopify.com"
        self.style_src = "'self' 'unsafe-inline' https://cdn.shopify.com"
        self.img_src = "'self' data: https:"
        self.font_src = "'self' data: https:"
        self.connect_src = "'self' https://api.shopify.com https://admin.shopify.com"
        self.object_src = "'none'"
        self.base_uri = "'self'"
        self.form_action = "'self'"

    def _get_frame_ancestors(self) -> list[str]:
        """
        Get allowed frame ancestors from environment or defaults.

        Environment: EMBED_FRAME_ANCESTORS (comma-separated)
        Default: 'self' https://admin.shopify.com https://*.myshopify.com
        """
        env_ancestors = os.getenv("EMBED_FRAME_ANCESTORS")
        if env_ancestors:
            return [a.strip() for a in env_ancestors.split(",")]

        return [
            "'self'",
            "https://admin.shopify.com",
            "https://*.myshopify.com",
        ]

    def build_csp_header(self) -> str:
        """Build the complete CSP header value."""
        directives = [
            f"default-src {self.default_src}",
            f"script-src {self.script_src}",
            f"style-src {self.style_src}",
            f"img-src {self.img_src}",
            f"font-src {self.font_src}",
            f"connect-src {self.connect_src}",
            f"frame-ancestors {' '.join(self.frame_ancestors)}",
            f"object-src {self.object_src}",
            f"base-uri {self.base_uri}",
            f"form-action {self.form_action}",
        ]
        return "; ".join(directives)


class ShopifyCSPMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce CSP headers for Shopify Admin embedding.

    Applied to all responses, but can be configured to only apply
    to specific paths (e.g., embed routes).
    """

    def __init__(
        self,
        app,
        config: Optional[CSPConfig] = None,
        apply_to_paths: Optional[list[str]] = None,
    ):
        """
        Initialize CSP middleware.

        Args:
            app: FastAPI application
            config: CSP configuration (uses defaults if not provided)
            apply_to_paths: Only apply CSP to paths starting with these prefixes.
                           If None, applies to all paths.
        """
        super().__init__(app)
        self.config = config or CSPConfig()
        self.apply_to_paths = apply_to_paths

    def _should_apply_csp(self, path: str) -> bool:
        """Check if CSP should be applied to this path."""
        if self.apply_to_paths is None:
            return True

        return any(path.startswith(prefix) for prefix in self.apply_to_paths)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and add CSP headers to response."""
        response = await call_next(request)

        if self._should_apply_csp(request.url.path):
            self._add_security_headers(response)

        return response

    def _add_security_headers(self, response: Response) -> None:
        """Add all security headers to response."""
        # Content Security Policy
        response.headers["Content-Security-Policy"] = self.config.build_csp_header()

        # X-Frame-Options: ALLOW-FROM is deprecated and unsupported in modern
        # browsers. Use SAMEORIGIN as a safe fallback; frame-ancestors in CSP
        # handles the actual embedding allowlist.
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # HSTS — force HTTPS for 1 year including subdomains
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        # Additional security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy (formerly Feature Policy)
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )


class EmbedOnlyCSPMiddleware(ShopifyCSPMiddleware):
    """
    CSP middleware that only applies to embed-related routes.

    Use this if you want different CSP policies for embedded
    vs non-embedded content.
    """

    def __init__(self, app, config: Optional[CSPConfig] = None):
        """Initialize with embed-only path prefixes."""
        super().__init__(
            app,
            config=config,
            apply_to_paths=["/api/v1/embed", "/embed"],
        )


def _is_origin_allowed(url_string: str, allowed_domains: list[str]) -> bool:
    """
    Check if a URL's hostname matches an allowed domain.

    Uses proper URL parsing instead of substring matching to prevent
    bypasses like evil-admin.shopify.com.attacker.com.
    """
    try:
        parsed = urlparse(url_string)
        hostname = parsed.hostname or ""
    except Exception:
        return False

    for domain in allowed_domains:
        if hostname == domain:
            return True
        # Support wildcard subdomains (e.g., *.myshopify.com)
        if domain.startswith("*.") and hostname.endswith(domain[1:]):
            return True
        # Also match if hostname ends with .domain (subdomain match)
        if hostname.endswith("." + domain):
            return True

    return False


def validate_frame_origin(request: Request) -> bool:
    """
    Validate that the request comes from an allowed frame origin.

    Checks Origin and Referer headers against the configured
    frame-ancestors using proper URL hostname parsing.

    Returns True if origin is allowed for embedding.
    """
    config = CSPConfig()
    allowed_domains = []
    for ancestor in config.frame_ancestors:
        if ancestor == "'self'":
            continue
        # Strip scheme, keep domain (including wildcard prefix)
        domain = ancestor.replace("https://", "").replace("http://", "")
        allowed_domains.append(domain)

    # Check Origin header
    origin = request.headers.get("Origin", "")
    if origin and _is_origin_allowed(origin, allowed_domains):
        return True

    # Check Referer header as fallback
    referer = request.headers.get("Referer", "")
    if referer and _is_origin_allowed(referer, allowed_domains):
        return True

    # Also allow direct access (no embedding)
    if not origin and not referer:
        return True

    logger.warning(
        "Frame origin validation failed",
        extra={
            "origin": origin,
            "referer": referer,
            "allowed_domains": allowed_domains,
            "path": request.url.path,
        }
    )

    return False


# CORS configuration for Shopify
SHOPIFY_CORS_CONFIG = {
    "allow_origins": [
        "https://admin.shopify.com",
        "https://*.myshopify.com",
    ],
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Authorization", "Content-Type", "X-Requested-With"],
}


# Talisman-style security configuration
# (For use with Flask-Talisman if needed)
TALISMAN_CONFIG = {
    "force_https": True,
    "strict_transport_security": True,
    "strict_transport_security_max_age": 31536000,  # 1 year
    "strict_transport_security_include_subdomains": True,
    "content_security_policy": CSPConfig().build_csp_header(),
    "referrer_policy": "strict-origin-when-cross-origin",
}

import os
import logging
from datetime import timedelta

# Import centralized performance limits (single source of truth — Story 5.1.6)
from performance_config import (
    PERFORMANCE_LIMITS,
    SQL_MAX_ROW,
    ROW_LIMIT,
    SAMPLES_ROW_LIMIT,
    SQLLAB_TIMEOUT,
    SQLLAB_ASYNC_TIME_LIMIT_SEC,
    SUPERSET_WEBSERVER_TIMEOUT,
    CACHE_DEFAULT_TIMEOUT,
    EXPLORE_CACHE_TTL,
    SAFETY_FEATURE_FLAGS,
)

# Import Explore Guardrails
from explore_guardrails import (
    PERFORMANCE_GUARDRAILS,
    EXPLORE_FEATURE_FLAGS,
    ExploreGuardrailEnforcer,
)

# Import JWT authentication handler
from security.jwt_auth import authenticate_embed_request

# Flask App Configuration
SECRET_KEY = os.getenv('SUPERSET_SECRET_KEY')
SQLALCHEMY_DATABASE_URI = os.getenv(
    'SUPERSET_METADATA_DB_URI',
    'postgresql://user:password@postgres:5432/superset'
)

# SQLAlchemy Connection Pool (production-ready)
SQLALCHEMY_POOL_SIZE = int(os.getenv('SUPERSET_POOL_SIZE', '5'))
SQLALCHEMY_POOL_TIMEOUT = 30
SQLALCHEMY_POOL_RECYCLE = 300
SQLALCHEMY_MAX_OVERFLOW = 10

# Security & HTTPS
PREFERRED_URL_SCHEME = 'https'
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
WTF_CSRF_CHECK_DEFAULT = True

# Security Headers (HSTS, CSP, X-Frame-Options)
HTTP_HEADERS = {
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff',
    'Content-Security-Policy': "frame-ancestors 'self' https://admin.shopify.com",
    'Referrer-Policy': 'strict-origin',
}

# JWT Embedded Authentication
SUPERSET_JWT_SECRET = os.getenv('SUPERSET_JWT_SECRET_CURRENT')
SUPERSET_JWT_SECRET_PREVIOUS = os.getenv('SUPERSET_JWT_SECRET_PREVIOUS')

# Guest token configuration for Superset 3.x embedded SDK
GUEST_TOKEN_JWT_SECRET = os.getenv('SUPERSET_JWT_SECRET_CURRENT')
GUEST_TOKEN_JWT_ALGO = 'HS256'
GUEST_TOKEN_HEADER_NAME = 'X-GuestToken'

# Register JWT before_request handler for deny-by-default auth
FLASK_APP_MUTATOR = lambda app: app.before_request(authenticate_embed_request)

# Feature Flags
# Base flags merged with Explore guardrail flags and safety flags
_BASE_FEATURE_FLAGS = {
    'EMBEDDED_SUPERSET': True,
    'ENABLE_SUPERSET_META_DB_COMMENTS': True,
}

# Merge: safety flags (from performance_config) override everything
FEATURE_FLAGS = {**_BASE_FEATURE_FLAGS, **EXPLORE_FEATURE_FLAGS, **SAFETY_FEATURE_FLAGS}

# Disable SQL Lab
SQLLAB_QUERY_COST_ESTIMATE_ENABLED = False

# =============================================================================
# EXPLORE MODE GUARDRAILS
# All values sourced from performance_config.PERFORMANCE_LIMITS
# =============================================================================
EXPLORE_ROW_LIMIT = ROW_LIMIT

# Disable data export features (enforced centrally via SAFETY_FEATURE_FLAGS)
ALLOW_FILE_EXPORT = False
ENABLE_PIVOT_TABLE_DATA_EXPORT = False
CSV_EXPORT = False

# Disable dataset creation for non-admins
ALLOWED_USER_CSV_UPLOAD = False

# Cache Configuration (Redis)
CACHE_CONFIG = {
    'CACHE_TYPE': 'RedisCache',
    'CACHE_REDIS_URL': os.getenv('REDIS_URL', 'redis://redis:6379/0'),
    'CACHE_DEFAULT_TIMEOUT': EXPLORE_CACHE_TTL,
    'CACHE_REDIS_DB': 0,
    'CACHE_REDIS_SOCKET_CONNECT_TIMEOUT': 5,
    'CACHE_REDIS_SOCKET_TIMEOUT': 5,
}

# Data cache for Explore queries
DATA_CACHE_CONFIG = {
    'CACHE_TYPE': 'RedisCache',
    'CACHE_REDIS_URL': os.getenv('REDIS_URL', 'redis://redis:6379/0'),
    'CACHE_DEFAULT_TIMEOUT': EXPLORE_CACHE_TTL,
    'CACHE_KEY_PREFIX': PERFORMANCE_LIMITS.cache_key_prefix,
}

# Performance Indices (to be created in PostgreSQL for optimal query performance)
# CREATE INDEX IF NOT EXISTS idx_orders_tenant_date ON fact_orders (tenant_id, order_date);
# CREATE INDEX IF NOT EXISTS idx_spend_tenant_channel ON fact_marketing_spend (tenant_id, channel);
# CREATE INDEX IF NOT EXISTS idx_campaign_performance_tenant ON fact_campaign_performance (tenant_id, campaign_id);

# Session Configuration
PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
SESSION_REFRESH_EACH_REQUEST = True

# Logging Configuration
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': {
        'default': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'loggers': {
        '': {
            'handlers': ['default'],
            'level': 'INFO',
            'propagate': True
        }
    }
}

# Datadog APM Integration
DATADOG_ENABLED = os.getenv('DATADOG_ENABLED', 'false').lower() == 'true'
if DATADOG_ENABLED:
    DATADOG_TRACE_ENABLED = True
    DATADOG_SERVICE_NAME = 'superset-analytics'

# Public role disabled (no public dashboards)
PUBLIC_ROLE_LIKE_GAMMA = False

# Allow HTTPS to be disabled for local development (env override)
TALISMAN_ENABLED = os.getenv('TALISMAN_ENABLED', 'true').lower() == 'true'
TALISMAN_CONFIG = {
    'force_https': TALISMAN_ENABLED,
    'strict_transport_security': TALISMAN_ENABLED,
    'strict_transport_security_max_age': 31536000,
}

# =============================================================================
# STARTUP GUARDS (Story 5.1.8)
# Validate configuration on boot — log CRITICAL on failure
# =============================================================================
try:
    from guards import StartupGuards
    _guard_passed, _guard_results = StartupGuards.run_all_startup_checks()
    if not _guard_passed:
        logging.getLogger(__name__).critical(
            "STARTUP GUARDS FAILED — Superset may not be safe to serve data"
        )
except ImportError:
    # guards.py not yet deployed — skip (will be added in Story 5.1.8)
    pass

# =============================================================================
# EXPLORE MODE GUARDRAILS SUMMARY
# =============================================================================
# All values sourced from performance_config.PERFORMANCE_LIMITS:
#
# | Guardrail              | Value       | Enforcement                    |
# |------------------------|-------------|--------------------------------|
# | Max date range         | 90 days     | ExplorePermissionValidator     |
# | Query timeout          | 20 seconds  | SQLLAB_ASYNC_TIME_LIMIT_SEC    |
# | Row limit              | 50,000      | SQL_MAX_ROW / ROW_LIMIT        |
# | Max group-by dims      | 2           | ExplorePermissionValidator     |
# | Cache TTL              | 30 minutes  | CACHE_DEFAULT_TIMEOUT          |
#
# See performance_config.py for the single source of truth.
# See explore_guardrails.py for validation implementation.
# =============================================================================

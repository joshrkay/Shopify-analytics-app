"""
Graceful degradation tests — CI gate that prevents HTTP 500 responses when
dbt-managed analytics tables are absent.

Why this matters
----------------
When dbt hasn't run (fresh deploy, dbt pipeline failure, DR restore), these
tables are absent:
  - canonical.orders
  - attribution.last_click
  - marts.mart_marketing_metrics
  - analytics.marketing_spend

If an endpoint's SQL query raises an uncaught exception, FastAPI's global
exception handler returns HTTP 500 with a generic error body.  On the frontend
this surfaces as a broken page rather than a graceful "data unavailable" state.

Every endpoint that queries dbt-managed tables MUST:
  1. Catch the exception (try/except around the SQL block)
  2. Return HTTP 503 — NOT 500
  3. Return a JSON body — NOT HTML

These tests verify that contract.  They use the `dbt_absent_client` fixture
(from conftest.py) which injects a valid tenant context and a DB session that
raises ProgrammingError on every execute() call.

Adding a new dbt-querying endpoint
-----------------------------------
1. Add it to ANALYTICS_ENDPOINTS below.
2. The two parameterized test classes will automatically cover it.
3. If the endpoint doesn't exist yet in the test app (conftest.py), add the
   router there too.
"""

import pytest

# ---------------------------------------------------------------------------
# Endpoint registry
# ---------------------------------------------------------------------------
# Each entry: (http_method, url_path, acceptable_status_codes)
#
# acceptable_status_codes must NOT include 500.
# Typical acceptable values: {503} or {200, 503}.
#
# 200 is included for endpoints that already degrade to empty-data responses
# (returning a valid schema with zero rows is also acceptable graceful degradation).

ANALYTICS_ENDPOINTS: list[tuple[str, str, frozenset[int]]] = [
    # channels — queries marts.mart_marketing_metrics + analytics.marketing_spend
    ("GET", "/api/channels/google_ads/metrics",    frozenset({200, 503})),
    ("GET", "/api/channels/meta_ads/metrics",       frozenset({200, 503})),
    ("GET", "/api/channels/tiktok_ads/metrics",     frozenset({200, 503})),
    # orders — queries canonical.orders LEFT JOIN attribution.last_click
    ("GET", "/api/orders",                           frozenset({200, 503})),
    ("GET", "/api/orders?timeframe=7days",           frozenset({200, 503})),
    # attribution — queries attribution.last_click + marts.mart_marketing_metrics
    ("GET", "/api/attribution/summary",              frozenset({200, 503})),
    ("GET", "/api/attribution/orders",               frozenset({200, 503})),
]

# IDs for parametrize — makes pytest output readable
_ENDPOINT_IDS = [
    f"{method} {path.split('?')[0]}"
    for method, path, _ in ANALYTICS_ENDPOINTS
]


# ---------------------------------------------------------------------------
# Test class 1: status code contract
# ---------------------------------------------------------------------------

class TestNeverReturns500WhenDbtTablesAbsent:
    """
    Verifies that every analytics endpoint returns an acceptable status code
    (not 500) when dbt tables are absent.

    HTTP 500 means an unhandled exception leaked through — the endpoint has no
    try/except around its dbt SQL query.  Acceptable codes are 200 (empty data)
    or 503 (analytics unavailable).
    """

    @pytest.mark.parametrize(
        "method,path,acceptable_codes",
        ANALYTICS_ENDPOINTS,
        ids=_ENDPOINT_IDS,
    )
    def test_status_code_is_not_500(
        self,
        dbt_absent_client,
        method: str,
        path: str,
        acceptable_codes: frozenset[int],
    ):
        response = getattr(dbt_absent_client, method.lower())(path)

        assert response.status_code != 500, (
            f"\n{method} {path} returned HTTP 500 when dbt tables were absent.\n\n"
            f"Expected one of {sorted(acceptable_codes)}.\n\n"
            f"Response body (first 500 chars):\n{response.text[:500]}\n\n"
            "Fix: wrap the SQL query in try/except and raise HTTPException(503):\n\n"
            "    try:\n"
            "        rows = db.execute(text('SELECT ... FROM canonical.orders ...'))\n"
            "    except Exception as exc:\n"
            "        logger.warning('Query failed: %s', exc)\n"
            "        raise HTTPException(status_code=503, detail='Analytics data unavailable')"
        )

        assert response.status_code in acceptable_codes, (
            f"\n{method} {path} returned HTTP {response.status_code}.\n"
            f"Expected one of {sorted(acceptable_codes)}.\n"
            f"Response body: {response.text[:200]}"
        )


# ---------------------------------------------------------------------------
# Test class 2: response body contract
# ---------------------------------------------------------------------------

class TestErrorResponseIsJsonNotHtml:
    """
    Verifies that error responses are JSON-encoded, not HTML.

    HTML error responses (e.g. from the SPA fallback or an nginx error page)
    cause `"Unexpected token '<'"` parse errors on the frontend.  All API
    error responses must have Content-Type: application/json.

    This test only runs on responses that are actually errors (non-2xx).
    """

    @pytest.mark.parametrize(
        "method,path,acceptable_codes",
        ANALYTICS_ENDPOINTS,
        ids=_ENDPOINT_IDS,
    )
    def test_error_response_is_json(
        self,
        dbt_absent_client,
        method: str,
        path: str,
        acceptable_codes: frozenset[int],
    ):
        response = getattr(dbt_absent_client, method.lower())(path)

        # Only check content-type for non-2xx responses
        if response.status_code >= 300:
            content_type = response.headers.get("content-type", "")
            assert "text/html" not in content_type.lower(), (
                f"\n{method} {path} returned Content-Type: {content_type!r}\n"
                f"Error responses must be JSON, not HTML.\n"
                f"Response body (first 200 chars): {response.text[:200]}"
            )

            # Also verify it's actually parseable as JSON (not empty body)
            assert response.text.strip(), (
                f"\n{method} {path} returned HTTP {response.status_code} with empty body.\n"
                "Error responses should include a JSON body with a 'detail' field."
            )

            try:
                body = response.json()
                assert "detail" in body or "error" in body, (
                    f"\n{method} {path} error response missing 'detail'/'error' key.\n"
                    f"Body: {body}"
                )
            except Exception:
                pytest.fail(
                    f"{method} {path} HTTP {response.status_code} response "
                    f"body is not valid JSON: {response.text[:200]}"
                )


# ---------------------------------------------------------------------------
# Test class 3: 503 is explicit (not a catch-all fallback)
# ---------------------------------------------------------------------------

class TestServiceUnavailableHasInformativeDetail:
    """
    When an endpoint returns 503, the detail message should clearly indicate
    the analytics data is unavailable — not a generic "internal server error".

    This helps frontend code distinguish between:
      - 503 "analytics data unavailable" → show empty state UI
      - 503 "database unreachable"       → show connection error UI
    """

    @pytest.mark.parametrize(
        "method,path,acceptable_codes",
        ANALYTICS_ENDPOINTS,
        ids=_ENDPOINT_IDS,
    )
    def test_503_has_detail_message(
        self,
        dbt_absent_client,
        method: str,
        path: str,
        acceptable_codes: frozenset[int],
    ):
        response = getattr(dbt_absent_client, method.lower())(path)

        if response.status_code != 503:
            pytest.skip(f"Endpoint returned {response.status_code}, not 503 — skipping detail check")

        try:
            body = response.json()
        except Exception:
            pytest.fail(
                f"{method} {path} returned 503 but body is not JSON: {response.text[:200]}"
            )

        detail = body.get("detail", "")
        assert detail, (
            f"{method} {path} returned 503 with no 'detail' in response body.\n"
            f"Body: {body}\n"
            "Add a descriptive detail message like 'Analytics data unavailable'."
        )

        # Should not expose raw exception messages (security)
        forbidden_phrases = [
            "ProgrammingError",
            "psycopg2",
            "sqlalchemy",
            "Traceback",
            "relation",   # postgres-internal: "relation 'canonical.orders' does not exist"
        ]
        for phrase in forbidden_phrases:
            assert phrase.lower() not in detail.lower(), (
                f"{method} {path} 503 detail leaks internal error info: {detail!r}\n"
                f"Do not expose raw database exception messages to API clients."
            )

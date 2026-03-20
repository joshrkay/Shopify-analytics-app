"""
Unit tests for the Warehouse Export API routes.

Tests cover:
- GET /api/warehouse/types — List supported warehouse types
- GET /api/warehouse/destinations — List destinations (requires entitlement)
- POST /api/warehouse/destinations — Create destination (validation + limits)
- DELETE /api/warehouse/destinations/{id} — Delete destination
- POST /api/warehouse/destinations/{id}/test — Test connection (stub)
- POST /api/warehouse/destinations/{id}/sync — Trigger sync (stub)
"""

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes.warehouse_export import (
    router,
    SUPPORTED_DESTINATIONS,
    DESTINATION_TO_AIRBYTE_TYPE,
    _get_max_destinations,
    _validate_destination_config,
)
from src.database.session import get_db_session
from src.services.billing_entitlements import EntitlementCheckResult


# =============================================================================
# Fixtures
# =============================================================================

TENANT_ID = "test-tenant-warehouse"


def _mock_entitlements(entitled=True, tier="pro"):
    mock = MagicMock()
    mock.check_feature_entitlement.return_value = EntitlementCheckResult(
        is_entitled=entitled,
        current_tier=tier,
        required_tier="pro" if not entitled else None,
    )
    mock.get_billing_tier.return_value = tier
    return mock


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_session] = lambda: MagicMock()
    return app


@pytest.fixture
def client(app):
    with patch("src.api.routes.warehouse_export.get_tenant_context") as mock_gtc:
        ctx = MagicMock()
        ctx.tenant_id = TENANT_ID
        mock_gtc.return_value = ctx
        yield TestClient(app)


# =============================================================================
# GET /api/warehouse/types
# =============================================================================

class TestListWarehouseTypes:

    def test_returns_all_types(self, client):
        """Returns BigQuery, Snowflake, and Redshift."""
        response = client.get("/api/warehouse/types")

        assert response.status_code == 200
        data = response.json()
        type_ids = {t["id"] for t in data["types"]}
        assert "bigquery" in type_ids
        assert "snowflake" in type_ids
        assert "redshift" in type_ids
        assert len(data["types"]) == 3

    def test_type_fields(self, client):
        """Each type has required fields."""
        response = client.get("/api/warehouse/types")

        for t in response.json()["types"]:
            assert "id" in t
            assert "name" in t
            assert "description" in t
            assert "required_fields" in t
            assert isinstance(t["required_fields"], list)
            assert len(t["required_fields"]) > 0

    def test_bigquery_required_fields(self, client):
        """BigQuery requires project_id, dataset_id, credentials_json."""
        response = client.get("/api/warehouse/types")

        bq = next(t for t in response.json()["types"] if t["id"] == "bigquery")
        assert "project_id" in bq["required_fields"]
        assert "dataset_id" in bq["required_fields"]
        assert "credentials_json" in bq["required_fields"]


# =============================================================================
# GET /api/warehouse/destinations — entitlement checks
# =============================================================================

class TestListDestinations:

    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_free_tier_gets_402(self, MockBES, client):
        """Free tier cannot list warehouse destinations."""
        MockBES.return_value = _mock_entitlements(entitled=False, tier="free")

        response = client.get("/api/warehouse/destinations")

        assert response.status_code == 402

    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_growth_tier_gets_402(self, MockBES, client):
        """Growth tier cannot access warehouse export."""
        MockBES.return_value = _mock_entitlements(entitled=False, tier="growth")

        response = client.get("/api/warehouse/destinations")

        assert response.status_code == 402


# =============================================================================
# POST /api/warehouse/destinations — validation
# =============================================================================

class TestCreateDestination:

    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_invalid_type_returns_400(self, MockBES, client):
        """Unsupported destination type returns 400."""
        MockBES.return_value = _mock_entitlements(entitled=True, tier="pro")

        response = client.post(
            "/api/warehouse/destinations",
            json={
                "destination_type": "mysql",
                "display_name": "My MySQL",
                "configuration": {},
            },
        )

        assert response.status_code == 400
        assert "Unsupported destination type" in response.json()["detail"]

    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_missing_fields_returns_400(self, MockBES, client):
        """Missing required fields returns 400."""
        MockBES.return_value = _mock_entitlements(entitled=True, tier="pro")

        response = client.post(
            "/api/warehouse/destinations",
            json={
                "destination_type": "bigquery",
                "display_name": "My BQ",
                "configuration": {"project_id": "proj-1"},
                # Missing dataset_id and credentials_json
            },
        )

        assert response.status_code == 400
        assert "Missing required fields" in response.json()["detail"]

    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_requires_entitlement(self, MockBES, client):
        """Free tier cannot create destinations."""
        MockBES.return_value = _mock_entitlements(entitled=False, tier="free")

        response = client.post(
            "/api/warehouse/destinations",
            json={
                "destination_type": "bigquery",
                "display_name": "My BQ",
                "configuration": {
                    "project_id": "p",
                    "dataset_id": "d",
                    "credentials_json": "{}",
                },
            },
        )

        assert response.status_code == 402

    @patch("src.services.airbyte_service.AirbyteService")
    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_pro_limited_to_1_destination(self, MockBES, MockAirbyte, client):
        """Pro tier limited to 1 warehouse destination."""
        MockBES.return_value = _mock_entitlements(entitled=True, tier="pro")

        # Mock existing destinations — 1 already exists
        mock_service = MagicMock()
        mock_conn = MagicMock()
        mock_conn.source_type = "destination-bigquery"
        mock_conn.status = "active"
        mock_result = MagicMock()
        mock_result.connections = [mock_conn]
        mock_service.list_connections.return_value = mock_result
        MockAirbyte.return_value = mock_service

        response = client.post(
            "/api/warehouse/destinations",
            json={
                "destination_type": "snowflake",
                "display_name": "My Snowflake",
                "configuration": {
                    "host": "h",
                    "database": "d",
                    "schema": "s",
                    "warehouse": "w",
                    "username": "u",
                    "password": "p",
                },
            },
        )

        assert response.status_code == 402
        assert "Maximum" in response.json()["detail"]

    @patch("src.services.airbyte_service.AirbyteService")
    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_successful_creation(self, MockBES, MockAirbyte, client):
        """Successful creation returns 201 with destination info."""
        MockBES.return_value = _mock_entitlements(entitled=True, tier="pro")

        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.connections = []  # No existing destinations
        mock_service.list_connections.return_value = mock_result

        mock_conn = MagicMock()
        mock_conn.id = "dest-001"
        mock_service.register_connection.return_value = mock_conn
        MockAirbyte.return_value = mock_service

        response = client.post(
            "/api/warehouse/destinations",
            json={
                "destination_type": "bigquery",
                "display_name": "My BQ",
                "configuration": {
                    "project_id": "p",
                    "dataset_id": "d",
                    "credentials_json": "{}",
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "dest-001"
        assert data["destination_type"] == "bigquery"
        assert data["display_name"] == "My BQ"
        assert data["status"] == "pending"


# =============================================================================
# DELETE /api/warehouse/destinations/{id}
# =============================================================================

class TestDeleteDestination:

    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_requires_entitlement(self, MockBES, client):
        """Free tier cannot delete destinations."""
        MockBES.return_value = _mock_entitlements(entitled=False, tier="free")

        response = client.delete("/api/warehouse/destinations/dest-001")

        assert response.status_code == 402

    @patch("src.services.airbyte_service.AirbyteService")
    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_successful_delete_returns_204(self, MockBES, MockAirbyte, client):
        """Successful delete returns 204."""
        MockBES.return_value = _mock_entitlements(entitled=True, tier="pro")
        mock_service = MagicMock()
        MockAirbyte.return_value = mock_service

        response = client.delete("/api/warehouse/destinations/dest-001")

        assert response.status_code == 204
        mock_service.delete_connection.assert_called_once_with("dest-001")


# =============================================================================
# POST /api/warehouse/destinations/{id}/test
# =============================================================================

class TestTestConnection:

    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_returns_success_message(self, MockBES, client):
        """Test connection returns success with pending message."""
        MockBES.return_value = _mock_entitlements(entitled=True, tier="pro")

        response = client.post("/api/warehouse/destinations/dest-001/test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["message"]) > 0

    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_requires_entitlement(self, MockBES, client):
        """Free tier cannot test connections."""
        MockBES.return_value = _mock_entitlements(entitled=False, tier="free")

        response = client.post("/api/warehouse/destinations/dest-001/test")

        assert response.status_code == 402


# =============================================================================
# POST /api/warehouse/destinations/{id}/sync
# =============================================================================

class TestTriggerSync:

    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_returns_success_message(self, MockBES, client):
        """Trigger sync returns success with pending message."""
        MockBES.return_value = _mock_entitlements(entitled=True, tier="pro")

        response = client.post("/api/warehouse/destinations/dest-001/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["message"]) > 0

    @patch("src.api.routes.warehouse_export.BillingEntitlementsService")
    def test_requires_entitlement(self, MockBES, client):
        """Free tier cannot trigger syncs."""
        MockBES.return_value = _mock_entitlements(entitled=False, tier="free")

        response = client.post("/api/warehouse/destinations/dest-001/sync")

        assert response.status_code == 402


# =============================================================================
# Helper functions
# =============================================================================

class TestHelpers:

    def test_max_destinations_by_tier(self):
        assert _get_max_destinations("free") == 0
        assert _get_max_destinations("growth") == 0
        assert _get_max_destinations("pro") == 1
        assert _get_max_destinations("enterprise") == 999
        assert _get_max_destinations("unknown") == 0

    def test_validate_config_valid(self):
        error = _validate_destination_config("bigquery", {
            "project_id": "p",
            "dataset_id": "d",
            "credentials_json": "{}",
        })
        assert error is None

    def test_validate_config_missing_fields(self):
        error = _validate_destination_config("bigquery", {"project_id": "p"})
        assert error is not None
        assert "Missing required fields" in error

    def test_validate_config_unsupported_type(self):
        error = _validate_destination_config("mysql", {})
        assert error is not None
        assert "Unsupported" in error

    def test_airbyte_type_mapping(self):
        """All supported destinations map to valid Airbyte types."""
        for dest_type in SUPPORTED_DESTINATIONS:
            assert dest_type in DESTINATION_TO_AIRBYTE_TYPE

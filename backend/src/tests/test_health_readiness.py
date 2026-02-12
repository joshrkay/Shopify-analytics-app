"""Tests for DB readiness helpers and endpoint handler logic."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.platform.db_readiness import check_required_tables
from src.api.routes.health import readiness


def test_check_required_tables_all_present():
    session = Mock()
    session.execute.return_value.scalar.return_value = "public.users"

    result = check_required_tables(session, ["users", "tenants"])

    assert result.ready is True
    assert result.missing_tables == []
    assert result.checked_tables == ["users", "tenants"]


def test_check_required_tables_reports_missing_tables():
    session = Mock()
    values = [None, "public.tenants"]

    def _scalar_side_effect():
        return values.pop(0)

    execute_result = Mock()
    execute_result.scalar.side_effect = _scalar_side_effect
    session.execute.return_value = execute_result

    result = check_required_tables(session, ["users", "tenants"])

    assert result.ready is False
    assert result.missing_tables == ["users"]


def test_readiness_handler_returns_not_ready_payload():
    fake_db = Mock()
    with patch("src.api.routes.health.check_required_tables") as mock_check:
        mock_check.return_value = SimpleNamespace(
            ready=False,
            checked_tables=["users", "tenants", "user_tenant_roles"],
            missing_tables=["users"],
        )

        payload = __import__("asyncio").run(readiness(db=fake_db))

    assert payload["status"] == "not_ready"
    assert payload["checks"]["identity_tables"]["missing"] == ["users"]

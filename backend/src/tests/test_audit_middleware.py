"""Tests for audit middleware helpers."""

from src.middleware import audit_middleware


def test_map_refresh_failure_reason():
    assert audit_middleware._map_refresh_failure_reason(401) == "token_expired"
    assert audit_middleware._map_refresh_failure_reason(400) == "token_validation_failed"
    assert audit_middleware._map_refresh_failure_reason(403) == "access_denied"
    assert audit_middleware._map_refresh_failure_reason(500) == "refresh_failed"


def test_parse_json_handles_invalid():
    assert audit_middleware._parse_json(b"") == {}
    assert audit_middleware._parse_json(b"not-json") == {}

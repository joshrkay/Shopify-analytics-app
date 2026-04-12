"""
Tests for backend.src.platform.logging_config.

Verifies that:
- In production mode, stdlib ``logger.info("...", extra={...})`` calls are
  emitted as single-line JSON with structured fields.
- Extra kwargs like ``tenant_id`` become first-class JSON keys.
- Exception info is rendered.
- Development mode uses the console renderer (not JSON).
"""

from __future__ import annotations

import json
import logging

import pytest

from src.platform.logging_config import configure_logging


def _capture_logs(caplog_stream, env: str) -> logging.Logger:
    configure_logging(env=env, log_level="INFO")
    return logging.getLogger(f"test_logging_config_{env}")


def test_production_logging_emits_json(capsys):
    configure_logging(env="production", log_level="INFO")
    log = logging.getLogger("test_logging_config.prod")
    log.info("hello world", extra={"tenant_id": "abc-123", "user_id": "u1"})

    captured = capsys.readouterr().out.strip().splitlines()
    assert captured, "expected at least one log line on stdout"

    # The structlog JSONRenderer emits one JSON object per line.
    record = json.loads(captured[-1])
    assert record["event"] == "hello world"
    assert record["level"] == "info"
    assert record["tenant_id"] == "abc-123"
    assert record["user_id"] == "u1"
    assert "timestamp" in record
    assert record["logger"] == "test_logging_config.prod"


def test_production_logging_preserves_exception_info(capsys):
    configure_logging(env="production", log_level="INFO")
    log = logging.getLogger("test_logging_config.exc")
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("oops", extra={"tenant_id": "abc"})

    captured = capsys.readouterr().out.strip().splitlines()
    assert captured, "expected at least one log line on stdout"
    record = json.loads(captured[-1])
    assert record["event"] == "oops"
    assert record["level"] == "error"
    assert record["tenant_id"] == "abc"
    assert "ValueError" in record.get("exception", "")


def test_development_logging_is_not_json(capsys):
    configure_logging(env="development", log_level="INFO")
    log = logging.getLogger("test_logging_config.dev")
    log.info("dev mode hello", extra={"tenant_id": "xyz"})

    captured = capsys.readouterr().out.strip()
    assert captured, "expected at least one log line on stdout"
    # Dev mode uses ConsoleRenderer — definitely not JSON.
    with pytest.raises(json.JSONDecodeError):
        json.loads(captured.splitlines()[-1])
    # But the tenant_id field should still appear somewhere in the
    # rendered text (ConsoleRenderer prints it as a key=value).
    assert "tenant_id" in captured
    assert "xyz" in captured


@pytest.fixture(autouse=True)
def _reset_logging():
    """
    Reset root logger handlers between tests so each test configures
    logging from a clean state. Without this, handlers from previous
    tests leak and pollute ``capsys``.
    """
    yield
    root = logging.getLogger()
    root.handlers = []

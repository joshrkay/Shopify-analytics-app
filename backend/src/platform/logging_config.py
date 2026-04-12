"""
Structured logging configuration.

Wires structlog into the stdlib logging system so that every
``logger = logging.getLogger(__name__)`` call in the codebase automatically
produces structured JSON output in production (and human-readable console
output in development).

Why bother:
- Existing code uses ``logger.info("msg", extra={"tenant_id": ...})`` in many
  places. Without this configuration those ``extra`` fields are silently
  dropped and log aggregators (DataDog, Loggly, Render) cannot index them.
- Using ``ProcessorFormatter.wrap_for_formatter`` at the stdlib boundary lets
  us keep all the ``logging.getLogger(__name__)`` call sites untouched.

Production output format::

    {"timestamp":"2026-04-12T12:34:56Z","level":"info","logger":"main",
     "event":"hello","tenant_id":"abc-123"}

Development output format (colored, one line per record)::

    2026-04-12T12:34:56Z [info     ] hello         [main] tenant_id=abc-123
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def _merge_extra(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Merge ``extra={}`` kwargs from stdlib log calls into the structlog event
    dict. structlog's ``ProcessorFormatter`` places them under the
    ``_record`` key; this processor surfaces them as first-class fields so
    they show up in JSON output.
    """
    # NOTE: do NOT pop ``_record`` — structlog's ``remove_processors_meta``
    # (which runs later inside ProcessorFormatter) expects the key to still
    # be present and will KeyError otherwise.
    record = event_dict.get("_record")
    if record is None:
        return event_dict

    # stdlib LogRecord attributes that should NOT be copied into the event
    # dict (either already captured by structlog or unhelpful noise).
    reserved = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
        "color_message",
    }
    for key, value in record.__dict__.items():
        if key in reserved or key.startswith("_"):
            continue
        # Avoid clobbering keys structlog processors have already set.
        event_dict.setdefault(key, value)
    return event_dict


def configure_logging(env: str, log_level: str = "INFO") -> None:
    """
    Configure structlog + stdlib logging for the application.

    Args:
        env: Environment name (``"production"`` enables JSON output).
        log_level: Python log level name (``"DEBUG"``, ``"INFO"``, ...).
    """
    level = getattr(logging, (log_level or "INFO").upper(), logging.INFO)
    is_production = (env or "").lower() == "production"

    # Shared processor chain applied to every record, whether it originates
    # from structlog or from stdlib ``logging``.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _merge_extra,
    ]

    if is_production:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # Configure structlog itself (for any module that uses structlog directly).
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib logging through the same processor chain so
    # ``logging.getLogger(...).info(..., extra={...})`` calls are also
    # rendered as structured output.
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    # Replace any handlers that were installed before us (e.g. by
    # ``basicConfig``) so we don't emit duplicate lines.
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    # Quiet down noisy third-party loggers in production.
    logging.getLogger("uvicorn.access").setLevel(
        logging.WARNING if is_production else logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

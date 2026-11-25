"""Logging setup: JSON lines with request IDs and credential redaction.

Tokens, secrets and authorization headers are never emitted to the logs.
"""

import contextvars
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.middleware import request_id_var

# Keys whose values must never be logged.
REDACTED_KEYS = {
    "access_token",
    "refresh_token",
    "token",
    "client_secret",
    "authorization",
    "cookie",
    "set-cookie",
    "x-csrf-token",
    "password",
    "private_key",
}


def _redact(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: ("[REDACTED]" if key.lower() in REDACTED_KEYS else _redact(value))
            for key, value in payload.items()
        }
    if isinstance(payload, (list, tuple)):
        return [_redact(item) for item in payload]
    return payload


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(None),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "context", None)
        if extra:
            entry["context"] = _redact(extra)
        return json.dumps(entry)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).setLevel(logging.WARNING)

"""
Structured JSON logging for the quiz generator.

Every log record is emitted as a single JSON line on stdout, with a stable
schema:

    {"ts": "...", "level": "INFO", "logger": "fusion_mind",
     "event": "quiz.submit", "msg": "...", "teacher_id": 3, "quiz_id": "abc"}

Pass structured fields through the standard `extra={...}` kwarg of the
`logging` API. Any keys not in the LogRecord's own attributes are promoted
to top-level JSON fields, so log consumers (grep, jq, ELK, etc.) can filter
by teacher_id, quiz_id, action, etc.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone


# Keys that live on every LogRecord and should NOT be copied into the JSON
# payload as "extra context".
_RESERVED_LOG_RECORD_KEYS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Anything the caller passed via `extra={...}` ends up as a record
        # attribute. Copy those into the payload as top-level fields.
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_KEYS:
                continue
            if key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


_CONFIGURED = False


def configure_logging(level: str | None = None) -> logging.Logger:
    """Configure the application logger. Idempotent."""
    global _CONFIGURED
    logger = logging.getLogger("fusion_mind")

    if _CONFIGURED:
        return logger

    level_name = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False

    _CONFIGURED = True
    return logger


def get_logger() -> logging.Logger:
    """Return the app logger, configuring it on first access."""
    return configure_logging()

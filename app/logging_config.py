"""Structured JSON logging to stdout (Twelve-Factor XI: logs as event streams).

The app never writes log files. Each record is one JSON object per line on
stdout, so Docker, Kubernetes (kubectl logs), Loki, Datadog, etc. can collect
and index it. We also route uvicorn's loggers through the same formatter so
access logs are JSON too.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

# Attributes every LogRecord has; anything else was passed via `extra=` and
# gets merged into the JSON payload (e.g. logger.info("x", extra={"job_id": j})).
_STD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STD_ATTRS and key != "color_message" and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Make uvicorn use our handler instead of its own text formatter.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
    # LiteLLM / httpx are chatty at INFO.
    for noisy in ("LiteLLM", "httpx", "neo4j"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))

import json
import logging
import logging.config
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

# Attributes present on every LogRecord; anything else was passed via `extra=`.
_RESERVED_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "request_id"}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in _RESERVED_ATTRS})
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    formatter = "json" if json_logs else "console"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {
                "json": {"()": JsonFormatter},
                "console": {
                    "format": "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s",
                },
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": formatter,
                    "filters": ["request_id"],
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {"handlers": ["default"], "level": level.upper()},
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": level.upper(), "propagate": False},
                "uvicorn.error": {
                    "handlers": ["default"],
                    "level": level.upper(),
                    "propagate": False,
                },
                # Access logs are emitted by RequestContextMiddleware instead.
                "uvicorn.access": {"handlers": [], "level": "WARNING", "propagate": False},
                "sqlalchemy.engine": {"level": "WARNING"},
            },
        }
    )

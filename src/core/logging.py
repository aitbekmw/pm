import logging
import logging.config
import sys
from typing import Any, Dict

try:
    from pythonjsonlogger.json import JsonFormatter

    _json_logger_available = True
except ModuleNotFoundError:
    # Fallback for environments where python-json-logger is absent or incompatible.
    JsonFormatter = logging.Formatter  # type: ignore[assignment]
    _json_logger_available = False

from src.core.config import settings
from src.core.middleware.request_id import get_request_id

# Idempotency flag
_logging_setup_done = False

class RequestIdFilter(logging.Filter):
    """Adds the `request_id` to log records."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True

if _json_logger_available:
    class CustomJsonFormatter(JsonFormatter):
        """Custom JSON formatter to guarantee specific fields exist for PROD/ELK."""

        def add_fields(
            self,
            log_data: Dict[str, Any],
            record: logging.LogRecord,
            message_dict: Dict[str, Any],
        ) -> None:
            super().add_fields(log_data, record, message_dict)
            if not log_data.get("timestamp"):
                log_data["timestamp"] = self.formatTime(record, self.datefmt)
            if log_data.get("level"):
                log_data["level"] = log_data["level"].upper()
            else:
                log_data["level"] = record.levelname

            # Optional: OpenTelemetry compatible traces placeholders.
            # Once otel is configured, trace_id and span_id can be injected here.
            if "trace_id" not in log_data:
                log_data["trace_id"] = ""
            if "span_id" not in log_data:
                log_data["span_id"] = ""
else:
    class CustomJsonFormatter(logging.Formatter):
        """Compatibility formatter if python-json-logger is unavailable."""

def setup_logging(level: str = None) -> None:
    """Configures the entire logging system for the application. Idempotent."""
    global _logging_setup_done
    if _logging_setup_done:
        return

    # Base configuration mapping
    if level is None:
        log_level = "DEBUG" if settings.debug else "INFO"
    else:
        log_level = level.upper()
    
    # DEV formatting (readable, structured nicely for console)
    dev_formatter = {
        "format": "%(asctime)s | %(levelname)-8s | [%(request_id)s] | %(name)s:%(lineno)d - %(message)s",
        "datefmt": "%Y-%m-%d %H:%M:%S",
    }
    
    # PROD formatting (JSON)
    prod_formatter = {
        "()": CustomJsonFormatter,
        "format": "%(timestamp)s %(level)s %(name)s %(message)s %(request_id)s %(module)s %(lineno)d %(http_method)s %(url_path)s %(status_code)s %(duration_ms)s",
        "datefmt": "%Y-%m-%dT%H:%M:%S%z"
    }

    formatter_config = dev_formatter if settings.debug or not _json_logger_available else prod_formatter

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id_filter": {
                "()": RequestIdFilter,
            }
        },
        "formatters": {
            "default": formatter_config,
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "default",
                "filters": ["request_id_filter"],
            },
        },
        "loggers": {
            # Application structure logs
            "src": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            # Uvicorn routing/error configurations
            "uvicorn.access": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            # FastAPI configuration
            "fastapi": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            # Prevent noisy DB logs unless DEBUG
            "sqlalchemy.engine": {
                "handlers": ["console"],
                "level": "WARNING" if not settings.debug else "INFO",
                "propagate": False,
            },
            # Background tasks
            "arq": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            }
        },
        "root": {
            "handlers": ["console"],
            "level": log_level,
        },
    }

    logging.config.dictConfig(logging_config)
    _logging_setup_done = True


def get_logger(name: str) -> logging.Logger:
    """Helper method to retrieve loggers systematically."""
    return logging.getLogger(name)


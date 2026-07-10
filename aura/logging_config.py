import contextvars
import logging
import os
from collections import deque
from typing import Optional
from pythonjsonlogger import jsonlogger
import sentry_sdk

# Context variable to hold request_id
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter to inject request_id and custom metadata."""
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        if not log_record.get("timestamp"):
            # Format as ISO 8601 string
            from datetime import datetime
            log_record["timestamp"] = datetime.utcfromtimestamp(record.created).isoformat() + "Z"
        if not log_record.get("level"):
            log_record["level"] = record.levelname
        if not log_record.get("logger"):
            log_record["logger"] = record.name

        # Inject request_id if set in the context
        req_id = request_id_var.get()
        if req_id:
            log_record["request_id"] = req_id
        elif "request_id" in log_record:
            del log_record["request_id"]

class MemoryLogHandler(logging.Handler):
    """In-memory handler keeping a rolling buffer of the last N log lines."""
    def __init__(self, capacity=500):
        super().__init__()
        self.capacity = capacity
        self.buffer = deque(maxlen=capacity)

    def emit(self, record):
        try:
            msg = self.format(record)
            self.buffer.append(msg)
        except Exception:
            self.handleError(record)

    def get_logs(self):
        return list(self.buffer)

# Global in-memory log buffer handler
memory_log_handler = MemoryLogHandler(capacity=500)

def setup_logging(level=logging.INFO, structured=True):
    """Configure structured logging, memory log buffer, and Sentry."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers to prevent duplicate messages
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Console Handler
    console_handler = logging.StreamHandler()
    
    if structured:
        # Structured JSON formatter
        formatter = CustomJsonFormatter(
            "%(timestamp)s %(level)s %(logger)s %(message)s %(request_id)s"
        )
    else:
        # Standard readable formatter for local development CLI if desired
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Memory Handler (always formats as JSON for API log output)
    json_formatter = CustomJsonFormatter(
        "%(timestamp)s %(level)s %(logger)s %(message)s %(request_id)s"
    )
    memory_log_handler.setFormatter(json_formatter)
    root_logger.addHandler(memory_log_handler)

    # Sentry SDK Init
    sentry_dsn = os.environ.get("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            traces_sample_rate=1.0,
        )
        logging.info("Sentry SDK initialized successfully.")

"""
Structured logging configuration for J.A.R.V.I.S. application.

Provides JSON-formatted logging for production environments with
human-readable fallback for development.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Optional


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in production."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # Add extra fields if present
        if hasattr(record, 'extra') and record.extra:
            log_entry.update(record.extra)

        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class DevelopmentFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, '')
        reset = self.RESET if color else ''

        timestamp = datetime.now().strftime('%H:%M:%S')
        location = f'{record.module}:{record.lineno}'

        base = f'{color}[{timestamp}] {record.levelname:8}{reset} {location:30} {record.getMessage()}'

        # Add extra fields if present
        if hasattr(record, 'extra') and record.extra:
            extras = ' | '.join(f'{k}={v}' for k, v in record.extra.items())
            base = f'{base} | {extras}'

        return base


def setup_logging(
    level: str = 'INFO',
    json_format: bool = None,
    logger_name: str = 'jarvis'
) -> logging.Logger:
    """Configure and return the application logger.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON formatting. If None, auto-detects based on environment.
        logger_name: Name for the logger instance.

    Returns:
        Configured logger instance.
    """
    # Auto-detect format based on environment
    if json_format is None:
        # Use JSON in production (when running under Gunicorn or with PRODUCTION env)
        json_format = os.environ.get('PRODUCTION', '').lower() == 'true' or \
                      'gunicorn' in os.environ.get('SERVER_SOFTWARE', '')

    # Get or create logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logger.level)

    # Set formatter based on environment
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(DevelopmentFormatter())

    logger.addHandler(handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str = 'jarvis') -> logging.Logger:
    """Get a logger instance. Creates child logger if name contains dots.

    Args:
        name: Logger name (e.g., 'jarvis.database', 'jarvis.parser')

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding extra fields to log records."""

    def __init__(self, logger: logging.Logger, **kwargs):
        self.logger = logger
        self.extra = kwargs
        self._old_factory = None

    def __enter__(self):
        self._old_factory = logging.getLogRecordFactory()

        extra = self.extra

        def record_factory(*args, **kwargs):
            record = self._old_factory(*args, **kwargs)
            record.extra = getattr(record, 'extra', {})
            record.extra.update(extra)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.setLogRecordFactory(self._old_factory)
        return False


def log_with_context(logger: logging.Logger, level: int, message: str, **context):
    """Log a message with additional context fields.

    Args:
        logger: Logger instance
        level: Log level (logging.INFO, logging.ERROR, etc.)
        message: Log message
        **context: Additional key-value pairs to include in log
    """
    record = logger.makeRecord(
        logger.name, level, '', 0, message, (), None
    )
    record.extra = context
    logger.handle(record)

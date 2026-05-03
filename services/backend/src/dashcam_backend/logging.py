"""Structured logging configuration for the dashcam backend service."""

import logging
import sys
from typing import Any, Dict, Optional
import structlog


def configure_logging(log_level: str = "INFO", service_name: str = "dashcam-backend") -> None:
    """Configure structured logging for the backend service."""
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer() if log_level.upper() == "DEBUG" else structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Add service context
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: str = "") -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def add_correlation_id(correlation_id: str) -> None:
    """Add correlation ID to logging context."""
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)


def add_request_context(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    video_id: Optional[str] = None,
) -> None:
    """Add request context to logging."""
    context = {}
    if user_id:
        context["user_id"] = user_id
    if session_id:
        context["session_id"] = session_id
    if task_id:
        context["task_id"] = task_id
    if worker_id:
        context["worker_id"] = worker_id
    if video_id:
        context["video_id"] = video_id
    
    if context:
        structlog.contextvars.bind_contextvars(**context)


def clear_context() -> None:
    """Clear logging context."""
    structlog.contextvars.clear_contextvars()


class LoggerMixin:
    """Mixin class that provides structured logging to any class."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = get_logger(self.__class__.__name__)
    
    def log_info(self, message: str, **kwargs) -> None:
        """Log info message with context."""
        self.logger.info(message, **kwargs)
    
    def log_error(self, message: str, error: Optional[Exception] = None, **kwargs) -> None:
        """Log error message with context."""
        if error:
            kwargs["error"] = str(error)
            kwargs["error_type"] = type(error).__name__
        self.logger.error(message, **kwargs)
    
    def log_warning(self, message: str, **kwargs) -> None:
        """Log warning message with context."""
        self.logger.warning(message, **kwargs)
    
    def log_debug(self, message: str, **kwargs) -> None:
        """Log debug message with context."""
        self.logger.debug(message, **kwargs)

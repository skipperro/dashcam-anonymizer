"""
Logging configuration for the Dashcam Worker.

Provides structured logging with appropriate levels and formatting.
"""

import structlog
import logging
import sys
from typing import Any, Dict

from .config import get_config


def setup_logging() -> structlog.BoundLogger:
    """
    Set up structured logging for the worker.
    
    Returns:
        Configured logger instance
    """
    config = get_config()
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, config.processing.log_level.upper())
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    return structlog.get_logger("dashcam_worker")


def log_worker_event(logger: structlog.BoundLogger, event_type: str, **kwargs: Any) -> None:
    """
    Log worker events with consistent structure.
    
    Args:
        logger: Configured logger instance
        event_type: Type of event (startup, shutdown, task_start, etc.)
        **kwargs: Additional event data
    """
    config = get_config()
    
    event_data = {
        "event_type": event_type,
        "worker_id": config.worker_id,
        "hostname": config.hostname,
        **kwargs
    }
    
    if event_type in ["error", "processing_error", "network_error"]:
        logger.error("Worker event", **event_data)
    elif event_type in ["warning", "memory_warning"]:
        logger.warning("Worker event", **event_data)
    else:
        logger.info("Worker event", **event_data)


def log_progress_milestone(logger: structlog.BoundLogger, task_id: str, progress: int, **kwargs: Any) -> None:
    """
    Log progress milestones (every 25%).
    
    Args:
        logger: Configured logger instance
        task_id: Task identifier
        progress: Progress percentage
        **kwargs: Additional progress data
    """
    if progress % 25 == 0:  # Log every 25%
        log_worker_event(
            logger, 
            "progress_milestone",
            task_id=task_id,
            progress_percentage=progress,
            **kwargs
        )


def log_resource_usage(logger: structlog.BoundLogger, cpu_percent: float, 
                      memory_percent: float, gpu_percent: float = None) -> None:
    """
    Log resource usage statistics.
    
    Args:
        logger: Configured logger instance
        cpu_percent: CPU usage percentage
        memory_percent: Memory usage percentage
        gpu_percent: GPU usage percentage (optional)
    """
    resource_data = {
        "cpu_percent": cpu_percent,
        "memory_percent": memory_percent
    }
    
    if gpu_percent is not None:
        resource_data["gpu_percent"] = gpu_percent
    
    log_worker_event(logger, "resource_usage", **resource_data)

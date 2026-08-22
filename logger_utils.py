"""
Logger Utilities for YoutubeAutomator
Provides structured logging and context managers to log timing and events for both file/console and DB storage.
"""

import time
import logging
from contextlib import contextmanager
from database import log_pipeline_event

logger = logging.getLogger("YoutubeAutomator")

@contextmanager
def stage_timer(pipeline_id: int | None, stage: str):
    """
    Context manager to time a pipeline stage and record performance/error metrics in database log.
    """
    start = time.monotonic()
    try:
        yield
        duration_ms = int((time.monotonic() - start) * 1000)
        message = f"Stage '{stage}' completed successfully in {duration_ms}ms"
        logger.info(f"[Pipeline {pipeline_id}] {message}")
        log_pipeline_event(pipeline_id, stage, "INFO", message, duration_ms=duration_ms)
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        message = f"Stage '{stage}' failed after {duration_ms}ms: {str(e)}"
        logger.error(f"[Pipeline {pipeline_id}] {message}")
        log_pipeline_event(pipeline_id, stage, "ERROR", message, duration_ms=duration_ms)
        raise

def log_event(pipeline_id: int | None, stage: str, level: str, message: str, duration_ms: int = None):
    """
    Helper function to record a single log entry to both Python logging and database.
    """
    lvl_upper = level.upper()
    if lvl_upper == "ERROR":
        logger.error(f"[Pipeline {pipeline_id}] [{stage}] {message}")
    elif lvl_upper == "WARNING":
        logger.warning(f"[Pipeline {pipeline_id}] [{stage}] {message}")
    else:
        logger.info(f"[Pipeline {pipeline_id}] [{stage}] {message}")

    log_pipeline_event(pipeline_id, stage, lvl_upper, message, duration_ms=duration_ms)

"""Logging utilities for WhisperFree."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from loguru import logger

from whisperfree.config import CONFIG_DIR


LOG_PATH = CONFIG_DIR / "whisperfree.log"


class InterceptHandler(logging.Handler):
    """Forward stdlib logging records into Loguru."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.bind(module=record.module).opt(depth=6, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(level: str = "INFO") -> None:
    """Initialise log sinks and intercept stdlib logging."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        LOG_PATH,
        rotation="1 MB",
        retention=5,
        enqueue=True,
        encoding="utf-8",
        level=level,
        backtrace=False,
        diagnose=False,
    )
    logger.add(lambda msg: print(msg, end=""), level=level)

    logging.basicConfig(handlers=[InterceptHandler()], level=level)


def get_logger(name: Optional[str] = None):
    """Return a module scoped logger bound to Loguru."""
    return logger.bind(name=name or "whisperfree")

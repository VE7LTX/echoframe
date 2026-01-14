"""Logging helpers."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(log_dir: str = "logs", level: int = logging.INFO) -> tuple[logging.Logger, str]:
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "echoframe.log")

    logger = logging.getLogger("echoframe")
    logger.setLevel(level)

    if not logger.handlers:
        handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3)
        fmt = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)

    return logger, log_path

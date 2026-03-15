"""Logging setup — coloured console via Rich."""

from __future__ import annotations

import logging
import sys

from rich.logging import RichHandler


def setup_logging(level: int = logging.INFO) -> None:
    handler = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        show_path=False,
    )
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
    )
    # Quiet noisy 3rd-party loggers
    for name in ("httpx", "httpcore", "urllib3", "PIL"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

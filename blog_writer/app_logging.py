"""Application logging setup for terminal-visible workflow events."""

from __future__ import annotations

import logging
import sys


LOGGER_NAME = "blog_writer"


def configure_terminal_logging() -> None:
    """Attach one stdout handler so app logs appear in the Streamlit terminal."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if any(getattr(handler, "_blog_writer_terminal", False) for handler in logger.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    )
    handler._blog_writer_terminal = True  # type: ignore[attr-defined]
    logger.addHandler(handler)


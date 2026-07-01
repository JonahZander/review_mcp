"""Logging helpers for consistent module-level instrumentation."""

import logging

DEFAULT_LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "event=%(message)s module=%(module)s func=%(funcName)s line=%(lineno)d"
)


def configure_logging(log_level: str = "INFO") -> None:
    """
    Configure process-wide logging.

    This function is idempotent for existing handlers and can be called safely during startup.
    """

    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(log_level.upper())
        return

    logging.basicConfig(level=log_level.upper(), format=DEFAULT_LOG_FORMAT)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger."""

    return logging.getLogger(name)

"""Logging configuration for the agent."""

import logging
import sys
from pathlib import Path

# Log file path
LOG_FILE_NAME = "agent_debug.log"
LOG_FILE = Path(LOG_FILE_NAME)

# Global flag to control debug output
DEBUG_ENABLED = False


def setup_logging(
    debug: bool = False,
    log_to_file: bool = False,
    log_file: str | Path | None = None,
):
    """Set up logging configuration.

    Args:
        debug: Whether to enable debug logging to console.
        log_to_file: Whether to write logs to file.
        log_file: Optional path for the log file.
    """
    global DEBUG_ENABLED
    DEBUG_ENABLED = debug

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Clear any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # File handler - only if log_to_file is True
    log_path = Path(log_file).expanduser().resolve() if log_file else LOG_FILE
    if log_to_file:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Console handler - always present, but level depends on debug
    console_formatter = logging.Formatter(
        "%(levelname)s: %(message)s"
    )
    console_handler = logging.StreamHandler(sys.stdout)

    if debug:
        console_handler.setLevel(logging.DEBUG)
    else:
        console_handler.setLevel(logging.WARNING)

    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Confirm logging setup
    status_parts = []
    if debug:
        status_parts.append("debug to console")
    if log_to_file:
        status_parts.append(f"logs to {log_path}")

    if status_parts:
        print(f"\033[90m[INFO] {', '.join(status_parts)}\033[0m")
    else:
        print("\033[90m[INFO] No logging configured\033[0m")


def get_logger(name: str) -> logging.Logger:
    """Get a named logger.

    Args:
        name: Logger name, usually __name__.

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)


def debug_print(*args, **kwargs):
    """Print debug messages only if DEBUG is enabled.

    Args:
        *args: Positional arguments to print.
        **kwargs: Keyword arguments to print.
    """
    if DEBUG_ENABLED:
        print(*args, **kwargs)

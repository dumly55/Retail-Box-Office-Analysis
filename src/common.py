"""Folders, logging and error messages shared by the sales analysis, the prediction report and the desktop app."""

import logging
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = PROJECT_ROOT / "logs"


def setup_logging(log_name: str) -> None:
    """Logs the full run detail to logs/<log_name>.log. Console output is handled separately via
    rich (progress bar, summary table, friendly errors), so no console handler here.

    Reconfigures the root logger's handlers on every call (rather than relying on
    `logging.basicConfig`'s "first call wins" behavior), so a long-lived process
    that runs more than once -- the GUI -- gets a fresh log file per run.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"{log_name}.log"

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.INFO)


def describe_error(exc: Exception) -> str:
    """Translates an exception into a plain-language message, shared by the CLI
    and the GUI so a network failure, bad data, etc. reads the same either way.
    """
    if isinstance(exc, requests.exceptions.RequestException):
        return "Couldn't download the source data. Check your internet connection and try again."
    if isinstance(exc, ValueError):
        return f"Invalid input data: {exc}"
    if isinstance(exc, OSError):
        return f"Couldn't read or write a required file: {exc}"
    return "Something went wrong. Check the log file for details."


def next_free_path(path: Path) -> Path:
    """Returns `path`, or "name (2).ext", "name (3).ext", ... if it already exists."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1

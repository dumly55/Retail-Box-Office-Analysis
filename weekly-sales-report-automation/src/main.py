"""CLI entrypoint: cleans a sales dataset and builds the sales analysis workbook.

Usage:
    python -m src.main
"""

import argparse
import logging
import sys
from pathlib import Path

import requests
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from .clean import QualityLog, clean_transactions, load_raw
from .download_data import (
    StatusCallback,
    ensure_raw_data,
    fetch_remote_dataset,
    load_local_dataset,
)
from .excel_report import build_workbook
from .findings import build_findings
from .normalize import detect_currency, parse_column_map, standardize
from .report import SalesReportData, build_report_data

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = PROJECT_ROOT / "logs"
DEMO_CURRENCY = "£"
DEFAULT_CURRENCY = "$"

console = Console()


def _parse_column_map(value: str) -> dict[str, str]:
    try:
        return parse_column_map(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean a sales dataset and build the sales analysis workbook.")
    parser.add_argument(
        "--data-url",
        default=None,
        help=(
            "Optional: a link to a CSV/Excel file, or a Google Sheet shared as "
            '"Anyone with the link can view", to use instead of the built-in demo dataset.'
        ),
    )
    parser.add_argument(
        "--data-file",
        default=None,
        help="Optional: path to a local CSV/Excel file to use instead of the built-in demo dataset. Takes priority over --data-url.",
    )
    parser.add_argument(
        "--column-map",
        default=None,
        type=_parse_column_map,
        help=(
            'Optional: tell the analysis which of your sheet\'s columns to use, e.g. "date=Order Placed, line_total=Net Sales". '
            "Only needed when automatic column recognition misses or picks the wrong column."
        ),
    )
    parser.add_argument(
        "--currency",
        default=None,
        help=(
            'Optional: currency symbol to show on amounts, e.g. "€". Defaults to the symbol used in your '
            'data\'s amounts (like "€1,200.00"), or "$" if there isn\'t one. The demo dataset is in £.'
        ),
    )
    return parser.parse_args()


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


def run_pipeline(
    data_url: str | None = None,
    data_file: str | Path | None = None,
    column_map: dict[str, str] | None = None,
    currency: str | None = None,
    status_callback: StatusCallback | None = None,
) -> tuple[SalesReportData, QualityLog, Path]:
    """Runs the full pipeline (fetch -> clean -> compute KPIs -> build workbook)
    and returns the results. Shared by the CLI and the GUI -- neither one owns
    this logic, they just present it differently.

    `data_file` (a local path) takes priority over `data_url` (a link), which
    takes priority over the built-in demo dataset. `currency` overrides the
    symbol otherwise detected from the data. `status_callback`, if given,
    receives a short human-readable string at each stage instead of the CLI's
    console/log output.
    """
    notify = status_callback or (lambda _msg: None)
    logger = logging.getLogger("main")

    if data_file or data_url:
        if data_file:
            raw_df = load_local_dataset(Path(data_file), status_callback=status_callback)
        else:
            raw_df = fetch_remote_dataset(data_url, status_callback=status_callback)
        detected_currency = detect_currency(raw_df) or DEFAULT_CURRENCY
    else:
        notify("Checking for the cached demo dataset...")
        raw_path = ensure_raw_data(status_callback=status_callback)
        notify("Loading dataset...")
        raw_df = load_raw(raw_path)
        detected_currency = DEMO_CURRENCY
    if currency is None:
        currency = detected_currency
    logger.info("Currency symbol: %r", currency)

    notify("Matching the sheet's columns...")
    raw_df, _ = standardize(raw_df, column_map)

    notify("Cleaning and validating data...")
    sales_df, cancellations_df, quality_log = clean_transactions(raw_df)

    notify("Computing KPIs...")
    report_data = build_report_data(sales_df, cancellations_df, currency)
    report_data.findings = build_findings(sales_df, report_data)

    notify("Building the Excel workbook...")
    out_path = next_free_path(OUTPUT_DIR / "sales_analysis.xlsx")
    build_workbook(report_data, quality_log, out_path, organized_rows=sales_df)
    logger.info("Workbook written to %s", out_path)

    notify("Done.")
    return report_data, quality_log, out_path


def _print_summary(report_data: SalesReportData, out_path: Path) -> None:
    table = Table(title=f"Sales Analysis - {report_data.period_label}", title_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    for metric, value in report_data.summary_rows():
        table.add_row(metric, value)

    console.print()
    console.print(table)
    if report_data.findings:
        console.print("\n[bold cyan]Key findings[/bold cyan]")
        for finding in report_data.findings:
            console.print(f"  • {escape(finding)}")
        console.print()
    console.print(f"[bold green]Workbook written[/bold green] to [bold]{out_path}[/bold]\n")


def main() -> None:
    args = parse_args()
    setup_logging("sales_analysis")
    logger = logging.getLogger("main")
    logger.info("Starting sales analysis run")

    try:
        report_data, _quality_log, out_path = run_pipeline(
            data_url=args.data_url,
            data_file=args.data_file,
            column_map=args.column_map,
            currency=args.currency,
        )
    except Exception as exc:
        logger.exception("Sales analysis failed")
        console.print(f"[bold red]Error:[/bold red] {describe_error(exc)}")
        sys.exit(1)

    _print_summary(report_data, out_path)


if __name__ == "__main__":
    main()

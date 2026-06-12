"""Download Databento historical CME MBP-1 data to the M3A CSV format."""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MISSING_DATABENTO_MESSAGE = (
    "Install databento or set up optional dependencies to use this command."
)
MISSING_API_KEY_MESSAGE = "Set DATABENTO_API_KEY to use this command."
CSV_COLUMNS = ["timestamp", "symbol", "bid_price", "ask_price", "last_price"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download Databento historical CME MBP-1 data as an M3A-compatible CSV."
    )
    parser.add_argument("--dataset", default="GLBX.MDP3")
    parser.add_argument("--schema", default="mbp-1")
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        print(MISSING_API_KEY_MESSAGE, file=sys.stderr)
        return 2

    try:
        databento = _import_databento()
    except ModuleNotFoundError:
        print(MISSING_DATABENTO_MESSAGE, file=sys.stderr)
        return 2

    try:
        download_mbp1_to_csv(
            databento_module=databento,
            api_key=api_key,
            dataset=args.dataset,
            schema=args.schema,
            symbols=_parse_symbols(args.symbols),
            start=args.start,
            end=args.end,
            out=args.out,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def download_mbp1_to_csv(
    *,
    databento_module: Any,
    api_key: str,
    dataset: str,
    schema: str,
    symbols: list[str],
    start: str,
    end: str,
    out: str | Path,
) -> None:
    if schema != "mbp-1":
        raise ValueError("Only Databento schema mbp-1 is supported for this command.")

    client = databento_module.Historical(api_key)
    store = client.timeseries.get_range(
        dataset=dataset,
        schema=schema,
        symbols=symbols,
        start=start,
        end=end,
    )
    rows = list(_m3a_rows(store, fallback_symbol=symbols[0] if len(symbols) == 1 else ""))
    with Path(out).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _import_databento() -> Any:
    import databento  # type: ignore[import-not-found]

    return databento


def _parse_symbols(value: str) -> list[str]:
    symbols = [symbol.strip() for symbol in value.split(",") if symbol.strip()]
    if not symbols:
        raise ValueError("At least one Databento symbol is required.")
    return symbols


def _m3a_rows(store: Any, *, fallback_symbol: str) -> Iterable[dict[str, str]]:
    if hasattr(store, "to_df"):
        frame = store.to_df()
        records = frame.to_dict("records")
    else:
        records = store

    for record in records:
        row = _record_to_mapping(record)
        yield {
            "timestamp": _format_timestamp(_first_present(row, ["ts_event", "ts_recv", "timestamp"])),
            "symbol": str(_first_present(row, ["symbol", "raw_symbol", "stype_in_symbol"]) or fallback_symbol),
            "bid_price": _format_price(_first_present(row, ["bid_px_00", "bid_price", "bid"])),
            "ask_price": _format_price(_first_present(row, ["ask_px_00", "ask_price", "ask"])),
            "last_price": _format_price(_first_present(row, ["price", "last_price", "last"])),
        }


def _record_to_mapping(record: Any) -> dict[str, Any]:
    if isinstance(record, dict):
        return record
    if hasattr(record, "_asdict"):
        return dict(record._asdict())
    if hasattr(record, "__dict__"):
        return vars(record)
    raise TypeError(f"Unsupported Databento record type: {type(record).__name__}")


def _first_present(row: dict[str, Any], columns: list[str]) -> Any:
    for column in columns:
        value = row.get(column)
        if value is not None and value != "":
            return value
    return None


def _format_timestamp(value: Any) -> str:
    if _is_missing(value):
        return ""
    if hasattr(value, "isoformat"):
        iso_value = value.isoformat()
        return iso_value.replace("+00:00", "Z")
    if isinstance(value, int):
        dt = datetime.fromtimestamp(value / 1_000_000_000, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    return str(value)


def _format_price(value: Any) -> str:
    if _is_missing(value):
        return ""
    return str(value)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value) == "NaT"


if __name__ == "__main__":
    raise SystemExit(main())

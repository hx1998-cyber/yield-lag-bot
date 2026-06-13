"""Batch-run historical CME vs crypto event studies."""

from __future__ import annotations

import argparse
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from yield_lag_bot.config import load_settings
from yield_lag_bot.jobs.download_cme_databento import _import_databento, download_mbp1_to_csv
from yield_lag_bot.jobs.download_hyperliquid_candles import download_candles_to_csv
from yield_lag_bot.jobs.run_event_study import FAILED_COLUMNS, SUMMARY_COLUMNS, run_event_study

AGGREGATE_COLUMNS = [
    "event_name",
    "event_time_utc",
    "cme_symbol",
    "crypto_symbol",
    "start",
    "end",
    "status",
    "sample_count",
    "cme_nonzero_return_count",
    "cme_abs_return_bps_max",
    "correlation_1m",
    "correlation_3m",
    "correlation_5m",
    "direction_hit_rate_1m",
    "direction_hit_rate_3m",
    "direction_hit_rate_5m",
    "quality_status",
    "result_path",
    "summary_path",
    "error_message",
]


@dataclass(frozen=True, slots=True)
class EventBatchItem:
    event_name: str
    event_time_utc: str
    pre_minutes: int
    post_minutes: int
    cme_symbols: tuple[str, ...]
    crypto_symbols: tuple[str, ...]
    cme_dataset: str
    cme_schema: str
    crypto_interval: str


@dataclass(frozen=True, slots=True)
class EventBatchConfig:
    events: tuple[EventBatchItem, ...]


@dataclass(frozen=True, slots=True)
class EventBatchPlan:
    event: EventBatchItem
    event_time_utc: str
    start: str
    end: str
    event_dir: Path
    cme_paths: dict[str, Path]
    cme_cache_paths: dict[str, Path]
    cme_cache_matches: dict[str, Path | None]
    crypto_paths: dict[str, Path]
    crypto_cache_paths: dict[str, Path]
    crypto_cache_matches: dict[str, Path | None]
    pair_paths: dict[tuple[str, str], tuple[Path, Path]]
    cme_large_download_blocked: bool
    cme_large_download_message: str


CmeDownloadFunc = Callable[..., None]
CryptoDownloadFunc = Callable[..., None]
EventStudyFunc = Callable[..., None]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reuse-existing", action="store_true")
    parser.add_argument("--allow-large-cme-download", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = load_event_batch_config(args.config)
    settings = load_settings()
    summary_path = run_event_batch(
        config=config,
        data_root=settings.data_root,
        dry_run=args.dry_run,
        reuse_existing=args.reuse_existing,
        allow_large_cme_download=args.allow_large_cme_download,
    )
    if not args.dry_run:
        print(f"Wrote event batch summary: {summary_path}")


def load_event_batch_config(path: str | Path) -> EventBatchConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("Event batch config must be a YAML mapping")
    raw_events = raw.get("events")
    if raw_events is None:
        raw_events = [raw]
    if not isinstance(raw_events, list) or not raw_events:
        raise ValueError("Event batch config requires at least one event")
    return EventBatchConfig(events=tuple(_load_event(item) for item in raw_events))


def run_event_batch(
    *,
    config: EventBatchConfig,
    data_root: str | Path,
    cme_download_func: CmeDownloadFunc | None = None,
    crypto_download_func: CryptoDownloadFunc | None = None,
    event_study_func: EventStudyFunc = run_event_study,
    dry_run: bool = False,
    reuse_existing: bool = False,
    allow_large_cme_download: bool = False,
) -> Path:
    root = Path(data_root)
    events_root = root / "reports" / "events"
    if dry_run:
        _print_dry_run(
            config=config,
            data_root=root,
            events_root=events_root,
            allow_large_cme_download=allow_large_cme_download,
        )
        return events_root / "summary.csv"

    events_root.mkdir(parents=True, exist_ok=True)
    aggregate_rows: list[dict[str, object]] = []
    for event in config.events:
        aggregate_rows.extend(
            _run_event(
                event=event,
                events_root=events_root,
                cme_download_func=cme_download_func or _download_cme_csv,
                crypto_download_func=crypto_download_func or download_candles_to_csv,
                event_study_func=event_study_func,
                reuse_existing=reuse_existing,
                allow_large_cme_download=allow_large_cme_download,
            )
        )
    summary_path = events_root / "summary.csv"
    pd.DataFrame(aggregate_rows, columns=AGGREGATE_COLUMNS).to_csv(summary_path, index=False)
    return summary_path


def _run_event(
    *,
    event: EventBatchItem,
    events_root: Path,
    cme_download_func: CmeDownloadFunc,
    crypto_download_func: CryptoDownloadFunc,
    event_study_func: EventStudyFunc,
    reuse_existing: bool,
    allow_large_cme_download: bool,
) -> list[dict[str, object]]:
    data_root = events_root.parent.parent
    plan = _build_event_plan(event=event, data_root=data_root, events_root=events_root)
    start_iso = plan.start
    end_iso = plan.end
    event_dir = plan.event_dir
    event_dir.mkdir(parents=True, exist_ok=True)

    cme_paths: dict[str, Path] = {}
    cme_errors: dict[str, str] = {}
    for cme_symbol in event.cme_symbols:
        path = plan.cme_paths[cme_symbol]
        cache_path = plan.cme_cache_paths[cme_symbol]
        try:
            if reuse_existing and _is_nonempty_file(path):
                print(f"Reusing existing CME CSV for {cme_symbol}: {path}")
            elif reuse_existing and plan.cme_cache_matches[cme_symbol] is not None:
                central_cache_path = plan.cme_cache_matches[cme_symbol]
                print(f"Reusing central cache: {central_cache_path}")
                _copy_to_event_path(central_cache_path, path)
            else:
                _raise_if_large_cme_download_blocked(
                    plan=plan,
                    allow_large_cme_download=allow_large_cme_download,
                )
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cme_download_func(
                    dataset=event.cme_dataset,
                    schema=event.cme_schema,
                    symbols=[cme_symbol],
                    start=start_iso,
                    end=end_iso,
                    out=cache_path,
                )
                _copy_to_event_path(cache_path, path)
            cme_paths[cme_symbol] = path
        except Exception as exc:  # noqa: BLE001 - batch summary should capture per-symbol failures.
            cme_errors[cme_symbol] = str(exc)

    crypto_paths: dict[str, Path] = {}
    crypto_errors: dict[str, str] = {}
    for crypto_symbol in event.crypto_symbols:
        path = plan.crypto_paths[crypto_symbol]
        cache_path = plan.crypto_cache_paths[crypto_symbol]
        try:
            if reuse_existing and _is_nonempty_file(path):
                print(f"Reusing existing Hyperliquid candle CSV for {crypto_symbol}: {path}")
            elif reuse_existing and plan.crypto_cache_matches[crypto_symbol] is not None:
                central_cache_path = plan.crypto_cache_matches[crypto_symbol]
                print(f"Reusing central cache: {central_cache_path}")
                _copy_to_event_path(central_cache_path, path)
            else:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                crypto_download_func(
                    coin=crypto_symbol,
                    interval=event.crypto_interval,
                    start=start_iso,
                    end=end_iso,
                    out=cache_path,
                )
                _copy_to_event_path(cache_path, path)
            crypto_paths[crypto_symbol] = path
        except Exception as exc:  # noqa: BLE001 - batch summary should capture per-symbol failures.
            crypto_errors[crypto_symbol] = str(exc)

    rows: list[dict[str, object]] = []
    for cme_symbol in event.cme_symbols:
        for crypto_symbol in event.crypto_symbols:
            result_path, summary_path = plan.pair_paths[(cme_symbol, crypto_symbol)]
            blocking_error = cme_errors.get(cme_symbol) or crypto_errors.get(crypto_symbol)
            if blocking_error is not None:
                _write_pair_failure_outputs(
                    cme_symbol=cme_symbol,
                    crypto_symbol=crypto_symbol,
                    start=start_iso,
                    end=end_iso,
                    result_path=result_path,
                    summary_path=summary_path,
                    error_message=blocking_error,
                )
                rows.append(
                    _aggregate_failure_row(
                        event=event,
                        cme_symbol=cme_symbol,
                        crypto_symbol=crypto_symbol,
                        start=start_iso,
                        end=end_iso,
                        result_path=result_path,
                        summary_path=summary_path,
                        error_message=blocking_error,
                    )
                )
                continue
            rows.append(
                _run_pair(
                    event=event,
                    cme_symbol=cme_symbol,
                    crypto_symbol=crypto_symbol,
                    start=start_iso,
                    end=end_iso,
                    cme_csv=cme_paths[cme_symbol],
                    crypto_csv=crypto_paths[crypto_symbol],
                    result_path=result_path,
                    summary_path=summary_path,
                    event_study_func=event_study_func,
                )
            )
    return rows


def _build_event_plan(*, event: EventBatchItem, data_root: Path, events_root: Path) -> EventBatchPlan:
    event_time = _parse_iso_utc(event.event_time_utc)
    start = event_time - pd.Timedelta(minutes=event.pre_minutes)
    end = event_time + pd.Timedelta(minutes=event.post_minutes)
    start_token = _cache_time_token(start)
    end_token = _cache_time_token(end)
    event_dir = events_root / _safe_token(event.event_name)
    cme_paths = {
        cme_symbol: event_dir / f"{_safe_token(cme_symbol)}__cme.csv"
        for cme_symbol in event.cme_symbols
    }
    cme_cache_paths = {
        cme_symbol: _cme_cache_dir(data_root, event.cme_schema)
        / f"cme_{_safe_token(cme_symbol)}_{start_token}_{end_token}.csv"
        for cme_symbol in event.cme_symbols
    }
    cme_cache_matches = {
        cme_symbol: _first_nonempty_match(
            _cme_cache_dir(data_root, event.cme_schema).glob(
                f"cme_{_safe_token(cme_symbol)}*{start_token}*{end_token}.csv"
            )
        )
        for cme_symbol in event.cme_symbols
    }
    crypto_paths = {
        crypto_symbol: event_dir / f"{_safe_token(crypto_symbol)}__candles.csv"
        for crypto_symbol in event.crypto_symbols
    }
    crypto_cache_paths = {
        crypto_symbol: _crypto_cache_dir(data_root)
        / f"{_safe_token(crypto_symbol)}_{_safe_token(event.crypto_interval)}_{start_token}_{end_token}.csv"
        for crypto_symbol in event.crypto_symbols
    }
    crypto_cache_matches = {
        crypto_symbol: _first_nonempty_match(
            _crypto_cache_dir(data_root).glob(
                f"{_safe_token(crypto_symbol)}*{_safe_token(event.crypto_interval)}*"
                f"{start_token}_{end_token}.csv"
            )
        )
        for crypto_symbol in event.crypto_symbols
    }
    pair_paths = {
        (cme_symbol, crypto_symbol): (
            event_dir / f"{_safe_token(cme_symbol)}__{_safe_token(crypto_symbol)}__event_detail.csv",
            event_dir / f"{_safe_token(cme_symbol)}__{_safe_token(crypto_symbol)}__event_summary.csv",
        )
        for cme_symbol in event.cme_symbols
        for crypto_symbol in event.crypto_symbols
    }
    return EventBatchPlan(
        event=event,
        event_time_utc=_format_iso_utc(event_time),
        start=_format_iso_utc(start),
        end=_format_iso_utc(end),
        event_dir=event_dir,
        cme_paths=cme_paths,
        cme_cache_paths=cme_cache_paths,
        cme_cache_matches=cme_cache_matches,
        crypto_paths=crypto_paths,
        crypto_cache_paths=crypto_cache_paths,
        crypto_cache_matches=crypto_cache_matches,
        pair_paths=pair_paths,
        cme_large_download_blocked=_large_cme_download_blocked(event=event, start=start, end=end),
        cme_large_download_message=_large_cme_download_message(event=event, start=start, end=end),
    )


def _print_dry_run(
    *,
    config: EventBatchConfig,
    data_root: Path,
    events_root: Path,
    allow_large_cme_download: bool,
) -> None:
    print("M3G dry run: no downloads or reports will be written.")
    print(f"expected aggregate output path: {events_root / 'summary.csv'}")
    for event in config.events:
        plan = _build_event_plan(event=event, data_root=data_root, events_root=events_root)
        print("")
        print(f"event_name: {event.event_name}")
        print(f"event_time_utc: {plan.event_time_utc}")
        print(f"start: {plan.start}")
        print(f"end: {plan.end}")
        print(f"cme_symbols: {', '.join(event.cme_symbols)}")
        print(f"crypto_symbols: {', '.join(event.crypto_symbols)}")
        print("expected CME CSV paths:")
        for symbol, path in plan.cme_paths.items():
            print(f"  {symbol}: {path}")
        print("expected CME central cache paths:")
        for symbol, path in plan.cme_cache_paths.items():
            match = plan.cme_cache_matches[symbol]
            exists = _is_nonempty_file(path) or match is not None
            print(f"  {symbol}: {path} exists={exists}")
            if match is not None and match != path:
                print(f"  {symbol} matched central cache: {match}")
        guard_blocked = plan.cme_large_download_blocked and not allow_large_cme_download
        print(f"large CME guard would block request: {guard_blocked}")
        if guard_blocked:
            print(f"large CME guard message: {plan.cme_large_download_message}")
        print("expected Hyperliquid candle CSV paths:")
        for symbol, path in plan.crypto_paths.items():
            print(f"  {symbol}: {path}")
        print("expected Hyperliquid central cache paths:")
        for symbol, path in plan.crypto_cache_paths.items():
            match = plan.crypto_cache_matches[symbol]
            exists = _is_nonempty_file(path) or match is not None
            print(f"  {symbol}: {path} exists={exists}")
            if match is not None and match != path:
                print(f"  {symbol} matched central cache: {match}")
        print("expected event study output paths:")
        for (cme_symbol, crypto_symbol), (detail_path, summary_path) in plan.pair_paths.items():
            print(f"  {cme_symbol}->{crypto_symbol} detail: {detail_path}")
            print(f"  {cme_symbol}->{crypto_symbol} summary: {summary_path}")


def _is_nonempty_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _first_nonempty_match(paths) -> Path | None:
    matches = sorted(path for path in paths if _is_nonempty_file(path))
    return matches[0] if matches else None


def _copy_to_event_path(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _cme_cache_dir(data_root: Path, schema: str) -> Path:
    return data_root / "cme" / "databento" / _schema_cache_token(schema)


def _crypto_cache_dir(data_root: Path) -> Path:
    return data_root / "hyperliquid" / "candles"


def _schema_cache_token(schema: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", schema).lower()


def _cache_time_token(value: pd.Timestamp | datetime) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(timezone.utc)
    return timestamp.tz_convert(timezone.utc).strftime("%Y%m%d_%H%M")


def _large_cme_download_blocked(*, event: EventBatchItem, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    return _schema_cache_token(event.cme_schema) == "mbp1" and (end - start) > pd.Timedelta(minutes=30)


def _large_cme_download_message(*, event: EventBatchItem, start: pd.Timestamp, end: pd.Timestamp) -> str:
    minutes = int((end - start).total_seconds() / 60)
    return (
        f"CME download guard blocked {event.cme_schema} request for {minutes} minutes. "
        "mbp-1 is high-volume; use a shorter window, reuse existing files, or explicitly pass "
        "--allow-large-cme-download."
    )


def _raise_if_large_cme_download_blocked(
    *,
    plan: EventBatchPlan,
    allow_large_cme_download: bool,
) -> None:
    if plan.cme_large_download_blocked and not allow_large_cme_download:
        raise ValueError(plan.cme_large_download_message)


def _run_pair(
    *,
    event: EventBatchItem,
    cme_symbol: str,
    crypto_symbol: str,
    start: str,
    end: str,
    cme_csv: Path,
    crypto_csv: Path,
    result_path: Path,
    summary_path: Path,
    event_study_func: EventStudyFunc,
) -> dict[str, object]:
    try:
        event_study_func(
            cme_csv=cme_csv,
            crypto_csv=crypto_csv,
            out=result_path,
            summary_out=summary_path,
            cme_symbol=cme_symbol,
            crypto_symbol=crypto_symbol,
        )
        summary = pd.read_csv(summary_path)
        if summary.empty:
            raise ValueError("event study summary is empty")
        row = summary.iloc[0]
        return {
            "event_name": event.event_name,
            "event_time_utc": _format_iso_utc(_parse_iso_utc(event.event_time_utc)),
            "cme_symbol": cme_symbol,
            "crypto_symbol": crypto_symbol,
            "start": start,
            "end": end,
            "status": row.get("status", ""),
            "sample_count": row.get("sample_count", 0),
            "cme_nonzero_return_count": row.get("cme_nonzero_return_count", 0),
            "cme_abs_return_bps_max": row.get("cme_abs_return_bps_max", float("nan")),
            "correlation_1m": row.get("correlation_1m", float("nan")),
            "correlation_3m": row.get("correlation_3m", float("nan")),
            "correlation_5m": row.get("correlation_5m", float("nan")),
            "direction_hit_rate_1m": row.get("direction_hit_rate_1m", float("nan")),
            "direction_hit_rate_3m": row.get("direction_hit_rate_3m", float("nan")),
            "direction_hit_rate_5m": row.get("direction_hit_rate_5m", float("nan")),
            "quality_status": row.get("quality_status", ""),
            "result_path": str(result_path),
            "summary_path": str(summary_path),
            "error_message": "" if pd.isna(row.get("error_message", "")) else row.get("error_message", ""),
        }
    except Exception as exc:  # noqa: BLE001 - continue remaining pairs.
        _write_pair_failure_outputs(
            cme_symbol=cme_symbol,
            crypto_symbol=crypto_symbol,
            start=start,
            end=end,
            result_path=result_path,
            summary_path=summary_path,
            error_message=str(exc),
        )
        return _aggregate_failure_row(
            event=event,
            cme_symbol=cme_symbol,
            crypto_symbol=crypto_symbol,
            start=start,
            end=end,
            result_path=result_path,
            summary_path=summary_path,
            error_message=str(exc),
        )


def _aggregate_failure_row(
    *,
    event: EventBatchItem,
    cme_symbol: str,
    crypto_symbol: str,
    start: str,
    end: str,
    result_path: Path,
    summary_path: Path,
    error_message: str,
) -> dict[str, object]:
    return {
        "event_name": event.event_name,
        "event_time_utc": _format_iso_utc(_parse_iso_utc(event.event_time_utc)),
        "cme_symbol": cme_symbol,
        "crypto_symbol": crypto_symbol,
        "start": start,
        "end": end,
        "status": "failed",
        "sample_count": 0,
        "cme_nonzero_return_count": 0,
        "cme_abs_return_bps_max": float("nan"),
        "correlation_1m": float("nan"),
        "correlation_3m": float("nan"),
        "correlation_5m": float("nan"),
        "direction_hit_rate_1m": float("nan"),
        "direction_hit_rate_3m": float("nan"),
        "direction_hit_rate_5m": float("nan"),
        "quality_status": "insufficient_data",
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "error_message": error_message,
    }


def _write_pair_failure_outputs(
    *,
    cme_symbol: str,
    crypto_symbol: str,
    start: str,
    end: str,
    result_path: Path,
    summary_path: Path,
    error_message: str,
) -> None:
    result_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    detail_row = {
        "status": "failed",
        "error_message": error_message,
        "cme_symbol": cme_symbol.upper(),
        "crypto_symbol": crypto_symbol.upper(),
        "cme_start": start,
        "cme_end": end,
        "crypto_start": start,
        "crypto_end": end,
        "overlap_seconds": 0.0,
    }
    summary_row = {
        "status": "failed",
        "error_message": error_message,
        "cme_symbol": cme_symbol.upper(),
        "crypto_symbol": crypto_symbol.upper(),
        "start": start,
        "end": end,
        "sample_count": 0,
        "valid_cme_return_count": 0,
        "valid_forward_1m_count": 0,
        "valid_forward_3m_count": 0,
        "valid_forward_5m_count": 0,
        "cme_nonzero_return_count": 0,
        "cme_abs_return_bps_mean": float("nan"),
        "cme_abs_return_bps_max": float("nan"),
        "crypto_abs_forward_1m_bps_mean": float("nan"),
        "crypto_abs_forward_3m_bps_mean": float("nan"),
        "crypto_abs_forward_5m_bps_mean": float("nan"),
        "correlation_1m": float("nan"),
        "correlation_3m": float("nan"),
        "correlation_5m": float("nan"),
        "direction_hit_rate_1m": float("nan"),
        "direction_hit_rate_3m": float("nan"),
        "direction_hit_rate_5m": float("nan"),
        "quality_status": "insufficient_data",
    }
    pd.DataFrame([detail_row], columns=FAILED_COLUMNS).to_csv(result_path, index=False)
    pd.DataFrame([summary_row], columns=SUMMARY_COLUMNS).to_csv(summary_path, index=False)


def _download_cme_csv(
    *,
    dataset: str,
    schema: str,
    symbols: list[str],
    start: str,
    end: str,
    out: str | Path,
) -> None:
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        raise ValueError("Set DATABENTO_API_KEY to use this command.")
    download_mbp1_to_csv(
        databento_module=_import_databento(),
        api_key=api_key,
        dataset=dataset,
        schema=schema,
        symbols=symbols,
        start=start,
        end=end,
        out=out,
    )


def _load_event(raw: object) -> EventBatchItem:
    if not isinstance(raw, dict):
        raise ValueError("Each event must be a YAML mapping")
    return EventBatchItem(
        event_name=_required_str(raw, "event_name"),
        event_time_utc=_required_str(raw, "event_time_utc"),
        pre_minutes=_required_int(raw, "pre_minutes"),
        post_minutes=_required_int(raw, "post_minutes"),
        cme_symbols=_required_str_tuple(raw, "cme_symbols"),
        crypto_symbols=_required_str_tuple(raw, "crypto_symbols"),
        cme_dataset=_required_str(raw, "cme_dataset"),
        cme_schema=_required_str(raw, "cme_schema"),
        crypto_interval=_required_str(raw, "crypto_interval"),
    )


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Event config field {key!r} must be a non-empty string")
    return value


def _required_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Event config field {key!r} must be an integer")
    return value


def _required_str_tuple(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"Event config field {key!r} must be a non-empty list")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Event config field {key!r} must contain only non-empty strings")
    return tuple(value)


def _parse_iso_utc(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(datetime.fromisoformat(value.replace("Z", "+00:00")))
    if timestamp.tzinfo is None:
        return timestamp.tz_localize(timezone.utc)
    return timestamp.tz_convert(timezone.utc)


def _format_iso_utc(value: pd.Timestamp | datetime) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(timezone.utc)
    return timestamp.tz_convert(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


if __name__ == "__main__":
    main()

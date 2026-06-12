"""Run repeatable CME Treasury futures vs Hyperliquid BBO research experiments."""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from yield_lag_bot.jobs.run_lead_lag_study import run_study

SUMMARY_COLUMNS = [
    "experiment_name",
    "window_name",
    "cme_symbol",
    "crypto_symbol",
    "result_path",
    "rows_written",
    "status",
    "error_message",
]


@dataclass(frozen=True, slots=True)
class ExperimentWindow:
    name: str
    start: str
    end: str
    cme_symbols: tuple[str, ...]
    crypto_symbols: tuple[str, ...]
    dataset: str
    schema: str
    cme_csv: Path | None = None
    crypto_csv: Path | None = None


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    experiment_name: str
    output_dir: Path
    windows: tuple[ExperimentWindow, ...]


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    if not isinstance(raw, dict):
        raise ValueError("Experiment config must be a YAML mapping")

    experiment_name = _required_str(raw, "experiment_name")
    output_dir = _resolve_path(_required_str(raw, "output_dir"), base_dir=config_path.parent)
    windows_raw = raw.get("windows")
    if not isinstance(windows_raw, list) or not windows_raw:
        raise ValueError("Experiment config requires at least one window")

    windows = tuple(_load_window(item, config_path.parent) for item in windows_raw)
    return ExperimentConfig(
        experiment_name=experiment_name,
        output_dir=output_dir,
        windows=windows,
    )


def run_experiment(config: ExperimentConfig) -> Path:
    experiment_dir = config.output_dir / _safe_token(config.experiment_name)
    summary_rows: list[dict[str, object]] = []

    for window in config.windows:
        window_dir = experiment_dir / _safe_token(window.name)
        window_dir.mkdir(parents=True, exist_ok=True)
        for cme_symbol in window.cme_symbols:
            for crypto_symbol in window.crypto_symbols:
                result_path = (
                    window_dir
                    / f"{_safe_token(cme_symbol)}__{_safe_token(crypto_symbol)}__lead_lag.csv"
                )
                summary_rows.append(
                    _run_pair(
                        experiment_name=config.experiment_name,
                        window=window,
                        window_dir=window_dir,
                        cme_symbol=cme_symbol,
                        crypto_symbol=crypto_symbol,
                        result_path=result_path,
                    )
                )

    experiment_dir.mkdir(parents=True, exist_ok=True)
    summary_path = experiment_dir / "summary.csv"
    pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS).to_csv(summary_path, index=False)
    return summary_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to experiment YAML config")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary_path = run_experiment(load_experiment_config(args.config))
    print(f"Wrote experiment summary: {summary_path}")


def _load_window(raw: object, base_dir: Path) -> ExperimentWindow:
    if not isinstance(raw, dict):
        raise ValueError("Each experiment window must be a YAML mapping")

    return ExperimentWindow(
        name=_required_str(raw, "name"),
        start=_required_str(raw, "start"),
        end=_required_str(raw, "end"),
        cme_symbols=_required_str_tuple(raw, "cme_symbols"),
        crypto_symbols=_required_str_tuple(raw, "crypto_symbols"),
        dataset=_required_str(raw, "dataset"),
        schema=_required_str(raw, "schema"),
        cme_csv=_optional_path(raw, "cme_csv", base_dir=base_dir),
        crypto_csv=_optional_path(raw, "crypto_csv", base_dir=base_dir),
    )


def _run_pair(
    *,
    experiment_name: str,
    window: ExperimentWindow,
    window_dir: Path,
    cme_symbol: str,
    crypto_symbol: str,
    result_path: Path,
) -> dict[str, object]:
    cme_csv = window.cme_csv or window_dir / f"{_safe_token(cme_symbol)}__cme_ticks.csv"
    crypto_csv = window.crypto_csv or window_dir / f"{_safe_token(crypto_symbol)}__ticks_bbo.csv"

    try:
        run_study(
            cme_csv=cme_csv,
            crypto_csv=crypto_csv,
            out=result_path,
            cme_symbol=cme_symbol,
            crypto_symbol=crypto_symbol,
        )
        rows_written = len(pd.read_csv(result_path))
        status = "success"
        error_message = ""
    except Exception as exc:  # noqa: BLE001 - summary should capture per-pair failures.
        rows_written = 0
        status = "failed"
        error_message = str(exc)

    return {
        "experiment_name": experiment_name,
        "window_name": window.name,
        "cme_symbol": cme_symbol,
        "crypto_symbol": crypto_symbol,
        "result_path": str(result_path),
        "rows_written": rows_written,
        "status": status,
        "error_message": error_message,
    }


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Experiment config field {key!r} must be a non-empty string")
    return value


def _required_str_tuple(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"Experiment config field {key!r} must be a non-empty list")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Experiment config field {key!r} must contain only non-empty strings")
    return tuple(value)


def _optional_path(raw: dict[str, Any], key: str, *, base_dir: Path) -> Path | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"Experiment config field {key!r} must be a non-empty string")
    return _resolve_path(value, base_dir=base_dir)


def _resolve_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path(os.path.normpath(base_dir / path))


def _safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


if __name__ == "__main__":
    main()

"""Run a unified CME CSV + Hyperliquid BBO lead-lag study."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from yield_lag_bot.research.lead_lag_analyzer import LeadLagAnalyzer

CME_COLUMN_ALIASES = {
    "ts": "timestamp",
    "time": "timestamp",
    "price": "last_price",
    "bid": "bid_price",
    "ask": "ask_price",
}


def load_cme_ticks(path: str | Path, *, symbol: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame = _rename_aliases(frame, CME_COLUMN_ALIASES)
    required = {"timestamp", "symbol"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"CME CSV missing required columns: {sorted(missing)}")

    normalized = pd.DataFrame(
        {
            "symbol": frame["symbol"].astype(str).str.upper(),
            "receive_ts": pd.to_datetime(frame["timestamp"], utc=True, errors="coerce"),
            "bid_price": _numeric_column(frame, "bid_price"),
            "ask_price": _numeric_column(frame, "ask_price"),
            "last_price": _numeric_column(frame, "last_price"),
        }
    )
    return normalized[normalized["symbol"] == symbol.upper()]


def load_crypto_ticks(path: str | Path, *, symbol: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "receive_ts" not in frame.columns:
        raise ValueError("Crypto CSV missing required column: receive_ts")
    if "symbol" not in frame.columns:
        raise ValueError("Crypto CSV missing required column: symbol")

    normalized = pd.DataFrame(
        {
            "symbol": frame["symbol"].astype(str).str.upper(),
            "receive_ts": pd.to_datetime(frame["receive_ts"], utc=True, errors="coerce"),
            "mid_price": _numeric_column(frame, "mid_price"),
            "bid_price": _numeric_column(frame, "bid_price"),
            "ask_price": _numeric_column(frame, "ask_price"),
            "last_price": _numeric_column(frame, "last_price"),
        }
    )
    return normalized[normalized["symbol"] == symbol.upper()]


def build_study_ticks(
    *,
    cme_csv: str | Path,
    crypto_csv: str | Path,
    cme_symbol: str,
    crypto_symbol: str,
) -> pd.DataFrame:
    ticks = pd.concat(
        [
            load_cme_ticks(cme_csv, symbol=cme_symbol),
            load_crypto_ticks(crypto_csv, symbol=crypto_symbol),
        ],
        ignore_index=True,
        sort=False,
    )
    ticks = ticks.dropna(subset=["receive_ts"]).sort_values("receive_ts")
    return ticks


def run_study(
    *,
    cme_csv: str | Path,
    crypto_csv: str | Path,
    out: str | Path,
    cme_symbol: str,
    crypto_symbol: str,
) -> None:
    analyzer = LeadLagAnalyzer()
    ticks = build_study_ticks(
        cme_csv=cme_csv,
        crypto_csv=crypto_csv,
        cme_symbol=cme_symbol,
        crypto_symbol=crypto_symbol,
    )
    prepared = analyzer.prepare_ticks(ticks)
    results = (
        []
        if prepared.empty
        else analyzer.analyze_pair(
            prepared,
            cme_symbol=cme_symbol.upper(),
            crypto_symbol=crypto_symbol.upper(),
        )
    )
    analyzer.write_report(results, out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cme-csv", required=True)
    parser.add_argument("--crypto-csv", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--cme-symbol", default="ZN")
    parser.add_argument("--crypto-symbol", default="BTC")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_study(
        cme_csv=args.cme_csv,
        crypto_csv=args.crypto_csv,
        out=args.out,
        cme_symbol=args.cme_symbol,
        crypto_symbol=args.crypto_symbol,
    )


def _rename_aliases(frame: pd.DataFrame, aliases: dict[str, str]) -> pd.DataFrame:
    rename_map = {
        column: aliases[column]
        for column in frame.columns
        if column in aliases and aliases[column] not in frame.columns
    }
    return frame.rename(columns=rename_map)


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(pd.NA, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce")


if __name__ == "__main__":
    main()

"""Build an offline research feature panel from event-study detail CSVs."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

OUTPUT_COLUMNS = [
    "event_name",
    "event_time_utc",
    "date",
    "cme_symbol",
    "crypto_symbol",
    "timestamp",
    "cme_return_bps",
    "abs_cme_return_bps",
    "cme_return_sign",
    "eth_forward_return_1m_bps",
    "eth_forward_return_3m_bps",
    "eth_forward_return_5m_bps",
    "inverse_expected_side",
    "inverse_correct_1m",
    "candidate_score",
    "candidate_tier",
    "result_path",
    "curve_symbol_count",
    "curve_up_count",
    "curve_down_count",
    "curve_net_direction",
    "curve_abs_return_bps_avg",
    "curve_abs_return_bps_max",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ranked", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    build_research_feature_panel(ranked=args.ranked, out=args.out, report=args.report)


def build_research_feature_panel(
    *,
    ranked: str | Path,
    out: str | Path,
    report: str | Path,
) -> pd.DataFrame:
    ranked_path = Path(ranked)
    out_path = Path(out)
    report_path = Path(report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if not ranked_path.exists():
        panel = _empty_panel()
        panel.to_csv(out_path, index=False)
        report_path.write_text(
            _report_markdown(panel, warning=f"Ranked summary not found: {ranked_path}"),
            encoding="utf-8",
        )
        return panel

    ranked_frame = pd.read_csv(ranked_path)
    candidates = _candidate_rows(ranked_frame)
    frames = [_panel_rows_for_candidate(candidate) for _, candidate in candidates.iterrows()]
    panel = pd.concat(frames, ignore_index=True) if frames else _empty_panel()
    if not panel.empty:
        panel = _add_curve_consensus(panel)
        panel = panel.sort_values(["timestamp", "crypto_symbol", "cme_symbol"]).reset_index(drop=True)
    panel = panel.reindex(columns=OUTPUT_COLUMNS)
    panel.to_csv(out_path, index=False)
    report_path.write_text(_report_markdown(panel), encoding="utf-8")
    return panel


def _candidate_rows(ranked: pd.DataFrame) -> pd.DataFrame:
    required = {
        "crypto_symbol",
        "signal_direction",
        "best_horizon",
        "candidate_tier",
        "result_path",
    }
    if ranked.empty or not required.issubset(ranked.columns):
        return ranked.iloc[0:0].copy()
    return ranked[
        (ranked["crypto_symbol"] == "ETH")
        & (ranked["signal_direction"] == "inverse")
        & (ranked["best_horizon"] == "1m")
        & (ranked["candidate_tier"].isin({"strong_candidate", "watchlist"}))
    ].copy()


def _panel_rows_for_candidate(candidate: pd.Series) -> pd.DataFrame:
    result_path = Path(str(candidate.get("result_path", "")))
    if not result_path.exists():
        return _empty_panel()
    detail = pd.read_csv(result_path)
    required = {"timestamp", "cme_return_bps", "crypto_forward_return_1m_bps"}
    if detail.empty or not required.issubset(detail.columns):
        return _empty_panel()

    frame = detail.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    frame["cme_return_bps"] = pd.to_numeric(frame["cme_return_bps"], errors="coerce")
    frame["crypto_forward_return_1m_bps"] = pd.to_numeric(
        frame["crypto_forward_return_1m_bps"],
        errors="coerce",
    )
    for column in ["crypto_forward_return_3m_bps", "crypto_forward_return_5m_bps"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        else:
            frame[column] = pd.NA
    frame = frame.dropna(subset=["timestamp", "cme_return_bps", "crypto_forward_return_1m_bps"])
    if frame.empty:
        return _empty_panel()

    panel = pd.DataFrame(
        {
            "event_name": candidate.get("event_name", ""),
            "event_time_utc": candidate.get("event_time_utc", ""),
            "date": pd.to_datetime(candidate.get("event_time_utc", ""), errors="coerce", utc=True).date(),
            "cme_symbol": candidate.get("cme_symbol", ""),
            "crypto_symbol": candidate.get("crypto_symbol", ""),
            "timestamp": frame["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cme_return_bps": frame["cme_return_bps"],
            "abs_cme_return_bps": frame["cme_return_bps"].abs(),
            "cme_return_sign": frame["cme_return_bps"].map(_return_sign),
            "eth_forward_return_1m_bps": frame["crypto_forward_return_1m_bps"],
            "eth_forward_return_3m_bps": frame["crypto_forward_return_3m_bps"],
            "eth_forward_return_5m_bps": frame["crypto_forward_return_5m_bps"],
            "candidate_score": candidate.get("candidate_score", ""),
            "candidate_tier": candidate.get("candidate_tier", ""),
            "result_path": str(result_path),
        }
    )
    panel["inverse_expected_side"] = panel["cme_return_bps"].map(_inverse_expected_side)
    panel["inverse_correct_1m"] = panel.apply(
        lambda row: _inverse_correct(row["inverse_expected_side"], row["eth_forward_return_1m_bps"]),
        axis=1,
    )
    return panel


def _return_sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _inverse_expected_side(cme_return_bps: float) -> str:
    if cme_return_bps > 0:
        return "short"
    if cme_return_bps < 0:
        return "long"
    return "flat"


def _inverse_correct(expected_side: str, eth_forward_return_1m_bps: float) -> bool:
    if expected_side == "short":
        return eth_forward_return_1m_bps < 0
    if expected_side == "long":
        return eth_forward_return_1m_bps > 0
    return False


def _add_curve_consensus(panel: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        panel.groupby(["timestamp", "crypto_symbol"], dropna=False)
        .agg(
            curve_symbol_count=("cme_symbol", "nunique"),
            curve_up_count=("cme_return_sign", lambda values: int((values > 0).sum())),
            curve_down_count=("cme_return_sign", lambda values: int((values < 0).sum())),
            curve_abs_return_bps_avg=("abs_cme_return_bps", "mean"),
            curve_abs_return_bps_max=("abs_cme_return_bps", "max"),
        )
        .reset_index()
    )
    grouped["curve_net_direction"] = grouped["curve_up_count"] - grouped["curve_down_count"]
    return panel.merge(grouped, on=["timestamp", "crypto_symbol"], how="left")


def _empty_panel() -> pd.DataFrame:
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def _report_markdown(panel: pd.DataFrame, *, warning: str | None = None) -> str:
    lines = [
        "# M5A Research Feature Panel",
        "",
        "Research-only feature panel. This is not a trading strategy and must not be used for live trading.",
        "",
    ]
    if warning is not None:
        lines.extend(["## Warning", "", warning, ""])
    total_rows = len(panel)
    dates = sorted(panel["date"].dropna().astype(str).unique()) if not panel.empty else []
    symbols = sorted(panel["cme_symbol"].dropna().astype(str).unique()) if not panel.empty else []
    eth_only = bool(panel.empty or set(panel["crypto_symbol"].dropna().unique()) == {"ETH"})
    lines.extend(
        [
            f"- total rows: {total_rows}",
            f"- dates covered: {', '.join(dates) if dates else 'none'}",
            f"- CME symbols covered: {', '.join(symbols) if symbols else 'none'}",
            f"- ETH only confirmation: {eth_only}",
            "",
            "## Inverse Correct 1m By CME Symbol",
            "",
        ]
    )
    lines.extend(_markdown_table(_rate_by(panel, "cme_symbol")))
    lines.extend(["", "## Inverse Correct 1m By Date", ""])
    lines.extend(_markdown_table(_rate_by(panel, "date")))
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "This panel is for feature and risk-filter research only. It does not simulate PnL, place orders, "
            "call private APIs, enable live trading, or connect to a CME live stream.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _rate_by(panel: pd.DataFrame, column: str) -> pd.DataFrame:
    if panel.empty or column not in panel.columns:
        return pd.DataFrame()
    return (
        panel.groupby(column, dropna=False)
        .agg(
            row_count=("inverse_correct_1m", "size"),
            inverse_correct_1m_rate=("inverse_correct_1m", "mean"),
        )
        .reset_index()
        .sort_values(column)
    )


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["No rows."]
    clean = frame.copy()
    for column in clean.columns:
        if pd.api.types.is_float_dtype(clean[column]):
            clean[column] = clean[column].map(lambda value: "" if pd.isna(value) else f"{value:.6f}")
    header = "| " + " | ".join(clean.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(clean.columns)) + " |"
    rows = [
        "| " + " | ".join("" if pd.isna(value) else str(value) for value in row)
        + " |"
        for row in clean.itertuples(index=False, name=None)
    ]
    return [header, separator, *rows]


if __name__ == "__main__":
    main()

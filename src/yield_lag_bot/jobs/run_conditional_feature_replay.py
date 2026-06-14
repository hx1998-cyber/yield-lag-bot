"""Offline conditional replay for M5 research feature filters."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

DEFAULT_NOTIONAL = 100.0
DEFAULT_ROUND_TRIP_COST_BPS = 6.0
COST_LEVELS_BPS = [0.0, 1.0, 3.0, 6.0, 10.0]
OUTPUT_COLUMNS = [
    "filter_name",
    "round_trip_cost_bps",
    "rows",
    "dates_count",
    "cme_symbols_count",
    "gross_pnl",
    "net_pnl",
    "gross_win_rate",
    "net_win_rate",
    "avg_net_bps",
    "max_drawdown",
    "positive_dates_count",
    "positive_symbols_count",
    "pass_research_gate",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--notional", type=float, default=DEFAULT_NOTIONAL)
    parser.add_argument("--round-trip-cost-bps", type=float, default=DEFAULT_ROUND_TRIP_COST_BPS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_conditional_feature_replay(
        features=args.features,
        out=args.out,
        report=args.report,
        notional=args.notional,
        round_trip_cost_bps=args.round_trip_cost_bps,
    )


def run_conditional_feature_replay(
    *,
    features: str | Path,
    out: str | Path,
    report: str | Path,
    notional: float = DEFAULT_NOTIONAL,
    round_trip_cost_bps: float = DEFAULT_ROUND_TRIP_COST_BPS,
) -> pd.DataFrame:
    features_path = Path(features)
    out_path = Path(out)
    report_path = Path(report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if not features_path.exists():
        result = _empty_result()
        result.to_csv(out_path, index=False)
        report_path.write_text(
            _report_markdown(result, warning=f"Feature panel not found: {features_path}"),
            encoding="utf-8",
        )
        return result

    feature_panel = _prepare_features(pd.read_csv(features_path))
    rows = []
    for filter_name, mask in _filter_masks(feature_panel).items():
        filtered = feature_panel[mask].copy()
        for cost_bps in _cost_levels(round_trip_cost_bps):
            rows.append(_replay_metrics(filter_name, filtered, notional=notional, cost_bps=cost_bps))
    result = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    result.to_csv(out_path, index=False)
    report_path.write_text(_report_markdown(result), encoding="utf-8")
    return result


def _prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    numeric_columns = [
        "cme_return_bps",
        "abs_cme_return_bps",
        "eth_forward_return_1m_bps",
        "curve_up_count",
        "curve_down_count",
    ]
    for column in numeric_columns:
        if column in prepared.columns:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    return prepared.dropna(subset=["cme_return_bps", "eth_forward_return_1m_bps"])


def _filter_masks(features: pd.DataFrame) -> dict[str, pd.Series]:
    high = features["abs_cme_return_bps"] >= 0.5
    very_high = features["abs_cme_return_bps"] >= 1.0
    curve_down = (features["curve_down_count"] >= 2) & (features["curve_up_count"] == 0)
    return {
        "high_cme_move": high,
        "very_high_cme_move": very_high,
        "curve_consensus_down": curve_down,
        "very_high_and_curve_down": very_high & curve_down,
        "high_and_curve_down": high & curve_down,
    }


def _cost_levels(default_cost_bps: float) -> list[float]:
    levels = sorted({*COST_LEVELS_BPS, float(default_cost_bps)})
    return levels


def _replay_metrics(
    filter_name: str,
    rows: pd.DataFrame,
    *,
    notional: float,
    cost_bps: float,
) -> dict[str, object]:
    if rows.empty:
        return _empty_metric_row(filter_name, cost_bps)
    replay = rows.copy()
    replay["paper_side"] = replay["cme_return_bps"].map(_inverse_side)
    replay = replay[replay["paper_side"] != "flat"].copy()
    if replay.empty:
        return _empty_metric_row(filter_name, cost_bps)
    signed_return_bps = replay.apply(
        lambda row: -row["eth_forward_return_1m_bps"]
        if row["paper_side"] == "short"
        else row["eth_forward_return_1m_bps"],
        axis=1,
    )
    replay["gross_pnl"] = notional * signed_return_bps / 10000.0
    replay["cost"] = notional * cost_bps / 10000.0
    replay["net_pnl"] = replay["gross_pnl"] - replay["cost"]
    by_date = replay.groupby("date", dropna=False)["net_pnl"].sum() if "date" in replay.columns else pd.Series(dtype=float)
    by_symbol = replay.groupby("cme_symbol", dropna=False)["net_pnl"].sum()
    net_pnl = float(replay["net_pnl"].sum())
    metric = {
        "filter_name": filter_name,
        "round_trip_cost_bps": cost_bps,
        "rows": len(replay),
        "dates_count": int(replay["date"].nunique()) if "date" in replay.columns else 0,
        "cme_symbols_count": int(replay["cme_symbol"].nunique()),
        "gross_pnl": float(replay["gross_pnl"].sum()),
        "net_pnl": net_pnl,
        "gross_win_rate": float((replay["gross_pnl"] > 0).mean()),
        "net_win_rate": float((replay["net_pnl"] > 0).mean()),
        "avg_net_bps": float((replay["net_pnl"] / notional * 10000.0).mean()),
        "max_drawdown": _max_drawdown(replay["net_pnl"]),
        "positive_dates_count": int((by_date > 0).sum()),
        "positive_symbols_count": int((by_symbol > 0).sum()),
    }
    metric["pass_research_gate"] = _passes_research_gate(metric)
    return metric


def _inverse_side(cme_return_bps: float) -> str:
    if cme_return_bps > 0:
        return "short"
    if cme_return_bps < 0:
        return "long"
    return "flat"


def _max_drawdown(net_pnl: pd.Series) -> float:
    equity = net_pnl.cumsum()
    peak = equity.cummax().clip(lower=0.0)
    return float((equity - peak).min())


def _passes_research_gate(metric: dict[str, object]) -> bool:
    return bool(
        metric["rows"] >= 20
        and metric["net_pnl"] > 0
        and metric["net_win_rate"] >= 0.55
        and metric["positive_dates_count"] >= 2
        and metric["positive_symbols_count"] >= 2
        and metric["round_trip_cost_bps"] >= 6
    )


def _empty_metric_row(filter_name: str, cost_bps: float) -> dict[str, object]:
    metric = {
        "filter_name": filter_name,
        "round_trip_cost_bps": cost_bps,
        "rows": 0,
        "dates_count": 0,
        "cme_symbols_count": 0,
        "gross_pnl": 0.0,
        "net_pnl": 0.0,
        "gross_win_rate": 0.0,
        "net_win_rate": 0.0,
        "avg_net_bps": 0.0,
        "max_drawdown": 0.0,
        "positive_dates_count": 0,
        "positive_symbols_count": 0,
        "pass_research_gate": False,
    }
    return metric


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def _report_markdown(result: pd.DataFrame, *, warning: str | None = None) -> str:
    passing = result[result["pass_research_gate"] == True] if not result.empty else result
    best_6 = _best_at_cost(result, 6.0)
    best_3 = _best_at_cost(result, 3.0)
    sparse = result[result["rows"] < 20] if not result.empty else result
    one_date = result[(result["rows"] >= 20) & (result["positive_dates_count"] < 2)] if not result.empty else result
    lines = [
        "# M5C Conditional Feature Replay",
        "",
        "Offline research replay only. This is not a trading strategy and does not place orders.",
        "",
        f"- any filter passes research gate: {not passing.empty}",
        "",
        "## Overall Conclusion",
        "",
        _conclusion(passing),
        "",
    ]
    if warning is not None:
        lines.extend(["## Warning", "", warning, ""])
    lines.extend(["## Best Filter At 6 Bps", ""])
    lines.extend(_markdown_table(best_6))
    lines.extend(["", "## Best Filter At 3 Bps", ""])
    lines.extend(_markdown_table(best_3))
    lines.extend(["", "## Sparse Filters", ""])
    lines.extend(_markdown_table(sparse.head(20)))
    lines.extend(["", "## One-Date Concentration", ""])
    lines.extend(_markdown_table(one_date.head(20)))
    lines.extend(["", "## Passing Filters", ""])
    lines.extend(_markdown_table(passing))
    lines.extend(
        [
            "",
            "Research-only, not a trading strategy. No live trading, private APIs, order placement, "
            "Hyperliquid exchange endpoint, or CME live stream is involved.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _best_at_cost(result: pd.DataFrame, cost_bps: float) -> pd.DataFrame:
    if result.empty:
        return result
    rows = result[result["round_trip_cost_bps"] == cost_bps]
    if rows.empty:
        return rows
    return rows.sort_values(["net_pnl", "net_win_rate", "rows"], ascending=[False, False, False]).head(1)


def _conclusion(passing: pd.DataFrame) -> str:
    if passing.empty:
        return "No pre-registered conditional filter passed the research gate. Keep the feature research-only."
    return "At least one pre-registered conditional filter passed the research gate; keep it research-only pending more validation."


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

"""Parameter sweep for offline paper signal replay."""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import pandas as pd

from yield_lag_bot.jobs.run_paper_signal_replay import build_replay_trades

MIN_CME_RETURN_BPS_VALUES = [0.0, 0.25, 0.5, 1.0, 1.5, 2.0]
ROUND_TRIP_COST_BPS_VALUES = [0.0, 1.0, 3.0, 6.0, 10.0]
COOLDOWN_MINUTES_VALUES = [1, 2, 3]
CME_SYMBOL_SETS = {
    "all_robust_eth_symbols": {"ZNU6", "ZTU6", "ZNM6"},
    "ZNU6_only": {"ZNU6"},
    "ZTU6_only": {"ZTU6"},
    "ZNM6_only": {"ZNM6"},
    "ZNU6+ZTU6": {"ZNU6", "ZTU6"},
    "ZNU6+ZNM6": {"ZNU6", "ZNM6"},
    "ZTU6+ZNM6": {"ZTU6", "ZNM6"},
}
OUTPUT_COLUMNS = [
    "min_cme_return_bps",
    "round_trip_cost_bps",
    "cooldown_minutes",
    "cme_symbol_set",
    "total_trades",
    "gross_pnl",
    "net_pnl",
    "gross_win_rate",
    "net_win_rate",
    "avg_net_pnl",
    "avg_net_bps",
    "max_drawdown",
    "profit_factor",
    "positive_dates_count",
    "total_dates_count",
    "positive_symbols_count",
    "total_symbols_count",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_paper_signal_sweep(summary=args.summary, out=args.out, report=args.report)


def run_paper_signal_sweep(*, summary: str | Path, out: str | Path, report: str | Path) -> pd.DataFrame:
    summary_path = Path(summary)
    out_path = Path(out)
    report_path = Path(report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    summary_frame = pd.read_csv(summary_path) if summary_path.exists() else pd.DataFrame()
    rows: list[dict[str, object]] = []
    for min_cme, cost_bps, cooldown, symbol_set_name in itertools.product(
        MIN_CME_RETURN_BPS_VALUES,
        ROUND_TRIP_COST_BPS_VALUES,
        COOLDOWN_MINUTES_VALUES,
        CME_SYMBOL_SETS.keys(),
    ):
        trades = build_replay_trades(
            summary_frame,
            allowed_cme_symbols=CME_SYMBOL_SETS[symbol_set_name],
            min_cme_return_bps=min_cme,
            round_trip_cost_bps=cost_bps,
            cooldown_minutes=cooldown,
        )
        rows.append(
            {
                "min_cme_return_bps": min_cme,
                "round_trip_cost_bps": cost_bps,
                "cooldown_minutes": cooldown,
                "cme_symbol_set": symbol_set_name,
                **_metrics(trades),
            }
        )

    sweep = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    sweep.to_csv(out_path, index=False)
    report_path.write_text(_report_markdown(sweep, summary_path=summary_path), encoding="utf-8")
    return sweep


def _metrics(trades: pd.DataFrame) -> dict[str, object]:
    if trades.empty:
        return {
            "total_trades": 0,
            "gross_pnl": 0.0,
            "net_pnl": 0.0,
            "gross_win_rate": 0.0,
            "net_win_rate": 0.0,
            "avg_net_pnl": 0.0,
            "avg_net_bps": 0.0,
            "max_drawdown": 0.0,
            "profit_factor": 0.0,
            "positive_dates_count": 0,
            "total_dates_count": 0,
            "positive_symbols_count": 0,
            "total_symbols_count": 0,
        }
    gross_pnl = float(trades["gross_pnl"].sum())
    net_pnl = float(trades["net_pnl"].sum())
    by_date = _group_net_by_date(trades)
    by_symbol = trades.groupby("cme_symbol", dropna=False)["net_pnl"].sum()
    return {
        "total_trades": len(trades),
        "gross_pnl": round(gross_pnl, 8),
        "net_pnl": round(net_pnl, 8),
        "gross_win_rate": float((trades["gross_pnl"] > 0).mean()),
        "net_win_rate": float((trades["net_pnl"] > 0).mean()),
        "avg_net_pnl": float(trades["net_pnl"].mean()),
        "avg_net_bps": float((trades["net_pnl"] / trades["notional"] * 10000.0).mean()),
        "max_drawdown": _max_drawdown(trades),
        "profit_factor": _profit_factor(trades["net_pnl"]),
        "positive_dates_count": int((by_date > 0).sum()),
        "total_dates_count": int(len(by_date)),
        "positive_symbols_count": int((by_symbol > 0).sum()),
        "total_symbols_count": int(len(by_symbol)),
    }


def _group_net_by_date(trades: pd.DataFrame) -> pd.Series:
    with_dates = trades.copy()
    with_dates["date"] = pd.to_datetime(with_dates["signal_time_utc"], errors="coerce", utc=True).dt.date.astype(str)
    return with_dates.groupby("date", dropna=False)["net_pnl"].sum()


def _max_drawdown(trades: pd.DataFrame) -> float:
    equity = trades["net_pnl"].cumsum()
    peak = equity.cummax().clip(lower=0.0)
    return float((equity - peak).min())


def _profit_factor(values: pd.Series) -> float:
    wins = float(values[values > 0].sum())
    losses = abs(float(values[values < 0].sum()))
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def _report_markdown(sweep: pd.DataFrame, *, summary_path: Path) -> str:
    positive_6 = sweep[(sweep["round_trip_cost_bps"] == 6.0) & (sweep["net_pnl"] > 0)]
    positive_3 = sweep[(sweep["round_trip_cost_bps"] == 3.0) & (sweep["net_pnl"] > 0)]
    passing = sweep[
        (sweep["total_trades"] >= 20)
        & (sweep["net_pnl"] > 0)
        & (sweep["net_win_rate"] >= 0.55)
        & (sweep["positive_dates_count"] >= 2)
        & (sweep["positive_symbols_count"] >= 2)
    ]
    lines = [
        "# M4.1 Offline Paper Signal Sweep",
        "",
        "Offline replay only. This sweep does not place orders, use wallets, call private APIs, "
        "or enable live trading.",
        "",
        f"Source summary: `{summary_path}`",
        "",
        f"- parameter rows: {len(sweep)}",
        f"- positive after 6 bps: {len(positive_6)}",
        f"- positive after 3 bps: {len(positive_3)}",
        f"- any total_trades >= 20: {bool((sweep['total_trades'] >= 20).any())}",
        f"- any positive result across at least 2 dates: {bool(((sweep['net_pnl'] > 0) & (sweep['positive_dates_count'] >= 2)).any())}",
        f"- any positive result across at least 2 CME symbols: {bool(((sweep['net_pnl'] > 0) & (sweep['positive_symbols_count'] >= 2)).any())}",
        "",
        "## Best Positive After 6 Bps",
        "",
    ]
    lines.extend(_markdown_table(positive_6.sort_values("net_pnl", ascending=False).head(10)))
    lines.extend(["", "## Best Positive After 3 Bps", ""])
    lines.extend(_markdown_table(positive_3.sort_values("net_pnl", ascending=False).head(10)))
    lines.extend(["", "## Full Robustness Screen", ""])
    lines.extend(_markdown_table(passing.sort_values("net_pnl", ascending=False).head(20)))
    if not passing.empty and (
        (passing["total_trades"] < 30).any()
        or (passing["positive_dates_count"] < 2).any()
        or (passing["positive_symbols_count"] < 2).any()
    ):
        lines.extend(["", "Warning: at least one positive result is sparse or overfit-prone."])
    elif passing.empty:
        lines.extend(["", "Warning: no parameter set passed the full robustness screen."])
    return "\n".join(lines).rstrip() + "\n"


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

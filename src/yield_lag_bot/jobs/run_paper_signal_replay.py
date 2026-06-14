"""Offline paper replay for ranked CME -> crypto event-study signals."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ALLOWED_CME_SYMBOLS = {"ZNU6", "ZTU6", "ZNM6"}
DEFAULT_MIN_CME_RETURN_BPS = 0.5
DEFAULT_NOTIONAL = 100.0
DEFAULT_ROUND_TRIP_COST_BPS = 6.0
DEFAULT_COOLDOWN_MINUTES = 1
OUTPUT_COLUMNS = [
    "event_name",
    "event_time_utc",
    "cme_symbol",
    "crypto_symbol",
    "signal_time_utc",
    "horizon",
    "signal_direction",
    "cme_return_bps",
    "eth_forward_return_bps",
    "paper_side",
    "notional",
    "gross_pnl",
    "cost",
    "net_pnl",
    "candidate_score",
    "candidate_tier",
    "result_path",
]
AUDIT_COLUMNS = [
    "event_name",
    "event_time_utc",
    "cme_symbol",
    "crypto_symbol",
    "signal_time_utc",
    "cme_timestamp_used",
    "eth_return_start_time",
    "eth_return_end_time",
    "horizon",
    "signal_direction",
    "cme_return_bps",
    "eth_forward_return_bps",
    "expected_eth_direction",
    "paper_side",
    "gross_pnl",
    "net_pnl",
    "gross_win",
    "net_win",
    "reason_included",
    "reason_excluded",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--min-cme-return-bps", type=float, default=DEFAULT_MIN_CME_RETURN_BPS)
    parser.add_argument("--notional", type=float, default=DEFAULT_NOTIONAL)
    parser.add_argument("--round-trip-cost-bps", type=float, default=DEFAULT_ROUND_TRIP_COST_BPS)
    parser.add_argument("--cooldown-minutes", type=int, default=DEFAULT_COOLDOWN_MINUTES)
    parser.add_argument("--audit-out", default=None)
    parser.add_argument("--orientation-check", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_paper_signal_replay(
        summary=args.summary,
        out=args.out,
        report=args.report,
        min_cme_return_bps=args.min_cme_return_bps,
        notional=args.notional,
        round_trip_cost_bps=args.round_trip_cost_bps,
        cooldown_minutes=args.cooldown_minutes,
        audit_out=args.audit_out,
        orientation_check=args.orientation_check,
    )


def run_paper_signal_replay(
    *,
    summary: str | Path,
    out: str | Path,
    report: str | Path,
    min_cme_return_bps: float = DEFAULT_MIN_CME_RETURN_BPS,
    notional: float = DEFAULT_NOTIONAL,
    round_trip_cost_bps: float = DEFAULT_ROUND_TRIP_COST_BPS,
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
    audit_out: str | Path | None = None,
    orientation_check: bool = False,
) -> pd.DataFrame:
    summary_path = Path(summary)
    out_path = Path(out)
    report_path = Path(report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path = Path(audit_out) if audit_out is not None else None
    if audit_path is not None:
        audit_path.parent.mkdir(parents=True, exist_ok=True)

    if not summary_path.exists():
        trades = _empty_trades()
        audit = _empty_audit()
        trades.to_csv(out_path, index=False)
        if audit_path is not None:
            audit.to_csv(audit_path, index=False)
        report_path.write_text(
            _report_markdown(
                trades,
                summary_path=summary_path,
                warning=f"Summary file not found: {summary_path}",
                audit=audit,
                orientation_check=orientation_check,
            ),
            encoding="utf-8",
        )
        return trades

    summary_frame = pd.read_csv(summary_path)
    candidates = _candidate_rows(summary_frame)
    if candidates.empty:
        trades = _empty_trades()
        audit = _empty_audit()
        trades.to_csv(out_path, index=False)
        if audit_path is not None:
            audit.to_csv(audit_path, index=False)
        report_path.write_text(
            _report_markdown(
                trades,
                summary_path=summary_path,
                warning="No eligible strong ETH inverse 1m candidates were found.",
                audit=audit,
                orientation_check=orientation_check,
            ),
            encoding="utf-8",
        )
        return trades

    trade_frames = []
    audit_frames = []
    for _, candidate in candidates.iterrows():
        trades_for_candidate, audit_for_candidate = _replay_candidate(
            candidate,
            min_cme_return_bps=min_cme_return_bps,
            notional=notional,
            round_trip_cost_bps=round_trip_cost_bps,
            cooldown_minutes=cooldown_minutes,
        )
        trade_frames.append(trades_for_candidate)
        audit_frames.append(audit_for_candidate)
    trades = pd.concat(trade_frames, ignore_index=True) if trade_frames else _empty_trades()
    audit = pd.concat(audit_frames, ignore_index=True) if audit_frames else _empty_audit()
    if not trades.empty:
        trades = trades.sort_values(["signal_time_utc", "cme_symbol", "crypto_symbol"]).reset_index(drop=True)
    trades = trades.reindex(columns=OUTPUT_COLUMNS)
    if not audit.empty:
        audit = audit.sort_values(["signal_time_utc", "cme_symbol", "crypto_symbol"]).reset_index(drop=True)
    audit = audit.reindex(columns=AUDIT_COLUMNS)
    trades.to_csv(out_path, index=False)
    if audit_path is not None:
        audit.to_csv(audit_path, index=False)
    report_path.write_text(
        _report_markdown(
            trades,
            summary_path=summary_path,
            audit=audit,
            orientation_check=orientation_check,
        ),
        encoding="utf-8",
    )
    return trades


def _candidate_rows(summary: pd.DataFrame, allowed_cme_symbols: set[str] | None = None) -> pd.DataFrame:
    allowed = ALLOWED_CME_SYMBOLS if allowed_cme_symbols is None else allowed_cme_symbols
    required = {
        "cme_symbol",
        "crypto_symbol",
        "best_horizon",
        "signal_direction",
        "candidate_tier",
        "result_path",
    }
    if summary.empty or not required.issubset(summary.columns):
        return summary.iloc[0:0].copy()
    return summary[
        summary["cme_symbol"].isin(allowed)
        & (summary["crypto_symbol"] == "ETH")
        & (summary["best_horizon"] == "1m")
        & (summary["signal_direction"] == "inverse")
        & (summary["candidate_tier"] == "strong_candidate")
    ].copy()


def _replay_candidate(
    candidate: pd.Series,
    *,
    min_cme_return_bps: float,
    notional: float,
    round_trip_cost_bps: float,
    cooldown_minutes: int,
) -> pd.DataFrame:
    result_path = Path(str(candidate.get("result_path", "")))
    if not result_path.exists():
        return _empty_trades(), _empty_audit()

    detail = pd.read_csv(result_path)
    required = {"timestamp", "cme_return_bps", "crypto_forward_return_1m_bps"}
    if detail.empty or not required.issubset(detail.columns):
        return _empty_trades(), _empty_audit()

    replay = detail.copy()
    replay["timestamp"] = pd.to_datetime(replay["timestamp"], errors="coerce", utc=True)
    replay["cme_return_bps"] = pd.to_numeric(replay["cme_return_bps"], errors="coerce")
    replay["crypto_forward_return_1m_bps"] = pd.to_numeric(
        replay["crypto_forward_return_1m_bps"],
        errors="coerce",
    )
    replay = replay.dropna(subset=["timestamp", "cme_return_bps", "crypto_forward_return_1m_bps"])
    replay = replay.sort_values("timestamp").reset_index(drop=True)

    rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    last_trade_time: pd.Timestamp | None = None
    cooldown = pd.Timedelta(minutes=max(cooldown_minutes, 0))
    for _, row in replay.iterrows():
        signal_time = row["timestamp"]
        cme_return_bps = float(row["cme_return_bps"])
        eth_forward_return_bps = float(row["crypto_forward_return_1m_bps"])
        side = _inverse_side(cme_return_bps)
        excluded_reason = ""
        if abs(cme_return_bps) < min_cme_return_bps:
            excluded_reason = "below_threshold"
        elif last_trade_time is not None and signal_time < last_trade_time + cooldown:
            excluded_reason = "cooldown"

        signed_eth_return = eth_forward_return_bps / 10000.0
        if side == "short":
            signed_eth_return *= -1.0
        gross_pnl = notional * signed_eth_return
        cost = notional * round_trip_cost_bps / 10000.0
        net_pnl = gross_pnl - cost
        trade_row = {
            "event_name": candidate.get("event_name", ""),
            "event_time_utc": candidate.get("event_time_utc", ""),
            "cme_symbol": candidate.get("cme_symbol", ""),
            "crypto_symbol": candidate.get("crypto_symbol", ""),
            "signal_time_utc": signal_time.isoformat().replace("+00:00", "Z"),
            "horizon": "1m",
            "signal_direction": "inverse",
            "cme_return_bps": cme_return_bps,
            "eth_forward_return_bps": eth_forward_return_bps,
            "paper_side": side,
            "notional": notional,
            "gross_pnl": round(gross_pnl, 8),
            "cost": round(cost, 8),
            "net_pnl": round(net_pnl, 8),
            "candidate_score": candidate.get("candidate_score", ""),
            "candidate_tier": candidate.get("candidate_tier", ""),
            "result_path": str(result_path),
        }
        audit_rows.append(
            _audit_row(
                trade_row,
                signal_time=signal_time,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                reason_included="trade" if not excluded_reason else "",
                reason_excluded=excluded_reason,
            )
        )
        if excluded_reason:
            continue
        rows.append(
            trade_row
        )
        last_trade_time = signal_time

    trades = pd.DataFrame(rows, columns=OUTPUT_COLUMNS) if rows else _empty_trades()
    audit = pd.DataFrame(audit_rows, columns=AUDIT_COLUMNS) if audit_rows else _empty_audit()
    return trades, audit


def build_replay_trades(
    summary_frame: pd.DataFrame,
    *,
    allowed_cme_symbols: set[str] | None = None,
    min_cme_return_bps: float = DEFAULT_MIN_CME_RETURN_BPS,
    notional: float = DEFAULT_NOTIONAL,
    round_trip_cost_bps: float = DEFAULT_ROUND_TRIP_COST_BPS,
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
) -> pd.DataFrame:
    candidates = _candidate_rows(summary_frame, allowed_cme_symbols=allowed_cme_symbols)
    frames = [
        _replay_candidate(
            candidate,
            min_cme_return_bps=min_cme_return_bps,
            notional=notional,
            round_trip_cost_bps=round_trip_cost_bps,
            cooldown_minutes=cooldown_minutes,
        )[0]
        for _, candidate in candidates.iterrows()
    ]
    trades = pd.concat(frames, ignore_index=True) if frames else _empty_trades()
    if not trades.empty:
        trades = trades.sort_values(["signal_time_utc", "cme_symbol", "crypto_symbol"]).reset_index(drop=True)
    return trades.reindex(columns=OUTPUT_COLUMNS)


def _audit_row(
    trade_row: dict[str, object],
    *,
    signal_time: pd.Timestamp,
    gross_pnl: float,
    net_pnl: float,
    reason_included: str,
    reason_excluded: str,
) -> dict[str, object]:
    eth_end = signal_time + pd.Timedelta(minutes=1)
    return {
        "event_name": trade_row["event_name"],
        "event_time_utc": trade_row["event_time_utc"],
        "cme_symbol": trade_row["cme_symbol"],
        "crypto_symbol": trade_row["crypto_symbol"],
        "signal_time_utc": trade_row["signal_time_utc"],
        "cme_timestamp_used": signal_time.isoformat().replace("+00:00", "Z"),
        "eth_return_start_time": signal_time.isoformat().replace("+00:00", "Z"),
        "eth_return_end_time": eth_end.isoformat().replace("+00:00", "Z"),
        "horizon": trade_row["horizon"],
        "signal_direction": trade_row["signal_direction"],
        "cme_return_bps": trade_row["cme_return_bps"],
        "eth_forward_return_bps": trade_row["eth_forward_return_bps"],
        "expected_eth_direction": trade_row["paper_side"],
        "paper_side": trade_row["paper_side"],
        "gross_pnl": round(gross_pnl, 8),
        "net_pnl": round(net_pnl, 8),
        "gross_win": gross_pnl > 0,
        "net_win": net_pnl > 0,
        "reason_included": reason_included,
        "reason_excluded": reason_excluded,
    }


def _inverse_side(cme_return_bps: float) -> str:
    if cme_return_bps > 0:
        return "short"
    return "long"


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def _empty_audit() -> pd.DataFrame:
    return pd.DataFrame(columns=AUDIT_COLUMNS)


def _report_markdown(
    trades: pd.DataFrame,
    *,
    summary_path: Path,
    warning: str | None = None,
    audit: pd.DataFrame | None = None,
    orientation_check: bool = False,
) -> str:
    total_trades = len(trades)
    gross_pnl = float(trades["gross_pnl"].sum()) if total_trades else 0.0
    net_pnl = float(trades["net_pnl"].sum()) if total_trades else 0.0
    gross_win_rate = float((trades["gross_pnl"] > 0).mean()) if total_trades else 0.0
    net_win_rate = float((trades["net_pnl"] > 0).mean()) if total_trades else 0.0
    average_net_pnl = float(trades["net_pnl"].mean()) if total_trades else 0.0
    average_net_bps = float((trades["net_pnl"] / trades["notional"] * 10000.0).mean()) if total_trades else 0.0
    average_winning_trade = float(trades.loc[trades["net_pnl"] > 0, "net_pnl"].mean()) if total_trades else 0.0
    average_losing_trade = float(trades.loc[trades["net_pnl"] <= 0, "net_pnl"].mean()) if total_trades else 0.0
    max_drawdown = _max_drawdown(trades)
    gross_profit_factor = _profit_factor(trades["gross_pnl"]) if total_trades else 0.0
    net_profit_factor = _profit_factor(trades["net_pnl"]) if total_trades else 0.0

    lines = [
        "# M4 Offline Paper Signal Replay",
        "",
        "Offline replay only. This report does not place orders, use wallets, call private APIs, "
        "or enable live trading.",
        "",
        f"Source summary: `{summary_path}`",
        "",
        f"- total trades: {total_trades}",
        f"- gross pnl: {gross_pnl:.6f}",
        f"- net pnl: {net_pnl:.6f}",
        f"- gross win rate before cost: {gross_win_rate:.2%}",
        f"- net win rate after cost: {net_win_rate:.2%}",
        f"- average net pnl: {average_net_pnl:.6f}",
        f"- average net bps: {average_net_bps:.4f}",
        f"- average winning trade: {average_winning_trade:.6f}",
        f"- average losing trade: {average_losing_trade:.6f}",
        f"- profit factor before cost: {gross_profit_factor:.4f}",
        f"- profit factor after cost: {net_profit_factor:.4f}",
        f"- max drawdown: {max_drawdown:.6f}",
        "",
        "## Results By CME Symbol",
        "",
    ]
    if warning is not None:
        lines.extend(["## Warning", "", warning, ""])
    if total_trades < 30:
        lines.extend(
            [
                "## Small Sample Warning",
                "",
                "Trade count is small. Treat this replay as a diagnostic, not evidence of deployable edge.",
                "",
            ]
        )
    lines.extend(_markdown_table(_results_by_cme_symbol(trades)))
    lines.extend(["", "## Results By Event Name", ""])
    lines.extend(_markdown_table(_results_by_event_name(trades)))
    lines.extend(["", "## Results By Date", ""])
    lines.extend(_markdown_table(_results_by_date(trades)))
    if orientation_check:
        lines.extend(["", "## Orientation Check", ""])
        lines.extend(_orientation_lines(audit if audit is not None else trades))
    return "\n".join(lines).rstrip() + "\n"


def _results_by_cme_symbol(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    return (
        trades.groupby("cme_symbol", dropna=False)
        .agg(
            trades=("net_pnl", "size"),
            gross_pnl=("gross_pnl", "sum"),
            net_pnl=("net_pnl", "sum"),
            win_rate=("net_pnl", lambda values: float((values > 0).mean())),
            average_net_pnl=("net_pnl", "mean"),
        )
        .reset_index()
        .sort_values("net_pnl", ascending=False)
    )


def _results_by_date(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    with_dates = trades.copy()
    with_dates["date"] = pd.to_datetime(with_dates["signal_time_utc"], errors="coerce", utc=True).dt.date.astype(str)
    return (
        with_dates.groupby("date", dropna=False)
        .agg(
            trades=("net_pnl", "size"),
            gross_pnl=("gross_pnl", "sum"),
            net_pnl=("net_pnl", "sum"),
            win_rate=("net_pnl", lambda values: float((values > 0).mean())),
        )
        .reset_index()
        .sort_values("date")
    )


def _results_by_event_name(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    return (
        trades.groupby("event_name", dropna=False)
        .agg(
            trades=("net_pnl", "size"),
            gross_pnl=("gross_pnl", "sum"),
            net_pnl=("net_pnl", "sum"),
            win_rate=("net_pnl", lambda values: float((values > 0).mean())),
        )
        .reset_index()
        .sort_values("net_pnl", ascending=False)
    )


def _max_drawdown(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 0.0
    equity = trades["net_pnl"].cumsum()
    peak = equity.cummax().clip(lower=0.0)
    drawdown = equity - peak
    return float(drawdown.min())


def _profit_factor(values: pd.Series) -> float:
    wins = float(values[values > 0].sum())
    losses = abs(float(values[values < 0].sum()))
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def _orientation_lines(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["No rows."]
    included = frame[frame.get("reason_included", "") == "trade"] if "reason_included" in frame.columns else frame
    if included.empty:
        return ["No included trades to check."]
    up_rows = included[included["cme_return_bps"] > 0]
    down_rows = included[included["cme_return_bps"] < 0]
    up_ok = bool(up_rows.empty or (up_rows["paper_side"] == "short").all())
    down_ok = bool(down_rows.empty or (down_rows["paper_side"] == "long").all())
    lines = [
        f"- CME up -> ETH short: {'ok' if up_ok else 'warning'}",
        f"- CME down -> ETH long: {'ok' if down_ok else 'warning'}",
    ]
    if not (up_ok and down_ok):
        lines.append("- WARNING: inverse replay sign convention appears inconsistent.")
    else:
        lines.append("- Inverse replay sign convention is internally consistent.")
    return lines


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
        "| " + " | ".join("" if pd.isna(value) else str(value) for value in row) + " |"
        for row in clean.itertuples(index=False, name=None)
    ]
    return [header, separator, *rows]


if __name__ == "__main__":
    main()

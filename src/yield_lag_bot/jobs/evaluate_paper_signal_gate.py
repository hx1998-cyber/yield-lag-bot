"""Evaluate the M4 paper signal replay decision gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

MIN_TRADES = 20
MIN_NET_WIN_RATE = 0.55
MIN_POSITIVE_DATES = 2
MIN_POSITIVE_SYMBOLS = 2
MIN_COST_BPS = 6.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep", required=True)
    parser.add_argument("--replay-report", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--markdown", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    evaluate_paper_signal_gate(
        sweep=args.sweep,
        replay_report=args.replay_report,
        out=args.out,
        markdown=args.markdown,
    )


def evaluate_paper_signal_gate(
    *,
    sweep: str | Path,
    replay_report: str | Path,
    out: str | Path,
    markdown: str | Path,
) -> dict[str, Any]:
    sweep_path = Path(sweep)
    replay_report_path = Path(replay_report)
    out_path = Path(out)
    markdown_path = Path(markdown)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    sweep_frame = pd.read_csv(sweep_path) if sweep_path.exists() else pd.DataFrame()
    decision = _decision_payload(sweep_frame, replay_report_path=replay_report_path)
    out_path.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_decision_markdown(decision, sweep_path=sweep_path), encoding="utf-8")
    return decision


def _decision_payload(sweep: pd.DataFrame, *, replay_report_path: Path) -> dict[str, Any]:
    if sweep.empty:
        return {
            "decision": "fail",
            "reason": "Sweep input is missing or empty.",
            "best_6bps_candidate": None,
            "best_3bps_candidate": None,
            "full_gate_pass_count": 0,
            "research_status": "research_only",
            "recommended_next_step": "Regenerate the offline sweep, then rerun the decision gate.",
            "failed_criteria": ["sweep input missing or empty"],
            "replay_report": str(replay_report_path),
        }

    gated = _full_gate_rows(sweep)
    best_6 = _best_candidate(sweep[sweep["round_trip_cost_bps"] >= MIN_COST_BPS])
    best_3 = _best_candidate(sweep[sweep["round_trip_cost_bps"] == 3])
    decision = "pass" if not gated.empty else "fail"
    failed_criteria = [] if decision == "pass" else _failed_criteria(sweep)
    return {
        "decision": decision,
        "reason": _reason(decision, failed_criteria),
        "best_6bps_candidate": best_6,
        "best_3bps_candidate": best_3,
        "full_gate_pass_count": int(len(gated)),
        "research_status": "paper_research_passed" if decision == "pass" else "research_only",
        "recommended_next_step": _recommended_next_step(decision),
        "failed_criteria": failed_criteria,
        "replay_report": str(replay_report_path),
    }


def _full_gate_rows(sweep: pd.DataFrame) -> pd.DataFrame:
    return sweep[
        (sweep["total_trades"] >= MIN_TRADES)
        & (sweep["net_pnl"] > 0)
        & (_win_rate_fraction(sweep["net_win_rate"]) >= MIN_NET_WIN_RATE)
        & (sweep["positive_dates_count"] >= MIN_POSITIVE_DATES)
        & (sweep["positive_symbols_count"] >= MIN_POSITIVE_SYMBOLS)
        & (sweep["round_trip_cost_bps"] >= MIN_COST_BPS)
    ]


def _win_rate_fraction(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    return numeric.where(numeric <= 1.0, numeric / 100.0)


def _best_candidate(frame: pd.DataFrame) -> dict[str, Any] | None:
    if frame.empty:
        return None
    row = frame.sort_values(["net_pnl", "net_win_rate", "total_trades"], ascending=[False, False, False]).iloc[0]
    return {key: _json_value(value) for key, value in row.to_dict().items()}


def _json_value(value: object) -> object:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _failed_criteria(sweep: pd.DataFrame) -> list[str]:
    return [
        criterion
        for criterion, passed in [
            ("total_trades >= 20", bool((sweep["total_trades"] >= MIN_TRADES).any())),
            ("net_pnl > 0", bool((sweep["net_pnl"] > 0).any())),
            ("net_win_rate >= 55%", bool((_win_rate_fraction(sweep["net_win_rate"]) >= MIN_NET_WIN_RATE).any())),
            ("positive_dates_count >= 2", bool((sweep["positive_dates_count"] >= MIN_POSITIVE_DATES).any())),
            ("positive_symbols_count >= 2", bool((sweep["positive_symbols_count"] >= MIN_POSITIVE_SYMBOLS).any())),
            (
                "all full-gate criteria together at round_trip_cost_bps >= 6",
                bool(not _full_gate_rows(sweep).empty),
            ),
        ]
        if not passed
    ]


def _reason(decision: str, failed_criteria: list[str]) -> str:
    if decision == "pass":
        return "At least one parameter set passed the full 6 bps robustness gate."
    return "No parameter set passed the full 6 bps robustness gate."


def _recommended_next_step(decision: str) -> str:
    if decision == "pass":
        return "Keep the signal in offline/paper research and expand out-of-sample validation before any review."
    return (
        "Keep the signal research-only; collect more out-of-sample dates and improve cost/slippage assumptions "
        "before considering any paper-trading escalation."
    )


def _decision_markdown(decision: dict[str, Any], *, sweep_path: Path) -> str:
    lines = [
        "# M4.2 Paper Signal Decision Gate",
        "",
        f"Decision: **{decision['decision']}**",
        f"Research status: `{decision['research_status']}`",
        "",
        f"Reason: {decision['reason']}",
        "",
        "Live trading remains forbidden. This gate is based on offline replay only and must not be used to "
        "place orders, call private APIs, enable live trading, or connect to a CME live stream.",
        "",
        f"Sweep input: `{sweep_path}`",
        "",
        "## Why Research-Only",
        "",
        "The signal remains research-only unless it is profitable after at least 6 bps round-trip cost, "
        "has enough trades, and is positive across multiple dates and CME symbols.",
        "",
        "## Best 6 Bps Result",
        "",
    ]
    lines.extend(_candidate_lines(decision.get("best_6bps_candidate")))
    lines.extend(["", "## Best 3 Bps Result", ""])
    lines.extend(_candidate_lines(decision.get("best_3bps_candidate")))
    lines.extend(["", "## Failed Criteria", ""])
    failed = decision.get("failed_criteria") or []
    if failed:
        lines.extend([f"- {item}" for item in failed])
    else:
        lines.append("No failed criteria.")
    lines.extend(["", "## Next Research Recommendations", ""])
    lines.append(f"- {decision['recommended_next_step']}")
    lines.append("- Re-run the gate only after new out-of-sample dates or materially better execution-cost evidence.")
    return "\n".join(lines).rstrip() + "\n"


def _candidate_lines(candidate: Any) -> list[str]:
    if not candidate:
        return ["No candidate."]
    fields = [
        "min_cme_return_bps",
        "round_trip_cost_bps",
        "cooldown_minutes",
        "cme_symbol_set",
        "total_trades",
        "net_pnl",
        "net_win_rate",
        "positive_dates_count",
        "positive_symbols_count",
    ]
    return [f"- {field}: {candidate.get(field)}" for field in fields]


if __name__ == "__main__":
    main()

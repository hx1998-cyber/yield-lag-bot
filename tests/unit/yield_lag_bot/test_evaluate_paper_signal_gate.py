from __future__ import annotations

import json

import pandas as pd

from yield_lag_bot.jobs.evaluate_paper_signal_gate import evaluate_paper_signal_gate


def test_gate_passes_when_all_filters_pass(tmp_path) -> None:
    decision = _run_gate(tmp_path, [_row()])

    assert decision["decision"] == "pass"
    assert decision["research_status"] == "paper_research_passed"
    assert decision["full_gate_pass_count"] == 1


def test_gate_fails_when_positive_only_at_3_bps(tmp_path) -> None:
    decision = _run_gate(tmp_path, [_row(round_trip_cost_bps=3)])

    assert decision["decision"] == "fail"
    assert decision["research_status"] == "research_only"


def test_gate_fails_when_positive_dates_count_below_two(tmp_path) -> None:
    decision = _run_gate(tmp_path, [_row(positive_dates_count=1)])

    assert decision["decision"] == "fail"
    assert "all full-gate criteria together at round_trip_cost_bps >= 6" in decision["failed_criteria"]


def test_gate_fails_when_trades_below_twenty(tmp_path) -> None:
    decision = _run_gate(tmp_path, [_row(total_trades=19)])

    assert decision["decision"] == "fail"
    assert "all full-gate criteria together at round_trip_cost_bps >= 6" in decision["failed_criteria"]


def test_gate_writes_json_and_markdown(tmp_path) -> None:
    _run_gate(tmp_path, [_row()])

    payload = json.loads((tmp_path / "decision.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "decision.md").read_text(encoding="utf-8")
    assert payload["decision"] == "pass"
    assert "M4.2 Paper Signal Decision Gate" in markdown
    assert "Live trading remains forbidden" in markdown


def _run_gate(tmp_path, rows: list[dict[str, object]]) -> dict[str, object]:
    sweep_path = tmp_path / "sweep.csv"
    replay_report_path = tmp_path / "replay.md"
    replay_report_path.write_text("offline replay", encoding="utf-8")
    pd.DataFrame(rows).to_csv(sweep_path, index=False)
    return evaluate_paper_signal_gate(
        sweep=sweep_path,
        replay_report=replay_report_path,
        out=tmp_path / "decision.json",
        markdown=tmp_path / "decision.md",
    )


def _row(
    *,
    total_trades: int = 20,
    net_pnl: float = 1.0,
    net_win_rate: float = 0.55,
    positive_dates_count: int = 2,
    positive_symbols_count: int = 2,
    round_trip_cost_bps: float = 6.0,
) -> dict[str, object]:
    return {
        "min_cme_return_bps": 0.5,
        "round_trip_cost_bps": round_trip_cost_bps,
        "cooldown_minutes": 1,
        "cme_symbol_set": "all_robust_eth_symbols",
        "total_trades": total_trades,
        "gross_pnl": 2.0,
        "net_pnl": net_pnl,
        "gross_win_rate": 0.70,
        "net_win_rate": net_win_rate,
        "avg_net_pnl": 0.05,
        "avg_net_bps": 5.0,
        "max_drawdown": -0.1,
        "profit_factor": 1.5,
        "positive_dates_count": positive_dates_count,
        "total_dates_count": 2,
        "positive_symbols_count": positive_symbols_count,
        "total_symbols_count": 2,
    }

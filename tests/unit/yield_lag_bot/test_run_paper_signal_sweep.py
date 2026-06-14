from __future__ import annotations

import hashlib

import pandas as pd

from yield_lag_bot.jobs.run_paper_signal_sweep import run_paper_signal_sweep


def test_sweep_creates_all_parameter_combinations(tmp_path) -> None:
    summary_path = _write_inputs(tmp_path)

    sweep = run_paper_signal_sweep(
        summary=summary_path,
        out=tmp_path / "sweep.csv",
        report=tmp_path / "sweep.md",
    )

    assert len(sweep) == 630
    assert (tmp_path / "sweep.csv").exists()
    assert (tmp_path / "sweep.md").exists()


def test_sweep_does_not_mutate_input_files(tmp_path) -> None:
    summary_path = _write_inputs(tmp_path)
    before = _sha256(summary_path)

    run_paper_signal_sweep(
        summary=summary_path,
        out=tmp_path / "sweep.csv",
        report=tmp_path / "sweep.md",
    )

    assert _sha256(summary_path) == before


def test_sweep_positive_dates_count(tmp_path) -> None:
    summary_path = _write_inputs(tmp_path)

    sweep = run_paper_signal_sweep(
        summary=summary_path,
        out=tmp_path / "sweep.csv",
        report=tmp_path / "sweep.md",
    )

    row = _row(sweep, cost=0, symbols="all_robust_eth_symbols")
    assert row["positive_dates_count"] == 2
    assert row["total_dates_count"] == 2


def test_sweep_positive_symbols_count(tmp_path) -> None:
    summary_path = _write_inputs(tmp_path)

    sweep = run_paper_signal_sweep(
        summary=summary_path,
        out=tmp_path / "sweep.csv",
        report=tmp_path / "sweep.md",
    )

    row = _row(sweep, cost=0, symbols="all_robust_eth_symbols")
    assert row["positive_symbols_count"] == 2
    assert row["total_symbols_count"] == 2


def test_sweep_cost_sensitivity_reduces_net_pnl(tmp_path) -> None:
    summary_path = _write_inputs(tmp_path)

    sweep = run_paper_signal_sweep(
        summary=summary_path,
        out=tmp_path / "sweep.csv",
        report=tmp_path / "sweep.md",
    )

    zero_cost = _row(sweep, cost=0, symbols="all_robust_eth_symbols")
    high_cost = _row(sweep, cost=10, symbols="all_robust_eth_symbols")
    assert high_cost["net_pnl"] < zero_cost["net_pnl"]


def _row(sweep: pd.DataFrame, *, cost: float, symbols: str) -> pd.Series:
    return sweep[
        (sweep["min_cme_return_bps"] == 0.5)
        & (sweep["round_trip_cost_bps"] == cost)
        & (sweep["cooldown_minutes"] == 1)
        & (sweep["cme_symbol_set"] == symbols)
    ].iloc[0]


def _write_inputs(tmp_path):
    znu_detail = tmp_path / "znu_detail.csv"
    ztu_detail = tmp_path / "ztu_detail.csv"
    _write_detail(znu_detail, "2026-06-10T12:01:00Z")
    _write_detail(ztu_detail, "2026-06-11T12:01:00Z")
    summary_path = tmp_path / "summary.csv"
    pd.DataFrame(
        [
            _candidate_row("ZNU6", znu_detail, "2026-06-10T12:15:00Z"),
            _candidate_row("ZTU6", ztu_detail, "2026-06-11T12:15:00Z"),
        ]
    ).to_csv(summary_path, index=False)
    return summary_path


def _write_detail(path, timestamp: str) -> None:
    pd.DataFrame(
        [
            {
                "timestamp": timestamp,
                "cme_return_bps": -1.0,
                "crypto_forward_return_1m_bps": 20.0,
            }
        ]
    ).to_csv(path, index=False)


def _candidate_row(cme_symbol: str, result_path, event_time_utc: str) -> dict[str, object]:
    return {
        "event_name": f"{cme_symbol}_event",
        "event_time_utc": event_time_utc,
        "cme_symbol": cme_symbol,
        "crypto_symbol": "ETH",
        "best_horizon": "1m",
        "signal_direction": "inverse",
        "candidate_tier": "strong_candidate",
        "candidate_score": 42.0,
        "result_path": str(result_path),
    }


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

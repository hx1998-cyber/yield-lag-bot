from __future__ import annotations

import pandas as pd

from yield_lag_bot.jobs.run_paper_signal_replay import run_paper_signal_replay


def test_inverse_signal_maps_cme_up_to_eth_short(tmp_path) -> None:
    detail_path = tmp_path / "detail.csv"
    summary_path = tmp_path / "summary.csv"
    _write_detail(detail_path, [{"timestamp": "2026-06-12T12:01:00Z", "cme": 1.0, "eth": -10.0}])
    _write_summary(summary_path, detail_path)

    trades = run_paper_signal_replay(
        summary=summary_path,
        out=tmp_path / "replay.csv",
        report=tmp_path / "report.md",
        round_trip_cost_bps=0,
    )

    assert trades.iloc[0]["paper_side"] == "short"
    assert trades.iloc[0]["gross_pnl"] == 0.10


def test_inverse_signal_maps_cme_down_to_eth_long(tmp_path) -> None:
    detail_path = tmp_path / "detail.csv"
    summary_path = tmp_path / "summary.csv"
    _write_detail(detail_path, [{"timestamp": "2026-06-12T12:01:00Z", "cme": -1.0, "eth": 10.0}])
    _write_summary(summary_path, detail_path)

    trades = run_paper_signal_replay(
        summary=summary_path,
        out=tmp_path / "replay.csv",
        report=tmp_path / "report.md",
        round_trip_cost_bps=0,
    )

    assert trades.iloc[0]["paper_side"] == "long"
    assert trades.iloc[0]["gross_pnl"] == 0.10


def test_replay_uses_same_row_forward_return_without_lookahead(tmp_path) -> None:
    detail_path = tmp_path / "detail.csv"
    summary_path = tmp_path / "summary.csv"
    _write_detail(
        detail_path,
        [
            {"timestamp": "2026-06-12T12:01:00Z", "cme": -1.0, "eth": 10.0},
            {"timestamp": "2026-06-12T12:02:00Z", "cme": 0.0, "eth": -100.0},
        ],
    )
    _write_summary(summary_path, detail_path)

    trades = run_paper_signal_replay(
        summary=summary_path,
        out=tmp_path / "replay.csv",
        report=tmp_path / "report.md",
        round_trip_cost_bps=0,
    )

    assert len(trades) == 1
    assert trades.iloc[0]["eth_forward_return_bps"] == 10.0
    assert trades.iloc[0]["gross_pnl"] == 0.10


def test_cost_reduces_net_pnl(tmp_path) -> None:
    detail_path = tmp_path / "detail.csv"
    summary_path = tmp_path / "summary.csv"
    _write_detail(detail_path, [{"timestamp": "2026-06-12T12:01:00Z", "cme": -1.0, "eth": 10.0}])
    _write_summary(summary_path, detail_path)

    trades = run_paper_signal_replay(
        summary=summary_path,
        out=tmp_path / "replay.csv",
        report=tmp_path / "report.md",
        round_trip_cost_bps=6,
    )

    assert trades.iloc[0]["gross_pnl"] == 0.10
    assert trades.iloc[0]["cost"] == 0.06
    assert trades.iloc[0]["net_pnl"] == 0.04


def test_threshold_filters_small_cme_moves(tmp_path) -> None:
    detail_path = tmp_path / "detail.csv"
    summary_path = tmp_path / "summary.csv"
    _write_detail(detail_path, [{"timestamp": "2026-06-12T12:01:00Z", "cme": 0.49, "eth": -10.0}])
    _write_summary(summary_path, detail_path)

    trades = run_paper_signal_replay(
        summary=summary_path,
        out=tmp_path / "replay.csv",
        report=tmp_path / "report.md",
        min_cme_return_bps=0.5,
    )

    assert trades.empty


def test_cooldown_prevents_duplicate_trades(tmp_path) -> None:
    detail_path = tmp_path / "detail.csv"
    summary_path = tmp_path / "summary.csv"
    _write_detail(
        detail_path,
        [
            {"timestamp": "2026-06-12T12:01:00Z", "cme": -1.0, "eth": 10.0},
            {"timestamp": "2026-06-12T12:02:00Z", "cme": -1.0, "eth": 10.0},
            {"timestamp": "2026-06-12T12:03:00Z", "cme": -1.0, "eth": 10.0},
        ],
    )
    _write_summary(summary_path, detail_path)

    trades = run_paper_signal_replay(
        summary=summary_path,
        out=tmp_path / "replay.csv",
        report=tmp_path / "report.md",
        cooldown_minutes=2,
        round_trip_cost_bps=0,
    )

    assert list(trades["signal_time_utc"]) == ["2026-06-12T12:01:00Z", "2026-06-12T12:03:00Z"]


def test_empty_candidate_input_writes_clear_report(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    pd.DataFrame([_candidate_row(result_path=tmp_path / "detail.csv", crypto_symbol="BTC")]).to_csv(
        summary_path,
        index=False,
    )

    trades = run_paper_signal_replay(
        summary=summary_path,
        out=tmp_path / "replay.csv",
        report=tmp_path / "report.md",
    )

    assert trades.empty
    assert "No eligible strong ETH inverse 1m candidates" in (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Offline replay only" in (tmp_path / "report.md").read_text(encoding="utf-8")


def _write_detail(path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(
        [
            {
                "status": "ok",
                "timestamp": row["timestamp"],
                "cme_return_bps": row["cme"],
                "crypto_forward_return_1m_bps": row["eth"],
            }
            for row in rows
        ]
    ).to_csv(path, index=False)


def _write_summary(path, detail_path) -> None:
    pd.DataFrame([_candidate_row(result_path=detail_path)]).to_csv(path, index=False)


def _candidate_row(
    *,
    result_path,
    cme_symbol: str = "ZNU6",
    crypto_symbol: str = "ETH",
) -> dict[str, object]:
    return {
        "event_name": "event",
        "event_time_utc": "2026-06-12T12:15:00Z",
        "cme_symbol": cme_symbol,
        "crypto_symbol": crypto_symbol,
        "best_horizon": "1m",
        "signal_direction": "inverse",
        "candidate_tier": "strong_candidate",
        "candidate_score": 42.0,
        "result_path": str(result_path),
    }

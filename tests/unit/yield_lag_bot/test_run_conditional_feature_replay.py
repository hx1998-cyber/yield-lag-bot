from __future__ import annotations

import pandas as pd

from yield_lag_bot.jobs.run_conditional_feature_replay import run_conditional_feature_replay


def test_conditional_replay_filter_conditions_work(tmp_path) -> None:
    features_path = _write_features(tmp_path)

    result = run_conditional_feature_replay(
        features=features_path,
        out=tmp_path / "out.csv",
        report=tmp_path / "report.md",
    )

    high = _row(result, "high_cme_move", 0)
    curve_down = _row(result, "curve_consensus_down", 0)
    very_high_curve_down = _row(result, "very_high_and_curve_down", 0)
    assert high["rows"] == 4
    assert curve_down["rows"] == 3
    assert very_high_curve_down["rows"] == 1


def test_conditional_replay_pnl_direction_logic_works(tmp_path) -> None:
    features_path = _write_features(tmp_path)

    result = run_conditional_feature_replay(
        features=features_path,
        out=tmp_path / "out.csv",
        report=tmp_path / "report.md",
    )

    high = _row(result, "high_cme_move", 0)
    assert high["gross_pnl"] > 0
    assert high["gross_win_rate"] == 1.0


def test_conditional_replay_costs_reduce_net_pnl(tmp_path) -> None:
    features_path = _write_features(tmp_path)

    result = run_conditional_feature_replay(
        features=features_path,
        out=tmp_path / "out.csv",
        report=tmp_path / "report.md",
    )

    zero = _row(result, "high_cme_move", 0)
    ten = _row(result, "high_cme_move", 10)
    assert ten["net_pnl"] < zero["net_pnl"]


def test_conditional_replay_positive_dates_count_works(tmp_path) -> None:
    features_path = _write_features(tmp_path)

    result = run_conditional_feature_replay(
        features=features_path,
        out=tmp_path / "out.csv",
        report=tmp_path / "report.md",
    )

    high = _row(result, "high_cme_move", 0)
    assert high["positive_dates_count"] == 2


def test_conditional_replay_positive_symbols_count_works(tmp_path) -> None:
    features_path = _write_features(tmp_path)

    result = run_conditional_feature_replay(
        features=features_path,
        out=tmp_path / "out.csv",
        report=tmp_path / "report.md",
    )

    high = _row(result, "high_cme_move", 0)
    assert high["positive_symbols_count"] == 2


def test_conditional_replay_pass_research_gate_works(tmp_path) -> None:
    features_path = tmp_path / "features.csv"
    rows = []
    for i in range(10):
        rows.append(_feature_row("2026-06-11", "ZNU6", -1.0, 10.0, 0, 2))
        rows.append(_feature_row("2026-06-12", "ZTU6", 1.0, -10.0, 2, 0))
    pd.DataFrame(rows).to_csv(features_path, index=False)

    result = run_conditional_feature_replay(
        features=features_path,
        out=tmp_path / "out.csv",
        report=tmp_path / "report.md",
    )

    high_6 = _row(result, "high_cme_move", 6)
    assert high_6["pass_research_gate"] == True


def test_conditional_replay_report_handles_no_passing_filters(tmp_path) -> None:
    features_path = _write_features(tmp_path)

    run_conditional_feature_replay(
        features=features_path,
        out=tmp_path / "out.csv",
        report=tmp_path / "report.md",
    )

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "No pre-registered conditional filter passed" in report
    assert "Research-only" in report


def _row(result: pd.DataFrame, filter_name: str, cost_bps: float) -> pd.Series:
    return result[
        (result["filter_name"] == filter_name)
        & (result["round_trip_cost_bps"] == cost_bps)
    ].iloc[0]


def _write_features(tmp_path):
    path = tmp_path / "features.csv"
    pd.DataFrame(
        [
            _feature_row("2026-06-11", "ZNU6", -0.6, 10.0, 0, 2),
            _feature_row("2026-06-11", "ZTU6", 0.8, -10.0, 2, 0),
            _feature_row("2026-06-12", "ZNU6", -1.2, 20.0, 0, 2),
            _feature_row("2026-06-12", "ZTU6", 1.5, -20.0, 1, 1),
            _feature_row("2026-06-12", "ZNM6", 0.2, -20.0, 0, 2),
        ]
    ).to_csv(path, index=False)
    return path


def _feature_row(
    date: str,
    cme_symbol: str,
    cme_return_bps: float,
    eth_forward_return_1m_bps: float,
    curve_up_count: int,
    curve_down_count: int,
) -> dict[str, object]:
    return {
        "event_name": "event",
        "event_time_utc": f"{date}T12:15:00Z",
        "date": date,
        "cme_symbol": cme_symbol,
        "crypto_symbol": "ETH",
        "timestamp": f"{date}T12:01:00Z",
        "cme_return_bps": cme_return_bps,
        "abs_cme_return_bps": abs(cme_return_bps),
        "eth_forward_return_1m_bps": eth_forward_return_1m_bps,
        "curve_up_count": curve_up_count,
        "curve_down_count": curve_down_count,
    }

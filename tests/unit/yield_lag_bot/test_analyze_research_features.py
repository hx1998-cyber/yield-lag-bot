from __future__ import annotations

import pandas as pd

from yield_lag_bot.jobs.analyze_research_features import analyze_research_features


def test_feature_diagnostics_binning_works(tmp_path) -> None:
    features_path = _write_features(tmp_path)

    diagnostics = analyze_research_features(
        features=features_path,
        out=tmp_path / "diagnostics.csv",
        markdown=tmp_path / "report.md",
    )

    bins = diagnostics[diagnostics["group_type"] == "abs_cme_return_bps_bin"]
    assert {"0_to_0.25", "0.25_to_0.5", "0.5_to_1.0", "1.0_to_2.0", "2.0_plus"}.issubset(
        set(bins["group_key"])
    )


def test_feature_diagnostics_grouped_outputs_are_generated(tmp_path) -> None:
    features_path = _write_features(tmp_path)

    diagnostics = analyze_research_features(
        features=features_path,
        out=tmp_path / "diagnostics.csv",
        markdown=tmp_path / "report.md",
    )

    assert {"cme_symbol", "date", "event_name", "candidate_tier"}.issubset(
        set(diagnostics["group_type"])
    )
    assert (diagnostics["rows"] > 0).any()


def test_feature_diagnostics_curve_consensus_labels_are_correct(tmp_path) -> None:
    features_path = _write_features(tmp_path)

    diagnostics = analyze_research_features(
        features=features_path,
        out=tmp_path / "diagnostics.csv",
        markdown=tmp_path / "report.md",
    )

    conditions = diagnostics[diagnostics["group_type"] == "condition"]
    counts = dict(zip(conditions["group_key"], conditions["rows"], strict=False))
    assert counts["curve_consensus_up"] == 1
    assert counts["curve_consensus_down"] == 1
    assert counts["mixed_curve"] == 2


def test_feature_diagnostics_report_handles_low_row_groups(tmp_path) -> None:
    features_path = _write_features(tmp_path)

    analyze_research_features(
        features=features_path,
        out=tmp_path / "diagnostics.csv",
        markdown=tmp_path / "report.md",
    )

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Best Bins By Inverse Correct Rate" in report
    assert "No rows." in report
    assert "research-only" in report


def test_feature_diagnostics_create_no_trading_or_pnl_fields(tmp_path) -> None:
    features_path = _write_features(tmp_path)

    diagnostics = analyze_research_features(
        features=features_path,
        out=tmp_path / "diagnostics.csv",
        markdown=tmp_path / "report.md",
    )

    forbidden = {"gross_pnl", "net_pnl", "paper_side", "order_id", "position"}
    assert forbidden.isdisjoint(diagnostics.columns)


def _write_features(tmp_path):
    path = tmp_path / "features.csv"
    pd.DataFrame(
        [
            _row("ZNU6", "event_a", 0.10, 0.10, 1, 0, True, 5.0),
            _row("ZNU6", "event_a", 0.30, 0.30, 0, 1, False, -5.0),
            _row("ZTU6", "event_b", 0.75, 0.75, 1, 1, True, 10.0),
            _row("ZNM6", "event_b", 1.50, 1.50, 1, 1, False, -10.0),
            _row("ZNM6", "event_c", 2.50, 2.50, 2, 0, True, 20.0),
            _row("ZTU6", "event_c", 0.60, 0.60, 0, 2, False, -20.0),
        ]
    ).to_csv(path, index=False)
    return path


def _row(
    cme_symbol: str,
    event_name: str,
    abs_cme_return_bps: float,
    curve_abs_return_bps_max: float,
    curve_up_count: int,
    curve_down_count: int,
    inverse_correct: bool,
    eth_return: float,
) -> dict[str, object]:
    return {
        "event_name": event_name,
        "event_time_utc": "2026-06-12T12:15:00Z",
        "date": "2026-06-12",
        "cme_symbol": cme_symbol,
        "crypto_symbol": "ETH",
        "timestamp": "2026-06-12T12:01:00Z",
        "cme_return_bps": abs_cme_return_bps,
        "abs_cme_return_bps": abs_cme_return_bps,
        "cme_return_sign": 1,
        "eth_forward_return_1m_bps": eth_return,
        "inverse_correct_1m": inverse_correct,
        "candidate_tier": "strong_candidate",
        "curve_symbol_count": curve_up_count + curve_down_count,
        "curve_up_count": curve_up_count,
        "curve_down_count": curve_down_count,
        "curve_net_direction": curve_up_count - curve_down_count,
        "curve_abs_return_bps_avg": curve_abs_return_bps_max / 2,
        "curve_abs_return_bps_max": curve_abs_return_bps_max,
    }

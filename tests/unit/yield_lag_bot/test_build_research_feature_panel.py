from __future__ import annotations

import pandas as pd

from yield_lag_bot.jobs.build_research_feature_panel import build_research_feature_panel


def test_feature_panel_reads_ranked_summary_and_detail_files(tmp_path) -> None:
    ranked_path = _write_inputs(tmp_path)

    panel = build_research_feature_panel(
        ranked=ranked_path,
        out=tmp_path / "panel.csv",
        report=tmp_path / "report.md",
    )

    assert len(panel) == 4
    assert set(panel["cme_symbol"]) == {"ZNU6", "ZTU6"}
    assert (tmp_path / "panel.csv").exists()
    assert (tmp_path / "report.md").exists()


def test_feature_panel_filters_to_eth_inverse_1m(tmp_path) -> None:
    ranked_path = _write_inputs(tmp_path)

    panel = build_research_feature_panel(
        ranked=ranked_path,
        out=tmp_path / "panel.csv",
        report=tmp_path / "report.md",
    )

    assert set(panel["crypto_symbol"]) == {"ETH"}
    assert "BTC" not in set(panel["crypto_symbol"])


def test_feature_panel_computes_inverse_expected_side(tmp_path) -> None:
    ranked_path = _write_inputs(tmp_path)

    panel = build_research_feature_panel(
        ranked=ranked_path,
        out=tmp_path / "panel.csv",
        report=tmp_path / "report.md",
    )

    sides = dict(zip(panel["cme_return_bps"], panel["inverse_expected_side"], strict=False))
    assert sides[1.0] == "short"
    assert sides[-1.0] == "long"


def test_feature_panel_computes_inverse_correct_1m(tmp_path) -> None:
    ranked_path = _write_inputs(tmp_path)

    panel = build_research_feature_panel(
        ranked=ranked_path,
        out=tmp_path / "panel.csv",
        report=tmp_path / "report.md",
    )

    correct = dict(zip(panel["cme_return_bps"], panel["inverse_correct_1m"], strict=False))
    assert correct[1.0] == True
    assert correct[-1.0] == True


def test_feature_panel_computes_curve_consensus_features(tmp_path) -> None:
    ranked_path = _write_inputs(tmp_path)

    panel = build_research_feature_panel(
        ranked=ranked_path,
        out=tmp_path / "panel.csv",
        report=tmp_path / "report.md",
    )

    first_timestamp = panel[panel["timestamp"] == "2026-06-12T12:01:00Z"].iloc[0]
    assert first_timestamp["curve_symbol_count"] == 2
    assert first_timestamp["curve_up_count"] == 1
    assert first_timestamp["curve_down_count"] == 1
    assert first_timestamp["curve_net_direction"] == 0
    assert first_timestamp["curve_abs_return_bps_max"] == 1.0


def test_feature_panel_writes_csv_and_markdown(tmp_path) -> None:
    ranked_path = _write_inputs(tmp_path)

    build_research_feature_panel(
        ranked=ranked_path,
        out=tmp_path / "panel.csv",
        report=tmp_path / "report.md",
    )

    written = pd.read_csv(tmp_path / "panel.csv")
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert len(written) == 4
    assert "Research-only feature panel" in report
    assert "Inverse Correct 1m By CME Symbol" in report


def _write_inputs(tmp_path):
    znu_detail = tmp_path / "znu_detail.csv"
    ztu_detail = tmp_path / "ztu_detail.csv"
    btc_detail = tmp_path / "btc_detail.csv"
    _write_detail(znu_detail, [1.0, -1.0])
    _write_detail(ztu_detail, [-1.0, 1.0])
    _write_detail(btc_detail, [1.0])
    ranked_path = tmp_path / "ranked.csv"
    pd.DataFrame(
        [
            _ranked_row("ZNU6", "ETH", znu_detail, "strong_candidate"),
            _ranked_row("ZTU6", "ETH", ztu_detail, "watchlist"),
            _ranked_row("ZNU6", "BTC", btc_detail, "strong_candidate"),
            {
                **_ranked_row("ZNU6", "ETH", znu_detail, "strong_candidate"),
                "signal_direction": "positive",
            },
        ]
    ).to_csv(ranked_path, index=False)
    return ranked_path


def _write_detail(path, cme_returns: list[float]) -> None:
    rows = []
    for index, cme_return in enumerate(cme_returns, start=1):
        rows.append(
            {
                "timestamp": f"2026-06-12T12:0{index}:00Z",
                "cme_return_bps": cme_return,
                "crypto_forward_return_1m_bps": -10.0 if cme_return > 0 else 10.0,
                "crypto_forward_return_3m_bps": -20.0 if cme_return > 0 else 20.0,
                "crypto_forward_return_5m_bps": -30.0 if cme_return > 0 else 30.0,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def _ranked_row(cme_symbol: str, crypto_symbol: str, result_path, candidate_tier: str) -> dict[str, object]:
    return {
        "event_name": "event",
        "event_time_utc": "2026-06-12T12:15:00Z",
        "cme_symbol": cme_symbol,
        "crypto_symbol": crypto_symbol,
        "signal_direction": "inverse",
        "best_horizon": "1m",
        "candidate_tier": candidate_tier,
        "candidate_score": 42.0,
        "result_path": str(result_path),
    }

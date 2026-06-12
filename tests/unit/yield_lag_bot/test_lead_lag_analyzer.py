from __future__ import annotations

import math
import warnings

import pandas as pd

from yield_lag_bot.research.lead_lag_analyzer import LeadLagAnalyzer, LeadLagResult


def test_lead_lag_analyzer_aligns_windows_correctly() -> None:
    ticks = pd.DataFrame(
        [
            {"symbol": "ZN", "receive_ts": "2024-01-01T00:00:00.000Z", "bid_price": 99, "ask_price": 101},
            {"symbol": "BTCUSDT", "receive_ts": "2024-01-01T00:00:00.000Z", "bid_price": 199, "ask_price": 201},
            {"symbol": "ZN", "receive_ts": "2024-01-01T00:00:00.100Z", "bid_price": 100, "ask_price": 102},
            {"symbol": "BTCUSDT", "receive_ts": "2024-01-01T00:00:00.100Z", "bid_price": 201, "ask_price": 203},
            {"symbol": "ZN", "receive_ts": "2024-01-01T00:00:00.200Z", "bid_price": 101, "ask_price": 103},
            {"symbol": "BTCUSDT", "receive_ts": "2024-01-01T00:00:00.200Z", "bid_price": 203, "ask_price": 205},
        ]
    )

    analyzer = LeadLagAnalyzer(windows_ms=(100,), horizons_ms=(100,))
    aligned = analyzer.align_symbol_pair(
        ticks,
        cme_symbol="ZN",
        crypto_symbol="BTCUSDT",
        frequency_ms=100,
    )
    results = analyzer.analyze_pair(ticks, cme_symbol="ZN", crypto_symbol="BTCUSDT")

    assert list(aligned.columns) == ["BTCUSDT", "ZN"]
    assert len(aligned) == 3
    assert aligned.loc[pd.Timestamp("2024-01-01T00:00:00.100Z"), "ZN"] == 101
    assert len(results) == 1
    assert results[0].window_ms == 100
    assert results[0].horizon_ms == 100
    assert results[0].sample_count == 1


def test_write_report_serializes_lead_lag_result(tmp_path) -> None:
    report_path = tmp_path / "lead_lag_report.csv"
    result = LeadLagResult(
        cme_symbol="BTC",
        crypto_symbol="ETH",
        window_ms=100,
        horizon_ms=100,
        sample_count=3,
        correlation=0.5,
        hit_rate=1.0,
        average_forward_return_bps=12.5,
        estimated_fee_bps=5.0,
        estimated_slippage_bps=2.0,
        net_forward_return_bps=5.5,
    )

    LeadLagAnalyzer().write_report([result], report_path)

    report = pd.read_csv(report_path)
    assert report.to_dict("records") == [
        {
            "cme_symbol": "BTC",
            "crypto_symbol": "ETH",
            "window_ms": 100,
            "horizon_ms": 100,
            "sample_count": 3,
            "correlation": 0.5,
            "hit_rate": 1.0,
            "average_forward_return_bps": 12.5,
            "estimated_fee_bps": 5.0,
            "estimated_slippage_bps": 2.0,
            "net_forward_return_bps": 5.5,
        }
    ]


def test_write_report_handles_empty_results(tmp_path) -> None:
    report_path = tmp_path / "empty_report.csv"

    LeadLagAnalyzer().write_report([], report_path)

    report = pd.read_csv(report_path)
    assert report.empty
    assert list(report.columns) == [
        "cme_symbol",
        "crypto_symbol",
        "window_ms",
        "horizon_ms",
        "sample_count",
        "correlation",
        "hit_rate",
        "average_forward_return_bps",
        "estimated_fee_bps",
        "estimated_slippage_bps",
        "net_forward_return_bps",
    ]


def test_analyze_pair_does_not_warn_when_one_price_series_is_constant() -> None:
    ticks = pd.DataFrame(
        [
            {"symbol": "BTC", "receive_ts": "2024-01-01T00:00:00.000Z", "mid_price": 100.0},
            {"symbol": "ETH", "receive_ts": "2024-01-01T00:00:00.000Z", "mid_price": 200.0},
            {"symbol": "BTC", "receive_ts": "2024-01-01T00:00:00.100Z", "mid_price": 100.0},
            {"symbol": "ETH", "receive_ts": "2024-01-01T00:00:00.100Z", "mid_price": 201.0},
            {"symbol": "BTC", "receive_ts": "2024-01-01T00:00:00.200Z", "mid_price": 100.0},
            {"symbol": "ETH", "receive_ts": "2024-01-01T00:00:00.200Z", "mid_price": 203.0},
            {"symbol": "BTC", "receive_ts": "2024-01-01T00:00:00.300Z", "mid_price": 100.0},
            {"symbol": "ETH", "receive_ts": "2024-01-01T00:00:00.300Z", "mid_price": 206.0},
        ]
    )
    analyzer = LeadLagAnalyzer(windows_ms=(100,), horizons_ms=(100,))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        results = analyzer.analyze_pair(ticks, cme_symbol="BTC", crypto_symbol="ETH")

    assert results
    assert math.isnan(results[0].correlation)
    assert caught == []


def test_prepare_ticks_prefers_mid_then_bbo_mid_then_last_price() -> None:
    ticks = pd.DataFrame(
        [
            {
                "symbol": "BTC",
                "receive_ts": "2024-01-01T00:00:00.000Z",
                "mid_price": "100",
                "bid_price": "90",
                "ask_price": "92",
                "last_price": "80",
            },
            {
                "symbol": "BTC",
                "receive_ts": "2024-01-01T00:00:00.100Z",
                "mid_price": None,
                "bid_price": "101",
                "ask_price": "103",
                "last_price": "99",
            },
            {
                "symbol": "BTC",
                "receive_ts": "2024-01-01T00:00:00.200Z",
                "mid_price": None,
                "bid_price": None,
                "ask_price": None,
                "last_price": "104",
            },
        ]
    )

    prepared = LeadLagAnalyzer().prepare_ticks(ticks)

    assert prepared["mid_price"].tolist() == [100.0, 102.0, 104.0]

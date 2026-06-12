from __future__ import annotations

import pandas as pd

from yield_lag_bot.jobs.run_lead_lag_study import (
    load_cme_ticks,
    load_crypto_ticks,
    run_study,
)
from yield_lag_bot.research.lead_lag_analyzer import LeadLagAnalyzer


def test_cme_csv_alias_columns(tmp_path) -> None:
    path = tmp_path / "cme_alias.csv"
    path.write_text(
        "ts,symbol,bid,ask,price\n"
        "2024-01-01T00:00:00Z,ZN,108.10,108.12,108.11\n",
        encoding="utf-8",
    )

    ticks = load_cme_ticks(path, symbol="ZN")

    assert ticks.to_dict("records") == [
        {
            "symbol": "ZN",
            "receive_ts": pd.Timestamp("2024-01-01T00:00:00Z"),
            "bid_price": 108.10,
            "ask_price": 108.12,
            "last_price": 108.11,
        }
    ]


def test_crypto_bbo_prefers_mid_price(tmp_path) -> None:
    path = tmp_path / "ticks_bbo.csv"
    path.write_text(
        "symbol,receive_ts,bid_price,ask_price,last_price,mid_price\n"
        "BTC,2024-01-01T00:00:00Z,90,92,80,100\n"
        "BTC,2024-01-01T00:00:00.100Z,101,103,99,\n"
        "BTC,2024-01-01T00:00:00.200Z,,,104,\n",
        encoding="utf-8",
    )

    ticks = load_crypto_ticks(path, symbol="BTC")
    prepared = LeadLagAnalyzer().prepare_ticks(ticks)

    assert prepared["mid_price"].tolist() == [100.0, 102.0, 104.0]


def test_unified_lead_lag_study_output_file_is_created(tmp_path) -> None:
    cme_path = tmp_path / "cme.csv"
    crypto_path = tmp_path / "ticks_bbo.csv"
    out_path = tmp_path / "lead_lag_study.csv"
    cme_path.write_text(
        "timestamp,symbol,bid_price,ask_price,last_price\n"
        "2024-01-01T00:00:00.000Z,ZN,108.100,108.110,108.105\n"
        "2024-01-01T00:00:00.100Z,ZN,108.120,108.130,108.125\n"
        "2024-01-01T00:00:00.200Z,ZN,108.115,108.125,108.120\n",
        encoding="utf-8",
    )
    crypto_path.write_text(
        "symbol,receive_ts,bid_price,ask_price,last_price,mid_price\n"
        "BTC,2024-01-01T00:00:00.000Z,42000,42001,,42000.5\n"
        "BTC,2024-01-01T00:00:00.100Z,42008,42010,,42009\n"
        "BTC,2024-01-01T00:00:00.200Z,42004,42006,,42005\n",
        encoding="utf-8",
    )

    run_study(
        cme_csv=cme_path,
        crypto_csv=crypto_path,
        out=out_path,
        cme_symbol="ZN",
        crypto_symbol="BTC",
    )

    report = pd.read_csv(out_path)
    assert out_path.exists()
    assert not report.empty
    assert set(report["window_ms"]) == {100}
    assert set(report["cme_symbol"]) == {"ZN"}
    assert set(report["crypto_symbol"]) == {"BTC"}


def test_unified_lead_lag_study_empty_input_does_not_crash(tmp_path) -> None:
    cme_path = tmp_path / "cme.csv"
    crypto_path = tmp_path / "ticks_bbo.csv"
    out_path = tmp_path / "lead_lag_study.csv"
    cme_path.write_text(
        "timestamp,symbol,bid_price,ask_price,last_price\n"
        "2024-01-01T00:00:00Z,ZN,,,\n",
        encoding="utf-8",
    )
    crypto_path.write_text(
        "symbol,receive_ts,bid_price,ask_price,last_price,mid_price\n"
        "BTC,2024-01-01T00:00:00Z,,,,\n",
        encoding="utf-8",
    )

    run_study(
        cme_csv=cme_path,
        crypto_csv=crypto_path,
        out=out_path,
        cme_symbol="ZN",
        crypto_symbol="BTC",
    )

    report = pd.read_csv(out_path)
    assert report.empty

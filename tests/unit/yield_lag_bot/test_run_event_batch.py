from __future__ import annotations

from pathlib import Path

import pandas as pd

from yield_lag_bot.jobs.run_event_batch import load_event_batch_config, run_event_batch


def test_event_batch_config_loading(tmp_path: Path) -> None:
    config_path = tmp_path / "events.yaml"
    config_path.write_text(
        """
events:
  - event_name: fomc_test
    event_time_utc: "2026-06-17T18:00:00Z"
    pre_minutes: 60
    post_minutes: 120
    cme_symbols: ["ZNM6", "ZNU6"]
    crypto_symbols: ["BTC", "ETH"]
    cme_dataset: "GLBX.MDP3"
    cme_schema: "mbp-1"
    crypto_interval: "1m"
""",
        encoding="utf-8",
    )

    config = load_event_batch_config(config_path)

    event = config.events[0]
    assert event.event_name == "fomc_test"
    assert event.event_time_utc == "2026-06-17T18:00:00Z"
    assert event.pre_minutes == 60
    assert event.post_minutes == 120
    assert event.cme_symbols == ("ZNM6", "ZNU6")
    assert event.crypto_symbols == ("BTC", "ETH")
    assert event.cme_dataset == "GLBX.MDP3"
    assert event.cme_schema == "mbp-1"
    assert event.crypto_interval == "1m"


def test_event_batch_mocked_successful_batch(tmp_path: Path) -> None:
    config = load_event_batch_config(_write_config(tmp_path, cme_symbols=["ZNM6"], crypto_symbols=["BTC"]))
    calls: list[tuple[str, dict[str, object]]] = []

    def cme_download_func(**kwargs) -> None:
        calls.append(("cme", kwargs))
        Path(kwargs["out"]).write_text("timestamp,symbol,bid_price,ask_price,last_price\n", encoding="utf-8")

    def crypto_download_func(**kwargs) -> None:
        calls.append(("crypto", kwargs))
        Path(kwargs["out"]).write_text("timestamp,symbol,open,high,low,close,volume,price\n", encoding="utf-8")

    def event_study_func(**kwargs) -> None:
        calls.append(("study", kwargs))
        Path(kwargs["out"]).write_text("status,timestamp\nok,2026-06-17T17:00:00+00:00\n", encoding="utf-8")
        Path(kwargs["summary_out"]).write_text(
            "status,error_message,cme_symbol,crypto_symbol,start,end,sample_count,"
            "valid_cme_return_count,valid_forward_1m_count,valid_forward_3m_count,"
            "valid_forward_5m_count,cme_nonzero_return_count,cme_abs_return_bps_mean,"
            "cme_abs_return_bps_max,crypto_abs_forward_1m_bps_mean,"
            "crypto_abs_forward_3m_bps_mean,crypto_abs_forward_5m_bps_mean,"
            "correlation_1m,correlation_3m,correlation_5m,direction_hit_rate_1m,"
            "direction_hit_rate_3m,direction_hit_rate_5m,quality_status\n"
            "ok,,ZNM6,BTC,2026-06-17T17:00:00+00:00,2026-06-17T20:00:00+00:00,"
            "42,41,41,39,37,20,1.1,4.2,2.0,3.0,5.0,0.1,0.2,0.3,0.51,0.52,0.53,ok\n",
            encoding="utf-8",
        )

    summary_path = run_event_batch(
        config=config,
        data_root=tmp_path / "data",
        cme_download_func=cme_download_func,
        crypto_download_func=crypto_download_func,
        event_study_func=event_study_func,
        allow_large_cme_download=True,
    )

    summary = pd.read_csv(summary_path)
    row = summary.iloc[0]
    event_dir = tmp_path / "data" / "reports" / "events" / "fomc_test"
    assert summary_path == tmp_path / "data" / "reports" / "events" / "summary.csv"
    assert event_dir.exists()
    assert [kind for kind, _ in calls] == ["cme", "crypto", "study"]
    assert calls[0][1]["start"] == "2026-06-17T17:00:00Z"
    assert calls[0][1]["end"] == "2026-06-17T20:00:00Z"
    assert calls[1][1]["interval"] == "1m"
    assert row["event_name"] == "fomc_test"
    assert row["event_time_utc"] == "2026-06-17T18:00:00Z"
    assert row["cme_symbol"] == "ZNM6"
    assert row["crypto_symbol"] == "BTC"
    assert row["status"] == "ok"
    assert row["sample_count"] == 42
    assert row["cme_nonzero_return_count"] == 20
    assert row["cme_abs_return_bps_max"] == 4.2
    assert row["correlation_5m"] == 0.3
    assert row["direction_hit_rate_5m"] == 0.53
    assert row["quality_status"] == "ok"
    assert Path(row["result_path"]).exists()
    assert Path(row["summary_path"]).exists()


def test_event_batch_failed_pair_continues_remaining_pairs(tmp_path: Path) -> None:
    config = load_event_batch_config(
        _write_config(tmp_path, cme_symbols=["ZNM6", "ZNU6"], crypto_symbols=["BTC"])
    )

    def cme_download_func(**kwargs) -> None:
        if kwargs["symbols"] == ["ZNM6"]:
            raise RuntimeError("databento unavailable for ZNM6")
        Path(kwargs["out"]).write_text("timestamp,symbol,bid_price,ask_price,last_price\n", encoding="utf-8")

    def crypto_download_func(**kwargs) -> None:
        Path(kwargs["out"]).write_text("timestamp,symbol,open,high,low,close,volume,price\n", encoding="utf-8")

    def event_study_func(**kwargs) -> None:
        Path(kwargs["summary_out"]).write_text(
            "status,error_message,cme_symbol,crypto_symbol,start,end,sample_count,"
            "valid_cme_return_count,valid_forward_1m_count,valid_forward_3m_count,"
            "valid_forward_5m_count,cme_nonzero_return_count,cme_abs_return_bps_mean,"
            "cme_abs_return_bps_max,crypto_abs_forward_1m_bps_mean,"
            "crypto_abs_forward_3m_bps_mean,crypto_abs_forward_5m_bps_mean,"
            "correlation_1m,correlation_3m,correlation_5m,direction_hit_rate_1m,"
            "direction_hit_rate_3m,direction_hit_rate_5m,quality_status\n"
            "ok,,ZNU6,BTC,2026-06-17T17:00:00+00:00,2026-06-17T20:00:00+00:00,"
            "7,6,6,4,2,3,1.0,2.0,1.0,2.0,3.0,0.1,0.2,0.3,0.4,0.5,0.6,ok\n",
            encoding="utf-8",
        )
        Path(kwargs["out"]).write_text("status,timestamp\nok,2026-06-17T17:00:00+00:00\n", encoding="utf-8")

    summary_path = run_event_batch(
        config=config,
        data_root=tmp_path / "data",
        cme_download_func=cme_download_func,
        crypto_download_func=crypto_download_func,
        event_study_func=event_study_func,
        allow_large_cme_download=True,
    )

    summary = pd.read_csv(summary_path).sort_values("cme_symbol").reset_index(drop=True)
    failed = summary[summary["cme_symbol"] == "ZNM6"].iloc[0]
    succeeded = summary[summary["cme_symbol"] == "ZNU6"].iloc[0]
    assert len(summary) == 2
    assert failed["status"] == "failed"
    assert "databento unavailable for ZNM6" in failed["error_message"]
    assert Path(failed["result_path"]).exists()
    assert Path(failed["summary_path"]).exists()
    failed_detail = pd.read_csv(failed["result_path"])
    failed_pair_summary = pd.read_csv(failed["summary_path"])
    assert failed_detail.iloc[0]["status"] == "failed"
    assert failed_pair_summary.iloc[0]["sample_count"] == 0
    assert succeeded["status"] == "ok"
    assert succeeded["sample_count"] == 7


def test_event_batch_dry_run_does_not_call_downloads_or_write_reports(tmp_path: Path, capsys) -> None:
    config = load_event_batch_config(_write_config(tmp_path, cme_symbols=["ZNM6"], crypto_symbols=["BTC"]))
    calls: list[str] = []

    def cme_download_func(**kwargs) -> None:
        calls.append("cme")

    def crypto_download_func(**kwargs) -> None:
        calls.append("crypto")

    def event_study_func(**kwargs) -> None:
        calls.append("study")

    summary_path = run_event_batch(
        config=config,
        data_root=tmp_path / "data",
        cme_download_func=cme_download_func,
        crypto_download_func=crypto_download_func,
        event_study_func=event_study_func,
        dry_run=True,
    )

    output = capsys.readouterr().out
    assert calls == []
    assert summary_path == tmp_path / "data" / "reports" / "events" / "summary.csv"
    assert "M3G dry run" in output
    assert "expected aggregate output path:" in output
    assert "event_name: fomc_test" in output
    assert "event_time_utc: 2026-06-17T18:00:00Z" in output
    assert "start: 2026-06-17T17:00:00Z" in output
    assert "ZNM6__cme.csv" in output
    assert "expected CME central cache paths:" in output
    assert "cme_ZNM6_20260617_1700_20260617_2000.csv exists=False" in output
    assert "large CME guard would block request: True" in output
    assert "mbp-1 is high-volume" in output
    assert "BTC__candles.csv" in output
    assert "expected Hyperliquid central cache paths:" in output
    assert "BTC_1m_20260617_1700_20260617_2000.csv exists=False" in output
    assert "ZNM6__BTC__event_detail.csv" in output
    assert not (tmp_path / "data").exists()


def test_event_batch_reuse_existing_skips_downloads(tmp_path: Path) -> None:
    config = load_event_batch_config(_write_config(tmp_path, cme_symbols=["ZNM6"], crypto_symbols=["BTC"]))
    event_dir = tmp_path / "data" / "reports" / "events" / "fomc_test"
    event_dir.mkdir(parents=True)
    (event_dir / "ZNM6__cme.csv").write_text(
        "timestamp,symbol,bid_price,ask_price,last_price\n",
        encoding="utf-8",
    )
    (event_dir / "BTC__candles.csv").write_text(
        "timestamp,symbol,open,high,low,close,volume,price\n",
        encoding="utf-8",
    )
    calls: list[str] = []

    def cme_download_func(**kwargs) -> None:
        calls.append("cme")

    def crypto_download_func(**kwargs) -> None:
        calls.append("crypto")

    def event_study_func(**kwargs) -> None:
        calls.append("study")
        assert Path(kwargs["cme_csv"]).name == "ZNM6__cme.csv"
        assert Path(kwargs["crypto_csv"]).name == "BTC__candles.csv"
        Path(kwargs["summary_out"]).write_text(
            _summary_csv_row(status="ok", cme_symbol="ZNM6", crypto_symbol="BTC"),
            encoding="utf-8",
        )
        Path(kwargs["out"]).write_text("status,timestamp\nok,2026-06-17T17:00:00+00:00\n", encoding="utf-8")

    summary_path = run_event_batch(
        config=config,
        data_root=tmp_path / "data",
        cme_download_func=cme_download_func,
        crypto_download_func=crypto_download_func,
        event_study_func=event_study_func,
        reuse_existing=True,
    )

    summary = pd.read_csv(summary_path)
    assert calls == ["study"]
    assert summary.iloc[0]["status"] == "ok"


def test_event_batch_reuse_existing_prints_reused_files(tmp_path: Path, capsys) -> None:
    config = load_event_batch_config(_write_config(tmp_path, cme_symbols=["ZNM6"], crypto_symbols=["BTC"]))
    event_dir = tmp_path / "data" / "reports" / "events" / "fomc_test"
    event_dir.mkdir(parents=True)
    (event_dir / "ZNM6__cme.csv").write_text(
        "timestamp,symbol,bid_price,ask_price,last_price\n",
        encoding="utf-8",
    )
    (event_dir / "BTC__candles.csv").write_text(
        "timestamp,symbol,open,high,low,close,volume,price\n",
        encoding="utf-8",
    )

    def event_study_func(**kwargs) -> None:
        Path(kwargs["summary_out"]).write_text(
            _summary_csv_row(status="ok", cme_symbol="ZNM6", crypto_symbol="BTC"),
            encoding="utf-8",
        )
        Path(kwargs["out"]).write_text("status,timestamp\nok,2026-06-17T17:00:00+00:00\n", encoding="utf-8")

    run_event_batch(
        config=config,
        data_root=tmp_path / "data",
        cme_download_func=lambda **kwargs: None,
        crypto_download_func=lambda **kwargs: None,
        event_study_func=event_study_func,
        reuse_existing=True,
    )

    output = capsys.readouterr().out
    assert "Reusing existing CME CSV for ZNM6:" in output
    assert "Reusing existing Hyperliquid candle CSV for BTC:" in output


def test_event_batch_reuse_existing_uses_central_cme_cache(tmp_path: Path, capsys) -> None:
    config = load_event_batch_config(_write_config(tmp_path, cme_symbols=["ZNM6"], crypto_symbols=["BTC"]))
    data_root = tmp_path / "data"
    cme_cache = data_root / "cme" / "databento" / "mbp1" / "cme_ZNM6_20260617_1700_20260617_2000.csv"
    cme_cache.parent.mkdir(parents=True)
    cme_cache.write_text("timestamp,symbol,bid_price,ask_price,last_price\n", encoding="utf-8")
    event_dir = data_root / "reports" / "events" / "fomc_test"
    event_dir.mkdir(parents=True)
    (event_dir / "BTC__candles.csv").write_text(
        "timestamp,symbol,open,high,low,close,volume,price\n",
        encoding="utf-8",
    )
    calls: list[str] = []

    def cme_download_func(**kwargs) -> None:
        calls.append("cme")

    def event_study_func(**kwargs) -> None:
        calls.append("study")
        assert Path(kwargs["cme_csv"]) == event_dir / "ZNM6__cme.csv"
        assert Path(kwargs["cme_csv"]).read_text(encoding="utf-8").startswith("timestamp")
        Path(kwargs["summary_out"]).write_text(
            _summary_csv_row(status="ok", cme_symbol="ZNM6", crypto_symbol="BTC"),
            encoding="utf-8",
        )
        Path(kwargs["out"]).write_text("status,timestamp\nok,2026-06-17T17:00:00+00:00\n", encoding="utf-8")

    run_event_batch(
        config=config,
        data_root=data_root,
        cme_download_func=cme_download_func,
        crypto_download_func=lambda **kwargs: None,
        event_study_func=event_study_func,
        reuse_existing=True,
    )

    output = capsys.readouterr().out
    assert calls == ["study"]
    assert "Reusing central cache:" in output
    assert str(cme_cache) in output
    assert (event_dir / "ZNM6__cme.csv").exists()


def test_event_batch_reuse_existing_uses_central_crypto_cache(tmp_path: Path, capsys) -> None:
    config = load_event_batch_config(_write_config(tmp_path, cme_symbols=["ZNM6"], crypto_symbols=["BTC"]))
    data_root = tmp_path / "data"
    crypto_cache = data_root / "hyperliquid" / "candles" / "BTC_1m_20260617_1700_20260617_2000.csv"
    crypto_cache.parent.mkdir(parents=True)
    crypto_cache.write_text("timestamp,symbol,open,high,low,close,volume,price\n", encoding="utf-8")
    event_dir = data_root / "reports" / "events" / "fomc_test"
    event_dir.mkdir(parents=True)
    (event_dir / "ZNM6__cme.csv").write_text(
        "timestamp,symbol,bid_price,ask_price,last_price\n",
        encoding="utf-8",
    )
    calls: list[str] = []

    def crypto_download_func(**kwargs) -> None:
        calls.append("crypto")

    def event_study_func(**kwargs) -> None:
        calls.append("study")
        assert Path(kwargs["crypto_csv"]) == event_dir / "BTC__candles.csv"
        assert Path(kwargs["crypto_csv"]).read_text(encoding="utf-8").startswith("timestamp")
        Path(kwargs["summary_out"]).write_text(
            _summary_csv_row(status="ok", cme_symbol="ZNM6", crypto_symbol="BTC"),
            encoding="utf-8",
        )
        Path(kwargs["out"]).write_text("status,timestamp\nok,2026-06-17T17:00:00+00:00\n", encoding="utf-8")

    run_event_batch(
        config=config,
        data_root=data_root,
        cme_download_func=lambda **kwargs: None,
        crypto_download_func=crypto_download_func,
        event_study_func=event_study_func,
        reuse_existing=True,
    )

    output = capsys.readouterr().out
    assert calls == ["study"]
    assert "Reusing central cache:" in output
    assert str(crypto_cache) in output
    assert (event_dir / "BTC__candles.csv").exists()


def test_event_batch_large_mbp1_window_fails_without_allow_flag(tmp_path: Path) -> None:
    config = load_event_batch_config(_write_config(tmp_path, cme_symbols=["ZNM6"], crypto_symbols=["BTC"]))
    calls: list[str] = []

    def cme_download_func(**kwargs) -> None:
        calls.append("cme")

    def crypto_download_func(**kwargs) -> None:
        calls.append("crypto")
        Path(kwargs["out"]).write_text("timestamp,symbol,open,high,low,close,volume,price\n", encoding="utf-8")

    summary_path = run_event_batch(
        config=config,
        data_root=tmp_path / "data",
        cme_download_func=cme_download_func,
        crypto_download_func=crypto_download_func,
        event_study_func=lambda **kwargs: calls.append("study"),
    )

    summary = pd.read_csv(summary_path)
    row = summary.iloc[0]
    assert calls == ["crypto"]
    assert row["status"] == "failed"
    assert "mbp-1 is high-volume" in row["error_message"]
    assert "--allow-large-cme-download" in row["error_message"]


def test_event_batch_large_mbp1_window_downloads_with_allow_flag(tmp_path: Path) -> None:
    config = load_event_batch_config(_write_config(tmp_path, cme_symbols=["ZNM6"], crypto_symbols=["BTC"]))
    calls: list[str] = []

    def cme_download_func(**kwargs) -> None:
        calls.append("cme")
        assert Path(kwargs["out"]).name == "cme_ZNM6_20260617_1700_20260617_2000.csv"
        Path(kwargs["out"]).write_text("timestamp,symbol,bid_price,ask_price,last_price\n", encoding="utf-8")

    def crypto_download_func(**kwargs) -> None:
        calls.append("crypto")
        assert Path(kwargs["out"]).name == "BTC_1m_20260617_1700_20260617_2000.csv"
        Path(kwargs["out"]).write_text("timestamp,symbol,open,high,low,close,volume,price\n", encoding="utf-8")

    def event_study_func(**kwargs) -> None:
        calls.append("study")
        Path(kwargs["summary_out"]).write_text(
            _summary_csv_row(status="ok", cme_symbol="ZNM6", crypto_symbol="BTC"),
            encoding="utf-8",
        )
        Path(kwargs["out"]).write_text("status,timestamp\nok,2026-06-17T17:00:00+00:00\n", encoding="utf-8")

    summary_path = run_event_batch(
        config=config,
        data_root=tmp_path / "data",
        cme_download_func=cme_download_func,
        crypto_download_func=crypto_download_func,
        event_study_func=event_study_func,
        allow_large_cme_download=True,
    )

    summary = pd.read_csv(summary_path)
    assert calls == ["cme", "crypto", "study"]
    assert summary.iloc[0]["status"] == "ok"
    assert (tmp_path / "data" / "cme" / "databento" / "mbp1").exists()
    assert (tmp_path / "data" / "hyperliquid" / "candles").exists()


def test_event_batch_failed_event_study_writes_error_message_and_continues(tmp_path: Path) -> None:
    config = load_event_batch_config(
        _write_config(tmp_path, cme_symbols=["ZNM6"], crypto_symbols=["BTC", "ETH"])
    )

    def cme_download_func(**kwargs) -> None:
        Path(kwargs["out"]).write_text("timestamp,symbol,bid_price,ask_price,last_price\n", encoding="utf-8")

    def crypto_download_func(**kwargs) -> None:
        Path(kwargs["out"]).write_text("timestamp,symbol,open,high,low,close,volume,price\n", encoding="utf-8")

    def event_study_func(**kwargs) -> None:
        if kwargs["crypto_symbol"] == "BTC":
            raise RuntimeError("event study insufficient overlap for BTC")
        Path(kwargs["summary_out"]).write_text(
            _summary_csv_row(status="ok", cme_symbol="ZNM6", crypto_symbol="ETH"),
            encoding="utf-8",
        )
        Path(kwargs["out"]).write_text("status,timestamp\nok,2026-06-17T17:00:00+00:00\n", encoding="utf-8")

    summary_path = run_event_batch(
        config=config,
        data_root=tmp_path / "data",
        cme_download_func=cme_download_func,
        crypto_download_func=crypto_download_func,
        event_study_func=event_study_func,
        allow_large_cme_download=True,
    )

    summary = pd.read_csv(summary_path).sort_values("crypto_symbol").reset_index(drop=True)
    failed = summary[summary["crypto_symbol"] == "BTC"].iloc[0]
    succeeded = summary[summary["crypto_symbol"] == "ETH"].iloc[0]
    assert failed["status"] == "failed"
    assert failed["start"] == "2026-06-17T17:00:00Z"
    assert failed["end"] == "2026-06-17T20:00:00Z"
    assert "event study insufficient overlap for BTC" in failed["error_message"]
    assert succeeded["status"] == "ok"
    assert succeeded["start"] == "2026-06-17T17:00:00Z"
    assert succeeded["end"] == "2026-06-17T20:00:00Z"


def _write_config(tmp_path: Path, *, cme_symbols: list[str], crypto_symbols: list[str]) -> Path:
    config_path = tmp_path / "events.yaml"
    config_path.write_text(
        f"""
events:
  - event_name: fomc_test
    event_time_utc: "2026-06-17T18:00:00Z"
    pre_minutes: 60
    post_minutes: 120
    cme_symbols: {cme_symbols}
    crypto_symbols: {crypto_symbols}
    cme_dataset: "GLBX.MDP3"
    cme_schema: "mbp-1"
    crypto_interval: "1m"
""",
        encoding="utf-8",
    )
    return config_path


def _summary_csv_row(*, status: str, cme_symbol: str, crypto_symbol: str) -> str:
    return (
        "status,error_message,cme_symbol,crypto_symbol,start,end,sample_count,"
        "valid_cme_return_count,valid_forward_1m_count,valid_forward_3m_count,"
        "valid_forward_5m_count,cme_nonzero_return_count,cme_abs_return_bps_mean,"
        "cme_abs_return_bps_max,crypto_abs_forward_1m_bps_mean,"
        "crypto_abs_forward_3m_bps_mean,crypto_abs_forward_5m_bps_mean,"
        "correlation_1m,correlation_3m,correlation_5m,direction_hit_rate_1m,"
        "direction_hit_rate_3m,direction_hit_rate_5m,quality_status\n"
        f"{status},,{cme_symbol},{crypto_symbol},2026-06-17T17:00:00+00:00,"
        "2026-06-17T20:00:00+00:00,42,41,41,39,37,20,1.1,4.2,2.0,3.0,5.0,"
        "0.1,0.2,0.3,0.51,0.52,0.53,ok\n"
    )

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

from __future__ import annotations

import pandas as pd

from yield_lag_bot.jobs.run_event_study import run_event_study


def test_event_study_creates_output(tmp_path) -> None:
    cme_path = tmp_path / "cme.csv"
    crypto_path = tmp_path / "crypto_candles.csv"
    out_path = tmp_path / "event_study.csv"
    _write_cme(cme_path, start_minute=0, rows=9)
    _write_crypto(crypto_path, start_minute=0, rows=9)

    run_event_study(
        cme_csv=cme_path,
        crypto_csv=crypto_path,
        out=out_path,
        cme_symbol="ZNM6",
        crypto_symbol="BTC",
    )

    report = pd.read_csv(out_path)
    assert out_path.exists()
    assert len(report) == 9
    assert set(report["status"]) == {"ok"}
    assert set(report["cme_symbol"]) == {"ZNM6"}
    assert set(report["crypto_symbol"]) == {"BTC"}
    assert "cme_return_bps" in report.columns
    assert "crypto_forward_return_1m_bps" in report.columns
    assert "crypto_forward_return_3m_bps" in report.columns
    assert "crypto_forward_return_5m_bps" in report.columns
    assert "correlation_1m" in report.columns
    assert "correlation_3m" in report.columns
    assert "correlation_5m" in report.columns
    assert "direction_hit_rate_1m" in report.columns
    assert "direction_hit_rate_3m" in report.columns
    assert "direction_hit_rate_5m" in report.columns
    assert report["correlation_1m"].notna().all()
    assert report["correlation_3m"].notna().all()
    assert report["correlation_5m"].notna().all()


def test_event_study_writes_optional_summary_output(tmp_path) -> None:
    cme_path = tmp_path / "cme.csv"
    crypto_path = tmp_path / "crypto_candles.csv"
    out_path = tmp_path / "event_study.csv"
    summary_path = tmp_path / "event_study_summary.csv"
    _write_cme(cme_path, start_minute=0, rows=9)
    _write_crypto(crypto_path, start_minute=0, rows=9)

    run_event_study(
        cme_csv=cme_path,
        crypto_csv=crypto_path,
        out=out_path,
        summary_out=summary_path,
        cme_symbol="ZNM6",
        crypto_symbol="BTC",
    )

    summary = pd.read_csv(summary_path)
    assert list(summary.columns) == [
        "status",
        "error_message",
        "cme_symbol",
        "crypto_symbol",
        "start",
        "end",
        "sample_count",
        "valid_cme_return_count",
        "valid_forward_1m_count",
        "valid_forward_3m_count",
        "valid_forward_5m_count",
        "cme_nonzero_return_count",
        "cme_abs_return_bps_mean",
        "cme_abs_return_bps_max",
        "crypto_abs_forward_1m_bps_mean",
        "crypto_abs_forward_3m_bps_mean",
        "crypto_abs_forward_5m_bps_mean",
        "correlation_1m",
        "correlation_3m",
        "correlation_5m",
        "direction_hit_rate_1m",
        "direction_hit_rate_3m",
        "direction_hit_rate_5m",
        "quality_status",
    ]
    row = summary.iloc[0]
    assert row["status"] == "ok"
    assert row["quality_status"] == "ok"
    assert row["sample_count"] == 9
    assert row["valid_cme_return_count"] == 8
    assert row["valid_forward_1m_count"] == 8
    assert row["valid_forward_3m_count"] == 6
    assert row["valid_forward_5m_count"] == 4
    assert row["cme_nonzero_return_count"] == 8
    assert row["cme_abs_return_bps_max"] > 0
    assert row["crypto_abs_forward_5m_bps_mean"] > 0
    assert pd.notna(row["correlation_1m"])
    assert pd.notna(row["direction_hit_rate_5m"])


def test_event_study_no_overlap_does_not_crash(tmp_path) -> None:
    cme_path = tmp_path / "cme.csv"
    crypto_path = tmp_path / "crypto_candles.csv"
    out_path = tmp_path / "event_study.csv"
    _write_cme(cme_path, start_minute=0, rows=7)
    _write_crypto(crypto_path, start_minute=60, rows=7)

    run_event_study(
        cme_csv=cme_path,
        crypto_csv=crypto_path,
        out=out_path,
        cme_symbol="ZNM6",
        crypto_symbol="BTC",
    )

    report = pd.read_csv(out_path)
    row = report.iloc[0]
    assert row["status"] == "failed"
    assert row["error_message"] == "no overlapping time range between CME and crypto data"


def test_event_study_no_overlap_writes_summary_quality_status(tmp_path) -> None:
    cme_path = tmp_path / "cme.csv"
    crypto_path = tmp_path / "crypto_candles.csv"
    out_path = tmp_path / "event_study.csv"
    summary_path = tmp_path / "event_study_summary.csv"
    _write_cme(cme_path, start_minute=0, rows=7)
    _write_crypto(crypto_path, start_minute=60, rows=7)

    run_event_study(
        cme_csv=cme_path,
        crypto_csv=crypto_path,
        out=out_path,
        summary_out=summary_path,
        cme_symbol="ZNM6",
        crypto_symbol="BTC",
    )

    summary = pd.read_csv(summary_path)
    row = summary.iloc[0]
    assert row["status"] == "failed"
    assert row["quality_status"] == "no_overlap"
    assert row["sample_count"] == 0


def test_event_study_insufficient_data_reports_failed_status(tmp_path) -> None:
    cme_path = tmp_path / "cme.csv"
    crypto_path = tmp_path / "crypto_candles.csv"
    out_path = tmp_path / "event_study.csv"
    _write_cme(cme_path, start_minute=0, rows=2)
    _write_crypto(crypto_path, start_minute=0, rows=2)

    run_event_study(
        cme_csv=cme_path,
        crypto_csv=crypto_path,
        out=out_path,
        cme_symbol="ZNM6",
        crypto_symbol="BTC",
    )

    report = pd.read_csv(out_path)
    row = report.iloc[0]
    assert row["status"] == "failed"
    assert row["error_message"] == "insufficient_data"


def test_event_study_insufficient_data_writes_summary_quality_status(tmp_path) -> None:
    cme_path = tmp_path / "cme.csv"
    crypto_path = tmp_path / "crypto_candles.csv"
    out_path = tmp_path / "event_study.csv"
    summary_path = tmp_path / "event_study_summary.csv"
    _write_cme(cme_path, start_minute=0, rows=2)
    _write_crypto(crypto_path, start_minute=0, rows=2)

    run_event_study(
        cme_csv=cme_path,
        crypto_csv=crypto_path,
        out=out_path,
        summary_out=summary_path,
        cme_symbol="ZNM6",
        crypto_symbol="BTC",
    )

    summary = pd.read_csv(summary_path)
    row = summary.iloc[0]
    assert row["status"] == "failed"
    assert row["quality_status"] == "insufficient_data"
    assert row["valid_cme_return_count"] == 0


def test_event_study_constant_price_reports_low_movement(tmp_path) -> None:
    cme_path = tmp_path / "cme.csv"
    crypto_path = tmp_path / "crypto_candles.csv"
    out_path = tmp_path / "event_study.csv"
    _write_cme(cme_path, start_minute=0, rows=7, constant=True)
    _write_crypto(crypto_path, start_minute=0, rows=7)

    run_event_study(
        cme_csv=cme_path,
        crypto_csv=crypto_path,
        out=out_path,
        cme_symbol="ZNM6",
        crypto_symbol="BTC",
    )

    report = pd.read_csv(out_path)
    assert set(report["status"]) == {"low_movement"}


def test_event_study_constant_cme_price_summary_marks_low_cme_movement(tmp_path) -> None:
    cme_path = tmp_path / "cme.csv"
    crypto_path = tmp_path / "crypto_candles.csv"
    out_path = tmp_path / "event_study.csv"
    summary_path = tmp_path / "event_study_summary.csv"
    _write_cme(cme_path, start_minute=0, rows=9, constant=True)
    _write_crypto(crypto_path, start_minute=0, rows=9)

    run_event_study(
        cme_csv=cme_path,
        crypto_csv=crypto_path,
        out=out_path,
        summary_out=summary_path,
        cme_symbol="ZNM6",
        crypto_symbol="BTC",
    )

    summary = pd.read_csv(summary_path)
    row = summary.iloc[0]
    assert row["status"] == "low_movement"
    assert row["quality_status"] == "low_cme_movement"
    assert row["cme_nonzero_return_count"] == 0
    assert row["cme_abs_return_bps_max"] == 0


def _write_cme(path, *, start_minute: int, rows: int, constant: bool = False) -> None:
    lines = ["timestamp,symbol,bid_price,ask_price,last_price"]
    start = pd.Timestamp("2026-06-12T13:00:00Z") + pd.Timedelta(minutes=start_minute)
    for index in range(rows):
        timestamp = start + pd.Timedelta(minutes=index)
        price = 108.0 if constant else 108.0 + index * 0.01
        lines.append(
            f"{timestamp.isoformat().replace('+00:00', 'Z')},ZNM6,{price:.3f},{price + 0.010:.3f},"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_crypto(path, *, start_minute: int, rows: int) -> None:
    lines = ["timestamp,symbol,open,high,low,close,volume,price"]
    start = pd.Timestamp("2026-06-12T13:00:00Z") + pd.Timedelta(minutes=start_minute)
    for index in range(rows):
        timestamp = start + pd.Timedelta(minutes=index)
        price = 65000 + index * 10
        lines.append(
            f"{timestamp.isoformat().replace('+00:00', 'Z')},BTC,{price},{price + 5},{price - 5},{price},1.0,{price}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

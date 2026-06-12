from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from yield_lag_bot.jobs import download_cme_databento


class FakeDatabento:
    calls: list[dict[str, object]] = []

    class Historical:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key
            self.timeseries = FakeTimeseries(api_key)


class FakeTimeseries:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def get_range(self, **kwargs):
        FakeDatabento.calls.append({"api_key": self.api_key, **kwargs})
        return FakeStore()


class FakeStore:
    def to_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "ts_event": pd.Timestamp("2026-06-12T13:00:00Z"),
                    "symbol": "ZN.c.0",
                    "bid_px_00": 108.125,
                    "ask_px_00": 108.140625,
                    "price": None,
                }
            ]
        )


@dataclass
class FakeRecord:
    ts_event: int
    bid_px_00: str
    ask_px_00: str
    last_price: str | None = None


def test_command_creates_m3a_compatible_csv(monkeypatch, tmp_path: Path) -> None:
    out = tmp_path / "cme_ticks.csv"
    FakeDatabento.calls = []
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    monkeypatch.setattr(download_cme_databento, "_import_databento", lambda: FakeDatabento)

    exit_code = download_cme_databento.main(
        [
            "--dataset",
            "GLBX.MDP3",
            "--schema",
            "mbp-1",
            "--symbols",
            "ZN.c.0",
            "--start",
            "2026-06-12T13:00:00Z",
            "--end",
            "2026-06-12T14:00:00Z",
            "--out",
            str(out),
        ]
    )

    assert exit_code == 0
    assert FakeDatabento.calls == [
        {
            "api_key": "test-key",
            "dataset": "GLBX.MDP3",
            "schema": "mbp-1",
            "symbols": ["ZN.c.0"],
            "start": "2026-06-12T13:00:00Z",
            "end": "2026-06-12T14:00:00Z",
        }
    ]
    assert out.read_text(encoding="utf-8").splitlines() == [
        "timestamp,symbol,bid_price,ask_price,last_price",
        "2026-06-12T13:00:00Z,ZN.c.0,108.125,108.140625,",
    ]


def test_missing_databento_api_key_fails_with_clear_message(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)

    exit_code = download_cme_databento.main(
        [
            "--symbols",
            "ZN.c.0",
            "--start",
            "2026-06-12T13:00:00Z",
            "--end",
            "2026-06-12T14:00:00Z",
            "--out",
            "cme_ticks.csv",
        ]
    )

    assert exit_code == 2
    assert "Set DATABENTO_API_KEY to use this command." in capsys.readouterr().err


def test_missing_databento_package_fails_gracefully(monkeypatch, capsys) -> None:
    def raise_missing():
        raise ModuleNotFoundError("No module named 'databento'")

    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    monkeypatch.setattr(download_cme_databento, "_import_databento", raise_missing)

    exit_code = download_cme_databento.main(
        [
            "--symbols",
            "ZN.c.0",
            "--start",
            "2026-06-12T13:00:00Z",
            "--end",
            "2026-06-12T14:00:00Z",
            "--out",
            "cme_ticks.csv",
        ]
    )

    assert exit_code == 2
    assert (
        "Install databento or set up optional dependencies to use this command."
        in capsys.readouterr().err
    )


def test_record_iterable_uses_fallback_symbol_and_empty_last_price(tmp_path: Path) -> None:
    out = tmp_path / "cme_ticks.csv"

    download_cme_databento.download_mbp1_to_csv(
        databento_module=_fake_module_for_records([FakeRecord(1_781_269_200_000_000_000, "1", "2")]),
        api_key="test-key",
        dataset="GLBX.MDP3",
        schema="mbp-1",
        symbols=["ZF.c.0"],
        start="2026-06-12T13:00:00Z",
        end="2026-06-12T14:00:00Z",
        out=out,
    )

    assert out.read_text(encoding="utf-8").splitlines() == [
        "timestamp,symbol,bid_price,ask_price,last_price",
        "2026-06-12T13:00:00Z,ZF.c.0,1,2,",
    ]


def _fake_module_for_records(records):
    class Module:
        class Historical:
            def __init__(self, api_key: str) -> None:
                self.timeseries = Timeseries()

    class Timeseries:
        def get_range(self, **kwargs):
            return records

    return Module

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from yield_lag_bot.jobs.archive_hyperliquid_bbo import (
    archive_hyperliquid_bbo,
    build_archive_path,
)


@pytest.mark.asyncio
async def test_archive_creates_path_and_manifest_row(tmp_path: Path) -> None:
    start = datetime(2026, 6, 12, 18, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 12, 19, 0, tzinfo=timezone.utc)
    calls: list[dict[str, object]] = []

    async def export_func(**kwargs) -> None:
        calls.append(kwargs)
        Path(kwargs["out"]).write_text(
            "venue,symbol,instrument_type,exchange_ts,receive_ts,process_ts,bid_price,ask_price,bid_size,ask_size,last_price,mid_price,sequence_id,raw_payload\n"
            "hyperliquid,BTC,crypto_perp,2026-06-12T18:00:00Z,2026-06-12T18:00:00Z,,65000,65001,1,1,,65000.5,1,\"{}\"\n",
            encoding="utf-8",
        )

    row = await archive_hyperliquid_bbo(
        data_root=tmp_path,
        symbols=["BTC", "ETH"],
        start=start,
        end=end,
        export_func=export_func,
    )

    expected_path = build_archive_path(tmp_path, symbols=["BTC", "ETH"], start=start, end=end)
    manifest_path = tmp_path / "manifests" / "hyperliquid_bbo_manifest.csv"
    manifest = pd.read_csv(manifest_path)
    assert expected_path.exists()
    assert calls[0]["venue"] == "hyperliquid"
    assert calls[0]["channel"] == "bbo"
    assert calls[0]["symbols"] == ["BTC", "ETH"]
    assert calls[0]["start"] == start
    assert calls[0]["end"] == end
    assert calls[0]["out"] == expected_path
    assert row["status"] == "ok"
    assert row["row_count"] == 1
    assert manifest.iloc[0]["status"] == "ok"
    assert manifest.iloc[0]["file_path"] == str(expected_path)


@pytest.mark.asyncio
async def test_archive_no_data_writes_manifest_status(tmp_path: Path) -> None:
    start = datetime(2026, 6, 12, 18, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 12, 19, 0, tzinfo=timezone.utc)

    async def export_func(**kwargs) -> None:
        Path(kwargs["out"]).write_text(
            "venue,symbol,instrument_type,exchange_ts,receive_ts,process_ts,bid_price,ask_price,bid_size,ask_size,last_price,mid_price,sequence_id,raw_payload\n",
            encoding="utf-8",
        )

    row = await archive_hyperliquid_bbo(
        data_root=tmp_path,
        symbols=["BTC"],
        start=start,
        end=end,
        export_func=export_func,
    )

    manifest = pd.read_csv(tmp_path / "manifests" / "hyperliquid_bbo_manifest.csv")
    assert row["status"] == "no_data"
    assert row["row_count"] == 0
    assert manifest.iloc[0]["status"] == "no_data"


@pytest.mark.asyncio
async def test_archive_does_not_overwrite_existing_file_without_flag(tmp_path: Path) -> None:
    start = datetime(2026, 6, 12, 18, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 12, 19, 0, tzinfo=timezone.utc)
    archive_path = build_archive_path(tmp_path, symbols=["BTC"], start=start, end=end)
    archive_path.parent.mkdir(parents=True)
    archive_path.write_text("existing\n", encoding="utf-8")
    called = False

    async def export_func(**kwargs) -> None:
        nonlocal called
        called = True

    row = await archive_hyperliquid_bbo(
        data_root=tmp_path,
        symbols=["BTC"],
        start=start,
        end=end,
        export_func=export_func,
    )

    manifest = pd.read_csv(tmp_path / "manifests" / "hyperliquid_bbo_manifest.csv")
    assert called is False
    assert archive_path.read_text(encoding="utf-8") == "existing\n"
    assert row["status"] == "failed"
    assert "already exists" in row["error_message"]
    assert manifest.iloc[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_archive_failed_export_writes_manifest_status(tmp_path: Path) -> None:
    start = datetime(2026, 6, 12, 18, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 12, 19, 0, tzinfo=timezone.utc)

    async def export_func(**kwargs) -> None:
        raise RuntimeError("database unavailable")

    row = await archive_hyperliquid_bbo(
        data_root=tmp_path,
        symbols=["BTC"],
        start=start,
        end=end,
        export_func=export_func,
    )

    manifest = pd.read_csv(tmp_path / "manifests" / "hyperliquid_bbo_manifest.csv")
    assert row["status"] == "failed"
    assert row["error_message"] == "database unavailable"
    assert manifest.iloc[0]["status"] == "failed"
    assert manifest.iloc[0]["error_message"] == "database unavailable"

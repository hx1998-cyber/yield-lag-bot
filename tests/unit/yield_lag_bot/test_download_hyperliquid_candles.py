from __future__ import annotations

from pathlib import Path

from yield_lag_bot.jobs.download_hyperliquid_candles import download_candles_to_csv


def test_hyperliquid_candle_downloader_parses_mocked_api_response(tmp_path: Path) -> None:
    out = tmp_path / "crypto_candles.csv"
    calls: list[dict[str, object]] = []

    def post_func(payload):
        calls.append(payload)
        return [
            {
                "t": 1_781_269_200_000,
                "T": 1_781_269_259_999,
                "s": "BTC",
                "i": "1m",
                "o": "65000",
                "h": "65010",
                "l": "64990",
                "c": "65005",
                "v": "12.5",
            }
        ]

    download_candles_to_csv(
        coin="BTC",
        interval="1m",
        start="2026-06-12T13:00:00Z",
        end="2026-06-12T13:01:00Z",
        out=out,
        post_func=post_func,
    )

    assert calls == [
        {
            "type": "candleSnapshot",
            "req": {
                "coin": "BTC",
                "interval": "1m",
                "startTime": 1_781_269_200_000,
                "endTime": 1_781_269_260_000,
            },
        }
    ]
    assert out.read_text(encoding="utf-8").splitlines() == [
        "timestamp,symbol,open,high,low,close,volume,price",
        "2026-06-12T13:00:00Z,BTC,65000,65010,64990,65005,12.5,65005",
    ]

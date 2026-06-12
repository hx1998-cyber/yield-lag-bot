"""Safe defaults for Project YIELD-LAG M1."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for data collection and paper-only research."""

    model_config = SettingsConfigDict(
        env_prefix="YIELD_LAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "postgresql+asyncpg://yield_lag:yield_lag@localhost:5432/yield_lag"
    redis_url: str = "redis://localhost:6379/0"

    live_trading: bool = False
    paper_trading: bool = True
    max_order_usd: Decimal = Decimal("10")
    max_position_usd: Decimal = Decimal("50")
    max_daily_loss_usd: Decimal = Decimal("20")
    max_latency_ms: int = 300
    stale_data_ms: int = 500
    kill_switch_on_error: bool = True

    crypto_symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    hyperliquid_symbols: list[str] = Field(default_factory=lambda: ["BTC", "ETH"])
    cme_symbols: list[str] = Field(default_factory=lambda: ["ZT", "ZF", "ZN", "TN"])
    binance_ws_url: str = "wss://fstream.binance.com/ws"
    bybit_ws_url: str = "wss://stream.bybit.com/v5/public/linear"
    hyperliquid_network: str = "mainnet"
    hyperliquid_mainnet_ws_url: str = "wss://api.hyperliquid.xyz/ws"
    hyperliquid_testnet_ws_url: str = "wss://api.hyperliquid-testnet.xyz/ws"

    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 10
    log_level: str = "INFO"

    @field_validator("crypto_symbols", "hyperliquid_symbols", "cme_symbols", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @property
    def hyperliquid_ws_url(self) -> str:
        if self.hyperliquid_network.lower() == "testnet":
            return self.hyperliquid_testnet_ws_url
        return self.hyperliquid_mainnet_ws_url


_cached: Settings | None = None


def load_settings(*, refresh: bool = False) -> Settings:
    global _cached
    if _cached is None or refresh:
        _cached = Settings()
    return _cached

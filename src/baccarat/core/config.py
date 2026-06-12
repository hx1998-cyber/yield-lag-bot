"""Application configuration via Pydantic Settings.

Layered loading (later wins):

1. Defaults baked into the model.
2. ``config/settings.yaml`` (path overridable via ``BACCARAT_CONFIG_FILE``).
3. ``.env`` and process env vars prefixed with ``BACCARAT_``. Nested fields
   use ``__`` as the separator, e.g. ``BACCARAT_RISK__MAX_POSITION_SIZE_USDC``.

This keeps secrets out of YAML while letting non-sensitive defaults live in
version control.

Sensitive fields (``private_key``, ``database_url``, ``redis_url``,
``alerting.telegram_bot_token``) intentionally have NO YAML default — they
must come from env / .env. Failing fast at startup is preferable to running
with a bogus key.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from baccarat.core.exceptions import ConfigError

# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class NetworkSettings(BaseModel):
    chain: Literal["polygon", "amoy"] = "polygon"
    rpc_endpoints: list[str] = Field(default_factory=list, min_length=1)
    ws_endpoints: list[str] = Field(default_factory=list)
    request_timeout_sec: int = 10
    health_check_interval_sec: int = 30

    @field_validator("rpc_endpoints", "ws_endpoints", mode="before")
    @classmethod
    def _split_csv(cls, v: Any) -> Any:
        # Accept comma-separated strings from env vars.
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


class PolymarketSettings(BaseModel):
    clob_api: str = "https://clob.polymarket.com"
    clob_ws: str = "wss://ws-subscriptions-clob.polymarket.com"
    exchange_address: str
    ctf_address: str
    usdc_address: str
    reconnect_initial_delay_sec: float = 1.0
    reconnect_max_delay_sec: float = 30.0


class RiskSettings(BaseModel):
    max_position_size_usdc: Decimal
    max_daily_drawdown_usdc: Decimal
    max_open_positions: int = 20
    max_signals_per_minute: int = 30
    min_arb_profit_usdc: Decimal = Decimal("0.5")
    min_arb_profit_bps: int = 30


class ArbitrageSettings(BaseModel):
    enabled: bool = True
    safety_margin_bps: int = 20
    maker_timeout_ms: int = 3000
    signal_ttl_ms: int = 5000


class CopyTradeSettings(BaseModel):
    enabled: bool = True
    default_copy_ratio: Decimal = Decimal("0.05")
    default_max_slippage_bps: int = 50
    signal_ttl_ms: int = 8000


class AlertingSettings(BaseModel):
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    heartbeat_interval_sec: int = 3600
    alert_on_hedge_fail: bool = True
    alert_on_consecutive_failures: int = 3


class LoggingSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["json", "console"] = "json"
    include_trace_id: bool = True


class StorageSettings(BaseModel):
    postgres_pool_min_size: int = 2
    postgres_pool_max_size: int = 10
    redis_decode_responses: bool = True


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------


def _resolve_yaml_path() -> Path | None:
    """Pick the YAML file path. Env var wins; otherwise ``config/settings.yaml``."""
    env_path = os.getenv("BACCARAT_CONFIG_FILE")
    if env_path:
        return Path(env_path)
    candidate = Path("config/settings.yaml")
    return candidate if candidate.is_file() else None


class Settings(BaseSettings):
    """Single root settings object. Build with :func:`load_settings`."""

    model_config = SettingsConfigDict(
        env_prefix="BACCARAT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Secrets — must come from env, never from YAML.
    private_key: SecretStr = Field(
        default=SecretStr(""),
        description="Hex private key. Required for live trading, may be empty for dry-run.",
    )
    database_url: str = Field(
        default="postgresql+asyncpg://baccarat:baccarat@localhost:5432/baccarat",
        description="SQLAlchemy async URL. asyncpg driver mandatory.",
    )
    redis_url: str = "redis://localhost:6379/0"

    # Non-secret config — populated from YAML by default.
    network: NetworkSettings
    polymarket: PolymarketSettings
    risk: RiskSettings
    arbitrage: ArbitrageSettings = Field(default_factory=ArbitrageSettings)
    copy_trade: CopyTradeSettings = Field(default_factory=CopyTradeSettings)
    alerting: AlertingSettings = Field(default_factory=AlertingSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)

    # Dry-run mode — when true, executor MUST short-circuit before signing.
    dry_run: bool = False

    @model_validator(mode="after")
    def _check_url_drivers(self) -> Settings:
        if not self.database_url.startswith("postgresql+asyncpg://"):
            raise ConfigError(
                "database_url must use the asyncpg driver",
                got=self.database_url.split("://", 1)[0],
            )
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Priority (highest first): init kwargs → env → .env → YAML → file secrets.
        yaml_path = _resolve_yaml_path()
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]
        if yaml_path is not None:
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path))
        sources.append(file_secret_settings)
        return tuple(sources)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_cached: Settings | None = None


def load_settings(*, refresh: bool = False) -> Settings:
    """Build (and cache) the :class:`Settings` instance.

    Raises :class:`ConfigError` with a friendly message if any required field
    is missing — Pydantic's default error is too noisy for an operator.
    """
    global _cached
    if _cached is not None and not refresh:
        return _cached

    try:
        _cached = Settings()  # type: ignore[call-arg]
    except Exception as exc:  # pydantic.ValidationError + others
        # Surface a single-line summary; full traceback already on stderr.
        raise ConfigError(
            "failed to load settings",
            yaml_file=str(_resolve_yaml_path()),
            cause=str(exc),
        ) from exc

    # Sanity check: warn (not fatal) if private key empty and not dry-run.
    if not _cached.dry_run and not _cached.private_key.get_secret_value():
        # We don't have a logger configured at this point necessarily; print
        # to stderr so the operator sees it before logging takes over.
        print(
            "[baccarat] WARNING: private_key is empty and dry_run=False. "
            "Live trading will fail. Set PRIVATE_KEY in .env or enable dry_run.",
            flush=True,
        )

    return _cached


def reset_cache() -> None:
    """Test helper — drop the cached settings instance."""
    global _cached
    _cached = None

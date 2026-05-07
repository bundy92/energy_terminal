"""Application configuration management.

Settings are resolved in priority order (highest first):

1. Environment variables (prefixed ``ET_``)
2. ``~/.energy_terminal/config.toml``
3. Module-level defaults defined here

Usage::

    from energy_terminal.config.settings import settings
    print(settings.gateway_url)
    print(settings.eia_api_key)
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import structlog
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = structlog.get_logger(__name__)

_CONFIG_DIR  = Path.home() / ".energy_terminal"
_CONFIG_FILE = _CONFIG_DIR / "config.toml"


def _load_toml_defaults() -> dict[str, Any]:
    """Load TOML config if it exists; return empty dict otherwise."""
    if not _CONFIG_FILE.exists():
        return {}
    with _CONFIG_FILE.open("rb") as fh:
        return tomllib.load(fh)


class Settings(BaseSettings):
    """Top-level application settings.

    Parameters
    ----------
    gateway_url : str
        WebSocket URL of the Erlang data gateway.
    gateway_reconnect_delay_s : float
        Seconds to wait between WebSocket reconnect attempts.
    eia_api_key : SecretStr
        US EIA Open Data API key.  Set via ``ET_EIA_API_KEY`` env var.
    fred_api_key : SecretStr
        Federal Reserve FRED API key.  Set via ``ET_FRED_API_KEY``.
    iea_api_key : SecretStr
        IEA Open Data API key.  Set via ``ET_IEA_API_KEY``.
    cache_db_path : Path
        Path to the DuckDB time-series cache database file.
    cache_max_age_days : int
        Maximum age of cached OHLCV records before re-fetch.
    log_level : str
        Logging level (``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``).
    theme : str
        UI colour theme identifier (``bloomberg_dark`` | ``classic_dark``).
    default_timezone : str
        IANA timezone used for all display timestamps.
    poll_interval_s : float
        Fallback direct-API poll interval used when the Erlang gateway is
        unavailable.
    """

    model_config = SettingsConfigDict(
        env_prefix="ET_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Gateway
    gateway_url:               str   = "ws://127.0.0.1:8765/ws"
    gateway_reconnect_delay_s: float = 5.0

    # API keys (read from env / keyring; never from config.toml)
    eia_api_key:  SecretStr = Field(default=SecretStr(""), alias="ET_EIA_API_KEY")
    fred_api_key: SecretStr = Field(default=SecretStr(""), alias="ET_FRED_API_KEY")
    iea_api_key:  SecretStr = Field(default=SecretStr(""), alias="ET_IEA_API_KEY")

    # Storage
    cache_db_path:      Path = _CONFIG_DIR / "cache.duckdb"
    cache_max_age_days: int  = 7

    # Application
    log_level:        str  = "INFO"
    theme:            str  = "bloomberg_dark"
    default_timezone: str  = "UTC"
    poll_interval_s:  float = 30.0

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is one of the accepted values."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str) -> str:
        """Ensure theme identifier is supported."""
        allowed = {"bloomberg_dark", "classic_dark"}
        if v not in allowed:
            raise ValueError(f"theme must be one of {allowed}")
        return v

    def ensure_config_dir(self) -> None:
        """Create the config directory and default TOML stub if absent."""
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not _CONFIG_FILE.exists():
            _CONFIG_FILE.write_text(
                "# Energy Terminal configuration\n"
                "# All values can be overridden via ET_* environment variables.\n\n"
                'gateway_url = "ws://127.0.0.1:8765/ws"\n'
                'theme       = "bloomberg_dark"\n'
                'log_level   = "INFO"\n',
                encoding="utf-8",
            )
            log.info("Created default config", path=str(_CONFIG_FILE))


settings = Settings()
settings.ensure_config_dir()

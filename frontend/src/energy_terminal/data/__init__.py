"""Data sub-package.

Components:

- :mod:`models`      — Pydantic event and domain models
- :mod:`client`      — Async WebSocket client for the Erlang gateway
- :mod:`direct_feed` — yfinance fallback feed (offline / gateway-down)
- :mod:`cache`       — DuckDB persistent time-series cache
- :mod:`alerts`      — Alert threshold evaluation engine
"""

from energy_terminal.data.models import (
    Alert,
    AlertCondition,
    BaseEvent,
    EventSource,
    EventType,
    FundamentalReading,
    MacroReading,
    OHLCVBar,
    Tick,
    WeatherReading,
)
from energy_terminal.data.alerts import AlertEngine, AlertFired
from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.data.client import GatewayClient
from energy_terminal.data.direct_feed import DirectFeed, INSTRUMENT_NAMES

__all__ = [
    "Alert", "AlertCondition", "AlertEngine", "AlertFired",
    "BaseEvent", "EventSource", "EventType",
    "FundamentalReading", "MacroReading", "OHLCVBar",
    "Tick", "WeatherReading",
    "TimeSeriesCache", "GatewayClient", "DirectFeed", "INSTRUMENT_NAMES",
]

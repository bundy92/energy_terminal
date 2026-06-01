"""Internal data models for all event types received from the Erlang gateway.

Every field includes source and timestamp metadata so the UI can always
display data provenance and detect stale values.

All models use strict Pydantic v2 validation.

Examples
--------
>>> tick = Tick(symbol="CL=F", open=85.0, high=86.5, low=84.8,
...             close=85.9, volume=120_000, change=0.9, change_pct=1.06,
...             timestamp=1710000000000, source="yahoo_finance")
>>> tick.change_pct
1.06
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EventSource(str, Enum):
    """Enumeration of all supported data-source identifiers."""

    YAHOO_FINANCE = "yahoo_finance"
    EIA           = "eia"
    IEA           = "iea"
    OPEN_METEO    = "open_meteo"
    FRED          = "fred"
    DIRECT        = "direct"   # fallback direct API call


class EventType(str, Enum):
    """Enumeration of all event types published by the gateway."""

    TICK        = "tick"
    FUNDAMENTAL = "fundamental"
    WEATHER     = "weather"
    MACRO       = "macro"
    PONG        = "pong"
    ERROR       = "error"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class BaseEvent(BaseModel):
    """Common fields shared by all gateway events.

    Parameters
    ----------
    type : EventType
        Category of the event.
    source : EventSource
        Data-provider that produced this event.
    symbol : str
        Instrument or series identifier (e.g. ``"CL=F"``, ``"PET.WCRSTUS1.W"``).
    timestamp : int
        Unix epoch milliseconds at which the event was generated.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    type:      EventType
    source:    EventSource
    symbol:    str
    timestamp: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Tick (price)
# ---------------------------------------------------------------------------

class Tick(BaseEvent):
    """OHLCV price tick for a tradeable instrument.

    Parameters
    ----------
    open : float
        Session open price.
    high : float
        Session high price.
    low : float
        Session low price.
    close : float
        Last traded / current price.
    volume : int
        Session volume (contracts or shares).
    change : float
        Absolute change from previous close.
    change_pct : float
        Percentage change from previous close.
    """

    type: EventType = EventType.TICK

    open:       float
    high:       float
    low:        float
    close:      float
    volume:     int   = Field(ge=0)
    change:     float = 0.0
    change_pct: float = 0.0

    @model_validator(mode="after")
    def validate_high_low(self) -> "Tick":
        """Validate that high is greater than or equal to low."""
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) must be >= low ({self.low})")
        return self


# ---------------------------------------------------------------------------
# Fundamental (EIA / IEA supply-demand)
# ---------------------------------------------------------------------------

class FundamentalReading(BaseEvent):
    """A single observation from a fundamental data series.

    Parameters
    ----------
    series : str
        Series identifier (e.g. ``"PET.WCRSTUS1.W"``).
    value : float | None
        Numeric value; ``None`` when the series reports a missing
        observation (FRED uses ``"."`` for this).
    period : str
        Reporting period string (e.g. ``"2024-01-05"``).
    unit : str
        Unit of measurement (e.g. ``"thousand barrels"``).
    """

    type: EventType = EventType.FUNDAMENTAL

    series: str
    value:  float | None
    period: str
    unit:   str = ""


# ---------------------------------------------------------------------------
# Weather / HDD-CDD
# ---------------------------------------------------------------------------

class WeatherReading(BaseEvent):
    """Current weather and degree-day metrics for an energy demand centre.

    Parameters
    ----------
    location : str
        Human-readable city name.
    temp_c : float
        Current temperature in degrees Celsius.
    hdd : float
        Heating Degree Days relative to 18.3°C (65°F) base.
    cdd : float
        Cooling Degree Days relative to 18.3°C (65°F) base.
    forecast_7d : list[float]
        Daily mean temperature forecast for the next 7 days (°C).
    """

    type: EventType = EventType.WEATHER

    location:    str
    temp_c:      float
    hdd:         float   = Field(ge=0)
    cdd:         float   = Field(ge=0)
    forecast_7d: list[float] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Macro (FRED)
# ---------------------------------------------------------------------------

class MacroReading(BaseEvent):
    """A macro-economic indicator observation from FRED.

    Parameters
    ----------
    series : str
        FRED series ID (e.g. ``"DTWEXBGS"``).
    value : float | None
        Indicator value; ``None`` for missing observations.
    date : str
        Observation date as ISO 8601 string (``"YYYY-MM-DD"``).
    description : str
        Human-readable series description.
    """

    type: EventType = EventType.MACRO

    series:      str
    value:       float | None
    date:        str
    description: str = ""


# ---------------------------------------------------------------------------
# OHLCV bar (historical)
# ---------------------------------------------------------------------------

class OHLCVBar(BaseModel):
    """A single OHLCV candlestick bar for historical chart rendering.

    Parameters
    ----------
    timestamp : int
        Bar open time as Unix epoch milliseconds.
    open : float
    high : float
    low : float
    close : float
    volume : int
    """

    model_config = ConfigDict(frozen=True)

    timestamp: int
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    int = 0


# ---------------------------------------------------------------------------
# Alert definition
# ---------------------------------------------------------------------------

class AlertCondition(str, Enum):
    """Supported alert trigger conditions."""
    ABOVE       = "above"
    BELOW       = "below"
    PCT_CHANGE  = "pct_change"
    SPREAD_WIDE = "spread_wide"


class Alert(BaseModel):
    """User-defined price or spread alert.

    Parameters
    ----------
    alert_id : str
        Unique identifier (UUID recommended).
    symbol : str
        Instrument to monitor.
    condition : AlertCondition
        Trigger condition type.
    threshold : float
        Numeric threshold value.
    message : str
        Display message when triggered.
    triggered : bool
        Whether this alert has already fired.
    """

    alert_id:  str
    symbol:    str
    condition: AlertCondition
    threshold: float
    message:   str   = ""
    triggered: bool  = False

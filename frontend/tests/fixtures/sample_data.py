"""Shared test fixtures for the Energy Terminal test suite.

Import from ``tests.fixtures.sample_data`` in any test module.

All fixture functions return fresh objects to avoid inter-test mutation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from energy_terminal.data.models import (
    Alert,
    AlertCondition,
    EventSource,
    EventType,
    FundamentalReading,
    MacroReading,
    OHLCVBar,
    Tick,
    WeatherReading,
)

# ---------------------------------------------------------------------------
# Price series
# ---------------------------------------------------------------------------

def make_price_series(
    n: int = 252,
    start: float = 80.0,
    vol: float = 0.02,
    seed: int = 42,
) -> np.ndarray:
    """Generate a log-normal random-walk price series.

    Parameters
    ----------
    n : int
        Number of price points.
    start : float
        Starting price.
    vol : float
        Daily volatility (log-normal).
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    np.ndarray
        Price series of length ``n``.
    """
    rng    = np.random.default_rng(seed)
    shocks = rng.normal(0, vol, n)
    log_p  = np.log(start) + np.cumsum(shocks)
    return np.exp(log_p)


def make_ohlcv_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame with a DatetimeIndex.

    Parameters
    ----------
    n : int
        Number of bars.
    seed : int
        Random seed.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns ``[open, high, low, close, volume]``
        and a daily DatetimeIndex.
    """
    close  = make_price_series(n, seed=seed)
    rng    = np.random.default_rng(seed)
    spread = rng.uniform(0.1, 2.0, n)
    opens  = close * (1 + rng.normal(0, 0.005, n))
    highs  = np.maximum(close, opens) + spread
    lows   = np.minimum(close, opens) - spread
    vol    = rng.integers(50_000, 500_000, n)

    index = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": close, "volume": vol,
    }, index=index)


# ---------------------------------------------------------------------------
# Model factories
# ---------------------------------------------------------------------------

def make_tick(
    symbol: str = "CL=F",
    close: float = 85.0,
    change_pct: float = 1.5,
    ts: int = 1_710_000_000_000,
) -> Tick:
    """Create a synthetic Tick for testing.

    Parameters
    ----------
    symbol : str
        Instrument ticker.
    close : float
        Closing / last price.
    change_pct : float
        Percentage change from previous close.
    ts : int
        Unix epoch milliseconds timestamp.

    Returns
    -------
    Tick
        Populated tick model.
    """
    return Tick(
        type=EventType.TICK,
        source=EventSource.YAHOO_FINANCE,
        symbol=symbol,
        timestamp=ts,
        open=close * 0.99,
        high=close * 1.01,
        low=close * 0.98,
        close=close,
        volume=100_000,
        change=close * change_pct / 100,
        change_pct=change_pct,
    )


def make_fundamental(
    series: str = "PET.WCRSTUS1.W",
    value: float = 430_000.0,
    period: str = "2024-01-05",
) -> FundamentalReading:
    """Create a synthetic FundamentalReading."""
    return FundamentalReading(
        type=EventType.FUNDAMENTAL,
        source=EventSource.EIA,
        symbol=series,
        timestamp=1_710_000_000_000,
        series=series,
        value=value,
        period=period,
        unit="thousand barrels",
    )


def make_weather(
    location: str = "New York",
    temp_c: float = 5.0,
) -> WeatherReading:
    """Create a synthetic WeatherReading."""
    hdd = max(0.0, 18.3 - temp_c)
    cdd = max(0.0, temp_c - 18.3)
    return WeatherReading(
        type=EventType.WEATHER,
        source=EventSource.OPEN_METEO,
        symbol=location,
        timestamp=1_710_000_000_000,
        location=location,
        temp_c=temp_c,
        hdd=hdd,
        cdd=cdd,
        forecast_7d=[temp_c + i * 0.5 for i in range(7)],
    )


def make_macro(
    series: str = "DTWEXBGS",
    value: float = 106.4,
    date: str = "2024-03-10",
) -> MacroReading:
    """Create a synthetic MacroReading."""
    return MacroReading(
        type=EventType.MACRO,
        source=EventSource.FRED,
        symbol=series,
        timestamp=1_710_000_000_000,
        series=series,
        value=value,
        date=date,
    )


def make_alert(
    symbol: str = "CL=F",
    condition: AlertCondition = AlertCondition.ABOVE,
    threshold: float = 90.0,
) -> Alert:
    """Create a synthetic Alert."""
    return Alert(
        alert_id="test-001",
        symbol=symbol,
        condition=condition,
        threshold=threshold,
        message=f"{symbol} {condition.value} {threshold}",
    )


def make_ohlcv_bars(n: int = 50, seed: int = 7) -> list[OHLCVBar]:
    """Generate a list of OHLCVBar instances."""
    df    = make_ohlcv_df(n, seed=seed)
    bars  = []
    for ts, row in df.iterrows():
        bars.append(OHLCVBar(
            timestamp=int(pd.Timestamp(ts).timestamp() * 1000),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"]),
        ))
    return bars

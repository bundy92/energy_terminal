"""Technical analysis indicators for energy market instruments.

All functions operate on :class:`numpy.ndarray` inputs and return
:class:`numpy.ndarray` outputs so they compose efficiently with Pandas
Series via ``.to_numpy()`` / ``pd.Series(result)``.

References
----------
.. [1] Wilder, J. W. (1978). *New Concepts in Technical Trading Systems*.
       Trend Research.
.. [2] Appel, G. (2005). *Technical Analysis: Power Tools for Active
       Investors*. FT Press.
.. [3] Bollinger, J. (2002). *Bollinger on Bollinger Bands*. McGraw-Hill.

Examples
--------
>>> import numpy as np
>>> prices = np.array([80., 82., 81., 85., 83., 86., 88., 87., 90., 89.,
...                    91., 93., 92., 95., 94.])
>>> rsi_vals = rsi(prices, period=14)
>>> len(rsi_vals) == len(prices)
True
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------

def sma(values: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average.

    Parameters
    ----------
    values : np.ndarray
        Input price or volume series.
    period : int
        Look-back window length.

    Returns
    -------
    np.ndarray
        SMA series.  The first ``period - 1`` elements are ``NaN``.

    Raises
    ------
    ValueError
        If ``period < 1`` or ``period > len(values)``.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    if period > len(values):
        raise ValueError(f"period ({period}) exceeds series length ({len(values)})")

    out = np.full(len(values), np.nan)
    kernel = np.ones(period) / period
    valid  = np.convolve(values, kernel, mode="valid")
    out[period - 1 :] = valid
    return out


def ema(values: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average.

    Parameters
    ----------
    values : np.ndarray
        Input series.
    period : int
        Look-back window (determines smoothing factor ``alpha = 2/(period+1)``).

    Returns
    -------
    np.ndarray
        EMA series.  First ``period - 1`` elements are ``NaN``.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    alpha = 2.0 / (period + 1)
    out   = np.full(len(values), np.nan)

    if len(values) < period:
        return out

    # Seed with SMA of first window
    out[period - 1] = np.mean(values[:period])
    for i in range(period, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

def rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index (Wilder smoothing).

    Parameters
    ----------
    close : np.ndarray
        Closing price series.
    period : int
        Look-back window (standard: 14).

    Returns
    -------
    np.ndarray
        RSI values in the range [0, 100].  First ``period`` elements are
        ``NaN``.

    Notes
    -----
    Uses Wilder's smoothed moving average (RMA / SMMA), not plain EMA,
    consistent with Bloomberg and TradingView implementations.
    """
    delta = np.diff(close, prepend=close[0])
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)

    out = np.full(len(close), np.nan)
    if len(close) <= period:
        return out

    # Seed with simple mean
    avg_gain = np.mean(gains[1 : period + 1])
    avg_loss = np.mean(losses[1 : period + 1])

    for i in range(period, len(close)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else np.inf
        out[i] = 100.0 - (100.0 / (1.0 + rs))

    return out


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def macd(
    close: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Moving Average Convergence Divergence.

    Parameters
    ----------
    close : np.ndarray
        Closing price series.
    fast : int
        Fast EMA period (default 12).
    slow : int
        Slow EMA period (default 26).
    signal : int
        Signal line EMA period (default 9).

    Returns
    -------
    macd_line : np.ndarray
        MACD line (fast EMA − slow EMA).
    signal_line : np.ndarray
        EMA of MACD line.
    histogram : np.ndarray
        MACD line − signal line.
    """
    fast_ema  = ema(close, fast)
    slow_ema  = ema(close, slow)
    macd_line = fast_ema - slow_ema

    valid_mask = ~np.isnan(macd_line)
    signal_line = np.full(len(close), np.nan)
    if np.any(valid_mask):
        first_valid = np.argmax(valid_mask)
        sig_values  = ema(macd_line[first_valid:], signal)
        signal_line[first_valid:] = sig_values

    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def bollinger_bands(
    close: np.ndarray,
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands.

    Parameters
    ----------
    close : np.ndarray
        Closing price series.
    period : int
        SMA look-back window (default 20).
    num_std : float
        Standard deviation multiplier for band width (default 2.0).

    Returns
    -------
    upper : np.ndarray
        Upper band (SMA + num_std × rolling std).
    middle : np.ndarray
        Middle band (SMA).
    lower : np.ndarray
        Lower band (SMA − num_std × rolling std).
    """
    middle = sma(close, period)
    std    = np.full(len(close), np.nan)

    for i in range(period - 1, len(close)):
        std[i] = np.std(close[i - period + 1 : i + 1], ddof=1)

    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

def atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """Average True Range (Wilder smoothing).

    Parameters
    ----------
    high : np.ndarray
        Daily high prices.
    low : np.ndarray
        Daily low prices.
    close : np.ndarray
        Daily close prices.
    period : int
        Smoothing period (default 14).

    Returns
    -------
    np.ndarray
        ATR series.  First ``period`` elements are ``NaN``.
    """
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]

    tr = np.maximum(
        high - low,
        np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)),
    )

    out = np.full(len(close), np.nan)
    if len(close) <= period:
        return out

    out[period - 1] = np.mean(tr[:period])
    for i in range(period, len(close)):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


# ---------------------------------------------------------------------------
# OBV
# ---------------------------------------------------------------------------

def obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """On-Balance Volume.

    Parameters
    ----------
    close : np.ndarray
        Closing price series.
    volume : np.ndarray
        Volume series (same length as ``close``).

    Returns
    -------
    np.ndarray
        Cumulative OBV series.  First element is ``volume[0]``.
    """
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)


# ---------------------------------------------------------------------------
# VWAP
# ---------------------------------------------------------------------------

def vwap(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
) -> np.ndarray:
    """Volume-Weighted Average Price (intraday, resets each day).

    Parameters
    ----------
    high : np.ndarray
        Bar high prices.
    low : np.ndarray
        Bar low prices.
    close : np.ndarray
        Bar close prices.
    volume : np.ndarray
        Bar volumes.

    Returns
    -------
    np.ndarray
        Cumulative VWAP over the supplied bars.
    """
    typical = (high + low + close) / 3.0
    cum_tpv = np.cumsum(typical * volume)
    cum_vol = np.cumsum(volume)
    # Avoid division by zero
    safe_vol = np.where(cum_vol == 0, 1, cum_vol)
    return cum_tpv / safe_vol


# ---------------------------------------------------------------------------
# Stochastic Oscillator
# ---------------------------------------------------------------------------

def stochastic(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """Stochastic Oscillator (%K and %D).

    Parameters
    ----------
    high : np.ndarray
        Daily high prices.
    low : np.ndarray
        Daily low prices.
    close : np.ndarray
        Daily close prices.
    k_period : int
        %K look-back window (default 14).
    d_period : int
        %D smoothing period (default 3).

    Returns
    -------
    k : np.ndarray
        Fast stochastic %K in [0, 100].
    d : np.ndarray
        Slow stochastic %D (SMA of %K).
    """
    k = np.full(len(close), np.nan)
    for i in range(k_period - 1, len(close)):
        window_high = np.max(high[i - k_period + 1 : i + 1])
        window_low  = np.min(low[i - k_period + 1 : i + 1])
        denom = window_high - window_low
        k[i]  = 100.0 * (close[i] - window_low) / denom if denom != 0 else 50.0

    d = sma(np.where(np.isnan(k), 0.0, k), d_period)
    d[np.isnan(k)] = np.nan
    return k, d

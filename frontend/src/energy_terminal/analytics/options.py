"""Options analytics for energy instruments.

This module provides Black-Scholes pricing, Greek sensitivities, and
implied volatility calculations suitable for energy derivative workflows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def _norm_pdf(x: float) -> float:
    return float(stats.norm.pdf(x))


def _norm_cdf(x: float) -> float:
    return float(stats.norm.cdf(x))


def _validate_option_type(option_type: str) -> str:
    option_type = option_type.lower().strip()
    if option_type not in {"call", "put"}:
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type}")
    return option_type


def _black_scholes_d1(
    spot: float,
    strike: float,
    time_to_expiry: float,
    rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> float:
    return float(
        (np.log(spot / strike)
         + (rate - dividend_yield + 0.5 * volatility ** 2) * time_to_expiry)
        / (volatility * np.sqrt(time_to_expiry))
    )


def _black_scholes_d2(d1: float, volatility: float, time_to_expiry: float) -> float:
    return float(d1 - volatility * np.sqrt(time_to_expiry))


def black_scholes_price(
    spot: float,
    strike: float,
    time_to_expiry: float,
    rate: float,
    volatility: float,
    option_type: str = "call",
    dividend_yield: float = 0.0,
) -> float:
    """Compute the Black-Scholes option price.

    Parameters
    ----------
    spot : float
        Underlying spot price.
    strike : float
        Option strike price.
    time_to_expiry : float
        Time to expiry in years.
    rate : float
        Risk-free interest rate as a decimal.
    volatility : float
        Implied volatility as a decimal.
    option_type : str
        Either ``'call'`` or ``'put'``.
    dividend_yield : float
        Continuous dividend yield or convenience yield.

    Returns
    -------
    float
        Option premium.
    """
    option_type = _validate_option_type(option_type)
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    if time_to_expiry < 0:
        raise ValueError("time_to_expiry must be non-negative")
    if volatility < 0:
        raise ValueError("volatility must be non-negative")

    if time_to_expiry == 0 or volatility == 0:
        intrinsic = max(0.0, spot - strike) if option_type == "call" else max(0.0, strike - spot)
        return float(intrinsic)

    d1 = _black_scholes_d1(spot, strike, time_to_expiry, rate, volatility, dividend_yield)
    d2 = _black_scholes_d2(d1, volatility, time_to_expiry)
    forward_discount = np.exp(-dividend_yield * time_to_expiry)
    discount = np.exp(-rate * time_to_expiry)

    if option_type == "call":
        return float(spot * forward_discount * _norm_cdf(d1) - strike * discount * _norm_cdf(d2))
    return float(strike * discount * _norm_cdf(-d2) - spot * forward_discount * _norm_cdf(-d1))


def black_scholes_delta(
    spot: float,
    strike: float,
    time_to_expiry: float,
    rate: float,
    volatility: float,
    option_type: str = "call",
    dividend_yield: float = 0.0,
) -> float:
    """Compute Black-Scholes delta."""
    option_type = _validate_option_type(option_type)
    if time_to_expiry == 0 or volatility == 0:
        intrinsic = 1.0 if option_type == "call" and spot > strike else 0.0
        if option_type == "put":
            intrinsic = 1.0 if spot < strike else 0.0
        return float(intrinsic)

    d1 = _black_scholes_d1(spot, strike, time_to_expiry, rate, volatility, dividend_yield)
    if option_type == "call":
        return float(np.exp(-dividend_yield * time_to_expiry) * _norm_cdf(d1))
    return float(np.exp(-dividend_yield * time_to_expiry) * (_norm_cdf(d1) - 1.0))


def black_scholes_gamma(
    spot: float,
    strike: float,
    time_to_expiry: float,
    rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> float:
    """Compute Black-Scholes gamma."""
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    if time_to_expiry <= 0 or volatility <= 0:
        return 0.0

    d1 = _black_scholes_d1(spot, strike, time_to_expiry, rate, volatility, dividend_yield)
    return float(
        _norm_pdf(d1)
        * np.exp(-dividend_yield * time_to_expiry)
        / (spot * volatility * np.sqrt(time_to_expiry))
    )


def black_scholes_vega(
    spot: float,
    strike: float,
    time_to_expiry: float,
    rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> float:
    """Compute Black-Scholes vega."""
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    if time_to_expiry <= 0 or volatility <= 0:
        return 0.0

    d1 = _black_scholes_d1(spot, strike, time_to_expiry, rate, volatility, dividend_yield)
    return float(spot * np.exp(-dividend_yield * time_to_expiry) * _norm_pdf(d1) * np.sqrt(time_to_expiry))


def implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    time_to_expiry: float,
    rate: float,
    option_type: str = "call",
    dividend_yield: float = 0.0,
    tolerance: float = 1e-6,
    max_iterations: int = 100,
) -> float:
    """Estimate implied volatility from a market option price."""
    option_type = _validate_option_type(option_type)
    if market_price < 0:
        raise ValueError("market_price must be non-negative")
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    if time_to_expiry < 0:
        raise ValueError("time_to_expiry must be non-negative")

    intrinsic = max(0.0, spot - strike) if option_type == "call" else max(0.0, strike - spot)
    if market_price < intrinsic:
        raise ValueError("market_price is below intrinsic value")

    low, high = 1e-6, 5.0
    low_price = black_scholes_price(spot, strike, time_to_expiry, rate, low, option_type, dividend_yield)
    high_price = black_scholes_price(spot, strike, time_to_expiry, rate, high, option_type, dividend_yield)

    while high_price < market_price and high < 10.0:
        high *= 2.0
        high_price = black_scholes_price(spot, strike, time_to_expiry, rate, high, option_type, dividend_yield)

    if market_price > high_price:
        raise ValueError("market_price is too high to imply within volatility bounds")

    for _ in range(max_iterations):
        mid = 0.5 * (low + high)
        price = black_scholes_price(spot, strike, time_to_expiry, rate, mid, option_type, dividend_yield)
        if abs(price - market_price) < tolerance:
            return float(mid)
        if price < market_price:
            low = mid
        else:
            high = mid
    return float(0.5 * (low + high))


def implied_vol_surface(
    strikes: list[float] | np.ndarray,
    maturities: list[float] | np.ndarray,
    market_prices: pd.DataFrame,
    spot: float,
    rate: float,
    option_type: str = "call",
    dividend_yield: float = 0.0,
) -> pd.DataFrame:
    """Generate an implied volatility surface from market option prices."""
    option_type = _validate_option_type(option_type)
    strikes_arr = np.asarray(strikes, dtype=float)
    maturities_arr = np.asarray(maturities, dtype=float)

    if market_prices.shape != (len(maturities_arr), len(strikes_arr)):
        raise ValueError("market_prices must have shape (len(maturities), len(strikes))")

    surface = pd.DataFrame(index=maturities_arr, columns=strikes_arr, dtype=float)
    for i, t in enumerate(maturities_arr):
        for j, k in enumerate(strikes_arr):
            try:
                surface.iloc[i, j] = implied_volatility(
                    market_price=market_prices.iloc[i, j],
                    spot=spot,
                    strike=k,
                    time_to_expiry=t,
                    rate=rate,
                    option_type=option_type,
                    dividend_yield=dividend_yield,
                )
            except ValueError:
                surface.iloc[i, j] = np.nan
    return surface

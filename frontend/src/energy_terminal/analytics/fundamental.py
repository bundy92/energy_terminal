"""Energy-specific fundamental analytical functions.

Covers crack spreads, spark spreads, refinery margin proxies, term
structure analysis, and supply/demand balance calculations.

All price inputs are assumed to be in USD per barrel unless otherwise
stated.  Unit conversion helpers are provided where industry practice
diverges from a single unit.

References
----------
.. [1] EIA. "Crack Spread". *Glossary*. US Energy Information
       Administration. https://www.eia.gov/tools/glossary/
.. [2] CME Group. "Petroleum Crack Spread Handbook". 2015.
.. [3] Hull, J. C. (2018). *Options, Futures, and Other Derivatives*,
       10th ed. Pearson.

Examples
--------
>>> crack_3_2_1(wti=85.0, rbob_usc=240.0, ulsd_usc=280.0)
16.8
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Unit conversion constants
# ---------------------------------------------------------------------------

GALLONS_PER_BARREL: float = 42.0
"""US gallons in one barrel of crude oil."""

MMBTU_PER_MCF: float = 1.02
"""Approximate MMBtu per thousand cubic feet of natural gas."""


def usc_per_gallon_to_usd_per_barrel(usc: float) -> float:
    """Convert US cents per gallon to USD per barrel.

    Parameters
    ----------
    usc : float
        Price in US cents per gallon (NYMEX RBOB / ULSD convention).

    Returns
    -------
    float
        Equivalent price in USD per barrel.
    """
    return usc * GALLONS_PER_BARREL / 100.0


# ---------------------------------------------------------------------------
# Crack spreads
# ---------------------------------------------------------------------------

def crack_3_2_1(
    wti: float,
    rbob_usc: float,
    ulsd_usc: float,
) -> float:
    """3-2-1 crack spread (two barrels gasoline, one barrel distillate).

    Industry-standard proxy for a US Gulf Coast refinery margin.

    Parameters
    ----------
    wti : float
        WTI crude price in USD per barrel.
    rbob_usc : float
        RBOB gasoline price in US cents per gallon.
    ulsd_usc : float
        ULSD (ultra-low sulphur diesel) price in US cents per gallon.

    Returns
    -------
    float
        3-2-1 crack spread in USD per barrel.

    Notes
    -----
    Formula::

        (2 × RBOB_bbl + 1 × ULSD_bbl − 3 × WTI) / 3
    """
    rbob_bbl = usc_per_gallon_to_usd_per_barrel(rbob_usc)
    ulsd_bbl = usc_per_gallon_to_usd_per_barrel(ulsd_usc)
    return (2.0 * rbob_bbl + 1.0 * ulsd_bbl - 3.0 * wti) / 3.0


def crack_2_1_1(
    brent: float,
    rbob_usc: float,
    ulsd_usc: float,
) -> float:
    """2-1-1 crack spread (equal split gasoline/distillate).

    Commonly used for European refinery margin approximation.

    Parameters
    ----------
    brent : float
        Brent crude price in USD per barrel.
    rbob_usc : float
        RBOB gasoline price in US cents per gallon.
    ulsd_usc : float
        ULSD price in US cents per gallon.

    Returns
    -------
    float
        2-1-1 crack spread in USD per barrel.
    """
    rbob_bbl = usc_per_gallon_to_usd_per_barrel(rbob_usc)
    ulsd_bbl = usc_per_gallon_to_usd_per_barrel(ulsd_usc)
    return (1.0 * rbob_bbl + 1.0 * ulsd_bbl - 2.0 * brent) / 2.0


def heating_oil_crack(brent: float, ulsd_usc: float) -> float:
    """1-1 heating oil crack spread.

    Parameters
    ----------
    brent : float
        Brent crude price in USD per barrel.
    ulsd_usc : float
        ULSD price in US cents per gallon.

    Returns
    -------
    float
        Heating oil crack spread in USD per barrel.
    """
    return usc_per_gallon_to_usd_per_barrel(ulsd_usc) - brent


# ---------------------------------------------------------------------------
# Spark spread
# ---------------------------------------------------------------------------

def spark_spread(
    power_price_mwh: float,
    gas_price_mmbtu: float,
    heat_rate_btu_kwh: float = 7_000.0,
) -> float:
    """Spark spread — profitability of gas-fired power generation.

    Parameters
    ----------
    power_price_mwh : float
        Day-ahead electricity price in USD per MWh.
    gas_price_mmbtu : float
        Natural gas price in USD per MMBtu (e.g. Henry Hub).
    heat_rate_btu_kwh : float
        Plant heat rate in BTU per kWh (efficiency measure).
        Default 7,000 = ~49% efficiency (combined-cycle).

    Returns
    -------
    float
        Spark spread in USD per MWh.  Positive = generation is profitable.

    Notes
    -----
    Formula::

        spark_spread = power_price − (gas_price × heat_rate / 1_000_000)
    """
    fuel_cost_mwh = gas_price_mmbtu * heat_rate_btu_kwh / 1_000.0
    return power_price_mwh - fuel_cost_mwh


# ---------------------------------------------------------------------------
# Term structure
# ---------------------------------------------------------------------------

def contango_backwardation_ratio(
    front_price: float,
    back_price: float,
) -> float:
    """Ratio of front-month to back-month price (term structure slope).

    Parameters
    ----------
    front_price : float
        Front-month futures price.
    back_price : float
        Deferred-month futures price.

    Returns
    -------
    float
        Ratio > 1 implies backwardation (spot premium);
        ratio < 1 implies contango (storage premium).
    """
    if back_price == 0:
        raise ValueError("back_price must be non-zero")
    return front_price / back_price


def term_structure_slope(prices: np.ndarray, tenors_months: np.ndarray) -> float:
    """Linear slope of the forward curve (USD/bbl per month).

    Parameters
    ----------
    prices : np.ndarray
        Futures prices for each tenor.
    tenors_months : np.ndarray
        Tenors in months (e.g. ``[1, 2, 3, 6, 12]``).

    Returns
    -------
    float
        OLS slope coefficient in USD per barrel per month.
        Negative = backwardation; positive = contango.
    """
    if len(prices) != len(tenors_months) or len(prices) < 2:
        raise ValueError("prices and tenors_months must have equal length >= 2")

    x = tenors_months.astype(float)
    y = prices.astype(float)
    coeffs = np.polyfit(x, y, deg=1)
    return float(coeffs[0])


def annualised_roll_yield(
    front_price: float,
    next_price: float,
    days_to_expiry: int,
) -> float:
    """Annualised roll yield from rolling a futures position.

    Parameters
    ----------
    front_price : float
        Current front-month futures price.
    next_price : float
        Price of the next contract (one month deferred).
    days_to_expiry : int
        Calendar days until front contract expiry.

    Returns
    -------
    float
        Annualised roll yield as a decimal (0.05 = 5% per annum).
    """
    if front_price == 0 or days_to_expiry == 0:
        raise ValueError("front_price and days_to_expiry must be non-zero")
    monthly_roll = (next_price - front_price) / front_price
    return monthly_roll * (365.0 / days_to_expiry)


# ---------------------------------------------------------------------------
# Seasonality
# ---------------------------------------------------------------------------

def seasonal_index(
    prices: pd.Series,
    method: str = "average",
) -> pd.DataFrame:
    """Compute average seasonal profile by calendar month.

    Parameters
    ----------
    prices : pd.Series
        Price series with a ``DatetimeIndex``.
    method : str
        Aggregation method: ``"average"`` (mean) or ``"median"``.

    Returns
    -------
    pd.DataFrame
        DataFrame indexed 1–12 with columns
        ``[mean, median, std, min, max, count]``.

    Raises
    ------
    ValueError
        If ``prices.index`` is not a ``DatetimeIndex``.
    """
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("prices must have a DatetimeIndex")

    df   = prices.to_frame(name="price")
    df["month"] = df.index.month  # type: ignore[attr-defined]
    grouped = df.groupby("month")["price"]

    return pd.DataFrame({
        "mean":   grouped.mean(),
        "median": grouped.median(),
        "std":    grouped.std(),
        "min":    grouped.min(),
        "max":    grouped.max(),
        "count":  grouped.count(),
    })


# ---------------------------------------------------------------------------
# Supply / demand balance
# ---------------------------------------------------------------------------

def supply_demand_balance(
    production: float,
    net_imports: float,
    consumption: float,
    inventory_change: float,
) -> float:
    """Compute the implied balance residual.

    Parameters
    ----------
    production : float
        Domestic production (thousand barrels per day or any consistent unit).
    net_imports : float
        Net imports (imports − exports).
    consumption : float
        Total product supplied / demand.
    inventory_change : float
        Reported stock change (positive = build, negative = draw).

    Returns
    -------
    float
        Residual (supply − demand − inventory_change).
        Non-zero values indicate data revisions or unreported flows.
    """
    supply = production + net_imports
    return supply - consumption - inventory_change

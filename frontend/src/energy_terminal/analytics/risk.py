"""Risk analytics for energy portfolio management.

Implements Value-at-Risk (historical simulation and parametric),
Conditional VaR (Expected Shortfall), rolling correlation matrices,
and volatility cones.

References
----------
.. [1] Jorion, P. (2007). *Value at Risk*, 3rd ed. McGraw-Hill.
.. [2] Rockafellar, R. T., & Uryasev, S. (2000). Optimization of
       conditional value-at-risk. *Journal of Risk*, 2(3), 21-41.
.. [3] Pafka, S., & Kondor, I. (2004). Estimated correlation matrices
       and portfolio optimization. *Physica A*, 343, 623-634.

Examples
--------
>>> import numpy as np
>>> returns = np.random.normal(0, 0.02, 500)
>>> var_95 = historical_var(returns, confidence=0.95)
>>> cvar_95 = historical_cvar(returns, confidence=0.95)
>>> cvar_95 <= var_95   # CVaR is always >= VaR in magnitude
True
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


# ---------------------------------------------------------------------------
# Return computation
# ---------------------------------------------------------------------------

def log_returns(prices: np.ndarray) -> np.ndarray:
    """Compute log returns from a price series.

    Parameters
    ----------
    prices : np.ndarray
        Price series (must be strictly positive).

    Returns
    -------
    np.ndarray
        Log returns of length ``len(prices) - 1``.
    """
    if np.any(prices <= 0):
        raise ValueError("prices must be strictly positive for log returns")
    return np.log(prices[1:] / prices[:-1])


def pct_returns(prices: np.ndarray) -> np.ndarray:
    """Compute simple percentage returns from a price series.

    Parameters
    ----------
    prices : np.ndarray
        Price series.

    Returns
    -------
    np.ndarray
        Percentage returns of length ``len(prices) - 1``.
    """
    return np.diff(prices) / prices[:-1]


# ---------------------------------------------------------------------------
# Value at Risk
# ---------------------------------------------------------------------------

def historical_var(
    returns: np.ndarray,
    confidence: float = 0.95,
    holding_period_days: int = 1,
) -> float:
    """Historical simulation Value-at-Risk.

    Parameters
    ----------
    returns : np.ndarray
        Observed return series (log or simple).
    confidence : float
        Confidence level in (0, 1).  Standard: 0.95 or 0.99.
    holding_period_days : int
        Holding period in trading days (default 1).  For multi-day VaR
        the square-root-of-time rule is applied.

    Returns
    -------
    float
        VaR as a positive number (loss convention).

    Notes
    -----
    VaR is reported as the magnitude of the loss at the given confidence
    level, following the risk management convention where VaR > 0
    denotes a loss.
    """
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")

    percentile = (1 - confidence) * 100
    one_day    = -np.percentile(returns, percentile)
    return float(one_day * np.sqrt(holding_period_days))


def parametric_var(
    returns: np.ndarray,
    confidence: float = 0.95,
    holding_period_days: int = 1,
) -> float:
    """Parametric (Gaussian) Value-at-Risk.

    Parameters
    ----------
    returns : np.ndarray
        Observed return series.
    confidence : float
        Confidence level in (0, 1).
    holding_period_days : int
        Holding period in trading days.

    Returns
    -------
    float
        Parametric VaR as a positive number.
    """
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")

    mu    = float(np.mean(returns))
    sigma = float(np.std(returns, ddof=1))
    z     = float(stats.norm.ppf(1 - confidence))
    one_day_var = -(mu + z * sigma)
    return float(one_day_var * np.sqrt(holding_period_days))


# ---------------------------------------------------------------------------
# Conditional VaR (Expected Shortfall)
# ---------------------------------------------------------------------------

def historical_cvar(
    returns: np.ndarray,
    confidence: float = 0.95,
    holding_period_days: int = 1,
) -> float:
    """Historical Conditional VaR (Expected Shortfall).

    CVaR is the expected loss *conditional on* the loss exceeding VaR.
    It is a coherent risk measure and satisfies sub-additivity.

    Parameters
    ----------
    returns : np.ndarray
        Observed return series.
    confidence : float
        Confidence level in (0, 1).
    holding_period_days : int
        Holding period in trading days.

    Returns
    -------
    float
        CVaR as a positive number.
    """
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")

    threshold  = np.percentile(returns, (1 - confidence) * 100)
    tail_losses = returns[returns <= threshold]
    if len(tail_losses) == 0:
        return 0.0
    one_day = -float(np.mean(tail_losses))
    return float(one_day * np.sqrt(holding_period_days))


# ---------------------------------------------------------------------------
# Correlation matrix
# ---------------------------------------------------------------------------

def rolling_correlation_matrix(
    prices_df: pd.DataFrame,
    window: int = 60,
) -> pd.DataFrame:
    """Compute a rolling correlation matrix for the most recent window.

    Parameters
    ----------
    prices_df : pd.DataFrame
        DataFrame where each column is a price series.  Must have at
        least ``window`` rows.
    window : int
        Rolling look-back in trading days (default 60).

    Returns
    -------
    pd.DataFrame
        Pairwise Pearson correlation matrix for the most recent ``window``
        observations.  Index and columns match ``prices_df.columns``.
    """
    if len(prices_df) < window:
        raise ValueError(
            f"DataFrame has {len(prices_df)} rows but window requires {window}"
        )
    recent_returns = prices_df.iloc[-window:].pct_change().dropna()
    return recent_returns.corr(method="pearson")


# ---------------------------------------------------------------------------
# Volatility cone
# ---------------------------------------------------------------------------

def volatility_cone(
    returns: np.ndarray,
    windows: tuple[int, ...] = (10, 20, 30, 60, 90),
    annualisation_factor: int = 252,
) -> dict[int, dict[str, float]]:
    """Compute historical realised volatility cone.

    Parameters
    ----------
    returns : np.ndarray
        Observed return series (log returns recommended).
    windows : tuple[int, ...]
        Rolling windows over which to compute realised vol.
    annualisation_factor : int
        Trading days per year (252 for equities/futures, 365 for energy).

    Returns
    -------
    dict[int, dict[str, float]]
        Mapping of window → ``{current, mean, percentile_25,
        percentile_75, min, max}`` all annualised as decimals.

    Notes
    -----
    Percentile bands represent the historical distribution of realised
    volatility for each window length, enabling comparison of current
    volatility against its own history.
    """
    result: dict[int, dict[str, float]] = {}
    for w in windows:
        if len(returns) < w:
            continue
        rolling_vols = [
            np.std(returns[i : i + w], ddof=1) * np.sqrt(annualisation_factor)
            for i in range(len(returns) - w + 1)
        ]
        arr = np.array(rolling_vols)
        result[w] = {
            "current":       float(arr[-1]),
            "mean":          float(np.mean(arr)),
            "percentile_25": float(np.percentile(arr, 25)),
            "percentile_75": float(np.percentile(arr, 75)),
            "min":           float(np.min(arr)),
            "max":           float(np.max(arr)),
        }
    return result


# ---------------------------------------------------------------------------
# Portfolio-level metrics
# ---------------------------------------------------------------------------

def portfolio_var(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
    confidence: float = 0.95,
    holding_period_days: int = 1,
) -> float:
    """Parametric portfolio VaR using a covariance matrix.

    Parameters
    ----------
    weights : np.ndarray
        Position weights (must sum to 1 for percentage notation).
    cov_matrix : np.ndarray
        Annualised covariance matrix of instrument returns.
    confidence : float
        Confidence level.
    holding_period_days : int
        Holding period in trading days.

    Returns
    -------
    float
        Portfolio VaR as a positive decimal.
    """
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")

    daily_cov  = cov_matrix / 252.0
    port_var   = float(weights @ daily_cov @ weights)
    port_sigma = np.sqrt(port_var)
    z          = float(stats.norm.ppf(1 - confidence))
    return float(-z * port_sigma * np.sqrt(holding_period_days))

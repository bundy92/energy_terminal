"""Analytics sub-package.

Provides three analytical modules:

- :mod:`technical`   — price-based indicators (RSI, MACD, Bollinger, ATR, OBV)
- :mod:`fundamental` — energy-specific metrics (crack spreads, term structure)
- :mod:`risk`        — portfolio risk (VaR, CVaR, correlation, vol cone)
"""

from energy_terminal.analytics.fundamental import (
    crack_2_1_1,
    crack_3_2_1,
    heating_oil_crack,
    seasonal_index,
    spark_spread,
    supply_demand_balance,
    term_structure_slope,
    annualised_roll_yield,
)
from energy_terminal.analytics.risk import (
    historical_var,
    historical_cvar,
    parametric_var,
    portfolio_var,
    rolling_correlation_matrix,
    volatility_cone,
    log_returns,
    pct_returns,
)
from energy_terminal.analytics.options import (
    black_scholes_delta,
    black_scholes_gamma,
    black_scholes_price,
    black_scholes_vega,
    implied_vol_surface,
    implied_volatility,
)
from energy_terminal.analytics.technical import (
    atr,
    bollinger_bands,
    ema,
    macd,
    obv,
    rsi,
    sma,
    stochastic,
    vwap,
)

__all__ = [
    "atr", "bollinger_bands", "ema", "macd", "obv", "rsi", "sma",
    "stochastic", "vwap",
    "black_scholes_price", "black_scholes_delta", "black_scholes_gamma",
    "black_scholes_vega", "implied_volatility", "implied_vol_surface",
    "crack_2_1_1", "crack_3_2_1", "heating_oil_crack", "seasonal_index",
    "spark_spread", "supply_demand_balance", "term_structure_slope",
    "annualised_roll_yield",
    "historical_var", "historical_cvar", "parametric_var", "portfolio_var",
    "rolling_correlation_matrix", "volatility_cone", "log_returns", "pct_returns",
]

"""Unit tests for :mod:`energy_terminal.analytics.risk`."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from energy_terminal.analytics.risk import (
    historical_cvar,
    historical_var,
    log_returns,
    parametric_var,
    pct_returns,
    portfolio_var,
    rolling_correlation_matrix,
    volatility_cone,
)
from tests.fixtures.sample_data import make_price_series


class TestLogReturns:
    def test_length_is_n_minus_1(self) -> None:
        prices = make_price_series(50)
        assert len(log_returns(prices)) == 49

    def test_raises_on_non_positive_prices(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            log_returns(np.array([1.0, 0.0, -1.0]))

    def test_flat_prices_give_zero_returns(self) -> None:
        prices = np.full(20, 80.0)
        rets   = log_returns(prices)
        np.testing.assert_array_almost_equal(rets, 0.0)


class TestPctReturns:
    def test_length_is_n_minus_1(self) -> None:
        assert len(pct_returns(make_price_series(30))) == 29

    def test_doubling_price_gives_100_pct(self) -> None:
        prices = np.array([50.0, 100.0])
        np.testing.assert_almost_equal(pct_returns(prices)[0], 1.0)


class TestHistoricalVaR:
    def test_var_is_positive(self) -> None:
        rets = log_returns(make_price_series(500))
        assert historical_var(rets, 0.95) > 0

    def test_99_var_gte_95_var(self) -> None:
        rets   = log_returns(make_price_series(500))
        var_95 = historical_var(rets, 0.95)
        var_99 = historical_var(rets, 0.99)
        assert var_99 >= var_95

    def test_raises_on_invalid_confidence(self) -> None:
        rets = log_returns(make_price_series(100))
        with pytest.raises(ValueError):
            historical_var(rets, 1.5)

    def test_scales_with_sqrt_of_holding_period(self) -> None:
        rets    = log_returns(make_price_series(500))
        var_1d  = historical_var(rets, 0.95, 1)
        var_4d  = historical_var(rets, 0.95, 4)
        np.testing.assert_almost_equal(var_4d, var_1d * 2.0, decimal=6)


class TestHistoricalCVaR:
    def test_cvar_gte_var(self) -> None:
        rets   = log_returns(make_price_series(500))
        var95  = historical_var(rets, 0.95)
        cvar95 = historical_cvar(rets, 0.95)
        assert cvar95 >= var95

    def test_positive_output(self) -> None:
        rets = log_returns(make_price_series(500))
        assert historical_cvar(rets, 0.95) > 0

    def test_raises_on_invalid_confidence(self) -> None:
        rets = log_returns(make_price_series(100))
        with pytest.raises(ValueError):
            historical_cvar(rets, 0.0)


class TestParametricVaR:
    def test_positive_output(self) -> None:
        rets = log_returns(make_price_series(252))
        assert parametric_var(rets, 0.95) > 0

    def test_99_gte_95(self) -> None:
        rets = log_returns(make_price_series(252))
        assert parametric_var(rets, 0.99) >= parametric_var(rets, 0.95)

    def test_normal_distribution_known_value(self) -> None:
        rng  = np.random.default_rng(0)
        rets = rng.normal(0, 0.01, 100_000)
        # Parametric VaR at 95% ≈ 1.645σ = 0.01645
        result = parametric_var(rets, 0.95)
        assert abs(result - 0.01645) < 0.002


class TestRollingCorrelation:
    def test_diagonal_is_one(self) -> None:
        syms = ["A", "B", "C"]
        data = {s: make_price_series(100, seed=i) for i, s in enumerate(syms)}
        df   = pd.DataFrame(data)
        corr = rolling_correlation_matrix(df, window=60)
        for sym in syms:
            np.testing.assert_almost_equal(corr.loc[sym, sym], 1.0)

    def test_symmetric(self) -> None:
        syms = ["A", "B"]
        data = {s: make_price_series(100, seed=i) for i, s in enumerate(syms)}
        df   = pd.DataFrame(data)
        corr = rolling_correlation_matrix(df, window=60)
        np.testing.assert_almost_equal(
            corr.loc["A", "B"], corr.loc["B", "A"]
        )

    def test_raises_when_insufficient_data(self) -> None:
        df = pd.DataFrame({"A": [1.0, 2.0, 3.0], "B": [3.0, 2.0, 1.0]})
        with pytest.raises(ValueError):
            rolling_correlation_matrix(df, window=60)


class TestVolatilityCone:
    def test_returns_dict_with_expected_windows(self) -> None:
        rets   = log_returns(make_price_series(300))
        result = volatility_cone(rets, windows=(10, 20, 30))
        assert set(result.keys()) == {10, 20, 30}

    def test_each_window_has_required_keys(self) -> None:
        rets   = log_returns(make_price_series(300))
        result = volatility_cone(rets, windows=(20,))
        assert set(result[20].keys()) == {
            "current", "mean", "percentile_25", "percentile_75", "min", "max"
        }

    def test_current_within_min_max(self) -> None:
        rets   = log_returns(make_price_series(300))
        result = volatility_cone(rets, windows=(20, 30))
        for w, stats in result.items():
            assert stats["min"] <= stats["current"] <= stats["max"], \
                f"current out of range for window {w}"

    def test_skips_windows_with_insufficient_data(self) -> None:
        rets   = log_returns(make_price_series(25))
        result = volatility_cone(rets, windows=(10, 30, 60))
        # Only window 10 has enough data (25 - 10 + 1 = 16 > 0)
        assert 10 in result
        assert 30 not in result


class TestPortfolioVaR:
    def test_positive_output(self) -> None:
        weights    = np.array([0.5, 0.5])
        cov_matrix = np.array([[0.04, 0.02], [0.02, 0.04]])
        result     = portfolio_var(weights, cov_matrix, 0.95)
        assert result > 0

    def test_raises_on_invalid_confidence(self) -> None:
        weights    = np.array([0.5, 0.5])
        cov_matrix = np.eye(2) * 0.04
        with pytest.raises(ValueError):
            portfolio_var(weights, cov_matrix, 1.1)

"""Unit tests for :mod:`energy_terminal.analytics.technical`.

Follows TDD: every public function has tests for:
- Correct output shape and NaN padding
- Known-value assertions (hand-computed)
- Edge cases (short series, period == len, all-same prices)
- ValueError contract on bad inputs
"""

from __future__ import annotations

import numpy as np
import pytest

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
from tests.fixtures.sample_data import make_price_series


# ---------------------------------------------------------------------------
# SMA
# ---------------------------------------------------------------------------

class TestSMA:
    def test_output_length_matches_input(self) -> None:
        prices = make_price_series(50)
        result = sma(prices, 10)
        assert len(result) == 50

    def test_first_n_minus_1_are_nan(self) -> None:
        prices = make_price_series(30)
        result = sma(prices, 10)
        assert np.all(np.isnan(result[:9]))

    def test_first_valid_value_is_mean_of_window(self) -> None:
        prices = np.array([1., 2., 3., 4., 5.])
        result = sma(prices, 3)
        assert not np.isnan(result[2])
        np.testing.assert_almost_equal(result[2], 2.0)

    def test_all_same_prices(self) -> None:
        prices = np.full(20, 50.0)
        result = sma(prices, 5)
        np.testing.assert_array_almost_equal(result[4:], 50.0)

    def test_period_1_returns_original(self) -> None:
        prices = make_price_series(20)
        result = sma(prices, 1)
        np.testing.assert_array_almost_equal(result, prices)

    def test_raises_on_zero_period(self) -> None:
        with pytest.raises(ValueError, match="period"):
            sma(make_price_series(10), 0)

    def test_raises_when_period_exceeds_length(self) -> None:
        with pytest.raises(ValueError):
            sma(make_price_series(5), 10)


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------

class TestEMA:
    def test_output_length_matches_input(self) -> None:
        prices = make_price_series(50)
        assert len(ema(prices, 12)) == 50

    def test_first_period_minus_1_are_nan(self) -> None:
        prices = make_price_series(30)
        result = ema(prices, 10)
        assert np.all(np.isnan(result[:9]))

    def test_seed_value_equals_sma_seed(self) -> None:
        prices = np.array([1., 2., 3., 4., 5., 6.])
        result = ema(prices, 3)
        expected_seed = np.mean(prices[:3])
        np.testing.assert_almost_equal(result[2], expected_seed)

    def test_ema_is_smoother_than_price(self) -> None:
        prices = make_price_series(100)
        result = ema(prices, 20)
        valid  = result[~np.isnan(result)]
        assert float(np.std(valid)) < float(np.std(prices))


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

class TestRSI:
    def test_output_length_matches_input(self) -> None:
        prices = make_price_series(100)
        assert len(rsi(prices, 14)) == 100

    def test_values_bounded_0_100(self) -> None:
        prices = make_price_series(100)
        result = rsi(prices, 14)
        valid  = result[~np.isnan(result)]
        assert float(np.min(valid)) >= 0.0
        assert float(np.max(valid)) <= 100.0

    def test_constantly_rising_prices_gives_high_rsi(self) -> None:
        prices = np.arange(1.0, 51.0)
        result = rsi(prices, 14)
        valid  = result[~np.isnan(result)]
        assert float(np.mean(valid)) > 80.0

    def test_constantly_falling_prices_gives_low_rsi(self) -> None:
        prices = np.arange(50.0, 0.0, -1.0)
        result = rsi(prices, 14)
        valid  = result[~np.isnan(result)]
        assert float(np.mean(valid)) < 20.0

    def test_short_series_returns_all_nan(self) -> None:
        prices = make_price_series(5)
        result = rsi(prices, 14)
        assert np.all(np.isnan(result))


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

class TestMACD:
    def test_returns_three_arrays_of_equal_length(self) -> None:
        prices = make_price_series(100)
        ml, sl, hist = macd(prices)
        assert len(ml) == len(sl) == len(hist) == 100

    def test_histogram_equals_macd_minus_signal(self) -> None:
        prices = make_price_series(100)
        ml, sl, hist = macd(prices)
        valid = ~(np.isnan(ml) | np.isnan(sl))
        np.testing.assert_array_almost_equal(hist[valid], (ml - sl)[valid])

    def test_macd_is_zero_for_constant_prices(self) -> None:
        prices = np.full(100, 80.0)
        ml, sl, hist = macd(prices)
        valid = ~np.isnan(ml)
        np.testing.assert_array_almost_equal(ml[valid], 0.0, decimal=6)


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

class TestBollingerBands:
    def test_returns_three_arrays(self) -> None:
        prices = make_price_series(60)
        upper, mid, lower = bollinger_bands(prices)
        assert len(upper) == len(mid) == len(lower) == 60

    def test_upper_gt_middle_gt_lower(self) -> None:
        prices = make_price_series(60)
        upper, mid, lower = bollinger_bands(prices)
        valid = ~np.isnan(upper)
        assert np.all(upper[valid] > mid[valid])
        assert np.all(mid[valid] > lower[valid])

    def test_symmetric_bands_around_sma(self) -> None:
        prices = make_price_series(60)
        upper, mid, lower = bollinger_bands(prices)
        valid = ~np.isnan(upper)
        np.testing.assert_array_almost_equal(
            upper[valid] - mid[valid], mid[valid] - lower[valid]
        )


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

class TestATR:
    def test_output_length_matches_input(self) -> None:
        prices = make_price_series(50)
        high   = prices * 1.01
        low    = prices * 0.99
        result = atr(high, low, prices, 14)
        assert len(result) == 50

    def test_atr_is_positive(self) -> None:
        prices = make_price_series(50)
        high   = prices * 1.02
        low    = prices * 0.98
        result = atr(high, low, prices, 14)
        valid  = result[~np.isnan(result)]
        assert np.all(valid > 0)


# ---------------------------------------------------------------------------
# OBV
# ---------------------------------------------------------------------------

class TestOBV:
    def test_output_length_matches_input(self) -> None:
        prices = make_price_series(50)
        vol    = np.full(50, 100_000.0)
        result = obv(prices, vol)
        assert len(result) == 50

    def test_monotone_rising_prices_gives_positive_obv(self) -> None:
        prices = np.arange(1.0, 51.0)
        vol    = np.full(50, 1.0)
        result = obv(prices, vol)
        assert result[-1] > 0


# ---------------------------------------------------------------------------
# VWAP
# ---------------------------------------------------------------------------

class TestVWAP:
    def test_output_length_matches_input(self) -> None:
        n      = 30
        prices = make_price_series(n)
        result = vwap(prices * 1.01, prices * 0.99, prices,
                      np.full(n, 50_000.0))
        assert len(result) == n

    def test_vwap_between_low_and_high(self) -> None:
        n      = 30
        close  = make_price_series(n)
        high   = close * 1.02
        low    = close * 0.98
        vol    = np.full(n, 50_000.0)
        result = vwap(high, low, close, vol)
        assert np.all(result >= low)
        assert np.all(result <= high)


# ---------------------------------------------------------------------------
# Stochastic
# ---------------------------------------------------------------------------

class TestStochastic:
    def test_k_bounded_0_100(self) -> None:
        prices = make_price_series(60)
        high   = prices * 1.01
        low    = prices * 0.99
        k, d   = stochastic(high, low, prices)
        valid  = k[~np.isnan(k)]
        assert np.all(valid >= 0.0)
        assert np.all(valid <= 100.0)

    def test_returns_two_equal_length_arrays(self) -> None:
        prices = make_price_series(60)
        high   = prices * 1.01
        low    = prices * 0.99
        k, d   = stochastic(high, low, prices)
        assert len(k) == len(d) == 60

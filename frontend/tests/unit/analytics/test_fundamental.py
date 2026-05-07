"""Unit tests for :mod:`energy_terminal.analytics.fundamental`."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from energy_terminal.analytics.fundamental import (
    annualised_roll_yield,
    contango_backwardation_ratio,
    crack_2_1_1,
    crack_3_2_1,
    heating_oil_crack,
    seasonal_index,
    spark_spread,
    supply_demand_balance,
    term_structure_slope,
    usc_per_gallon_to_usd_per_barrel,
)


class TestUnitConversion:
    def test_100_usc_per_gallon_equals_42_usd_per_barrel(self) -> None:
        result = usc_per_gallon_to_usd_per_barrel(100.0)
        np.testing.assert_almost_equal(result, 42.0)

    def test_zero_returns_zero(self) -> None:
        assert usc_per_gallon_to_usd_per_barrel(0.0) == 0.0


class TestCrack321:
    def test_known_value(self) -> None:
        # WTI=80, RBOB=240USC/gal → 100.8 $/bbl, ULSD=280USC/gal → 117.6$/bbl
        # (2×100.8 + 1×117.6 − 3×80) / 3 = (201.6+117.6-240)/3 = 79.2/3 = 26.4
        result = crack_3_2_1(wti=80.0, rbob_usc=240.0, ulsd_usc=280.0)
        np.testing.assert_almost_equal(result, 26.4, decimal=4)

    def test_positive_for_profitable_refinery(self) -> None:
        assert crack_3_2_1(80.0, 250.0, 290.0) > 0

    def test_negative_when_crude_very_expensive(self) -> None:
        assert crack_3_2_1(200.0, 100.0, 100.0) < 0


class TestCrack211:
    def test_positive_for_reasonable_margins(self) -> None:
        assert crack_2_1_1(80.0, 230.0, 270.0) > 0

    def test_symmetry_with_equal_products(self) -> None:
        # With equal RBOB and ULSD the 2-1-1 should equal the single-product crack
        result = crack_2_1_1(80.0, 240.0, 240.0)
        expected = usc_per_gallon_to_usd_per_barrel(240.0) - 80.0
        np.testing.assert_almost_equal(result, expected, decimal=4)


class TestHeatingOilCrack:
    def test_known_value(self) -> None:
        # ULSD 280 USC/gal → 117.6$/bbl; brent 80 → crack = 37.6
        result = heating_oil_crack(brent=80.0, ulsd_usc=280.0)
        np.testing.assert_almost_equal(result, 37.6, decimal=4)


class TestSparkSpread:
    def test_positive_when_power_exceeds_fuel_cost(self) -> None:
        assert spark_spread(power_price_mwh=60.0, gas_price_mmbtu=3.0) > 0

    def test_negative_when_gas_too_expensive(self) -> None:
        assert spark_spread(power_price_mwh=20.0, gas_price_mmbtu=8.0) < 0

    def test_known_value(self) -> None:
        # fuel_cost = 3.0 × 7000 / 1000 = 21.0; spread = 50 - 21 = 29.0
        result = spark_spread(power_price_mwh=50.0, gas_price_mmbtu=3.0,
                              heat_rate_btu_kwh=7_000.0)
        np.testing.assert_almost_equal(result, 29.0)


class TestTermStructure:
    def test_contango_ratio_below_1(self) -> None:
        ratio = contango_backwardation_ratio(front_price=80.0, back_price=82.0)
        assert ratio < 1.0

    def test_backwardation_ratio_above_1(self) -> None:
        ratio = contango_backwardation_ratio(front_price=85.0, back_price=80.0)
        assert ratio > 1.0

    def test_raises_on_zero_back_price(self) -> None:
        with pytest.raises(ValueError):
            contango_backwardation_ratio(85.0, 0.0)

    def test_slope_negative_for_backwardation(self) -> None:
        prices  = np.array([90.0, 88.0, 86.0, 84.0, 82.0])
        tenors  = np.array([1, 2, 3, 6, 12])
        slope   = term_structure_slope(prices, tenors)
        assert slope < 0.0

    def test_slope_positive_for_contango(self) -> None:
        prices  = np.array([80.0, 81.0, 82.0, 84.0, 87.0])
        tenors  = np.array([1, 2, 3, 6, 12])
        slope   = term_structure_slope(prices, tenors)
        assert slope > 0.0

    def test_slope_raises_on_mismatched_lengths(self) -> None:
        with pytest.raises(ValueError):
            term_structure_slope(np.array([80.0, 82.0]), np.array([1, 2, 3]))


class TestAnnualisedRollYield:
    def test_positive_roll_yield_in_contango(self) -> None:
        # next > front → rolling into deferred at higher price → positive roll cost
        result = annualised_roll_yield(front_price=80.0, next_price=82.0,
                                       days_to_expiry=30)
        assert result > 0.0

    def test_negative_roll_yield_in_backwardation(self) -> None:
        result = annualised_roll_yield(front_price=85.0, next_price=80.0,
                                       days_to_expiry=30)
        assert result < 0.0

    def test_raises_on_zero_front_price(self) -> None:
        with pytest.raises(ValueError):
            annualised_roll_yield(0.0, 82.0, 30)


class TestSeasonalIndex:
    def test_returns_12_row_dataframe(self) -> None:
        index  = pd.date_range("2020-01-01", periods=730, freq="D")
        prices = pd.Series(np.random.default_rng(1).normal(80, 2, 730), index=index)
        result = seasonal_index(prices)
        assert len(result) == 12

    def test_raises_on_non_datetime_index(self) -> None:
        prices = pd.Series([80.0, 82.0, 81.0])
        with pytest.raises(ValueError, match="DatetimeIndex"):
            seasonal_index(prices)

    def test_columns_present(self) -> None:
        index  = pd.date_range("2020-01-01", periods=365, freq="D")
        prices = pd.Series(np.ones(365) * 80, index=index)
        result = seasonal_index(prices)
        assert set(["mean", "median", "std", "min", "max", "count"]).issubset(
            result.columns)


class TestSupplyDemandBalance:
    def test_balanced_market_returns_zero(self) -> None:
        result = supply_demand_balance(
            production=10_000, net_imports=2_000,
            consumption=11_000, inventory_change=1_000,
        )
        np.testing.assert_almost_equal(result, 0.0)

    def test_surplus_returns_positive(self) -> None:
        result = supply_demand_balance(
            production=12_000, net_imports=0,
            consumption=10_000, inventory_change=0,
        )
        assert result > 0

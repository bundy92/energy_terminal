"""Unit tests for data models and the alert engine."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from energy_terminal.data.alerts import AlertEngine, AlertFired
from energy_terminal.data.models import (
    Alert,
    AlertCondition,
    EventSource,
    EventType,
    FundamentalReading,
    OHLCVBar,
    Tick,
    WeatherReading,
)
from tests.fixtures.sample_data import (
    make_alert,
    make_fundamental,
    make_tick,
    make_weather,
)


# ---------------------------------------------------------------------------
# Tick model
# ---------------------------------------------------------------------------

class TestTickModel:
    def test_valid_tick_creation(self) -> None:
        tick = make_tick()
        assert tick.symbol == "CL=F"
        assert tick.close == 85.0

    def test_high_must_be_gte_low(self) -> None:
        with pytest.raises(ValidationError):
            Tick(
                type=EventType.TICK,
                source=EventSource.YAHOO_FINANCE,
                symbol="CL=F",
                timestamp=1_000,
                open=85.0, high=80.0, low=86.0, close=85.0,
                volume=0,
            )

    def test_volume_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            Tick(
                type=EventType.TICK,
                source=EventSource.YAHOO_FINANCE,
                symbol="CL=F",
                timestamp=1_000,
                open=85.0, high=86.0, low=84.0, close=85.0,
                volume=-1,
            )

    def test_tick_is_frozen(self) -> None:
        tick = make_tick()
        with pytest.raises(Exception):
            tick.close = 99.0  # type: ignore[misc]

    def test_default_change_is_zero(self) -> None:
        tick = Tick(
            type=EventType.TICK, source=EventSource.DIRECT,
            symbol="NG=F", timestamp=1_000,
            open=3.0, high=3.1, low=2.9, close=3.0, volume=0,
        )
        assert tick.change == 0.0
        assert tick.change_pct == 0.0


# ---------------------------------------------------------------------------
# OHLCVBar model
# ---------------------------------------------------------------------------

class TestOHLCVBar:
    def test_valid_bar(self) -> None:
        bar = OHLCVBar(timestamp=1_000, open=80.0, high=82.0,
                       low=79.0, close=81.0, volume=1000)
        assert bar.close == 81.0

    def test_frozen(self) -> None:
        bar = OHLCVBar(timestamp=1_000, open=80.0, high=82.0,
                       low=79.0, close=81.0)
        with pytest.raises(Exception):
            bar.close = 99.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# WeatherReading model
# ---------------------------------------------------------------------------

class TestWeatherReading:
    def test_valid_reading(self) -> None:
        r = make_weather(temp_c=5.0)
        assert r.hdd > 0.0
        assert r.cdd == 0.0

    def test_hdd_cannot_be_negative(self) -> None:
        with pytest.raises(ValidationError):
            WeatherReading(
                type=EventType.WEATHER, source=EventSource.OPEN_METEO,
                symbol="NYC", timestamp=1_000,
                location="New York", temp_c=5.0, hdd=-1.0, cdd=0.0,
            )

    def test_hot_day_cdd_positive_hdd_zero(self) -> None:
        r = make_weather(temp_c=35.0)
        assert r.cdd > 0.0
        assert r.hdd == 0.0


# ---------------------------------------------------------------------------
# Alert model
# ---------------------------------------------------------------------------

class TestAlertModel:
    def test_valid_alert(self) -> None:
        a = make_alert()
        assert a.symbol == "CL=F"
        assert not a.triggered

    def test_alert_can_be_serialised(self) -> None:
        a    = make_alert()
        data = a.model_dump()
        assert data["alert_id"] == "test-001"


# ---------------------------------------------------------------------------
# AlertEngine
# ---------------------------------------------------------------------------

class TestAlertEngine:
    def setup_method(self) -> None:
        self.fired: list[AlertFired] = []
        self.engine = AlertEngine(on_fired=self.fired.append)

    def test_alert_fires_when_price_crosses_above(self) -> None:
        alert = make_alert(condition=AlertCondition.ABOVE, threshold=90.0)
        self.engine.add_alert(alert)
        tick = make_tick(close=91.0)
        result = self.engine.evaluate(tick)
        assert len(result) == 1
        assert len(self.fired) == 1

    def test_alert_does_not_fire_below_threshold(self) -> None:
        alert = make_alert(condition=AlertCondition.ABOVE, threshold=90.0)
        self.engine.add_alert(alert)
        tick = make_tick(close=89.0)
        assert self.engine.evaluate(tick) == []

    def test_alert_fires_when_price_crosses_below(self) -> None:
        alert = make_alert(condition=AlertCondition.BELOW, threshold=80.0)
        self.engine.add_alert(alert)
        tick = make_tick(close=75.0)
        assert len(self.engine.evaluate(tick)) == 1

    def test_alert_fires_only_once(self) -> None:
        alert = make_alert(condition=AlertCondition.ABOVE, threshold=90.0)
        self.engine.add_alert(alert)
        tick = make_tick(close=95.0)
        self.engine.evaluate(tick)
        self.engine.evaluate(tick)
        assert len(self.fired) == 1

    def test_reset_allows_re_firing(self) -> None:
        alert = make_alert(condition=AlertCondition.ABOVE, threshold=90.0)
        aid   = self.engine.add_alert(alert)
        self.engine.evaluate(make_tick(close=95.0))
        self.engine.reset_alert(aid)
        self.engine.evaluate(make_tick(close=96.0))
        assert len(self.fired) == 2

    def test_pct_change_alert(self) -> None:
        alert = make_alert(condition=AlertCondition.PCT_CHANGE, threshold=2.0)
        self.engine.add_alert(alert)
        # First tick sets baseline
        self.engine.evaluate(make_tick(close=80.0))
        # Second tick triggers (>2% change)
        self.engine.evaluate(make_tick(close=84.0))
        assert len(self.fired) == 1

    def test_remove_alert_stops_evaluation(self) -> None:
        alert = make_alert(condition=AlertCondition.ABOVE, threshold=90.0)
        aid   = self.engine.add_alert(alert)
        self.engine.remove_alert(aid)
        self.engine.evaluate(make_tick(close=95.0))
        assert len(self.fired) == 0

    def test_wrong_symbol_does_not_fire(self) -> None:
        alert = make_alert(symbol="NG=F", condition=AlertCondition.ABOVE,
                           threshold=3.0)
        self.engine.add_alert(alert)
        tick = make_tick(symbol="CL=F", close=95.0)
        assert self.engine.evaluate(tick) == []

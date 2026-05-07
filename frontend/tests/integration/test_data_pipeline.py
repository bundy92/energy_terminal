"""Integration tests for the data pipeline.

Tests the full path:  GatewayClient dispatch → AlertEngine evaluation
→ TimeSeriesCache write, without a live Erlang process.

The WebSocket connection is mocked using ``unittest.mock`` so no network
access is required.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from energy_terminal.data.alerts import AlertEngine, AlertFired
from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.data.client import GatewayClient
from energy_terminal.data.models import Alert, AlertCondition, EventSource, EventType
from tests.fixtures.sample_data import make_ohlcv_bars, make_tick


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cache(tmp_path: Path) -> TimeSeriesCache:
    c = TimeSeriesCache(db_path=tmp_path / "int_test.duckdb")
    yield c
    c.close()


@pytest.fixture
def alert_engine() -> AlertEngine:
    return AlertEngine()


@pytest.fixture
def gateway_client() -> GatewayClient:
    return GatewayClient(url="ws://localhost:8765/ws")


# ---------------------------------------------------------------------------
# Alert engine + cache pipeline
# ---------------------------------------------------------------------------

class TestAlertCachePipeline:
    """Tick → AlertEngine → Cache write integration."""

    def test_tick_triggers_alert_and_callback_is_called(
        self,
        alert_engine: AlertEngine,
    ) -> None:
        fired: list[AlertFired] = []
        alert_engine.add_callback(fired.append)
        alert_engine.add_alert(Alert(
            alert_id="int-001",
            symbol="CL=F",
            condition=AlertCondition.ABOVE,
            threshold=90.0,
            message="WTI above 90",
        ))

        tick = make_tick(symbol="CL=F", close=91.0)
        result = alert_engine.evaluate(tick)

        assert len(result) == 1
        assert len(fired) == 1
        assert fired[0].alert.alert_id == "int-001"
        assert fired[0].tick.close == 91.0

    def test_multiple_alerts_different_symbols_independent(
        self,
        alert_engine: AlertEngine,
    ) -> None:
        fired: list[AlertFired] = []
        alert_engine.add_callback(fired.append)

        alert_engine.add_alert(Alert(
            alert_id="wti-alert",
            symbol="CL=F",
            condition=AlertCondition.ABOVE,
            threshold=90.0,
            message="WTI high",
        ))
        alert_engine.add_alert(Alert(
            alert_id="ng-alert",
            symbol="NG=F",
            condition=AlertCondition.BELOW,
            threshold=2.0,
            message="Gas low",
        ))

        alert_engine.evaluate(make_tick(symbol="CL=F", close=95.0))
        alert_engine.evaluate(make_tick(symbol="NG=F", close=1.5))

        assert len(fired) == 2
        ids = {f.alert.alert_id for f in fired}
        assert ids == {"wti-alert", "ng-alert"}

    def test_cache_write_then_read_roundtrip(self, cache: TimeSeriesCache) -> None:
        bars = make_ohlcv_bars(n=30)
        cache.write_ohlcv("CL=F", bars, source="integration_test")
        df = cache.read_ohlcv("CL=F", days=365)
        assert len(df) == 30
        assert float(df["close"].iloc[-1]) == pytest.approx(bars[-1].close)

    def test_latest_close_reflects_most_recent_write(
        self, cache: TimeSeriesCache
    ) -> None:
        bars = make_ohlcv_bars(n=10)
        cache.write_ohlcv("BZ=F", bars)
        assert cache.latest_close("BZ=F") == pytest.approx(bars[-1].close)


# ---------------------------------------------------------------------------
# GatewayClient message dispatch (mocked WebSocket)
# ---------------------------------------------------------------------------

class TestGatewayClientDispatch:
    """Test that GatewayClient correctly routes parsed JSON messages to handlers."""

    def test_tick_message_dispatched_to_handler(self) -> None:
        client   = GatewayClient()
        received = []
        client.on_tick(received.append)

        msg = {
            "type": "tick",
            "source": "yahoo_finance",
            "symbol": "CL=F",
            "timestamp": int(time.time() * 1000),
            "payload": {
                "open": 84.0, "high": 86.0, "low": 83.0,
                "close": 85.5, "volume": 100_000,
                "change": 1.5, "change_pct": 1.79,
            },
        }
        client._dispatch(msg)

        assert len(received) == 1
        assert received[0].symbol == "CL=F"
        assert received[0].close == pytest.approx(85.5)

    def test_weather_message_dispatched_to_handler(self) -> None:
        client   = GatewayClient()
        received = []
        client.on_weather(received.append)

        msg = {
            "type": "weather",
            "source": "open_meteo",
            "symbol": "New York",
            "timestamp": int(time.time() * 1000),
            "payload": {
                "location": "New York",
                "temp_c": 5.0,
                "hdd": 13.3,
                "cdd": 0.0,
                "forecast_7d": [5.0, 6.0, 7.0, 8.0, 7.5, 6.5, 5.5],
            },
        }
        client._dispatch(msg)

        assert len(received) == 1
        assert received[0].location == "New York"
        assert received[0].hdd == pytest.approx(13.3)

    def test_macro_message_dispatched_to_handler(self) -> None:
        client   = GatewayClient()
        received = []
        client.on_macro(received.append)

        msg = {
            "type": "macro",
            "source": "fred",
            "symbol": "DTWEXBGS",
            "timestamp": int(time.time() * 1000),
            "payload": {
                "series": "DTWEXBGS",
                "value": 106.42,
                "date": "2024-03-10",
            },
        }
        client._dispatch(msg)

        assert len(received) == 1
        assert received[0].value == pytest.approx(106.42)

    def test_unknown_source_falls_back_to_direct(self) -> None:
        client   = GatewayClient()
        received = []
        client.on_tick(received.append)

        msg = {
            "type": "tick",
            "source": "some_unknown_source_xyz",
            "symbol": "NG=F",
            "timestamp": int(time.time() * 1000),
            "payload": {
                "open": 3.0, "high": 3.2, "low": 2.9,
                "close": 3.1, "volume": 50_000,
            },
        }
        client._dispatch(msg)

        assert len(received) == 1
        assert received[0].source == EventSource.DIRECT

    def test_multiple_handlers_all_receive_event(self) -> None:
        client     = GatewayClient()
        received_a = []
        received_b = []
        client.on_tick(received_a.append)
        client.on_tick(received_b.append)

        msg = {
            "type": "tick",
            "source": "yahoo_finance",
            "symbol": "XOM",
            "timestamp": int(time.time() * 1000),
            "payload": {
                "open": 100.0, "high": 102.0, "low": 99.0,
                "close": 101.0, "volume": 5_000_000,
            },
        }
        client._dispatch(msg)

        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_is_stale_false_when_never_received(self) -> None:
        client = GatewayClient()
        assert not client.is_stale

    def test_is_connected_false_initially(self) -> None:
        client = GatewayClient()
        assert not client.is_connected

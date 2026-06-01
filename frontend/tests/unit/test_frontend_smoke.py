import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from PyQt6.QtWidgets import QApplication
from pydantic import ValidationError

from energy_terminal.config import settings as app_settings
from energy_terminal.config.settings import Settings
from energy_terminal.data.alerts import AlertEngine, AlertFired
from energy_terminal.data.client import GatewayClient
from energy_terminal.data.direct_feed import DirectFeed, INSTRUMENT_NAMES
from energy_terminal.data.models import (
    EventSource,
    EventType,
    FundamentalReading,
    MacroReading,
    Tick,
    WeatherReading,
)
from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.ui.main_window import MainWindow
from energy_terminal.ui.panels.alert_panel import AlertPanel
from energy_terminal.ui.panels.analytics_panel import AnalyticsPanel
from energy_terminal.ui.panels.base_panel import BasePanel
from energy_terminal.ui.panels.chart_panel import ChartPanel
from energy_terminal.ui.panels.debug_panel import DebugPanel
from energy_terminal.ui.panels.fundamental_panel import FundamentalPanel
from energy_terminal.ui.panels.market_panel import MarketPanel
from energy_terminal.ui.panels.risk_panel import RiskPanel
from energy_terminal.ui.panels.weather_panel import WeatherPanel
from energy_terminal.ui.panels.watchlist_panel import WatchlistPanel
from energy_terminal.ui.theme import apply_theme
from tests.fixtures.sample_data import (
    make_fundamental,
    make_macro,
    make_ohlcv_df,
    make_price_series,
    make_tick,
    make_weather,
)


def test_settings_validation_and_config_dir(tmp_path, monkeypatch):
    import importlib

    settings_module = importlib.import_module("energy_terminal.config.settings")
    monkeypatch.setattr(settings_module, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "_CONFIG_FILE", tmp_path / "config.toml")

    config = settings_module.Settings()
    config.ensure_config_dir()

    assert (tmp_path / "config.toml").exists()
    assert config.log_level == "INFO"

    with pytest.raises(ValidationError):
        settings_module.Settings(theme="bad_theme")

    with pytest.raises(ValidationError):
        settings_module.Settings(log_level="notalevel")


def test_main_entry_creates_qt_event_loop(monkeypatch, qapp):
    import energy_terminal.main as main_module

    class DummyWindow:
        async def start_async(self):
            return None

        def show(self):
            return None

    class DummyLoop:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def create_task(self, coro):
            return None

        def run_forever(self):
            return None

    monkeypatch.setattr(main_module, "QApplication", lambda argv: qapp)
    monkeypatch.setattr(main_module, "apply_theme", lambda app: None)
    monkeypatch.setattr(main_module, "MainWindow", DummyWindow)
    monkeypatch.setattr(main_module.qasync, "QEventLoop", lambda app: DummyLoop())
    monkeypatch.setattr(main_module.asyncio, "set_event_loop", lambda loop: None)
    monkeypatch.setattr(main_module, "_async_main", lambda window: None)

    main_module.main()


def test_gateway_client_dispatches_every_event_type():
    client = GatewayClient(url="ws://example.local")

    ticks = []
    fundamentals = []
    weathers = []
    macros = []

    client.on_tick(lambda tick: ticks.append(tick))
    client.on_fundamental(lambda reading: fundamentals.append(reading))
    client.on_weather(lambda reading: weathers.append(reading))
    client.on_macro(lambda reading: macros.append(reading))

    client._dispatch({
        "type": EventType.TICK,
        "source": "direct",
        "symbol": "CL=F",
        "timestamp": 1,
        "payload": {"open": 80.0, "high": 82.0, "low": 79.0, "close": 81.0, "volume": 1000, "change": 1.0, "change_pct": 1.25},
    })
    client._dispatch({
        "type": EventType.FUNDAMENTAL,
        "source": "eia",
        "symbol": "PET.WCRSTUS1.W",
        "timestamp": 2,
        "payload": {"series": "PET.WCRSTUS1.W", "value": 430_000.0, "period": "2024-01-05", "unit": "kbbl"},
    })
    client._dispatch({
        "type": EventType.WEATHER,
        "source": "open_meteo",
        "symbol": "New York",
        "timestamp": 3,
        "payload": {"location": "New York", "temp_c": 4.0, "hdd": 14.3, "cdd": 0.0, "forecast_7d": [4.0, 5.0]},
    })
    client._dispatch({
        "type": EventType.MACRO,
        "source": "fred",
        "symbol": "DTWEXBGS",
        "timestamp": 4,
        "payload": {"series": "DTWEXBGS", "value": 106.4, "date": "2024-03-10"},
    })

    assert len(ticks) == 1
    assert len(fundamentals) == 1
    assert len(weathers) == 1
    assert len(macros) == 1
    assert ticks[0].symbol == "CL=F"
    assert fundamentals[0].series == "PET.WCRSTUS1.W"
    assert weathers[0].location == "New York"
    assert macros[0].series == "DTWEXBGS"

    client._last_event_ts = time.time() - 1000
    assert client.is_stale


def test_direct_feed_fetches_quote_and_history(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol: str):
            self.symbol = symbol
            self.fast_info = {
                "lastPrice": 100.0,
                "previousClose": 99.0,
                "open": 98.0,
                "dayHigh": 101.0,
                "dayLow": 97.0,
                "lastVolume": 1234,
            }

        def history(self, period: str, interval: str, auto_adjust: bool):
            return pd.DataFrame(
                {
                    "Open": [95.0, 96.0],
                    "High": [101.0, 102.0],
                    "Low": [94.0, 95.0],
                    "Close": [100.0, 101.0],
                    "Volume": [1000, 2000],
                },
                index=pd.date_range("2025-01-01", periods=2, freq="D"),
            )

    monkeypatch.setattr("energy_terminal.data.direct_feed.yf.Ticker", FakeTicker)

    feed = DirectFeed(instruments=["CL=F"])
    tick = asyncio.run(feed.fetch_quote("CL=F"))

    assert tick is not None
    assert tick.symbol == "CL=F"
    assert tick.close == pytest.approx(100.0)
    assert DirectFeed.display_name("CL=F") == INSTRUMENT_NAMES["CL=F"]
    assert DirectFeed.display_name("UNKNOWN") == "UNKNOWN"

    bars = asyncio.run(feed.fetch_ohlcv("CL=F", period="1d", interval="1d"))
    assert len(bars) == 2
    assert bars[0].close == pytest.approx(100.0)


def test_ui_panels_and_main_window(qtbot, tmp_path, monkeypatch):
    cache_path = tmp_path / "cache.duckdb"
    cache = TimeSeriesCache(db_path=cache_path)
    alerts = AlertEngine()

    market_selected = []
    watch_selected = []

    market = MarketPanel(cache, on_symbol_selected=lambda sym: market_selected.append(sym))
    watch = WatchlistPanel(cache, alerts, on_symbol_selected=lambda sym: watch_selected.append(sym))
    debug = DebugPanel()
    base_panel = BasePanel(title="Test", subtitle="SUB")
    fundamental = FundamentalPanel(cache)
    weather = WeatherPanel(cache)
    risk = RiskPanel(cache)
    analytics = AnalyticsPanel(cache)
    alert_panel = AlertPanel(alerts)

    qtbot.addWidget(market)
    qtbot.addWidget(watch)
    qtbot.addWidget(debug)
    qtbot.addWidget(base_panel)
    qtbot.addWidget(fundamental)
    qtbot.addWidget(weather)
    qtbot.addWidget(risk)
    qtbot.addWidget(analytics)
    qtbot.addWidget(alert_panel)

    # Base panel state transitions
    base_panel.set_active(True)
    base_panel.set_active(False)
    base_panel.set_subtitle("NEW")
    base_panel.set_stale(True)
    assert base_panel._subtitle_label.text() == "NEW"
    assert base_panel._stale is True
    assert not base_panel._stale_label.isHidden()

    # Market and watchlist behavior
    tick = make_tick(symbol="CL=F", close=88.0, change_pct=1.2)
    market.on_tick(tick)
    watch.on_tick(tick)
    assert market._table.item(0, 2).text() in {"88.0000", "—"}
    watch._handle_symbol_click(0, 0)
    assert watch_selected == [watch._table.item(0, 0).text()]

    # Debug panel logging
    debug.append_log("ui", "hello world", level="info")
    assert "hello world" in debug._log_view.toPlainText()

    # Fundamental and weather panels
    fundamental.on_reading(make_fundamental())
    weather.on_reading(make_weather())

    # Analytics panel updates and macro handler
    analytics.on_tick(make_tick(symbol="CL=F", close=90.0, change_pct=0.5))
    analytics.on_macro(make_macro())

    # Alert panel add and fired flow
    alert_panel._sym_input.setText("CL=F")
    alert_panel._msg_input.setText("Test alert")
    alert_panel._thresh_spin.setValue(1.0)
    alert_panel._add_alert()  # no error when adding a new alert
    event = AlertFired(alert=alerts.list_alerts()[0], tick=make_tick(symbol="CL=F", close=90.0), fired_at_ms=123)
    alert_panel.on_alert_fired(event)

    # Chart panel and main window
    monkeypatch.setattr("energy_terminal.ui.panels.chart_panel.QTimer.singleShot", lambda *args, **kwargs: None)
    monkeypatch.setattr("energy_terminal.ui.panels.chart_panel.DirectFeed.fetch_ohlcv", AsyncMock(return_value=[]))
    chart = ChartPanel(cache)
    qtbot.addWidget(chart)
    chart._set_timeframe("1W")
    chart._toggle_overlay("_show_sma20", True)
    chart._toggle_log_scale(True)
    chart.on_tick(make_tick(symbol="CL=F", close=92.0))

    monkeypatch.setattr("energy_terminal.ui.main_window.ChartPanel.load_symbol", lambda self, sym: setattr(self, "_symbol", sym))
    window = MainWindow()
    qtbot.addWidget(window)
    window._swap_panel("debug")
    window._swap_panel("market")
    window._swap_panel("analytics")
    window._cmd.setText("CL1")
    window._handle_command()
    assert window._panel_chart._symbol == "CL=F"
    window._on_symbol_selected("XOM")
    assert window._panel_chart._symbol == "XOM"

    cache.close()


def test_apply_theme_on_qt_application(qapp):
    apply_theme(qapp)
    assert qapp.styleSheet() != ""

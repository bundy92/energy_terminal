import asyncio
import numpy as np
import pandas as pd
import pytest
from unittest.mock import AsyncMock

from energy_terminal.analytics import fundamental as fmod
from energy_terminal.analytics import risk as rmod
from energy_terminal.analytics import technical as tmod
from energy_terminal.data.alerts import AlertEngine, AlertFired
from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.data.client import GatewayClient
from energy_terminal.data.direct_feed import DirectFeed
from energy_terminal.data.models import Alert, AlertCondition, FundamentalReading, MacroReading, Tick
from energy_terminal.ui.panels.alert_panel import AlertPanel
from energy_terminal.ui.panels.chart_panel import ChartPanel
from energy_terminal.ui.panels.market_panel import MarketPanel
from energy_terminal.ui.panels.watchlist_panel import WatchlistPanel


def test_analytics_fundamental_math():
    assert fmod.usc_per_gallon_to_usd_per_barrel(100.0) == pytest.approx(42.0)
    assert fmod.crack_3_2_1(80.0, 240.0, 280.0) == pytest.approx((2 * 100.8 + 1 * 117.6 - 240.0) / 3.0)
    assert fmod.crack_2_1_1(85.0, 220.0, 260.0) == pytest.approx((92.4 + 109.2 - 170.0) / 2.0)
    assert fmod.heating_oil_crack(90.0, 300.0) == pytest.approx(126.0 - 90.0)
    assert fmod.spark_spread(50.0, 3.0, heat_rate_btu_kwh=7_000.0) == pytest.approx(50.0 - 21.0)

    with pytest.raises(ValueError):
        fmod.contango_backwardation_ratio(1.0, 0.0)

    with pytest.raises(ValueError):
        fmod.term_structure_slope(np.array([1.0]), np.array([1.0]))

    with pytest.raises(ValueError):
        fmod.annualised_roll_yield(0.0, 101.0, 30)

    slope = fmod.term_structure_slope(np.array([100.0, 102.0]), np.array([1.0, 2.0]))
    assert slope == pytest.approx(2.0)
    assert fmod.annualised_roll_yield(100.0, 102.0, 30) == pytest.approx((2.0 / 100.0) * (365.0 / 30.0))


def test_analytics_risk_metrics():
    prices = np.array([100.0, 102.0, 101.0, 103.0])
    returns = rmod.log_returns(prices)
    assert returns.shape == (3,)
    assert returns[0] == pytest.approx(np.log(102.0 / 100.0))

    with pytest.raises(ValueError):
        rmod.log_returns(np.array([100.0, 0.0, 101.0]))

    pct = rmod.pct_returns(prices)
    assert pct[0] == pytest.approx(0.02)

    var = rmod.historical_var(np.array([-0.01, -0.02, 0.01]), confidence=0.95)
    assert var >= 0

    with pytest.raises(ValueError):
        rmod.historical_var(np.array([0.01]), confidence=1.0)

    param_var = rmod.parametric_var(np.array([0.01, -0.01, 0.02]), confidence=0.99)
    assert param_var >= 0

    with pytest.raises(ValueError):
        rmod.parametric_var(np.array([0.01]), confidence=-0.1)

    assert rmod.historical_cvar(np.array([-0.01, -0.02, 0.01]), confidence=0.90) >= 0
    assert isinstance(rmod.historical_cvar(np.array([0.01, 0.02, 0.03]), confidence=0.90), float)

    df = pd.DataFrame({"A": [1.0, 2.0, 3.0], "B": [2.0, 3.0, 4.0]})
    with pytest.raises(ValueError):
        rmod.rolling_correlation_matrix(df, window=5)

    corr = rmod.rolling_correlation_matrix(df, window=2)
    assert list(corr.columns) == ["A", "B"]

    cone = rmod.volatility_cone(np.array([0.01, -0.02, 0.03, -0.01, 0.02]), windows=(2, 3))
    assert 2 in cone and 3 in cone

    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    portfolio = rmod.portfolio_var(np.array([0.5, 0.5]), cov, confidence=0.95)
    assert portfolio >= 0
    with pytest.raises(ValueError):
        rmod.portfolio_var(np.array([0.5, 0.5]), cov, confidence=1.0)


def test_technical_indicators():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert np.isnan(tmod.sma(x, 2)[0])
    with pytest.raises(ValueError):
        tmod.sma(x, 0)

    assert np.isnan(tmod.ema(x, 10)[0])
    assert not np.isnan(tmod.ema(x, 1)[0])
    with pytest.raises(ValueError):
        tmod.ema(x, 0)

    assert np.all(np.isnan(tmod.rsi(np.array([1.0, 2.0, 3.0]), period=5)))
    rsi_out = tmod.rsi(np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0]), period=14)
    assert rsi_out.shape == (15,)

    macd_line, signal_line, hist = tmod.macd(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert macd_line.shape == signal_line.shape == hist.shape

    upper, mid, lower = tmod.bollinger_bands(np.arange(1.0, 21.0), period=5)
    assert upper.shape == mid.shape == lower.shape

    high = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    low = np.array([0.5, 1.5, 2.5, 3.5, 4.5])
    close = np.array([0.9, 1.8, 2.7, 3.6, 4.5])
    vol = np.array([100, 200, 150, 175, 125])
    assert np.isnan(tmod.atr(high, low, close, period=10)).all()
    assert tmod.obv(close, vol).shape == close.shape
    assert np.allclose(tmod.vwap(high, low, close, vol), (high + low + close) / 3.0)
    k, d = tmod.stochastic(high, low, close, k_period=3, d_period=2)
    assert k.shape == d.shape == close.shape


def test_time_series_cache_and_audit(tmp_path):
    db_path = tmp_path / "cache.duckdb"
    with TimeSeriesCache(db_path=db_path) as cache:
        assert cache.write_ohlcv("CL=F", []) == 0

        class Bar:
            def __init__(self, timestamp, open_, high, low, close, volume):
                self.timestamp = timestamp
                self.open = open_
                self.high = high
                self.low = low
                self.close = close
                self.volume = volume

        bars = [Bar(1_000, 10.0, 12.0, 9.0, 11.0, 100), Bar(2_000, 11.0, 13.0, 10.0, 12.0, 150)]
        assert cache.write_ohlcv("CL=F", bars) == 2
        df = cache.read_ohlcv("CL=F", days=365)
        assert len(df) == 2
        assert cache.latest_close("CL=F") == 12.0

        cache.write_fundamental(
            type("R", (), {
                "series": "TEST", "period": "2024-01", "value": 1.23, "unit": "usd", "source": type("S", (), {"value": "eia"})
            })()
        )
        fund = cache.read_fundamental("TEST", periods=1)
        assert fund.iloc[0]["series"] == "TEST"

        cache.write_weather(
            type("W", (), {
                "location": "NYC", "temp_c": 5.0, "hdd": 10.0, "cdd": 0.0, "forecast_7d": [5.0],
            })()
        )

        audit = cache._conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        assert audit >= 1

    assert db_path.exists()


def test_alert_engine_fire_and_reset():
    engine = AlertEngine()
    alert = Alert(alert_id="a1", symbol="CL=F", condition=AlertCondition.ABOVE, threshold=100.0, message="Above 100")
    aid = engine.add_alert(alert)
    assert aid != ""

    events = engine.evaluate(Tick(source="direct", symbol="CL=F", timestamp=1, open=99, high=101, low=99, close=101, volume=100, change=2, change_pct=2.0))
    assert len(events) == 1
    assert engine.list_alerts()[0].triggered

    engine.reset_alert(aid)
    assert engine.list_alerts()[0].triggered is False

    events = engine.evaluate(Tick(source="direct", symbol="CL=F", timestamp=2, open=101, high=102, low=100, close=102, volume=100, change=1, change_pct=1.0))
    assert len(events) == 1


def test_ui_panel_behaviors(qtbot, tmp_path, monkeypatch):
    cache = TimeSeriesCache(db_path=tmp_path / "cache.duckdb")
    market_responses = []
    market = MarketPanel(cache, on_symbol_selected=lambda sym: market_responses.append(sym))
    qtbot.addWidget(market)
    tick = Tick(source="direct", symbol="CL=F", timestamp=1, open=80, high=82, low=79, close=81, volume=100, change=1, change_pct=1.23)
    market.on_tick(tick)
    market._handle_symbol_click(0, 0)
    assert market_responses == ["CL=F"]

    watch = WatchlistPanel(cache, AlertEngine(), on_symbol_selected=lambda sym: market_responses.append(sym))
    qtbot.addWidget(watch)
    watch._add_input.setText("TEST")

    class DummyLoop:
        def create_task(self, coro):
            if hasattr(coro, "close"):
                coro.close()
            return None

    async def no_fetch(self, symbol):
        return None

    monkeypatch.setattr("energy_terminal.ui.panels.watchlist_panel.WatchlistPanel._fetch_initial_price", no_fetch)
    monkeypatch.setattr("energy_terminal.ui.panels.watchlist_panel.asyncio.get_running_loop", lambda: DummyLoop())
    watch._add_ticker()
    assert watch._table.rowCount() == len(watch._watchlist)

    alert_engine = AlertEngine()
    alert_panel = AlertPanel(alert_engine)
    qtbot.addWidget(alert_panel)
    alert_panel._sym_input.setText("CL=F")
    alert_panel._msg_input.setText("Alert")
    alert_panel._thresh_spin.setValue(99.0)
    alert_panel._add_alert()
    assert alert_panel._active_table.rowCount() == 1
    event = AlertFired(alert=alert_engine.list_alerts()[0], tick=tick, fired_at_ms=123)
    alert_panel.on_alert_fired(event)
    assert alert_panel._fired_table.rowCount() == 1

    monkeypatch.setattr("energy_terminal.ui.panels.chart_panel.QTimer.singleShot", lambda *args, **kwargs: None)
    chart = ChartPanel(cache)
    qtbot.addWidget(chart)
    chart._show_sma20 = True
    chart._refresh_chart()
    chart._set_timeframe("1W")
    chart._toggle_overlay("_show_ema12", True)
    cache.close()


def test_main_window_dispatch_and_switching(qtbot, tmp_path, monkeypatch):
    from energy_terminal.ui.main_window import MainWindow
    from energy_terminal.data.models import Tick, FundamentalReading, MacroReading

    monkeypatch.setattr("energy_terminal.config.settings.cache_db_path", tmp_path / "cache.duckdb")
    monkeypatch.setattr("energy_terminal.ui.main_window.ChartPanel.load_symbol", lambda self, sym: setattr(self, "_symbol", sym))

    window = MainWindow()
    qtbot.addWidget(window)
    window._tick_clock()
    assert "UTC" in window._clock_label.text()

    tick = Tick(source="direct", symbol="CL=F", timestamp=123, open=80.0, high=82.0, low=79.0, close=81.0, volume=100, change=1.0, change_pct=1.2)
    window._on_tick(tick)
    assert "FEED: EVENTSOURCE.DIRECT" in window._status_feed.text()

    fundamental = FundamentalReading(source=tick.source, symbol="CL=F", timestamp=123, series="TEST", value=1.23, period="2024-01", unit="usd")
    window._on_fundamental(fundamental)
    weather = type("W", (), {"source": tick.source, "symbol": "NYC", "timestamp": 123, "location": "NYC", "temp_c": 5.0, "hdd": 10.0, "cdd": 0.0, "forecast_7d": []})()
    window._on_weather(weather)
    macro = MacroReading(source=tick.source, symbol="ECON", timestamp=123, series="MACRO", value=100.0, date="2024-01-01")
    window._on_macro(macro)

    event = AlertFired(alert=Alert(alert_id="a1", symbol="CL=F", condition=AlertCondition.ABOVE, threshold=80.0, message="Test"), tick=tick, fired_at_ms=123)
    window._on_alert_fired(event)
    window._refresh_feeds()

    for name in ["market", "chart", "watchlist", "analytics", "fundamental", "weather", "risk", "alerts", "debug"]:
        window._swap_panel(name)
    assert window._panel_chart._symbol == "CL=F"


def test_direct_feed_bulk_quotes_and_history(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol
            self.fast_info = {
                "lastPrice": 100.0,
                "previousClose": 98.0,
                "open": 99.0,
                "dayHigh": 101.0,
                "dayLow": 97.0,
                "lastVolume": 1234,
            }

        def history(self, period, interval, auto_adjust):
            return pd.DataFrame(
                {
                    "Open": [95.0],
                    "High": [101.0],
                    "Low": [94.0],
                    "Close": [100.0],
                    "Volume": [1000],
                },
                index=pd.to_datetime(["2025-01-01"]),
            )

    monkeypatch.setattr("energy_terminal.data.direct_feed.yf.Ticker", FakeTicker)
    monkeypatch.setattr("energy_terminal.data.direct_feed.yf.download", lambda **kwargs: pd.DataFrame())

    feed = DirectFeed(instruments=["CL=F"])
    ticks = feed._fetch_quotes()
    assert len(ticks) == 1
    assert ticks[0].close == pytest.approx(100.0)

    bars = asyncio.run(feed.fetch_ohlcv("CL=F", period="1d", interval="1d"))
    assert len(bars) == 1

    monkeypatch.setattr("energy_terminal.data.direct_feed.yf.Ticker", type("T", (), {"history": staticmethod(lambda period, interval, auto_adjust: (_ for _ in ()).throw(Exception('boom')))}))
    assert asyncio.run(feed.fetch_ohlcv("CL=F")) == []


def test_alert_engine_pct_and_spread_branches():
    engine = AlertEngine()
    a1 = Alert(alert_id="p1", symbol="CL=F", condition=AlertCondition.PCT_CHANGE, threshold=1.0, message="Pct")
    a2 = Alert(alert_id="s1", symbol="CL=F", condition=AlertCondition.SPREAD_WIDE, threshold=100.5, message="Spread")
    engine.add_alert(a1)
    engine.add_alert(a2)

    baseline = Tick(source="direct", symbol="CL=F", timestamp=1, open=100, high=100, low=100, close=100, volume=100, change=0, change_pct=0.0)
    engine.evaluate(baseline)

    tick = Tick(source="direct", symbol="CL=F", timestamp=2, open=100, high=110, low=90, close=101, volume=100, change=1, change_pct=1.0)
    events = engine.evaluate(tick)
    assert len(events) == 2

    def failing_cb(event):
        raise RuntimeError("boom")

    engine.add_callback(failing_cb)
    engine.reset_alert("p1")
    engine.reset_alert("s1")
    tick2 = Tick(source="direct", symbol="CL=F", timestamp=3, open=101, high=103, low=100, close=103, volume=100, change=2, change_pct=1.980198)
    events = engine.evaluate(tick2)
    assert len(events) == 2


def test_gateway_client_send_and_stop(monkeypatch):
    client = GatewayClient(url="ws://localhost")
    mock_ws = AsyncMock()
    client._ws = mock_ws
    client._connected = True
    asyncio.run(client.send_command({"cmd": "ping"}))
    mock_ws.send.assert_awaited_once()

    asyncio.run(client.stop())
    assert client._running is False

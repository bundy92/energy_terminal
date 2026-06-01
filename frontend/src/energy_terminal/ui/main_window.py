"""Main application window.

Implements the Bloomberg Terminal layout paradigm:

- Full-screen dark canvas divided into a resizable 2×2 panel grid
- Amber command bar at the top (ticker + ``<GO>`` navigation)
- Function key panel switching (F1–F8)
- Persistent status bar showing connection state, data provenance, clock

Keybindings
-----------
+----------+-------------------------------+
| Key      | Action                        |
+==========+===============================+
| F1       | Market Overview panel         |
| F2       | Chart panel                   |
| F3       | Watchlist panel               |
| F4       | Analytics panel               |
| F5       | Fundamental / EIA panel       |
| F6       | Weather / HDD-CDD panel       |
| F7       | Risk panel                    |
| F8       | Alerts panel                  |
| F9       | Debug / log panel             |
| Ctrl+Q   | Quit                          |
| Ctrl+E   | Export current panel data     |
| Ctrl+R   | Refresh all feeds             |
+----------+-------------------------------+
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from energy_terminal.data.alerts import AlertEngine, AlertFired
from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.data.client import GatewayClient
from energy_terminal.data.direct_feed import DirectFeed
from energy_terminal.data.models import FundamentalReading, MacroReading, Tick, WeatherReading
from energy_terminal.ui.panels.alert_panel import AlertPanel
from energy_terminal.ui.panels.analytics_panel import AnalyticsPanel
from energy_terminal.ui.panels.base_panel import BasePanel
from energy_terminal.ui.panels.chart_panel import ChartPanel
from energy_terminal.ui.panels.debug_panel import DebugPanel
from energy_terminal.ui.panels.fundamental_panel import FundamentalPanel
from energy_terminal.ui.panels.market_panel import MarketPanel
from energy_terminal.ui.panels.news_panel import NewsPanel
from energy_terminal.ui.panels.risk_panel import RiskPanel
from energy_terminal.ui.panels.watchlist_panel import WatchlistPanel
from energy_terminal.ui.panels.weather_panel import WeatherPanel
from energy_terminal.ui.theme import PALETTE

log = structlog.get_logger(__name__)


class MainWindow(QMainWindow):  # type: ignore[misc]
    """Top-level Bloomberg-style terminal window.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget (None for top-level window).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Core subsystems
        self._cache = TimeSeriesCache()
        self._alerts = AlertEngine()
        self._client = GatewayClient()
        self._fallback = DirectFeed()

        # Wire tick handlers
        self._client.on_tick(self._on_tick)
        self._client.on_fundamental(self._on_fundamental)
        self._client.on_weather(self._on_weather)
        self._client.on_macro(self._on_macro)
        self._alerts.add_callback(self._on_alert_fired)

        self._build_ui()
        self._bind_shortcuts()
        self._start_clock()

        self.setWindowTitle("ENERGY TERMINAL  |  0.1.0")
        self.resize(1600, 900)
        self.setMinimumSize(1200, 700)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct the full window layout."""
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar: command bar
        layout.addWidget(self._build_command_bar())

        # Panel grid (2×2 resizable splitter)
        layout.addWidget(self._build_panel_grid(), stretch=1)

        # Status bar
        self._build_status_bar()

    def _build_command_bar(self) -> QWidget:
        """Build the amber Bloomberg-style command input bar."""
        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setStyleSheet(
            f"background-color: {PALETTE.BG_HEADER}; " f"border-bottom: 1px solid {PALETTE.AMBER};"
        )

        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 0, 8, 0)
        h.setSpacing(8)

        # Logo / brand
        logo = QLabel("⬡ ENERGY TERMINAL")
        logo.setStyleSheet(
            f"color: {PALETTE.AMBER}; font-weight: bold; " f"font-size: 13px; letter-spacing: 2px;"
        )
        h.addWidget(logo)

        h.addSpacing(20)

        # Command input
        self._cmd = QLineEdit()
        self._cmd.setObjectName("command_bar")
        self._cmd.setPlaceholderText("Enter ticker or command  <GO>")
        self._cmd.setFixedWidth(340)
        self._cmd.returnPressed.connect(self._handle_command)
        h.addWidget(self._cmd)

        h.addStretch()

        # Connection indicator
        self._conn_label = QLabel("● DISCONNECTED")
        self._conn_label.setStyleSheet(
            f"color: {PALETTE.NEGATIVE}; " f"font-size: 11px; font-weight: bold;"
        )
        h.addWidget(self._conn_label)

        h.addSpacing(16)

        # Clock
        self._clock_label = QLabel("")
        self._clock_label.setStyleSheet(f"color: {PALETTE.FG_SECONDARY}; " f"font-size: 11px;")
        h.addWidget(self._clock_label)

        return bar

    def _build_panel_grid(self) -> QSplitter:
        """Build the resizable 2×2 panel grid.

        Returns
        -------
        QSplitter
            Outer vertical splitter containing two horizontal splitters.
        """
        # Instantiate all panels
        self._panel_market = MarketPanel(self._cache, on_symbol_selected=self._on_symbol_selected)
        self._panel_chart = ChartPanel(self._cache)
        self._panel_watchlist = WatchlistPanel(self._cache, self._alerts, on_symbol_selected=self._on_symbol_selected)
        self._panel_analytics = AnalyticsPanel(self._cache)
        self._panel_fundamental = FundamentalPanel(self._cache)
        self._panel_weather = WeatherPanel(self._cache)
        self._panel_news = NewsPanel(self._cache)
        self._panel_risk = RiskPanel(self._cache)
        self._panel_alerts = AlertPanel(self._alerts)
        self._panel_debug = DebugPanel()

        # Default layout: market | chart (top row), watchlist | active panel stack (bottom)
        top = QSplitter(Qt.Orientation.Horizontal)
        top.addWidget(self._panel_market)
        top.addWidget(self._panel_chart)
        top.setSizes([600, 1000])

        self._panel_stack = QStackedWidget()
        for panel in (
            self._panel_analytics,
            self._panel_fundamental,
            self._panel_weather,
            self._panel_news,
            self._panel_risk,
            self._panel_alerts,
            self._panel_debug,
        ):
            self._panel_stack.addWidget(panel)

        bot = QSplitter(Qt.Orientation.Horizontal)
        bot.addWidget(self._panel_watchlist)
        bot.addWidget(self._panel_stack)
        bot.setSizes([600, 1000])

        outer = QSplitter(Qt.Orientation.Vertical)
        outer.addWidget(top)
        outer.addWidget(bot)
        outer.setSizes([450, 450])

        return outer

    def _build_status_bar(self) -> None:
        """Configure the bottom status bar."""
        sb = self.statusBar()
        assert sb is not None

        self._status_feed = QLabel("FEED: —")
        self._status_delay = QLabel("DELAY: —")
        self._status_cache = QLabel("CACHE: —")
        self._status_tz = QLabel("UTC")

        for lbl in (self._status_feed, self._status_delay, self._status_cache, self._status_tz):
            lbl.setStyleSheet(f"color: {PALETTE.FG_SECONDARY}; font-size: 10px;")
            sb.addPermanentWidget(lbl)

        sb.showMessage("Ready — press F1–F10 or Ctrl+N to switch panels, enter ticker + ENTER to navigate")

    # ------------------------------------------------------------------
    # Shortcuts
    # ------------------------------------------------------------------

    def _bind_shortcuts(self) -> None:
        """Bind function keys and Ctrl shortcuts."""
        panel_map = {
            Qt.Key.Key_F1: lambda: self._swap_panel("market"),
            Qt.Key.Key_F2: lambda: self._swap_panel("chart"),
            Qt.Key.Key_F3: lambda: self._swap_panel("watchlist"),
            Qt.Key.Key_F4: lambda: self._swap_panel("analytics"),
            Qt.Key.Key_F5: lambda: self._swap_panel("fundamental"),
            Qt.Key.Key_F6: lambda: self._swap_panel("weather"),
            Qt.Key.Key_F7: lambda: self._swap_panel("news"),
            Qt.Key.Key_F8: lambda: self._swap_panel("risk"),
            Qt.Key.Key_F9: lambda: self._swap_panel("alerts"),
            Qt.Key.Key_F10: lambda: self._swap_panel("debug"),
        }
        for key, fn in panel_map.items():
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(fn)

        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.close)
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(lambda: self._swap_panel("news"))
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self._refresh_feeds)

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------

    def _start_clock(self) -> None:
        """Start a 1-second timer to update the clock label."""
        timer = QTimer(self)
        timer.timeout.connect(self._tick_clock)
        timer.start(1000)
        self._tick_clock()

    def _tick_clock(self) -> None:
        """Update the clock display."""
        now = datetime.now(UTC)
        self._clock_label.setText(now.strftime("%Y-%m-%d  %H:%M:%S UTC"))

    # ------------------------------------------------------------------
    # Async startup
    # ------------------------------------------------------------------

    async def start_async(self) -> None:
        """Launch async subsystems (WebSocket client, fallback poller)."""
        self._fallback.on_tick(self._on_tick)
        asyncio.create_task(self._run_gateway())

    async def _run_gateway(self) -> None:
        """Connect to the Erlang gateway with fallback to direct feed."""
        asyncio.create_task(self._client.connect())
        fallback_task = None

        async def start_fallback() -> None:
            nonlocal fallback_task
            if fallback_task is None:
                self._set_connected(False)
                log.warning("Gateway unavailable — switching to direct feed")
                self._debug("gateway", "Gateway unavailable — starting direct feed fallback")
                fallback_task = asyncio.create_task(self._fallback.start_polling())

        async def stop_fallback() -> None:
            nonlocal fallback_task
            if fallback_task is not None:
                await self._fallback.stop()
                fallback_task = None

        # Wait briefly for an initial gateway connection. If it does not
        # connect quickly, start the direct fallback so the UI shows data.
        for _ in range(8):
            if self._client.is_connected:
                self._set_connected(True)
                await stop_fallback()
                break
            await asyncio.sleep(1.0)
        else:
            await start_fallback()

        # Wait for the first tick or fallback if the gateway remains silent.
        for _ in range(10):
            if self._client.is_connected and getattr(self._client, "_last_event_ts", 0) > 0:
                break
            await asyncio.sleep(1.0)
        if self._client.is_connected and getattr(self._client, "_last_event_ts", 0) == 0:
            await start_fallback()

        # Monitor gateway reconnects/stale state and keep fallback in sync.
        try:
            while True:
                await asyncio.sleep(2.0)
                if self._client.is_connected and not self._client.is_stale:
                    await stop_fallback()
                    self._set_connected(True)
                else:
                    await start_fallback()
        finally:
            await stop_fallback()

    # ------------------------------------------------------------------
    # Data event handlers
    # ------------------------------------------------------------------

    def _on_tick(self, tick: Tick) -> None:
        """Dispatch a price tick to all panels."""
        self._panel_market.on_tick(tick)
        self._panel_watchlist.on_tick(tick)
        self._panel_chart.on_tick(tick)
        self._alerts.evaluate(tick)
        self._update_status_feed(tick)

    def _on_fundamental(self, reading: FundamentalReading) -> None:
        """Dispatch a fundamental reading to relevant panels."""
        self._panel_fundamental.on_reading(reading)
        self._panel_analytics.on_fundamental(reading)

    def _on_weather(self, reading: WeatherReading) -> None:
        """Dispatch a weather reading to the weather panel."""
        self._panel_weather.on_reading(reading)

    def _on_macro(self, reading: MacroReading) -> None:
        """Dispatch a macro reading."""
        self._panel_analytics.on_macro(reading)

    def _on_alert_fired(self, event: AlertFired) -> None:
        """Handle a fired alert — flash status bar and update alert panel."""
        self._panel_alerts.on_alert_fired(event)
        self._debug("alert", f"{event.alert}")
        sb = self.statusBar()
        assert sb is not None
        sb.showMessage(
            f"⚠  ALERT: {event.alert}",
            8000,
        )

    # ------------------------------------------------------------------

    # Command bar
    # ------------------------------------------------------------------

    def _handle_command(self) -> None:
        """Parse command bar input and navigate or apply commands."""
        raw = self._cmd.text().strip().upper()
        self._cmd.clear()
        if not raw:
            return

        if raw == "NEWS":
            self._swap_panel("news")
            sb = self.statusBar()
            assert sb is not None
            sb.showMessage("Panel: NEWS", 3000)
            log.info("Command bar navigation", input=raw, resolved="NEWS")
            self._debug("command", "Loaded news panel")
            return

        # Simple ticker navigation: "CL1 <GO>" → load CL=F chart
        ticker_map = {
            "CL1": "CL=F",
            "CO1": "BZ=F",
            "NG1": "NG=F",
            "RB1": "RB=F",
            "HO1": "HO=F",
            "JKM1": "JKM=F",
            "TTF1": "TTF=F",
            "NBP1": "NBP=F",
            "JKM": "JKM=F",
            "TTF": "TTF=F",
            "NBP": "NBP=F",
        }
        symbol = ticker_map.get(raw, raw)
        self._panel_chart.load_symbol(symbol)
        sb = self.statusBar()
        assert sb is not None
        sb.showMessage(f"Loaded: {symbol}", 3000)
        log.info("Command bar navigation", input=raw, resolved=symbol)
        self._debug("command", f"Loaded chart for {symbol}")

    def _on_symbol_selected(self, symbol: str) -> None:
        """Load the chart for a selected symbol from market or watchlist."""
        self._panel_chart.load_symbol(symbol)
        self._swap_panel("chart")
        sb = self.statusBar()
        assert sb is not None
        sb.showMessage(f"Loaded: {symbol}", 3000)
        self._debug("selection", f"Loaded chart for {symbol}")

    def _debug(self, source: str, message: str, level: str = "INFO") -> None:
        if hasattr(self, "_panel_debug"):
            self._panel_debug.append_log(source, message, level)

    # ------------------------------------------------------------------
    # Panel switching
    # ------------------------------------------------------------------

    def _swap_panel(self, panel_name: str) -> None:
        """Switch the active panel, using the stacked bottom-right pane for extra views."""
        # Always mark all panels inactive first
        for panel in (
            self._panel_market,
            self._panel_chart,
            self._panel_watchlist,
            self._panel_analytics,
            self._panel_fundamental,
            self._panel_weather,
            self._panel_news,
            self._panel_risk,
            self._panel_alerts,
            self._panel_debug,
        ):
            panel.set_active(False)

        if panel_name == "market":
            self._panel_market.set_active(True)
            self._panel_market.raise_()
        elif panel_name == "chart":
            self._panel_chart.set_active(True)
            self._panel_chart.raise_()
        elif panel_name == "watchlist":
            self._panel_watchlist.set_active(True)
            self._panel_watchlist.raise_()
        elif panel_name == "debug":
            self._panel_debug.set_active(True)
            self._panel_stack.setCurrentIndex(5)
            sb = self.statusBar()
            assert sb is not None
            sb.showMessage("Panel: DEBUG", 2000)
        else:
            stack_index = {
                "analytics": 0,
                "fundamental": 1,
                "weather": 2,
                "news": 3,
                "risk": 4,
                "alerts": 5,
                "debug": 6,
            }.get(panel_name, 0)
            self._panel_stack.setCurrentIndex(stack_index)
            current = self._panel_stack.currentWidget()
            if isinstance(current, BasePanel):
                current.set_active(True)

            sb = self.statusBar()
            assert sb is not None
            sb.showMessage(f"Panel: {panel_name.upper()}", 2000)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_connected(self, connected: bool) -> None:
        """Update the connection indicator in the command bar."""
        if connected:
            self._conn_label.setText("● LIVE")
            self._conn_label.setStyleSheet(
                f"color: {PALETTE.POSITIVE}; font-size: 11px; font-weight: bold;"
            )
            self._debug("gateway", "Connected to live backend")
        else:
            self._conn_label.setText("● DELAYED")
            self._conn_label.setStyleSheet(
                f"color: {PALETTE.YELLOW}; font-size: 11px; font-weight: bold;"
            )
            self._debug("gateway", "Switched to delayed direct feed")

    def _update_status_feed(self, tick: object) -> None:
        """Refresh status bar feed indicator on each tick."""
        src = getattr(tick, "source", "—")
        sym = getattr(tick, "symbol", "—")
        self._status_feed.setText(f"FEED: {str(src).upper()}  {sym}")

    def _refresh_feeds(self) -> None:
        """Force a manual poll of all connected feeds."""
        sb = self.statusBar()
        assert sb is not None
        sb.showMessage("Refreshing all feeds…", 3000)
        log.info("Manual feed refresh triggered")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802
        """Clean up resources on close."""
        self._cache.close()
        log.info("Energy Terminal closed")
        super().closeEvent(event)

"""Chart panel — OHLCV candlestick with technical indicator overlays.

Renders a candlestick price chart using PyQtGraph with:
- Volume bar subplot
- Overlay toggles: SMA20, SMA50, EMA12, Bollinger Bands, VWAP
- Subplot toggles: RSI(14), MACD
- Timeframe selector: 1D, 1W, 1M, 3M, 6M, 1Y, 2Y
- Equivalent to Bloomberg ``GP`` (graph price) screen
"""

from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd
import pyqtgraph as pg
import structlog
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from energy_terminal.analytics.technical import (
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
)
from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.data.direct_feed import DirectFeed
from energy_terminal.data.models import Tick
from energy_terminal.ui.panels.base_panel import BasePanel
from energy_terminal.ui.theme import PALETTE

log = structlog.get_logger(__name__)

pg.setConfigOptions(antialias=True, background=PALETTE.BG_PANEL, foreground=PALETTE.FG_SECONDARY)

_TIMEFRAMES = ["1D", "1W", "1M", "3M", "6M", "1Y", "2Y"]
_TF_DAYS = {"1D": 1, "1W": 7, "1M": 30, "3M": 90, "6M": 182, "1Y": 365, "2Y": 730}


class ChartPanel(BasePanel):
    """OHLCV candlestick chart panel with indicator overlays.

    Parameters
    ----------
    cache : TimeSeriesCache
        Shared DuckDB cache used for historical data.
    """

    def __init__(self, cache: TimeSeriesCache, parent: object = None) -> None:
        super().__init__(title="CHART", subtitle="—")
        self._cache = cache
        self._symbol = "CL=F"
        self._tf = "1M"
        self._df: pd.DataFrame = pd.DataFrame()

        self._build_controls()
        self._build_chart()
        self.load_symbol(self._symbol)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_controls(self) -> None:
        """Build the timeframe selector and overlay toggle row."""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        # Timeframe buttons
        self._tf_btns: dict[str, QPushButton] = {}
        for tf in _TIMEFRAMES:
            btn = QPushButton(tf)
            btn.setFixedWidth(36)
            btn.setFixedHeight(20)
            btn.clicked.connect(lambda _, t=tf: self._set_timeframe(t))
            h.addWidget(btn)
            self._tf_btns[tf] = btn

        h.addSpacing(12)

        # Overlay toggles
        for label, attr in [
            ("BB", "_show_bb"),
            ("SMA20", "_show_sma20"),
            ("EMA12", "_show_ema12"),
            ("RSI", "_show_rsi"),
            ("MACD", "_show_macd"),
        ]:
            setattr(self, attr, False)
            btn = QPushButton(label)
            btn.setFixedWidth(46)
            btn.setFixedHeight(20)
            btn.setCheckable(True)
            btn.toggled.connect(lambda checked, a=attr: self._toggle_overlay(a, checked))
            h.addWidget(btn)

        h.addStretch()

        # Log scale toggle
        self._log_btn = QPushButton("LOG")
        self._log_btn.setFixedWidth(36)
        self._log_btn.setFixedHeight(20)
        self._log_btn.setCheckable(True)
        self._log_btn.toggled.connect(self._toggle_log_scale)
        h.addWidget(self._log_btn)

        self.content_layout.addWidget(row)

    def _build_chart(self) -> None:
        """Initialise PyQtGraph plot widgets."""
        self._plot_widget = pg.GraphicsLayoutWidget()
        self._plot_widget.setBackground(PALETTE.BG_PANEL)

        # Price plot
        self._price_plot = self._plot_widget.addPlot(row=0, col=0)
        self._price_plot.showGrid(x=True, y=True, alpha=0.15)
        self._price_plot.setLabel("left", "Price (USD)")

        # Volume plot
        self._plot_widget.nextRow()
        self._vol_plot = self._plot_widget.addPlot(row=1, col=0)
        self._vol_plot.setMaximumHeight(80)
        self._vol_plot.setLabel("left", "Volume")
        self._vol_plot.setXLink(self._price_plot)

        # RSI / MACD plot (hidden until toggled)
        self._plot_widget.nextRow()
        self._ind_plot = self._plot_widget.addPlot(row=2, col=0)
        self._ind_plot.setMaximumHeight(100)
        self._ind_plot.setXLink(self._price_plot)
        self._ind_plot.hide()

        self.content_layout.addWidget(self._plot_widget, stretch=1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_symbol(self, symbol: str) -> None:
        """Load and render chart data for a new symbol.

        Parameters
        ----------
        symbol : str
            Yahoo Finance ticker to chart.
        """
        self._symbol = symbol
        self.set_subtitle(symbol)
        self._clear_chart()
        self._refresh_chart()
        if self._df.empty:
            QTimer.singleShot(0, lambda: asyncio.create_task(self._fetch_history(symbol)))

    async def _fetch_history(self, symbol: str) -> None:
        """Fetch chart history for a symbol when no cache data exists."""
        bars = await DirectFeed().fetch_ohlcv(symbol, period="1y", interval="1d")
        if bars:
            self._cache.write_ohlcv(symbol, bars)
            if self._symbol == symbol:
                self._refresh_chart()

    def _clear_chart(self) -> None:
        """Clear all chart plots when data is not yet available."""
        self._price_plot.clear()
        self._vol_plot.clear()
        self._ind_plot.clear()

    def on_tick(self, tick: Tick) -> None:
        """Update the latest price bar on a live tick.

        Parameters
        ----------
        tick : Tick
            Incoming price tick.
        """
        if tick.symbol != self._symbol:
            return
        # For live updates just refresh the chart (lightweight for cached data)
        self._refresh_chart()

    # ------------------------------------------------------------------
    # Chart rendering
    # ------------------------------------------------------------------

    def _refresh_chart(self) -> None:
        """Re-query the cache and redraw all chart elements."""
        days = _TF_DAYS.get(self._tf, 30)
        self._df = self._cache.read_ohlcv(self._symbol, days=days)

        if self._df.empty:
            log.debug("No cached data for chart", symbol=self._symbol)
            return

        self._price_plot.clear()
        self._vol_plot.clear()
        self._ind_plot.clear()

        close = self._df["close"].to_numpy()
        high = self._df["high"].to_numpy()
        low = self._df["low"].to_numpy()
        volume = self._df["volume"].to_numpy()
        xs = np.arange(len(close))

        # Candlestick approximation: fill between open and close per bar
        opens = self._df["open"].to_numpy()
        for i, (o, c, h, low_value) in enumerate(zip(opens, close, high, low, strict=False)):
            colour = PALETTE.POSITIVE if c >= o else PALETTE.NEGATIVE
            # High-low wick
            self._price_plot.plot([i, i], [low_value, h], pen=pg.mkPen(colour, width=1))
            # Body
            self._price_plot.plot([i, i], [o, c], pen=pg.mkPen(colour, width=4))

        # Volume bars
        colours = [
            PALETTE.POSITIVE if close[i] >= opens[i] else PALETTE.NEGATIVE
            for i in range(len(close))
        ]
        bg = pg.BarGraphItem(
            x=xs, height=volume, width=0.8, brushes=[pg.mkBrush(c) for c in colours]
        )
        self._vol_plot.addItem(bg)

        # Overlays
        if self._show_sma20 and len(close) >= 20:
            s = sma(close, 20)
            self._price_plot.plot(xs, s, pen=pg.mkPen(PALETTE.SERIES[1], width=1.5), name="SMA20")

        if self._show_ema12 and len(close) >= 12:
            e = ema(close, 12)
            self._price_plot.plot(xs, e, pen=pg.mkPen(PALETTE.SERIES[2], width=1.5), name="EMA12")

        if self._show_bb and len(close) >= 20:
            upper, mid, lower = bollinger_bands(close, 20)
            kw = {"width": 1, "style": Qt.PenStyle.DashLine}
            self._price_plot.plot(xs, upper, pen=pg.mkPen(PALETTE.SERIES[3], **kw))
            self._price_plot.plot(xs, lower, pen=pg.mkPen(PALETTE.SERIES[3], **kw))

        # RSI / MACD subpanel
        if self._show_rsi and len(close) >= 15:
            r = rsi(close, 14)
            self._ind_plot.clear()
            self._ind_plot.plot(xs, r, pen=pg.mkPen(PALETTE.AMBER, width=1.5))
            self._ind_plot.addLine(y=70, pen=pg.mkPen(PALETTE.NEGATIVE, style=Qt.PenStyle.DashLine))
            self._ind_plot.addLine(y=30, pen=pg.mkPen(PALETTE.POSITIVE, style=Qt.PenStyle.DashLine))
            self._ind_plot.show()

        elif self._show_macd and len(close) >= 35:
            ml, sl, hist = macd(close)
            self._ind_plot.clear()
            self._ind_plot.plot(xs, ml, pen=pg.mkPen(PALETTE.AMBER, width=1.5), name="MACD")
            self._ind_plot.plot(xs, sl, pen=pg.mkPen(PALETTE.CYAN, width=1), name="Signal")
            hist_item = pg.BarGraphItem(
                x=xs,
                height=hist,
                width=0.8,
                brushes=[
                    pg.mkBrush(PALETTE.POSITIVE if v >= 0 else PALETTE.NEGATIVE) for v in hist
                ],
            )
            self._ind_plot.addItem(hist_item)
            self._ind_plot.show()

    # ------------------------------------------------------------------
    # UI event handlers
    # ------------------------------------------------------------------

    def _set_timeframe(self, tf: str) -> None:
        self._tf = tf
        self._refresh_chart()

    def _toggle_overlay(self, attr: str, checked: bool) -> None:
        setattr(self, attr, checked)
        self._refresh_chart()

    def _toggle_log_scale(self, checked: bool) -> None:
        self._price_plot.setLogMode(y=checked)

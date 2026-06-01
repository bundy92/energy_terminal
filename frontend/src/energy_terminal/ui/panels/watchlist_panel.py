"""Watchlist panel — user-managed instrument list with alert badges.

Displays a compact price table for a user-configurable watchlist.
Alert thresholds are shown inline; fired alerts are highlighted in
magenta.  Supports drag-to-reorder rows (Qt item model).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

import structlog

from energy_terminal.data.direct_feed import DirectFeed

from energy_terminal.data.alerts import AlertEngine, AlertFired
from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.data.direct_feed import INSTRUMENT_NAMES
from energy_terminal.data.models import Tick
from energy_terminal.ui.panels.base_panel import BasePanel
from energy_terminal.ui.theme import PALETTE

log = structlog.get_logger(__name__)

_COLUMNS = ["Symbol", "Last", "Chg %", "Alert"]
_DEFAULT_WATCHLIST = ["CL=F", "BZ=F", "NG=F", "RB=F", "HO=F"]


class WatchlistPanel(BasePanel):
    """User watchlist with live prices and alert indicators.

    Parameters
    ----------
    cache : TimeSeriesCache
        Shared cache (used to seed initial prices).
    alerts : AlertEngine
        Alert engine instance for displaying triggered states.
    """

    def __init__(
        self,
        cache: TimeSeriesCache,
        alerts: AlertEngine,
        on_symbol_selected: Callable[[str], None] | None = None,
        parent: object = None,
    ) -> None:
        super().__init__(title="WATCHLIST", subtitle="")
        self._cache    = cache
        self._alerts   = alerts
        self._on_symbol_selected = on_symbol_selected
        self._watchlist: list[str] = list(_DEFAULT_WATCHLIST)
        self._row_map:  dict[str, int] = {}
        self._fired:    set[str] = set()

        self._build_add_row()
        self._table = self._build_table()
        self.content_layout.addWidget(self._table, stretch=1)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_add_row(self) -> None:
        """Build the ticker-add input row."""
        row = QWidget()
        h   = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        self._add_input = QLineEdit()
        self._add_input.setPlaceholderText("Add ticker…")
        self._add_input.setFixedHeight(22)
        self._add_input.returnPressed.connect(self._add_ticker)
        h.addWidget(self._add_input, stretch=1)

        btn = QPushButton("ADD")
        btn.setFixedWidth(40)
        btn.setFixedHeight(22)
        btn.clicked.connect(self._add_ticker)
        h.addWidget(btn)

        self.content_layout.addWidget(row)

    def _build_table(self) -> QTableWidget:
        """Build the watchlist table."""
        t = QTableWidget(len(self._watchlist), len(_COLUMNS))
        t.setHorizontalHeaderLabels(_COLUMNS)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.setShowGrid(False)

        for i, sym in enumerate(self._watchlist):
            self._row_map[sym] = i
            t.setItem(i, 0, self._cell(sym))
            t.setItem(i, 1, self._cell("—"))
            t.setItem(i, 2, self._cell("—"))
            t.setItem(i, 3, self._cell(""))

        t.cellClicked.connect(self._handle_symbol_click)
        return t

    # ------------------------------------------------------------------
    # Data handlers
    # ------------------------------------------------------------------

    def on_tick(self, tick: Tick) -> None:
        """Update watchlist row for a matching symbol.

        Parameters
        ----------
        tick : Tick
            Incoming price tick.
        """
        row = self._row_map.get(tick.symbol)
        if row is None:
            return

        pct    = tick.change_pct
        colour = (PALETTE.POSITIVE if pct > 0 else
                  PALETTE.NEGATIVE if pct < 0 else PALETTE.NEUTRAL)

        fired = tick.symbol in self._fired
        row_colour = PALETTE.MAGENTA if fired else colour

        self._set_cell(row, 1, f"{tick.close:.4f}", row_colour)
        self._set_cell(row, 2, f"{pct:+.2f}%", row_colour)

    def on_alert_fired(self, event: AlertFired) -> None:
        """Highlight the watchlist row when an alert fires.

        Parameters
        ----------
        event : AlertFired
            The fired alert event.
        """
        sym = event.alert.symbol
        self._fired.add(sym)
        row = self._row_map.get(sym)
        if row is not None:
            self._set_cell(row, 3, "⚠ " + event.alert.message, PALETTE.MAGENTA)

    def _handle_symbol_click(self, row: int, col: int) -> None:
        """Handle clicks on watchlist rows and load the chart for that symbol."""
        if self._on_symbol_selected is None:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        symbol = item.text().strip().upper()
        if symbol:
            self._on_symbol_selected(symbol)

    # ------------------------------------------------------------------
    # Add / remove
    # ------------------------------------------------------------------

    def _add_ticker(self) -> None:
        """Add the ticker from the input field to the watchlist."""
        sym = self._add_input.text().strip().upper()
        self._add_input.clear()
        if not sym or sym in self._row_map:
            return
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._row_map[sym] = row
        self._watchlist.append(sym)
        self._table.setItem(row, 0, self._cell(sym))
        last_close = self._cache.latest_close(sym)
        if last_close is not None:
            self._set_cell(row, 1, f"{last_close:.4f}", PALETTE.FG_MUTED)
            self._set_cell(row, 2, "+0.00%", PALETTE.FG_MUTED)
        else:
            self._table.setItem(row, 1, self._cell("LOADING..."))
            self._table.setItem(row, 2, self._cell("—"))
        self._table.setItem(row, 3, self._cell(""))
        log.info("Watchlist ticker added", symbol=sym)
        try:
            asyncio.get_running_loop().create_task(self._fetch_initial_price(sym))
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cell(text: str, colour: str | None = None) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                              Qt.AlignmentFlag.AlignVCenter)
        if colour:
            item.setForeground(QColor(colour))
        return item

    async def _fetch_initial_price(self, symbol: str) -> None:
        tick = await DirectFeed().fetch_quote(symbol)
        if tick is None or tick.symbol != symbol:
            return
        row = self._row_map.get(symbol)
        if row is None:
            return
        self.on_tick(tick)

    def _set_cell(self, row: int, col: int, text: str,
                  colour: str | None = None) -> None:
        item = self._table.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self._table.setItem(row, col, item)
        item.setText(text)
        if colour:
            item.setForeground(QColor(colour))

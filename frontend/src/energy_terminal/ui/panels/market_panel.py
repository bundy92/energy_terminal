"""Market Overview panel.

Displays a live price table for all tracked instruments, colour-coded
by daily change direction.  Equivalent to Bloomberg's ``MHQP`` screen.

Columns: Symbol | Name | Last | Change | Chg% | High | Low | Volume
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

import structlog

from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.data.direct_feed import INSTRUMENT_NAMES
from energy_terminal.data.models import Tick
from energy_terminal.ui.panels.base_panel import BasePanel
from energy_terminal.ui.theme import PALETTE

log = structlog.get_logger(__name__)

_COLUMNS = ["Symbol", "Name", "Last", "Chg", "Chg %", "High", "Low", "Volume"]

_INSTRUMENTS = [
    "CL=F", "BZ=F", "NG=F", "RB=F", "HO=F",
    "XOM", "CVX", "BP", "SHEL", "TTE",
    "EURUSD=X", "DX-Y.NYB",
    "XLE", "ICLN",
]


class MarketPanel(BasePanel):
    """Live market overview table.

    Parameters
    ----------
    cache : TimeSeriesCache
        Shared DuckDB cache (used to seed last-known prices on startup).
    """

    def __init__(self, cache: TimeSeriesCache, parent: object = None) -> None:
        super().__init__(title="MARKET OVERVIEW", subtitle="ALL INSTRUMENTS")
        self._cache    = cache
        self._row_map: dict[str, int] = {}
        self._table    = self._build_table()
        self.content_layout.addWidget(self._table)
        self._seed_from_cache()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_table(self) -> QTableWidget:
        """Construct the price table widget."""
        t = QTableWidget(len(_INSTRUMENTS), len(_COLUMNS))
        t.setHorizontalHeaderLabels(_COLUMNS)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.setShowGrid(False)

        for i, sym in enumerate(_INSTRUMENTS):
            self._row_map[sym] = i
            self._set_cell(t, i, 0, sym)
            self._set_cell(t, i, 1, INSTRUMENT_NAMES.get(sym, sym))
            for col in range(2, len(_COLUMNS)):
                self._set_cell(t, i, col, "—")

        return t

    # ------------------------------------------------------------------
    # Data handlers
    # ------------------------------------------------------------------

    def on_tick(self, tick: Tick) -> None:
        """Update a row when a new price tick arrives.

        Parameters
        ----------
        tick : Tick
            Incoming price tick.
        """
        row = self._row_map.get(tick.symbol)
        if row is None:
            return

        chg_pct = tick.change_pct
        colour  = PALETTE.POSITIVE if chg_pct > 0 else (
                  PALETTE.NEGATIVE if chg_pct < 0 else PALETTE.NEUTRAL)

        self._set_cell(self._table, row, 2, f"{tick.close:.4f}", colour)
        self._set_cell(self._table, row, 3,
                       f"{tick.change:+.4f}", colour)
        self._set_cell(self._table, row, 4,
                       f"{tick.change_pct:+.2f}%", colour)
        self._set_cell(self._table, row, 5, f"{tick.high:.4f}")
        self._set_cell(self._table, row, 6, f"{tick.low:.4f}")
        self._set_cell(self._table, row, 7,
                       f"{tick.volume:,}" if tick.volume else "—")

    def _seed_from_cache(self) -> None:
        """Populate the table with last-known prices from DuckDB."""
        for sym, row in self._row_map.items():
            last = self._cache.latest_close(sym)
            if last is not None:
                self._set_cell(self._table, row, 2, f"{last:.4f}",
                               PALETTE.FG_MUTED)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _set_cell(
        table: QTableWidget,
        row: int,
        col: int,
        text: str,
        colour: str | None = None,
    ) -> None:
        """Write a cell value with optional foreground colour."""
        item = QTableWidgetItem(text)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            if col > 1 else
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        if colour:
            item.setForeground(QColor(colour))
        table.setItem(row, col, item)

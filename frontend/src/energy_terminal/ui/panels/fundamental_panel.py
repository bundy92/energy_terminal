"""Fundamental data panel — EIA weekly supply/demand readings."""

from __future__ import annotations

from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.data.models import FundamentalReading
from energy_terminal.ui.panels.base_panel import BasePanel

_SERIES_NAMES: dict[str, str] = {
    "PET.WCRSTUS1.W":         "US Crude Stocks (kbbl)",
    "PET.WCRFPUS2.W":         "US Production (kbd)",
    "PET.WCRRIUS2.W":         "Refinery Inputs (kbd)",
    "PET.WPULEUS2.W":         "Refinery Utilisation (%)",
    "NG.NW2EUS_EPG0_SWO_BCF.W": "US Nat Gas Storage (BCF)",
}


class FundamentalPanel(BasePanel):
    """EIA supply/demand fundamental data panel."""

    def __init__(self, cache: TimeSeriesCache, parent: object = None) -> None:
        super().__init__(title="FUNDAMENTALS", subtitle="EIA WEEKLY")
        self._cache = cache
        self._row_map: dict[str, int] = {}

        self._table = QTableWidget(len(_SERIES_NAMES), 3)
        self._table.setHorizontalHeaderLabels(["Series", "Value", "Period"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)

        for i, (sid, name) in enumerate(_SERIES_NAMES.items()):
            self._row_map[sid] = i
            self._table.setItem(i, 0, QTableWidgetItem(name))
            self._table.setItem(i, 1, QTableWidgetItem("—"))
            self._table.setItem(i, 2, QTableWidgetItem("—"))

        self.content_layout.addWidget(self._table)

    def on_reading(self, reading: FundamentalReading) -> None:
        """Update a fundamental series row.

        Parameters
        ----------
        reading : FundamentalReading
            Incoming EIA reading.
        """
        row = self._row_map.get(reading.series)
        if row is None:
            return
        val = f"{reading.value:,.1f}" if reading.value is not None else "—"
        self._table.setItem(row, 1, QTableWidgetItem(val))
        self._table.setItem(row, 2, QTableWidgetItem(reading.period))

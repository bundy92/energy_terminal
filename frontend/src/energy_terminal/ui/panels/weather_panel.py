"""Weather / HDD-CDD demand panel."""

from __future__ import annotations

from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.data.models import WeatherReading
from energy_terminal.ui.panels.base_panel import BasePanel
from energy_terminal.ui.theme import PALETTE

_LOCATIONS = ["New York", "Chicago", "Houston", "London", "Rotterdam", "Tokyo"]


class WeatherPanel(BasePanel):
    """HDD / CDD weather demand panel for key energy hubs."""

    def __init__(self, cache: TimeSeriesCache, parent: object = None) -> None:
        super().__init__(title="WEATHER / HDD-CDD", subtitle="DEMAND CENTRES")
        self._cache   = cache
        self._row_map: dict[str, int] = {}

        self._table = QTableWidget(len(_LOCATIONS), 5)
        self._table.setHorizontalHeaderLabels(
            ["Location", "Temp °C", "HDD", "CDD", "7D Forecast"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)

        for i, loc in enumerate(_LOCATIONS):
            self._row_map[loc] = i
            self._table.setItem(i, 0, QTableWidgetItem(loc))
            for col in range(1, 5):
                self._table.setItem(i, col, QTableWidgetItem("—"))

        self.content_layout.addWidget(self._table)

    def on_reading(self, reading: WeatherReading) -> None:
        """Update a location row with new weather data.

        Parameters
        ----------
        reading : WeatherReading
            Incoming weather observation.
        """
        row = self._row_map.get(reading.location)
        if row is None:
            return
        self._table.setItem(row, 1, QTableWidgetItem(f"{reading.temp_c:.1f}"))
        self._table.setItem(row, 2, QTableWidgetItem(f"{reading.hdd:.1f}"))
        self._table.setItem(row, 3, QTableWidgetItem(f"{reading.cdd:.1f}"))
        forecast = ", ".join(f"{t:.0f}" for t in reading.forecast_7d)
        self._table.setItem(row, 4, QTableWidgetItem(forecast))

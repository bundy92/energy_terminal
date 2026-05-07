"""Risk analytics panel.

Tabs:
- VAR     : Historical and parametric VaR / CVaR for each instrument
- CORR    : Rolling 60-day pairwise correlation matrix (colour heatmap)
- VOL     : Realised volatility cone (current vs historical distribution)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QLabel,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from energy_terminal.analytics.risk import (
    historical_cvar,
    historical_var,
    log_returns,
    rolling_correlation_matrix,
    volatility_cone,
)
from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.ui.panels.base_panel import BasePanel
from energy_terminal.ui.theme import PALETTE

_INSTRUMENTS = ["CL=F", "BZ=F", "NG=F", "RB=F", "HO=F"]
_CORR_WINDOWS = [30, 60, 90]


class RiskPanel(BasePanel):
    """Portfolio risk metrics panel.

    Parameters
    ----------
    cache : TimeSeriesCache
        Shared DuckDB cache used to compute return series.
    """

    def __init__(self, cache: TimeSeriesCache, parent: object = None) -> None:
        super().__init__(title="RISK", subtitle="VAR / CORR / VOL")
        self._cache = cache

        tabs = QTabWidget()
        tabs.addTab(self._build_var_tab(),  "VAR / CVAR")
        tabs.addTab(self._build_corr_tab(), "CORRELATION")
        tabs.addTab(self._build_vol_tab(),  "VOL CONE")
        tabs.currentChanged.connect(self._on_tab_change)

        self.content_layout.addWidget(tabs)
        self._tabs = tabs
        self.refresh()

    # ------------------------------------------------------------------
    # Tab construction
    # ------------------------------------------------------------------

    def _build_var_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)

        self._var_table = QTableWidget(len(_INSTRUMENTS), 5)
        self._var_table.setHorizontalHeaderLabels(
            ["Symbol", "HVaR 95%", "HVaR 99%", "CVaR 95%", "Ann. Vol"]
        )
        self._var_table.verticalHeader().setVisible(False)
        self._var_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._var_table.horizontalHeader().setStretchLastSection(True)

        for i, sym in enumerate(_INSTRUMENTS):
            self._var_table.setItem(i, 0, QTableWidgetItem(sym))
            for col in range(1, 5):
                self._var_table.setItem(i, col, QTableWidgetItem("—"))

        note = QLabel("All VaR figures: 1-day, USD per unit.  "
                      "Confidence levels: 95% and 99%.")
        note.setStyleSheet(f"color: {PALETTE.FG_MUTED}; font-size: 10px;")
        v.addWidget(self._var_table)
        v.addWidget(note)
        return w

    def _build_corr_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)

        n = len(_INSTRUMENTS)
        self._corr_table = QTableWidget(n, n)
        self._corr_table.setHorizontalHeaderLabels(_INSTRUMENTS)
        self._corr_table.setVerticalHeaderLabels(_INSTRUMENTS)
        self._corr_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        note = QLabel("60-day rolling Pearson correlation of log returns.  "
                      "Green = positive, Red = negative correlation.")
        note.setStyleSheet(f"color: {PALETTE.FG_MUTED}; font-size: 10px;")
        v.addWidget(note)
        v.addWidget(self._corr_table, stretch=1)
        return w

    def _build_vol_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)

        # Window rows, instrument columns
        windows = [10, 20, 30, 60, 90]
        self._vol_table = QTableWidget(len(windows), len(_INSTRUMENTS) + 1)
        self._vol_table.setHorizontalHeaderLabels(["Window"] + _INSTRUMENTS)
        self._vol_table.verticalHeader().setVisible(False)
        self._vol_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._vol_table.horizontalHeader().setStretchLastSection(True)

        for i, w_ in enumerate(windows):
            self._vol_table.setItem(i, 0, QTableWidgetItem(f"{w_}d"))
            for j in range(len(_INSTRUMENTS)):
                self._vol_table.setItem(i, j + 1, QTableWidgetItem("—"))

        note = QLabel("Annualised realised volatility (252 trading days).  "
                      "Current window value shown.")
        note.setStyleSheet(f"color: {PALETTE.FG_MUTED}; font-size: 10px;")
        v.addWidget(self._vol_table)
        v.addWidget(note)
        return w

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Recompute all risk metrics from the cache."""
        self._refresh_var()
        self._refresh_corr()
        self._refresh_vol()

    def _on_tab_change(self, _: int) -> None:
        self.refresh()

    def _refresh_var(self) -> None:
        """Populate VaR / CVaR table from cached OHLCV data."""
        for i, sym in enumerate(_INSTRUMENTS):
            df = self._cache.read_ohlcv(sym, days=252)
            if df.empty or len(df) < 30:
                continue
            rets = log_returns(df["close"].to_numpy())
            try:
                var95  = historical_var(rets, 0.95)
                var99  = historical_var(rets, 0.99)
                cvar95 = historical_cvar(rets, 0.95)
                ann_vol = float(np.std(rets, ddof=1)) * np.sqrt(252) * 100
            except Exception:  # noqa: BLE001
                continue

            last_close = df["close"].iloc[-1]
            self._var_table.setItem(i, 1,
                QTableWidgetItem(f"${var95 * last_close:.2f}"))
            self._var_table.setItem(i, 2,
                QTableWidgetItem(f"${var99 * last_close:.2f}"))
            self._var_table.setItem(i, 3,
                QTableWidgetItem(f"${cvar95 * last_close:.2f}"))
            self._var_table.setItem(i, 4,
                QTableWidgetItem(f"{ann_vol:.1f}%"))

    def _refresh_corr(self) -> None:
        """Populate correlation heatmap."""
        frames: dict[str, pd.Series] = {}
        for sym in _INSTRUMENTS:
            df = self._cache.read_ohlcv(sym, days=120)
            if not df.empty:
                frames[sym] = df.set_index("ts_ms")["close"]

        if len(frames) < 2:
            return

        prices_df = pd.DataFrame(frames).dropna()
        if len(prices_df) < 30:
            return

        try:
            corr = rolling_correlation_matrix(prices_df, window=min(60, len(prices_df)))
        except Exception:  # noqa: BLE001
            return

        for r, sym_r in enumerate(_INSTRUMENTS):
            for c, sym_c in enumerate(_INSTRUMENTS):
                if sym_r not in corr.index or sym_c not in corr.columns:
                    continue
                val  = corr.loc[sym_r, sym_c]
                text = f"{val:.2f}"
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # Colour scale: red (-1) → white (0) → green (+1)
                if r == c:
                    item.setBackground(QColor(PALETTE.BG_HEADER))
                else:
                    intensity = int(abs(val) * 180)
                    if val > 0:
                        item.setForeground(QColor(0, intensity, 0))
                    else:
                        item.setForeground(QColor(intensity, 0, 0))
                self._corr_table.setItem(r, c, item)

    def _refresh_vol(self) -> None:
        """Populate volatility cone table."""
        windows = [10, 20, 30, 60, 90]
        for j, sym in enumerate(_INSTRUMENTS):
            df = self._cache.read_ohlcv(sym, days=365)
            if df.empty or len(df) < 90:
                continue
            rets = log_returns(df["close"].to_numpy())
            try:
                cone = volatility_cone(rets, windows=tuple(windows))
            except Exception:  # noqa: BLE001
                continue

            for i, w in enumerate(windows):
                if w in cone:
                    pct = cone[w]["current"] * 100
                    self._vol_table.setItem(i, j + 1,
                        QTableWidgetItem(f"{pct:.1f}%"))

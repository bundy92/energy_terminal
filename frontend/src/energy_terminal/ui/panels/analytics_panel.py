"""Analytics panel — energy-specific derived analytics.

Tabs:
- SPREADS  : Live crack spread and spark spread calculator
- STRUCTURE: Forward curve term structure with slope metric
- MATRIX   : N×N pairwise spread matrix (z-score coloured)
- MACRO    : FRED macro overlay table (USD index, CPI, real rates)
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import structlog

from energy_terminal.analytics.fundamental import (
    crack_3_2_1,
    crack_2_1_1,
    spark_spread,
)
from energy_terminal.analytics.options import (
    black_scholes_delta,
    black_scholes_gamma,
    black_scholes_price,
    black_scholes_vega,
)
from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.data.models import FundamentalReading, MacroReading, Tick
from energy_terminal.ui.panels.base_panel import BasePanel
from energy_terminal.ui.theme import PALETTE

log = structlog.get_logger(__name__)

# Spread matrix instruments
_MATRIX_SYMS = ["CL=F", "BZ=F", "NG=F", "RB=F", "HO=F"]

# FRED series display names
_FRED_NAMES: dict[str, str] = {
    "DTWEXBGS":             "USD Broad Index",
    "CPIAUCSL":             "CPI (All Urban)",
    "REAINTRATREARAT10Y":   "10Y Real Rate",
    "INDPRO":               "Industrial Production",
    "DCOILWTICO":           "WTI Spot (FRED)",
}


class AnalyticsPanel(BasePanel):
    """Energy analytics panel with tabbed sub-screens.

    Parameters
    ----------
    cache : TimeSeriesCache
        Shared DuckDB cache.
    """

    def __init__(self, cache: TimeSeriesCache, parent: object = None) -> None:
        super().__init__(title="ANALYTICS", subtitle="")
        self._cache   = cache
        self._prices: dict[str, float] = {}

        tabs = QTabWidget()
        tabs.addTab(self._build_spreads_tab(),   "SPREADS")
        tabs.addTab(self._build_matrix_tab(),    "MATRIX")
        tabs.addTab(self._build_options_tab(),   "OPTIONS")
        tabs.addTab(self._build_macro_tab(),     "MACRO")
        self._tabs = tabs

        self.content_layout.addWidget(tabs)

    # ------------------------------------------------------------------
    # Spreads tab
    # ------------------------------------------------------------------

    def _build_spreads_tab(self) -> QWidget:
        """Crack and spark spread calculator."""
        w   = QWidget()
        g   = QGridLayout(w)
        g.setSpacing(6)
        g.setContentsMargins(8, 8, 8, 8)

        def hdr(text: str) -> QLabel:
            l = QLabel(text)
            l.setStyleSheet(f"color:{PALETTE.AMBER}; font-weight:bold; font-size:11px;")
            return l

        def val_lbl(text: str = "—") -> QLabel:
            l = QLabel(text)
            l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            l.setStyleSheet(f"color:{PALETTE.FG_PRIMARY}; font-size:13px; font-weight:bold;")
            return l

        row = 0
        g.addWidget(hdr("CRACK SPREADS"), row, 0, 1, 2); row += 1

        g.addWidget(QLabel("3-2-1 Crack (WTI)"),  row, 0)
        self._lbl_321 = val_lbl(); g.addWidget(self._lbl_321, row, 1); row += 1

        g.addWidget(QLabel("2-1-1 Crack (Brent)"), row, 0)
        self._lbl_211 = val_lbl(); g.addWidget(self._lbl_211, row, 1); row += 1

        g.addWidget(QLabel("HO Crack (Brent)"),    row, 0)
        self._lbl_ho  = val_lbl(); g.addWidget(self._lbl_ho,  row, 1); row += 1

        g.addWidget(hdr("SPARK SPREAD"),            row, 0, 1, 2); row += 1
        g.addWidget(QLabel("Gas–Power (7k BTU)"),   row, 0)
        self._lbl_spark = val_lbl(); g.addWidget(self._lbl_spark, row, 1); row += 1

        g.addWidget(hdr("FX OVERLAY"),              row, 0, 1, 2); row += 1
        g.addWidget(QLabel("EUR/USD"),               row, 0)
        self._lbl_eurusd = val_lbl(); g.addWidget(self._lbl_eurusd, row, 1); row += 1

        g.addWidget(QLabel("USD Index"),             row, 0)
        self._lbl_dxy = val_lbl(); g.addWidget(self._lbl_dxy, row, 1); row += 1

        g.setRowStretch(row, 1)
        return w

    def _build_options_tab(self) -> QWidget:
        """Black-Scholes options analytics builder."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(8)

        form = QFormLayout()
        self._opt_underly = QLineEdit("100.0")
        self._opt_strike = QLineEdit("100.0")
        self._opt_maturity = QLineEdit("0.25")
        self._opt_vol = QLineEdit("0.25")
        self._opt_rate = QLineEdit("0.02")
        self._opt_type = QComboBox()
        self._opt_type.addItems(["Call", "Put"])

        form.addRow("Underlying", self._opt_underly)
        form.addRow("Strike", self._opt_strike)
        form.addRow("Expiry (yrs)", self._opt_maturity)
        form.addRow("Volatility", self._opt_vol)
        form.addRow("Rate", self._opt_rate)
        form.addRow("Type", self._opt_type)

        calculate_btn = QPushButton("CALCULATE")
        calculate_btn.clicked.connect(self._update_options_metrics)

        self._opt_price_lbl = QLabel("Premium: —")
        self._opt_delta_lbl = QLabel("Delta: —")
        self._opt_gamma_lbl = QLabel("Gamma: —")
        self._opt_vega_lbl = QLabel("Vega: —")

        for lbl in [self._opt_price_lbl, self._opt_delta_lbl, self._opt_gamma_lbl, self._opt_vega_lbl]:
            lbl.setStyleSheet(f"color:{PALETTE.FG_PRIMARY}; font-size:12px; font-weight:bold;")

        v.addLayout(form)
        v.addWidget(calculate_btn)
        v.addWidget(self._opt_price_lbl)
        v.addWidget(self._opt_delta_lbl)
        v.addWidget(self._opt_gamma_lbl)
        v.addWidget(self._opt_vega_lbl)
        v.addStretch(1)
        return w

    # ------------------------------------------------------------------
    # Spread matrix tab
    # ------------------------------------------------------------------

    def _build_matrix_tab(self) -> QWidget:
        """N×N colour-coded pairwise spread matrix."""
        w = QWidget()
        from PyQt6.QtWidgets import QVBoxLayout
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)

        n = len(_MATRIX_SYMS)
        self._matrix = QTableWidget(n, n)
        self._matrix.setHorizontalHeaderLabels(_MATRIX_SYMS)
        self._matrix.setVerticalHeaderLabels(_MATRIX_SYMS)
        self._matrix.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._matrix.setShowGrid(True)

        v.addWidget(QLabel("Pairwise spread (row price − col price)  |  "
                           "Green = row premium, Red = col premium"))
        v.addWidget(self._matrix, stretch=1)
        return w

    # ------------------------------------------------------------------
    # Macro tab
    # ------------------------------------------------------------------

    def _build_macro_tab(self) -> QWidget:
        """FRED macro indicator table."""
        w = QWidget()
        from PyQt6.QtWidgets import QVBoxLayout
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)

        self._macro_table = QTableWidget(len(_FRED_NAMES), 3)
        self._macro_table.setHorizontalHeaderLabels(["Series", "Value", "Date"])
        self._macro_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._macro_table.verticalHeader().setVisible(False)
        self._macro_table.horizontalHeader().setStretchLastSection(True)
        self._macro_row: dict[str, int] = {}

        for i, (sid, name) in enumerate(_FRED_NAMES.items()):
            self._macro_row[sid] = i
            self._macro_table.setItem(i, 0, QTableWidgetItem(name))
            self._macro_table.setItem(i, 1, QTableWidgetItem("—"))
            self._macro_table.setItem(i, 2, QTableWidgetItem("—"))

        v.addWidget(self._macro_table)
        return w

    # ------------------------------------------------------------------
    # Data event handlers
    # ------------------------------------------------------------------

    def on_tick(self, tick: Tick) -> None:
        """Store the latest price and recalculate spreads."""
        self._prices[tick.symbol] = tick.close
        self._update_spreads()
        self._update_matrix()

    def on_fundamental(self, reading: FundamentalReading) -> None:
        """No-op — fundamentals handled by FundamentalPanel."""

    def on_macro(self, reading: MacroReading) -> None:
        """Update the FRED macro table.

        Parameters
        ----------
        reading : MacroReading
            Incoming macro observation.
        """
        row = self._macro_row.get(reading.series)
        if row is None:
            return
        val = f"{reading.value:.4f}" if reading.value is not None else "—"
        self._macro_table.setItem(row, 1, QTableWidgetItem(val))
        self._macro_table.setItem(row, 2, QTableWidgetItem(reading.date))

    # ------------------------------------------------------------------
    # Calculation helpers
    # ------------------------------------------------------------------

    def _update_spreads(self) -> None:
        """Recalculate and display crack and spark spreads."""
        p = self._prices
        wti   = p.get("CL=F", 0.0)
        brent = p.get("BZ=F", 0.0)
        rbob  = p.get("RB=F", 0.0) * 100   # convert $/gal → USC/gal
        ho    = p.get("HO=F", 0.0) * 100
        ng    = p.get("NG=F", 0.0)
        eurusd = p.get("EURUSD=X", 0.0)
        dxy    = p.get("DX-Y.NYB", 0.0)

        def _fmt(val: float) -> str:
            colour = PALETTE.POSITIVE if val > 0 else PALETTE.NEGATIVE
            return f'<span style="color:{colour}; font-size:13px; font-weight:bold;">' \
                   f'${val:.2f}/bbl</span>'

        if wti and rbob and ho:
            self._lbl_321.setText(_fmt(crack_3_2_1(wti, rbob, ho)))
        if brent and rbob and ho:
            self._lbl_211.setText(_fmt(crack_2_1_1(brent, rbob, ho)))
        if brent and ho:
            from energy_terminal.analytics.fundamental import heating_oil_crack
            self._lbl_ho.setText(_fmt(heating_oil_crack(brent, ho)))
        if ng:
            # Placeholder: power price hardcoded; real impl from EIA/power feed
            ss = spark_spread(power_price_mwh=50.0, gas_price_mmbtu=ng)
            self._lbl_spark.setText(_fmt(ss))
        if eurusd:
            self._lbl_eurusd.setText(f"{eurusd:.5f}")
        if dxy:
            self._lbl_dxy.setText(f"{dxy:.3f}")

    def _update_matrix(self) -> None:
        """Refresh pairwise spread matrix cells."""
        for r, sym_r in enumerate(_MATRIX_SYMS):
            for c, sym_c in enumerate(_MATRIX_SYMS):
                pr = self._prices.get(sym_r)
                pc = self._prices.get(sym_c)
                if pr is None or pc is None:
                    continue
                spread = pr - pc
                item   = QTableWidgetItem(f"{spread:+.3f}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if r == c:
                    item.setBackground(QColor(PALETTE.BG_HEADER))
                elif spread > 0:
                    item.setForeground(QColor(PALETTE.POSITIVE))
                else:
                    item.setForeground(QColor(PALETTE.NEGATIVE))
                self._matrix.setItem(r, c, item)

    def _parse_option_input(self, field: QLineEdit, default: float) -> float:
        try:
            return float(field.text())
        except ValueError:
            return default

    def _update_options_metrics(self) -> None:
        spot = self._parse_option_input(self._opt_underly, 100.0)
        strike = self._parse_option_input(self._opt_strike, 100.0)
        expiry = self._parse_option_input(self._opt_maturity, 0.25)
        vol = self._parse_option_input(self._opt_vol, 0.25)
        rate = self._parse_option_input(self._opt_rate, 0.02)
        option_type = self._opt_type.currentText().lower()

        try:
            price = black_scholes_price(spot, strike, expiry, rate, vol, option_type)
            delta = black_scholes_delta(spot, strike, expiry, rate, vol, option_type)
            gamma = black_scholes_gamma(spot, strike, expiry, rate, vol)
            vega = black_scholes_vega(spot, strike, expiry, rate, vol)
            self._opt_price_lbl.setText(f"Premium: ${price:,.2f}")
            self._opt_delta_lbl.setText(f"Delta: {delta:.4f}")
            self._opt_gamma_lbl.setText(f"Gamma: {gamma:.4f}")
            self._opt_vega_lbl.setText(f"Vega: {vega:.4f}")
        except ValueError:
            self._opt_price_lbl.setText("Premium: —")
            self._opt_delta_lbl.setText("Delta: —")
            self._opt_gamma_lbl.setText("Gamma: —")
            self._opt_vega_lbl.setText("Vega: —")

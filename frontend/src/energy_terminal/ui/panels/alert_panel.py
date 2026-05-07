"""Alert management panel — define, monitor, and review price alerts."""

from __future__ import annotations

import uuid
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from energy_terminal.data.alerts import AlertEngine, AlertFired
from energy_terminal.data.models import Alert, AlertCondition
from energy_terminal.ui.panels.base_panel import BasePanel
from energy_terminal.ui.theme import PALETTE


class AlertPanel(BasePanel):
    """Alert definition and audit log panel.

    Parameters
    ----------
    engine : AlertEngine
        Shared alert evaluation engine.
    """

    def __init__(self, engine: AlertEngine, parent: object = None) -> None:
        super().__init__(title="ALERTS", subtitle="")
        self._engine = engine
        self._fired_log: list[AlertFired] = []

        self.content_layout.addWidget(self._build_add_form())
        self.content_layout.addWidget(QLabel("ACTIVE ALERTS"),)
        self._active_table = self._build_active_table()
        self.content_layout.addWidget(self._active_table)

        self.content_layout.addWidget(QLabel("FIRED LOG"))
        self._fired_table = self._build_fired_table()
        self.content_layout.addWidget(self._fired_table, stretch=1)

        self._refresh_active()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_add_form(self) -> QWidget:
        """Build the new-alert definition form."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        self._sym_input = QLineEdit()
        self._sym_input.setPlaceholderText("Symbol (e.g. CL=F)")
        self._sym_input.setFixedWidth(100)
        h.addWidget(self._sym_input)

        self._cond_combo = QComboBox()
        for cond in AlertCondition:
            self._cond_combo.addItem(cond.value, cond)
        self._cond_combo.setFixedWidth(100)
        h.addWidget(self._cond_combo)

        self._thresh_spin = QDoubleSpinBox()
        self._thresh_spin.setRange(0.0, 999_999.0)
        self._thresh_spin.setDecimals(2)
        self._thresh_spin.setFixedWidth(90)
        h.addWidget(self._thresh_spin)

        self._msg_input = QLineEdit()
        self._msg_input.setPlaceholderText("Alert message")
        h.addWidget(self._msg_input, stretch=1)

        add_btn = QPushButton("ADD")
        add_btn.setFixedWidth(45)
        add_btn.clicked.connect(self._add_alert)
        h.addWidget(add_btn)

        return w

    def _build_active_table(self) -> QTableWidget:
        t = QTableWidget(0, 5)
        t.setHorizontalHeaderLabels(["ID", "Symbol", "Condition",
                                      "Threshold", "Actions"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.horizontalHeader().setStretchLastSection(True)
        t.setMaximumHeight(160)
        return t

    def _build_fired_table(self) -> QTableWidget:
        t = QTableWidget(0, 4)
        t.setHorizontalHeaderLabels(["Time (ms)", "Symbol", "Threshold", "Message"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.horizontalHeader().setStretchLastSection(True)
        return t

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _add_alert(self) -> None:
        """Create and register a new alert from the form."""
        sym    = self._sym_input.text().strip().upper()
        cond   = self._cond_combo.currentData()
        thresh = self._thresh_spin.value()
        msg    = self._msg_input.text().strip()
        if not sym:
            return

        alert = Alert(
            alert_id=str(uuid.uuid4())[:8],
            symbol=sym,
            condition=cond,
            threshold=thresh,
            message=msg or f"{sym} {cond.value} {thresh}",
        )
        self._engine.add_alert(alert)
        self._sym_input.clear()
        self._msg_input.clear()
        self._refresh_active()

    def on_alert_fired(self, event: AlertFired) -> None:
        """Append a fired alert to the audit log.

        Parameters
        ----------
        event : AlertFired
            The fired alert record.
        """
        self._fired_log.append(event)
        row = self._fired_table.rowCount()
        self._fired_table.insertRow(row)
        self._fired_table.setItem(row, 0,
            QTableWidgetItem(str(event.fired_at_ms)))
        self._fired_table.setItem(row, 1,
            QTableWidgetItem(event.alert.symbol))
        self._fired_table.setItem(row, 2,
            QTableWidgetItem(str(event.alert.threshold)))
        item = QTableWidgetItem(event.alert.message)
        item.setForeground(QColor(PALETTE.MAGENTA))
        self._fired_table.setItem(row, 3, item)
        self._fired_table.scrollToBottom()
        self._refresh_active()

    def _refresh_active(self) -> None:
        """Redraw the active alerts table."""
        alerts = self._engine.list_alerts()
        self._active_table.setRowCount(len(alerts))
        for i, a in enumerate(alerts):
            colour = PALETTE.MAGENTA if a.triggered else PALETTE.FG_PRIMARY
            for col, text in enumerate([
                a.alert_id[:8], a.symbol, a.condition.value,
                str(a.threshold)
            ]):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(colour))
                self._active_table.setItem(i, col, item)

            # Reset button
            btn = QPushButton("RESET")
            btn.setFixedHeight(18)
            btn.clicked.connect(
                lambda _, aid=a.alert_id: self._reset(aid))
            self._active_table.setCellWidget(i, 4, btn)

    def _reset(self, alert_id: str) -> None:
        """Re-arm a fired alert."""
        self._engine.reset_alert(alert_id)
        self._refresh_active()

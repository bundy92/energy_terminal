"""Debug panel — runtime event log and troubleshooting view."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QWidget,
)

from energy_terminal.ui.panels.base_panel import BasePanel
from energy_terminal.ui.theme import PALETTE


class DebugPanel(BasePanel):
    """Panel for displaying diagnostic messages and event trace output."""

    def __init__(self, parent: object = None) -> None:
        super().__init__(title="DEBUG", subtitle="LOGS")

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setStyleSheet(
            f"color: {PALETTE.FG_SECONDARY}; background-color: {PALETTE.BG_PANEL}; "
            "font-family: Consolas, Menlo, Monaco, Courier, monospace; font-size: 11px;"
        )
        self._log_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        self._build_toolbar()
        self.content_layout.addWidget(self._log_view, stretch=1)

    def _build_toolbar(self) -> None:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        clear_btn = QPushButton("CLEAR")
        clear_btn.setFixedHeight(22)
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self._log_view.clear)
        h.addWidget(clear_btn)
        h.addStretch()

        self.content_layout.addWidget(row)

    def append_log(self, source: str, message: str, level: str = "INFO") -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._log_view.append(f"[{timestamp}] [{level.upper()}] [{source}] {message}")
        self._log_view.verticalScrollBar().setValue(self._log_view.verticalScrollBar().maximum())

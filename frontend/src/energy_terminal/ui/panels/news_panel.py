"""News panel showing RSS headlines from energy agencies."""

from __future__ import annotations

import asyncio
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from energy_terminal.data.news_feed import NewsFeedAdapter, NewsItem
from energy_terminal.ui.panels.base_panel import BasePanel
from energy_terminal.ui.theme import PALETTE


class NewsPanel(BasePanel):
    """RSS feed aggregator panel."""

    def __init__(self, parent: object = None) -> None:
        super().__init__(title="NEWS", subtitle="EIA · IEA · OPEC")

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        self._status_label = QLabel("Latest release calendars and headlines")
        self._status_label.setStyleSheet(f"color: {PALETTE.FG_SECONDARY}; font-size: 10px;")
        header_layout.addWidget(self._status_label, stretch=1)

        self._refresh_button = QPushButton("REFRESH")
        self._refresh_button.setFixedHeight(22)
        self._refresh_button.clicked.connect(self._refresh_clicked)
        header_layout.addWidget(self._refresh_button)

        self.content_layout.addWidget(header)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Source", "Published", "Headline"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setWordWrap(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setDefaultSectionSize(120)
        self._table.setAlternatingRowColors(True)
        self._table.cellDoubleClicked.connect(self._open_link)

        self.content_layout.addWidget(self._table, stretch=1)
        self._items: list[NewsItem] = []

        self._schedule_initial_refresh()

    def _schedule_initial_refresh(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._refresh())
        except RuntimeError:
            pass

    def _refresh_clicked(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._refresh())
        except RuntimeError:
            asyncio.run(self._refresh())

    async def _refresh(self) -> None:
        self._set_loading(True)
        self._status_label.setText("Refreshing news feeds…")
        self._refresh_button.setEnabled(False)
        self._items = await NewsFeedAdapter.fetch_items()
        self._render_items()
        if self._items:
            self._status_label.setText(
                f"{len(self._items)} headlines | Last refresh: {self._get_timestamp()}"
            )
        else:
            self._status_label.setText(
                "No headlines available. Check your internet connection or try again."
            )
        self._refresh_button.setEnabled(True)
        self._set_loading(False)

    def _get_timestamp(self) -> str:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return now.strftime("%H:%M:%S UTC")

    def _render_items(self) -> None:
        if not self._items:
            self._table.setRowCount(1)
            empty_msg = QTableWidgetItem("No news available. Press REFRESH or check connection.")
            empty_msg.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_msg.setForeground(QColor(PALETTE.FG_MUTED))
            self._table.setItem(0, 0, empty_msg)
            self._table.setSpan(0, 0, 1, 3)
            return

        self._table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            source_item = QTableWidgetItem(item.source)
            source_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, source_item)

            published_item = QTableWidgetItem(item.published or "—")
            published_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, published_item)

            headline_item = QTableWidgetItem(item.title)
            headline_item.setToolTip(item.summary or item.link)
            headline_item.setData(Qt.ItemDataRole.UserRole, item.link)
            self._table.setItem(row, 2, headline_item)

    def _open_link(self, row: int, column: int) -> None:
        item = self._table.item(row, 2)
        if item is None:
            return
        link = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(link, str) and link:
            QDesktopServices.openUrl(QUrl(link))

    def _set_loading(self, loading: bool) -> None:
        if loading:
            self._status_label.setText("Loading news feeds…")
        self._refresh_button.setEnabled(not loading)

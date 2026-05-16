"""Base panel widget providing Bloomberg-style chrome for all panels.

Every panel in the terminal inherits from :class:`BasePanel`.  The base
class provides:

- Amber header bar with panel title and optional subtitle
- Active/inactive border state toggling
- Stale data indicator (amber ⚠ when data TTL exceeded)
- Consistent padding and background
- ``content_area`` — a plain :class:`QWidget` for child content

Usage
-----
::

    class MyPanel(BasePanel):
        def __init__(self, cache):
            super().__init__(title="MY PANEL", subtitle="INSTRUMENT")
            label = QLabel("Hello")
            self.content_layout.addWidget(label)
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from energy_terminal.ui.theme import PALETTE


class BasePanel(QWidget):  # type: ignore[misc]
    """Bloomberg-style panel with amber header chrome.

    Parameters
    ----------
    title : str
        Panel title shown in the amber header bar (uppercased automatically).
    subtitle : str
        Secondary label shown at right of header (e.g. current symbol).
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._title = title.upper()
        self._stale = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        # Panel frame with border
        self._frame = QFrame()
        self._frame.setObjectName("panel")
        self._frame.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self._frame)

        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        # Header bar
        frame_layout.addWidget(self._build_header(title, subtitle))

        # Content area — panels add their widgets here
        self.content_area = QWidget()
        self.content_area.setStyleSheet(f"background-color: {PALETTE.BG_PANEL};")
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(4)
        frame_layout.addWidget(self.content_area, stretch=1)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def _build_header(self, title: str, subtitle: str) -> QWidget:
        """Build the amber header bar."""
        header = QWidget()
        header.setFixedHeight(24)
        header.setStyleSheet(f"background-color: {PALETTE.BG_HEADER};")

        h = QHBoxLayout(header)
        h.setContentsMargins(6, 0, 6, 0)
        h.setSpacing(6)

        # Title
        self._title_label = QLabel(title.upper())
        self._title_label.setObjectName("panel_header")
        self._title_label.setStyleSheet(
            f"color: {PALETTE.AMBER}; font-weight: bold; " f"font-size: 11px; letter-spacing: 1px;"
        )
        h.addWidget(self._title_label)

        h.addStretch()

        # Subtitle (right-aligned, e.g. current symbol)
        self._subtitle_label = QLabel(subtitle)
        self._subtitle_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._subtitle_label.setStyleSheet(f"color: {PALETTE.FG_SECONDARY}; font-size: 10px;")
        h.addWidget(self._subtitle_label)

        # Stale indicator (hidden by default)
        self._stale_label = QLabel("⚠ STALE")
        self._stale_label.setStyleSheet(
            f"color: {PALETTE.YELLOW}; font-size: 10px; font-weight: bold;"
        )
        self._stale_label.setVisible(False)
        h.addWidget(self._stale_label)

        return header

    # ------------------------------------------------------------------
    # Public state API
    # ------------------------------------------------------------------

    def set_subtitle(self, text: str) -> None:
        """Update the panel subtitle (e.g. current symbol being viewed).

        Parameters
        ----------
        text : str
            New subtitle text.
        """
        self._subtitle_label.setText(text)

    def set_stale(self, stale: bool) -> None:
        """Show or hide the stale data indicator.

        Parameters
        ----------
        stale : bool
            ``True`` to show the amber ⚠ STALE badge.
        """
        self._stale = stale
        self._stale_label.setVisible(stale)

    def set_active(self, active: bool) -> None:
        """Toggle the active panel border (amber vs grey).

        Parameters
        ----------
        active : bool
            ``True`` draws the amber border; ``False`` the default grey.
        """
        obj = "panel_active" if active else "panel"
        self._frame.setObjectName(obj)
        border = PALETTE.BORDER_ACTIVE if active else PALETTE.BORDER
        self._frame.setStyleSheet(f"border: 1px solid {border};")

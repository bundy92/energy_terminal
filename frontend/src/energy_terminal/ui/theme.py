"""Bloomberg-inspired dark terminal colour palette and Qt stylesheet.

All UI components import from this module so the palette can be changed
in a single place.  The ``bloomberg_dark`` theme matches the canonical
Bloomberg Terminal colour scheme as closely as PyQt6 allows.

Usage
-----
::

    from energy_terminal.ui.theme import PALETTE, apply_theme
    apply_theme(app)

Colour reference
----------------
+-------------------+-------------+------------------------------------------+
| Token             | Hex         | Usage                                    |
+===================+=============+==========================================+
| BG_PRIMARY        | #000000     | Main window background                   |
| BG_PANEL          | #0D0D0D     | Panel / card background                  |
| BG_HEADER         | #1A1A1A     | Panel header bar                         |
| BG_INPUT          | #0A0A0A     | Command bar background                   |
| BG_SELECTED       | #1C2E4A     | Selected row / active panel border       |
| FG_PRIMARY        | #E8E8E8     | Primary text                             |
| FG_SECONDARY      | #A0A0A0     | Secondary / label text                   |
| FG_MUTED          | #5A5A5A     | Disabled / placeholder text              |
| AMBER             | #FF8C00     | Bloomberg amber — primary accent         |
| POSITIVE          | #00C176     | Positive price change (green)            |
| NEGATIVE          | #FF3B3B     | Negative price change (red)              |
| NEUTRAL           | #7B8FA8     | Flat / unchanged                         |
| BORDER            | #2A2A2A     | Panel borders and dividers               |
| BORDER_ACTIVE     | #FF8C00     | Active panel / focused widget border     |
| CYAN              | #00B4D8     | Data labels, series 2                    |
| MAGENTA           | #E040FB     | Alerts, series 3                         |
| YELLOW            | #FFD600     | Warnings, series 4                       |
+-------------------+-------------+------------------------------------------+
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Colour tokens
# ---------------------------------------------------------------------------

class PALETTE:
    """Static colour token namespace."""

    # Backgrounds
    BG_PRIMARY   = "#000000"
    BG_PANEL     = "#0D0D0D"
    BG_HEADER    = "#1A1A1A"
    BG_INPUT     = "#0A0A0A"
    BG_SELECTED  = "#1C2E4A"
    BG_ALT_ROW   = "#111111"

    # Foregrounds
    FG_PRIMARY   = "#E8E8E8"
    FG_SECONDARY = "#A0A0A0"
    FG_MUTED     = "#5A5A5A"

    # Accents
    AMBER        = "#FF8C00"
    POSITIVE     = "#00C176"
    NEGATIVE     = "#FF3B3B"
    NEUTRAL      = "#7B8FA8"
    CYAN         = "#00B4D8"
    MAGENTA      = "#E040FB"
    YELLOW       = "#FFD600"
    WHITE        = "#FFFFFF"

    # Structural
    BORDER        = "#2A2A2A"
    BORDER_ACTIVE = "#FF8C00"

    # Chart series colours (consistent across all panels)
    SERIES = [
        "#FF8C00",  # amber   — primary series
        "#00C176",  # green   — secondary
        "#00B4D8",  # cyan    — tertiary
        "#E040FB",  # magenta — quaternary
        "#FFD600",  # yellow  — quinary
        "#FF3B3B",  # red     — senary
        "#A0A0A0",  # grey    — septenary
    ]


# ---------------------------------------------------------------------------
# Qt Stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = f"""
/* ================================================================
   Energy Terminal — Bloomberg Dark Theme
   ================================================================ */

QMainWindow, QWidget {{
    background-color: {PALETTE.BG_PRIMARY};
    color:            {PALETTE.FG_PRIMARY};
    font-family:      "Courier New", "Consolas", monospace;
    font-size:        12px;
}}

/* ---- Panels ---- */
QFrame#panel {{
    background-color: {PALETTE.BG_PANEL};
    border:           1px solid {PALETTE.BORDER};
}}

QFrame#panel_active {{
    background-color: {PALETTE.BG_PANEL};
    border:           1px solid {PALETTE.BORDER_ACTIVE};
}}

QLabel#panel_header {{
    background-color: {PALETTE.BG_HEADER};
    color:            {PALETTE.AMBER};
    font-weight:      bold;
    font-size:        11px;
    padding:          3px 6px;
    letter-spacing:   1px;
}}

QLabel#panel_subheader {{
    background-color: {PALETTE.BG_HEADER};
    color:            {PALETTE.FG_SECONDARY};
    font-size:        10px;
    padding:          2px 6px;
}}

/* ---- Command bar ---- */
QLineEdit#command_bar {{
    background-color: {PALETTE.BG_INPUT};
    color:            {PALETTE.AMBER};
    border:           1px solid {PALETTE.AMBER};
    border-radius:    0px;
    padding:          4px 8px;
    font-family:      "Courier New", monospace;
    font-size:        13px;
    font-weight:      bold;
}}

QLineEdit#command_bar:focus {{
    border:  1px solid {PALETTE.WHITE};
    color:   {PALETTE.WHITE};
}}

/* ---- Tables ---- */
QTableWidget, QTableView {{
    background-color:    {PALETTE.BG_PANEL};
    alternate-background-color: {PALETTE.BG_ALT_ROW};
    color:               {PALETTE.FG_PRIMARY};
    gridline-color:      {PALETTE.BORDER};
    border:              none;
    selection-background-color: {PALETTE.BG_SELECTED};
    selection-color:     {PALETTE.WHITE};
    font-size:           11px;
}}

QTableWidget::item, QTableView::item {{
    padding:  2px 6px;
    border:   none;
}}

QHeaderView::section {{
    background-color: {PALETTE.BG_HEADER};
    color:            {PALETTE.FG_SECONDARY};
    border:           none;
    border-bottom:    1px solid {PALETTE.BORDER};
    padding:          3px 6px;
    font-size:        10px;
    font-weight:      bold;
    text-transform:   uppercase;
    letter-spacing:   0.5px;
}}

/* ---- Scroll bars ---- */
QScrollBar:vertical {{
    background:  {PALETTE.BG_PANEL};
    width:       8px;
    margin:      0;
}}
QScrollBar::handle:vertical {{
    background:  {PALETTE.BORDER};
    min-height:  20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {PALETTE.FG_MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {PALETTE.BG_PANEL};
    height:     8px;
    margin:     0;
}}
QScrollBar::handle:horizontal {{
    background: {PALETTE.BORDER};
    min-width:  20px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {PALETTE.FG_MUTED};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ---- Tabs ---- */
QTabWidget::pane {{
    border:           1px solid {PALETTE.BORDER};
    background-color: {PALETTE.BG_PANEL};
}}

QTabBar::tab {{
    background-color: {PALETTE.BG_HEADER};
    color:            {PALETTE.FG_SECONDARY};
    border:           none;
    border-right:     1px solid {PALETTE.BORDER};
    padding:          5px 14px;
    font-size:        11px;
    font-weight:      bold;
}}

QTabBar::tab:selected {{
    background-color: {PALETTE.BG_PRIMARY};
    color:            {PALETTE.AMBER};
    border-top:       2px solid {PALETTE.AMBER};
}}

QTabBar::tab:hover {{
    background-color: {PALETTE.BG_PANEL};
    color:            {PALETTE.FG_PRIMARY};
}}

/* ---- Buttons ---- */
QPushButton {{
    background-color: {PALETTE.BG_HEADER};
    color:            {PALETTE.FG_SECONDARY};
    border:           1px solid {PALETTE.BORDER};
    padding:          4px 10px;
    font-size:        11px;
}}
QPushButton:hover {{
    background-color: {PALETTE.BG_SELECTED};
    color:            {PALETTE.FG_PRIMARY};
    border-color:     {PALETTE.FG_MUTED};
}}
QPushButton:pressed {{
    background-color: {PALETTE.AMBER};
    color:            {PALETTE.BG_PRIMARY};
}}

/* ---- ComboBox ---- */
QComboBox {{
    background-color: {PALETTE.BG_HEADER};
    color:            {PALETTE.FG_PRIMARY};
    border:           1px solid {PALETTE.BORDER};
    padding:          3px 8px;
    font-size:        11px;
}}
QComboBox:hover  {{ border-color: {PALETTE.FG_MUTED}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background-color: {PALETTE.BG_HEADER};
    color:            {PALETTE.FG_PRIMARY};
    selection-background-color: {PALETTE.BG_SELECTED};
}}

/* ---- Status bar ---- */
QStatusBar {{
    background-color: {PALETTE.BG_HEADER};
    color:            {PALETTE.FG_SECONDARY};
    border-top:       1px solid {PALETTE.BORDER};
    font-size:        10px;
    padding:          1px 6px;
}}
QStatusBar::item {{ border: none; }}

/* ---- Splitter ---- */
QSplitter::handle {{
    background-color: {PALETTE.BORDER};
    width:            2px;
    height:           2px;
}}
QSplitter::handle:hover {{
    background-color: {PALETTE.AMBER};
}}

/* ---- ToolTip ---- */
QToolTip {{
    background-color: {PALETTE.BG_HEADER};
    color:            {PALETTE.FG_PRIMARY};
    border:           1px solid {PALETTE.AMBER};
    font-size:        11px;
    padding:          4px 8px;
}}

/* ---- Specific labels ---- */
QLabel#price_up   {{ color: {PALETTE.POSITIVE}; font-weight: bold; }}
QLabel#price_down {{ color: {PALETTE.NEGATIVE}; font-weight: bold; }}
QLabel#price_flat {{ color: {PALETTE.NEUTRAL};  }}
QLabel#alert_label {{ color: {PALETTE.MAGENTA}; font-weight: bold; }}
QLabel#stale_label {{ color: {PALETTE.YELLOW};  }}
"""


def apply_theme(app: QApplication) -> None:
    """Apply the Bloomberg dark theme to a QApplication.

    Parameters
    ----------
    app : QApplication
        The running Qt application instance.
    """
    app.setStyleSheet(STYLESHEET)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor(PALETTE.BG_PRIMARY))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor(PALETTE.FG_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base,            QColor(PALETTE.BG_PANEL))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(PALETTE.BG_ALT_ROW))
    palette.setColor(QPalette.ColorRole.Text,            QColor(PALETTE.FG_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button,          QColor(PALETTE.BG_HEADER))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor(PALETTE.FG_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor(PALETTE.BG_SELECTED))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(PALETTE.WHITE))
    palette.setColor(QPalette.ColorRole.Link,            QColor(PALETTE.AMBER))
    app.setPalette(palette)

"""Energy Terminal application entry point.

Bootstraps the Qt event loop with ``qasync`` so that asyncio coroutines
(WebSocket client, direct feed poller) share the same event loop as the
PyQt6 UI without blocking the GUI thread.

Usage
-----
::

    # Via installed script
    energy-terminal

    # Direct
    python -m energy_terminal.main
"""

from __future__ import annotations

import asyncio
import sys

import structlog
from PyQt6.QtWidgets import QApplication

import qasync

from energy_terminal.config import settings
from energy_terminal.ui.theme import apply_theme
from energy_terminal.ui.main_window import MainWindow

log = structlog.get_logger(__name__)


def _configure_logging() -> None:
    """Configure structlog with console renderer."""
    import logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(message)s",
    )
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def _async_main(window: MainWindow) -> None:
    """Run the async subsystems alongside the Qt event loop."""
    await window.start_async()


def main() -> None:
    """Application entry point."""
    _configure_logging()
    log.info("Energy Terminal starting", version="0.1.0")

    app = QApplication(sys.argv)
    app.setApplicationName("Energy Terminal")
    app.setOrganizationName("EnergyTerminal")

    apply_theme(app)

    loop   = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    with loop:
        loop.run_until_complete(_async_main(window))
        loop.run_forever()


if __name__ == "__main__":
    main()

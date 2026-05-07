"""Direct yfinance feed — fallback when the Erlang gateway is unavailable.

Used automatically by :class:`~energy_terminal.data.client.GatewayClient`
when it cannot establish a WebSocket connection.  Also available
standalone for historical data fetching.

Examples
--------
>>> feed = DirectFeed()
>>> bars = await feed.fetch_ohlcv("CL=F", period="1y", interval="1d")
>>> len(bars) > 0
True
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
import yfinance as yf

from energy_terminal.data.models import (
    EventSource,
    EventType,
    OHLCVBar,
    Tick,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Instrument catalogue
# ---------------------------------------------------------------------------

#: Default instrument list, mirroring the Erlang gateway configuration.
DEFAULT_INSTRUMENTS: list[str] = [
    # Crude
    "CL=F", "BZ=F",
    # Natural Gas
    "NG=F",
    # Refined Products
    "RB=F", "HO=F",
    # Carbon / Clean Energy ETFs
    "ICLN", "XLE",
    # FX
    "EURUSD=X", "DX-Y.NYB",
    # Energy equities
    "XOM", "CVX", "BP", "SHEL", "TTE",
    # Agricultural / feedstock crossovers
    "ZC=F", "ZS=F",
    # Freight proxy
    "BDRY",
]

#: Human-readable display names for known tickers.
INSTRUMENT_NAMES: dict[str, str] = {
    "CL=F":     "WTI Crude",
    "BZ=F":     "Brent Crude",
    "NG=F":     "Natural Gas (HH)",
    "RB=F":     "RBOB Gasoline",
    "HO=F":     "Heating Oil (ULSD)",
    "ICLN":     "Clean Energy ETF",
    "XLE":      "Energy Sector ETF",
    "EURUSD=X": "EUR/USD",
    "DX-Y.NYB": "USD Index",
    "XOM":      "ExxonMobil",
    "CVX":      "Chevron",
    "BP":       "BP plc",
    "SHEL":     "Shell plc",
    "TTE":      "TotalEnergies",
    "ZC=F":     "Corn Futures",
    "ZS=F":     "Soybean Futures",
    "BDRY":     "Dry Bulk ETF",
}


class DirectFeed:
    """yfinance-backed data feed used as an offline fallback.

    Parameters
    ----------
    instruments : list[str], optional
        List of Yahoo Finance tickers to monitor.  Defaults to
        :data:`DEFAULT_INSTRUMENTS`.
    poll_interval_s : float
        Polling interval in seconds for the live tick loop.

    Notes
    -----
    yfinance does not provide true real-time data; delays of 15–20 min
    apply for most futures contracts.  A staleness indicator is set on
    every :class:`~energy_terminal.data.models.Tick` via the ``source``
    field being :attr:`~energy_terminal.data.models.EventSource.DIRECT`.
    """

    def __init__(
        self,
        instruments: list[str] | None = None,
        poll_interval_s: float = 30.0,
    ) -> None:
        self._instruments    = instruments or DEFAULT_INSTRUMENTS
        self._poll_interval  = poll_interval_s
        self._running        = False
        self._tick_handlers: list[Any] = []

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def on_tick(self, handler: Any) -> None:
        """Register a tick callback (same signature as GatewayClient)."""
        self._tick_handlers.append(handler)

    # ------------------------------------------------------------------
    # Live polling loop
    # ------------------------------------------------------------------

    async def start_polling(self) -> None:
        """Start the live polling loop.  Runs until ``stop()`` is called."""
        self._running = True
        log.info("DirectFeed polling started", instruments=len(self._instruments))
        while self._running:
            await self._poll_once()
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False

    async def _poll_once(self) -> None:
        """Fetch latest quotes for all instruments and dispatch ticks."""
        loop = asyncio.get_event_loop()
        try:
            tickers = await loop.run_in_executor(None, self._fetch_quotes)
            for tick in tickers:
                for handler in self._tick_handlers:
                    handler(tick)
        except Exception as exc:  # noqa: BLE001
            log.error("DirectFeed poll error", exc=str(exc))

    def _fetch_quotes(self) -> list[Tick]:
        """Synchronous yfinance bulk quote fetch (runs in executor)."""
        symbols = " ".join(self._instruments)
        try:
            data = yf.download(
                tickers=symbols,
                period="1d",
                interval="1m",
                progress=False,
                auto_adjust=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("yfinance download error", exc=str(exc))
            return []

        ticks: list[Tick] = []
        ts_ms = int(time.time() * 1000)

        # Multi-ticker download returns MultiIndex columns
        if isinstance(data.columns, __import__("pandas").MultiIndex):
            for sym in self._instruments:
                try:
                    row = data.xs(sym, axis=1, level=1).iloc[-1]
                    tick = Tick(
                        type=EventType.TICK,
                        source=EventSource.DIRECT,
                        symbol=sym,
                        timestamp=ts_ms,
                        open=float(row.get("Open", 0)),
                        high=float(row.get("High", 0)),
                        low=float(row.get("Low", 0)),
                        close=float(row.get("Close", 0)),
                        volume=int(row.get("Volume", 0)),
                    )
                    ticks.append(tick)
                except Exception:  # noqa: BLE001
                    pass
        return ticks

    # ------------------------------------------------------------------
    # Historical OHLCV
    # ------------------------------------------------------------------

    async def fetch_ohlcv(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> list[OHLCVBar]:
        """Fetch historical OHLCV bars for a single symbol.

        Parameters
        ----------
        symbol : str
            Yahoo Finance ticker.
        period : str
            yfinance period string (``"1d"``, ``"5d"``, ``"1mo"``,
            ``"3mo"``, ``"6mo"``, ``"1y"``, ``"2y"``, ``"5y"``).
        interval : str
            Bar interval (``"1m"``, ``"5m"``, ``"1h"``, ``"1d"``,
            ``"1wk"``, ``"1mo"``).

        Returns
        -------
        list[OHLCVBar]
            List of OHLCV bars sorted ascending by timestamp.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._fetch_ohlcv_sync, symbol, period, interval
        )

    def _fetch_ohlcv_sync(
        self,
        symbol: str,
        period: str,
        interval: str,
    ) -> list[OHLCVBar]:
        """Synchronous yfinance history fetch (runs in executor)."""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval, auto_adjust=True)
            bars = []
            for ts, row in df.iterrows():
                bars.append(OHLCVBar(
                    timestamp=int(ts.timestamp() * 1000),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row.get("Volume", 0)),
                ))
            return bars
        except Exception as exc:  # noqa: BLE001
            log.error("yfinance history error", symbol=symbol, exc=str(exc))
            return []

    # ------------------------------------------------------------------
    # Instrument metadata
    # ------------------------------------------------------------------

    @staticmethod
    def display_name(symbol: str) -> str:
        """Return human-readable display name for a ticker.

        Parameters
        ----------
        symbol : str
            Yahoo Finance ticker.

        Returns
        -------
        str
            Display name, falling back to the symbol itself if unknown.
        """
        return INSTRUMENT_NAMES.get(symbol, symbol)

"""LNG-specific feed adapter for JKM, TTF, and NBP instruments.

This adapter normalizes common LNG tickers and provides a pluggable
fetching interface for LNG benchmark data.
"""

from __future__ import annotations

import time
from collections.abc import Iterable

import pandas as pd
import structlog
import yfinance as yf

from energy_terminal.data.models import EventSource, EventType, OHLCVBar, Tick

log = structlog.get_logger(__name__)

LNG_SYMBOL_ALIASES: dict[str, str] = {
    "JKM": "JKM=F",
    "TTF": "TTF=F",
    "NBP": "NBP=F",
    "JKM=F": "JKM=F",
    "TTF=F": "TTF=F",
    "NBP=F": "NBP=F",
}

LNG_INSTRUMENT_NAMES: dict[str, str] = {
    "JKM=F": "Japan Kerosene Marker (JKM)",
    "TTF=F": "Dutch TTF Gas",
    "NBP=F": "UK NBP Gas",
}

DEFAULT_LNG_INSTRUMENTS: list[str] = list(LNG_INSTRUMENT_NAMES)


def normalize_symbol(symbol: str) -> str:
    return LNG_SYMBOL_ALIASES.get(symbol.upper().strip(), symbol.upper().strip())


class LNGFeedAdapter:
    """Adapter for LNG benchmark tickers.

    This is currently a lightweight yfinance-backed adapter with
    dedicated symbol normalization support.
    """

    @classmethod
    def supports(cls, symbol: str) -> bool:
        return normalize_symbol(symbol) in LNG_INSTRUMENT_NAMES

    @classmethod
    def supported_symbols(cls) -> list[str]:
        return sorted(DEFAULT_LNG_INSTRUMENTS)

    async def fetch_quote(self, symbol: str) -> Tick | None:
        symbol = normalize_symbol(symbol)
        if not self.supports(symbol):
            return None

        ts_ms = int(time.time() * 1000)
        return await self._fetch_single_quote(symbol, ts_ms)

    async def fetch_ohlcv(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> list[OHLCVBar]:
        symbol = normalize_symbol(symbol)
        if not self.supports(symbol):
            return []
        return await self._fetch_ohlcv_sync(symbol, period, interval)

    async def fetch_quotes(self, symbols: Iterable[str]) -> list[Tick]:
        symbols = [normalize_symbol(sym) for sym in symbols if self.supports(sym)]
        if not symbols:
            return []

        try:
            data = yf.download(
                tickers=" ".join(symbols),
                period="1d",
                interval="1m",
                progress=False,
                auto_adjust=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("LNGFeedAdapter download error", exc=str(exc))
            return []

        ts_ms = int(time.time() * 1000)
        ticks: list[Tick] = []

        if isinstance(data.columns, pd.MultiIndex):
            for sym in symbols:
                tick = self._parse_bulk_quote(data, sym, ts_ms)
                if tick is not None:
                    ticks.append(tick)
        else:
            for sym in symbols:
                tick = self._fetch_single_quote(sym, ts_ms)
                if tick is not None:
                    ticks.append(tick)
        return ticks

    def _parse_bulk_quote(self, data: pd.DataFrame, sym: str, ts_ms: int) -> Tick | None:
        try:
            row = data.xs(sym, axis=1, level=1).iloc[-1]
            if row.isnull().all():
                return None
            close = float(row.get("Close", 0))
            open_ = float(row.get("Open", close))
            high = float(row.get("High", close))
            low = float(row.get("Low", close))
            prev_close = float(row.get("Close", close))
            volume = int(row.get("Volume", 0))
            change = close - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0.0
            return Tick(
                type=EventType.TICK,
                source=EventSource.DIRECT,
                symbol=sym,
                timestamp=ts_ms,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                change=change,
                change_pct=change_pct,
            )
        except Exception:  # noqa: BLE001
            return None

    def _fetch_single_quote(self, sym: str, ts_ms: int) -> Tick | None:
        try:
            ticker = yf.Ticker(sym)
            info = ticker.fast_info
            last = info.get("lastPrice") or info.get("previousClose")
            if last is None:
                last = info.get("regularMarketPreviousClose")
            if last is None:
                return None

            prev_close = (
                info.get("previousClose") or info.get("regularMarketPreviousClose") or float(last)
            )
            open_ = info.get("open") or float(last)
            high = info.get("dayHigh") or float(last)
            low = info.get("dayLow") or float(last)
            volume = int(info.get("lastVolume", 0) or 0)
            change = float(last) - float(prev_close)
            change_pct = (change / float(prev_close) * 100) if prev_close else 0.0
            return Tick(
                type=EventType.TICK,
                source=EventSource.DIRECT,
                symbol=sym,
                timestamp=ts_ms,
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(last),
                volume=volume,
                change=change,
                change_pct=change_pct,
            )
        except Exception:  # noqa: BLE001
            return None

    async def _fetch_ohlcv_sync(
        self,
        symbol: str,
        period: str,
        interval: str,
    ) -> list[OHLCVBar]:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval, auto_adjust=True)
            bars: list[OHLCVBar] = []
            for ts, row in df.iterrows():
                bars.append(
                    OHLCVBar(
                        timestamp=int(ts.timestamp() * 1000),
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=int(row.get("Volume", 0)),
                    )
                )
            return bars
        except Exception as exc:  # noqa: BLE001
            log.error("LNGFeedAdapter history error", symbol=symbol, exc=str(exc))
            return []

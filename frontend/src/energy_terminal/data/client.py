"""Async WebSocket client for the Erlang Energy Gateway.

Maintains a persistent connection, handles reconnection with exponential
back-off, and dispatches incoming events to registered callbacks.

When the gateway is unavailable the client falls back to the
``DirectFeedClient`` which polls Yahoo Finance and EIA directly.

Usage
-----
::

    client = GatewayClient()
    client.on_tick(my_tick_handler)
    client.on_fundamental(my_fund_handler)
    await client.connect()      # runs until cancelled
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

import structlog
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.legacy.protocol import WebSocketClientProtocol

from energy_terminal.config import settings
from energy_terminal.data.models import (
    EventSource,
    EventType,
    FundamentalReading,
    MacroReading,
    Tick,
    WeatherReading,
)

log = structlog.get_logger(__name__)

# Type aliases for handler callbacks
TickHandler = Callable[[Tick], None]
FundamentalHandler = Callable[[FundamentalReading], None]
WeatherHandler = Callable[[WeatherReading], None]
MacroHandler = Callable[[MacroReading], None]


class GatewayClient:
    """WebSocket client for the Erlang data gateway.

    Parameters
    ----------
    url : str, optional
        Gateway WebSocket URL.  Defaults to ``settings.gateway_url``.
    reconnect_delay : float, optional
        Base reconnect delay in seconds (doubles on each failure up to 60 s).

    Notes
    -----
    All handler callbacks are invoked synchronously in the event loop.
    Heavy processing should be offloaded to an executor.
    """

    def __init__(
        self,
        url: str | None = None,
        reconnect_delay: float | None = None,
    ) -> None:
        self._url = url or settings.gateway_url
        self._base_delay = reconnect_delay or settings.gateway_reconnect_delay_s
        self._ws: Any = None
        self._running = False
        self._connected = False
        self._last_event_ts = 0.0
        self._staleness_secs = 120.0

        self._tick_handlers: list[TickHandler] = []
        self._fundamental_handlers: list[FundamentalHandler] = []
        self._weather_handlers: list[WeatherHandler] = []
        self._macro_handlers: list[MacroHandler] = []

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def on_tick(self, handler: TickHandler) -> None:
        """Register a callback for price tick events.

        Parameters
        ----------
        handler : TickHandler
            Callable receiving a :class:`~energy_terminal.data.models.Tick`.
        """
        self._tick_handlers.append(handler)

    def on_fundamental(self, handler: FundamentalHandler) -> None:
        """Register a callback for fundamental data events."""
        self._fundamental_handlers.append(handler)

    def on_weather(self, handler: WeatherHandler) -> None:
        """Register a callback for weather events."""
        self._weather_handlers.append(handler)

    def on_macro(self, handler: MacroHandler) -> None:
        """Register a callback for macro economic events."""
        self._macro_handlers.append(handler)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Maintain a persistent WebSocket connection with reconnect logic.

        Runs until ``stop()`` is called.  Reconnect delay doubles on each
        failure (capped at 60 seconds).
        """
        self._running = True
        delay = self._base_delay

        while self._running:
            try:
                log.info("Connecting to gateway", url=self._url)
                async with websockets.connect(
                    self._url,
                    ping_interval=20,
                    ping_timeout=10,
                    open_timeout=10,
                ) as ws:
                    self._ws = ws
                    self._connected = True
                    delay = self._base_delay  # reset on success
                    log.info("Gateway connected")
                    await self._receive_loop(ws)

            except (ConnectionClosed, WebSocketException, OSError) as exc:
                self._connected = False
                self._ws = None
                log.warning("Gateway disconnected", reason=str(exc), retry_in=delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)

    async def stop(self) -> None:
        """Gracefully stop the connection loop."""
        self._running = False
        if self._ws is not None:
            await self._ws.close()

    async def send_command(self, cmd: dict[str, Any]) -> None:
        """Send a JSON command to the gateway.

        Parameters
        ----------
        cmd : dict
            Command dictionary (e.g. ``{"cmd": "ping"}``).
        """
        if self._ws is not None and self._connected:
            await self._ws.send(json.dumps(cmd))

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Whether the WebSocket is currently connected."""
        return self._connected

    @property
    def is_stale(self) -> bool:
        """Whether no event has been received recently (> staleness threshold)."""
        if self._last_event_ts == 0.0:
            return False
        return (time.time() - self._last_event_ts) > self._staleness_secs

    # ------------------------------------------------------------------
    # Internal receive loop
    # ------------------------------------------------------------------

    async def _receive_loop(self, ws: WebSocketClientProtocol) -> None:
        """Read messages until the connection closes."""
        async for raw in ws:
            self._last_event_ts = time.time()
            try:
                self._dispatch(json.loads(raw))
            except Exception as exc:  # noqa: BLE001
                log.error("Event dispatch error", exc=str(exc))

    def _dispatch(self, msg: dict[str, Any]) -> None:
        """Route a parsed message to the appropriate handlers."""
        event_type = msg.get("type")
        payload = msg.get("payload", {})
        source_str = msg.get("source", "direct")
        symbol = msg.get("symbol", "")
        timestamp = msg.get("timestamp", int(time.time() * 1000))

        try:
            source = EventSource(source_str)
        except ValueError:
            source = EventSource.DIRECT

        if event_type == EventType.TICK:
            tick = Tick(
                source=source,
                symbol=symbol,
                timestamp=timestamp,
                open=payload.get("open", 0.0),
                high=payload.get("high", 0.0),
                low=payload.get("low", 0.0),
                close=payload.get("close", 0.0),
                volume=payload.get("volume", 0),
                change=payload.get("change", 0.0),
                change_pct=payload.get("change_pct", 0.0),
            )
            for tick_handler in self._tick_handlers:
                tick_handler(tick)

        elif event_type == EventType.FUNDAMENTAL:
            fundamental_reading = FundamentalReading(
                source=source,
                symbol=symbol,
                timestamp=timestamp,
                series=payload.get("series", symbol),
                value=payload.get("value"),
                period=payload.get("period", ""),
                unit=payload.get("unit", ""),
            )
            for fundamental_handler in self._fundamental_handlers:
                fundamental_handler(fundamental_reading)

        elif event_type == EventType.WEATHER:
            weather_reading = WeatherReading(
                source=source,
                symbol=symbol,
                timestamp=timestamp,
                location=payload.get("location", symbol),
                temp_c=payload.get("temp_c", 0.0),
                hdd=payload.get("hdd", 0.0),
                cdd=payload.get("cdd", 0.0),
                forecast_7d=payload.get("forecast_7d", []),
            )
            for weather_handler in self._weather_handlers:
                weather_handler(weather_reading)

        elif event_type == EventType.MACRO:
            macro_reading = MacroReading(
                source=source,
                symbol=symbol,
                timestamp=timestamp,
                series=payload.get("series", symbol),
                value=payload.get("value"),
                date=payload.get("date", ""),
            )
            for macro_handler in self._macro_handlers:
                macro_handler(macro_reading)

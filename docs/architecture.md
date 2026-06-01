# Architecture

## Overview

Energy Terminal is a two-process desktop application. The Elixir/OTP
backend acts as a fault-tolerant data gateway; the Python frontend
provides the Bloomberg-style UI, analytics engine, and local cache.

---

## Component Diagram

```
╔══════════════════════════════════════════════════════════════════════╗
║                    PYTHON DESKTOP APPLICATION                        ║
║                                                                      ║
║  ┌──────────────────────────────────────────────────────────────┐   ║
║  │                     PyQt6 UI Layer                           │   ║
║  │                                                              │   ║
║  │  ┌─────────┐ ┌───────┐ ┌──────────┐ ┌────────┐ ┌────────┐  │   ║
║  │  │ Market  │ │ Chart │ │Analytics │ │  Risk  │ │ Alerts │  │   ║
║  │  │ Panel   │ │ Panel │ │  Panel   │ │ Panel  │ │ Panel  │  │   ║
║  │  └─────────┘ └───────┘ └──────────┘ └────────┘ └────────┘  │   ║
║  │                                                              │   ║
║  │  ┌─────────────────────────────────────────────────────┐    │   ║
║  │  │           Main Window (command bar, grid, status)   │    │   ║
║  │  └─────────────────────────────────────────────────────┘    │   ║
║  └───────────────────────────┬──────────────────────────────────┘  ║
║                              │                                      ║
║  ┌───────────────────────────▼──────────────────────────────────┐  ║
║  │                   Analytics Engine                           │  ║
║  │   technical.py   fundamental.py   risk.py                   │  ║
║  │   (RSI/MACD/BB)  (crack/spark)    (VaR/CVaR/corr)          │  ║
║  └────────────────────┬──────────────────────────────────────────┘  ║
║                       │                                              ║
║  ┌────────────────────▼──────────────────┐  ┌───────────────────┐  ║
║  │           GatewayClient               │  │   DirectFeed      │  ║
║  │   (asyncio WebSocket, reconnect)      │  │   (yfinance,      │  ║
║  │   Pydantic message validation         │  │    fallback)      │  ║
║  └────────────────────┬──────────────────┘  └────────┬──────────┘  ║
║                       │  primary                      │ fallback    ║
║  ┌────────────────────▼──────────────────────────────▼──────────┐  ║
║  │                  TimeSeriesCache (DuckDB)                    │  ║
║  │   ohlcv · fundamental · weather · audit_log                 │  ║
║  └──────────────────────────────────────────────────────────────┘  ║
╚══════════════════════════════╤═══════════════════════════════════════╝
                               │ WebSocket JSON
                               │ ws://localhost:8765/ws
╔══════════════════════════════▼═══════════════════════════════════════╗
║                  ELIXIR/OTP DATA GATEWAY                             ║
║                                                                      ║
║  ┌──────────────────────────────────────────────────────────────┐   ║
║  │  energy_gateway_sup  (one_for_one, intensity=5, period=10)   │   ║
║  │                                                              │   ║
║  │  ┌──────────┐  ┌─────────┐  ┌───────────┐  ┌────────────┐  │   ║
║  │  │ets_cache │  │rate_    │  │feed_      │  │data_router │  │   ║
║  │  │(ETS owner│  │limiter  │  │registry   │  │(pub/sub    │  │   ║
║  │  │public r/w│  │token bkt│  │PID lookup │  │fan-out)    │  │   ║
║  │  └──────────┘  └─────────┘  └───────────┘  └────────────┘  │   ║
║  │                                                              │   ║
║  │  ┌──────────────────────┐  ┌──────────────────────────────┐ │   ║
║  │  │  market_feed_server  │  │     eia_feed_server          │ │   ║
║  │  │  Yahoo Finance v7    │  │     US EIA Open Data         │ │   ║
║  │  │  OHLCV 30s poll      │  │     Weekly petroleum/gas     │ │   ║
║  │  └──────────────────────┘  └──────────────────────────────┘ │   ║
║  │  ┌──────────────────────┐  ┌──────────────────────────────┐ │   ║
║  │  │ weather_feed_server  │  │     fred_feed_server         │ │   ║
║  │  │ Open-Meteo HDD/CDD   │  │     Fed Reserve FRED         │ │   ║
║  │  │ 6 demand centres     │  │     USD/CPI/rates/IP         │ │   ║
║  │  └──────────────────────┘  └──────────────────────────────┘ │   ║
║  │  ┌──────────────────────┐                                    │   ║
║  │  │  iea_feed_server     │   (conditional on IEA_API_KEY)    │   ║
║  │  │  IEA global balance  │                                    │   ║
║  │  └──────────────────────┘                                    │   ║
║  └──────────────────────────────────────────────────────────────┘   ║
║                                                                      ║
║  ┌──────────────────────────────────────────────────────────────┐   ║
║  │  Cowboy HTTP/WebSocket server  (:8765)                       │   ║
║  │  ws_handler (per-connection subscriber) · /health endpoint   │   ║
║  └──────────────────────────────────────────────────────────────┘   ║
╚═══════════════════════════════════════════════════════════════════════╝
```

---

## Fault Tolerance Model

### Erlang side

- Every feed GenServer is supervised independently under `one_for_one`.
  A crash in `eia_feed_server` does not affect `market_feed_server` or
  the WebSocket handler.
- `ets_cache` is a separate process that *owns* the ETS tables. If a
  feed crashes and is restarted, it finds its data still in ETS rather
  than starting from a blank slate.
- `rate_limiter` survives feed crashes; token buckets are not reset on
  feed restart, preventing burst traffic after a reconnect.
- `iea_feed_server` deactivates itself when `IEA_API_KEY` is absent —
  it stays alive but never polls, preventing restart-storm loops.

### Python side

- `GatewayClient` reconnects with exponential back-off (5s → 10s → 20s
  → capped at 60s) on every `ConnectionClosed` or `OSError`.
- When the gateway cannot be reached, `MainWindow` transparently falls
  back to `DirectFeed` (yfinance direct HTTP polling, 15-20 min delayed).
- `TimeSeriesCache` seeds all panels from DuckDB on startup so the UI
  shows data immediately even if no live connection exists yet.
- Every panel marks itself ⚠ STALE if no tick has arrived within its
  configured TTL (default 120 s for price, 3 h for weather/macro).

---

## Data Flow

```
External API
    │
    ▼
Feed GenServer (rate-limited HTTP GET)
    │  normalise → internal schema
    ▼
ets_cache.put({tick, Symbol}, Tick)   ← fast, concurrent reads
    │
    ▼
data_router.publish(Event)
    │  sets:fold over subscriber PIDs
    ▼
ws_handler ! {data_event, Event}
    │  jsx:encode
    ▼
WebSocket frame → Python GatewayClient
    │  json.loads → Pydantic validation
    ▼
Handler callbacks (on_tick, on_fundamental, …)
    │
    ├── Panel.on_tick()         → UI update (Qt main thread)
    ├── AlertEngine.evaluate()  → alert check
    └── TimeSeriesCache.write_ohlcv()  → DuckDB persistence
```

---

## Technology Decisions

| Concern | Choice | Rationale |
|---|---|---|
| Real-time data routing | Erlang/OTP GenServer + ETS | Actor concurrency, supervisor fault isolation, ETS concurrent reads |
| WebSocket protocol | Cowboy + JSON | Simple, debuggable, language-agnostic; ETF considered but adds coupling |
| UI framework | PyQt6 | Mature, full-featured, native look on all platforms |
| Real-time charting | PyQtGraph | GPU-accelerated, shares Qt event loop without blocking |
| Analytics computation | NumPy + Pandas | Industry standard; composable with all Python ML/quant libraries |
| Data validation | Pydantic v2 | Fast, strict typing, excellent error messages |
| Persistent cache | DuckDB | Columnar, analytical SQL, zero-server, excellent Pandas interop |
| Configuration | Pydantic-settings + TOML | Env-var override, no secrets in files, self-documenting |
| Logging | structlog (Python) + lager (Erlang) | Structured JSON output, easy to pipe to ELK/Grafana |
| Testing | pytest + eunit + PropEr | TDD from day one; property tests catch invariant violations |

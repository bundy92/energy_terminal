# ⬡ Energy Terminal

A Bloomberg-inspired energy market analysis desktop terminal built on
an Elixir/OTP fault-tolerant data gateway and a Python/PyQt6 UI.

---

## Features

- **Real-time price feeds** — WTI, Brent, Natural Gas, RBOB, ULSD, energy equities, FX
- **Bloomberg-style dark UI** — command bar, F1–F8 panel switching, amber accent, status bar
- **Energy analytics** — 3-2-1/2-1-1 crack spreads, spark spreads, forward curve, seasonality
- **Technical indicators** — RSI, MACD, Bollinger Bands, ATR, OBV, VWAP, Stochastic
- **Risk metrics** — Historical/parametric VaR, CVaR, rolling correlation matrix, vol cone
- **Fundamental data** — EIA weekly petroleum status, IEA global supply/demand balance
- **Weather / HDD-CDD** — 6 key demand centres via Open-Meteo (free, no key required)
- **Macro overlays** — FRED USD index, CPI, real rates, industrial production
- **Alert engine** — ABOVE/BELOW/PCT_CHANGE/SPREAD_WIDE with audit log
- **Local DuckDB cache** — Offline mode; seeds all panels on startup from persisted data
- **Elixir/OTP backend** — Supervised feeds, token-bucket rate limiting, ETS cache, pub/sub

---

## Architecture

```
Python UI (PyQt6)  ←—WebSocket JSON—→  Elixir/OTP Gateway
     │                                       │
  DuckDB cache                        ETS + Cowboy
  AlertEngine                    Yahoo Finance · EIA · IEA
  Analytics                       Open-Meteo · FRED
```

See [`docs/architecture.md`](docs/architecture.md) for the full component diagram.

---

## Requirements

| Component | Version |
|-----------|---------|
| Python    | ≥ 3.11  |
| Elixir    | ≥ 1.15  |
| Erlang/OTP| ≥ 26    |
| mix       | ≥ 1.15  |

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/your-org/energy-terminal.git
cd energy-terminal
make install
```

### 2. Set API keys (optional but recommended)

```bash
export EIA_API_KEY=your_eia_key      # https://www.eia.gov/opendata/register.php
export FRED_API_KEY=your_fred_key    # https://fred.stlouisfed.org/docs/api/api_key.html
export IEA_API_KEY=your_iea_key      # https://www.iea.org/data-and-statistics
```

The terminal runs without any API keys — it falls back to Yahoo Finance
(free, no key) and Open-Meteo (free, no key) for price and weather data.

### 3. Start the Elixir data gateway

```bash
make run-backend
# or: ./scripts/start_backend.sh
```

### 4. Start the desktop UI (separate terminal)

```bash
make run-frontend
# or: ./scripts/start_terminal.sh
```

The UI auto-detects whether the gateway is running and falls back to
direct yfinance polling (15–20 min delayed) if it is not.

---

## Usage

### Navigation
| Input | Action |
|-------|--------|
| F1    | Market Overview panel |
| F2    | OHLCV Chart panel |
| F3    | Watchlist panel |
| F4    | Analytics (spreads, matrix, macro) |
| F5    | EIA Fundamental data |
| F6    | Weather / HDD-CDD |
| F7    | Risk (VaR, correlation, vol cone) |
| F8    | Alerts |
| Ctrl+R | Force refresh all feeds |
| Ctrl+Q | Quit |

### Command Bar
Type a ticker and press Enter to load it in the chart:
```
CL1 <ENTER>    → WTI Crude
NG1 <ENTER>    → Natural Gas
BZ1 <ENTER>    → Brent Crude
```

---

## Development

```bash
# Run all tests
make test

# Python tests only (faster)
make test-python-fast

# Lint everything
make lint

# Auto-format everything
make fmt

# Clean build artefacts
make clean
```

### Test coverage gate: 85%
```bash
cd frontend && python -m pytest --cov=energy_terminal --cov-fail-under=85
```

### Adding a new feed (Erlang)
1. Create `backend/apps/energy_gateway/src/{name}_feed_server.erl`
   implementing the `gen_server` behaviour
2. Add a child spec to `energy_gateway_sup.erl`
3. Register the atom in `feed_registry.erl`
4. Add rate limit entry to `config/sys.config`
5. Write EUnit tests in `backend/apps/energy_gateway/test/`

### Adding a new panel (Python)
1. Create `frontend/src/energy_terminal/ui/panels/{name}_panel.py`
   inheriting from `BasePanel`
2. Import and instantiate in `main_window.py`
3. Wire to a function key in `_bind_shortcuts()`
4. Add to `panels/__init__.py`

---

## Configuration

User configuration: `~/.energy_terminal/config.toml` (auto-created on first run)

```toml
gateway_url = "ws://127.0.0.1:8765/ws"
theme       = "bloomberg_dark"
log_level   = "INFO"
```

All settings can be overridden with `ET_*` environment variables:
```bash
ET_GATEWAY_URL=ws://192.168.1.10:8765/ws
ET_LOG_LEVEL=DEBUG
ET_THEME=classic_dark
```

---

## Documentation

| Document | Contents |
|----------|----------|
| [`docs/architecture.md`](docs/architecture.md) | Component diagram, fault tolerance model, data flow |
| [`docs/api_contracts.md`](docs/api_contracts.md) | WebSocket message schema, series reference |
| [`docs/data_dictionary.md`](docs/data_dictionary.md) | Energy terminology, units, calculation methodologies |
| [`CHANGELOG.md`](CHANGELOG.md) | Version history |

---

## Data Disclaimer

Price data from Yahoo Finance is delayed 15–20 minutes for most futures
contracts and is provided for informational and analytical purposes only.
This terminal is not connected to any live exchange feed and is not
suitable for execution decisions.  Every panel displays its data source
and timestamp; the ⚠ STALE indicator appears when data exceeds its
expected refresh TTL.

---

## License

MIT — see `LICENSE`.

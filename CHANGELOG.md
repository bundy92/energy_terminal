# Changelog

All notable changes to Energy Terminal are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Options analytics (delta, gamma, vega, implied vol surface)
- LNG-specific instruments: JKM, TTF, NBP via additional feed adapter
- News RSS feed aggregator (EIA, IEA, OPEC release calendars)
- Multi-user shared workspace via Erlang pub/sub authentication layer
- Historical replay mode (scrub timeline, all panels update historically)
- Mobile companion read-only app (iOS / Android)
- ML demand forecasting module (Prophet / NeuralProphet)
- Broker FIX protocol adapter for order routing
- PDF morning-brief export from any workspace layout

---

## [0.1.0] — 2024-03-15

### Added

#### Erlang/OTP Backend (`backend/`)
- `energy_gateway_app` — OTP application entry point with Cowboy HTTP/WS listener
- `energy_gateway_sup` — Root `one_for_one` supervisor covering all subsystems
- `ets_cache` — TTL-aware ETS in-memory cache; survives feed-server crashes
- `rate_limiter` — Token-bucket rate limiter per API endpoint (60 req/min default)
- `feed_registry` — Named process registry for all feed GenServers
- `data_router` — Pub/sub fan-out to WebSocket subscribers with process monitoring
- `market_feed_server` — Yahoo Finance v7 quote poller (OHLCV, 30-second interval)
- `eia_feed_server` — US EIA Open Data API: crude stocks, production, refinery utilisation, nat gas storage
- `iea_feed_server` — IEA Open Data API: global supply/demand balance (deactivates gracefully without key)
- `weather_feed_server` — Open-Meteo API: HDD/CDD for New York, Chicago, Houston, London, Rotterdam, Tokyo
- `fred_feed_server` — Federal Reserve FRED: USD index, CPI, 10Y real rate, industrial production
- `ws_handler` — Cowboy WebSocket handler: JSON envelope protocol, per-connection symbol subscriptions
- `health_handler` — HTTP `/health` endpoint for monitoring and Docker health checks
- EUnit test suites: `ets_cache_tests`, `data_router_tests`, `rate_limiter_tests`, `market_feed_server_tests`
- PropEr property-based tests: `prop_schema_tests`

#### Python Frontend (`frontend/`)
- `config.settings` — Pydantic-settings configuration: TOML + `ET_*` env var precedence
- `data.models` — Pydantic v2 models: `Tick`, `OHLCVBar`, `FundamentalReading`, `WeatherReading`, `MacroReading`, `Alert`
- `data.client` — Async WebSocket client with exponential-backoff reconnect
- `data.direct_feed` — yfinance fallback feed (15–20 min delayed); seamless gateway-down degradation
- `data.cache` — DuckDB persistent time-series cache: OHLCV, fundamental, weather, audit log
- `data.alerts` — Alert engine: `ABOVE`, `BELOW`, `PCT_CHANGE`, `SPREAD_WIDE` conditions; fires-once semantics
- `analytics.technical` — NumPy-based: SMA, EMA, RSI (Wilder), MACD, Bollinger Bands, ATR, OBV, VWAP, Stochastic
- `analytics.fundamental` — Energy analytics: 3-2-1 / 2-1-1 crack spreads, HO crack, spark spread, term structure, seasonality, supply/demand balance
- `analytics.risk` — Risk metrics: historical/parametric VaR, CVaR (Expected Shortfall), rolling correlation matrix, volatility cone, portfolio VaR
- `ui.theme` — Bloomberg dark colour palette and full Qt stylesheet
- `ui.main_window` — Main window: amber command bar, 2×2 splitter panel grid, F1–F8 keybindings, UTC clock, status bar, graceful close
- `ui.panels.base_panel` — Shared Bloomberg chrome: amber header, stale indicator, active border
- `ui.panels.market_panel` — Live OHLCV table for all instruments, colour-coded by change direction
- `ui.panels.chart_panel` — PyQtGraph candlestick chart: SMA20/EMA12/BB overlays, RSI/MACD subplots, multi-timeframe, log scale
- `ui.panels.watchlist_panel` — User-managed watchlist with add-ticker input and alert badges
- `ui.panels.analytics_panel` — Tabbed analytics: live crack/spark spreads, spread matrix, FRED macro table
- `ui.panels.fundamental_panel` — EIA weekly supply/demand table
- `ui.panels.weather_panel` — HDD/CDD table for six key demand centres with 7-day forecast
- `ui.panels.risk_panel` — Tabbed risk: VaR/CVaR table, 60-day correlation heatmap, volatility cone
- `ui.panels.alert_panel` — Alert definition form, active alert list, immutable fired-alert audit log
- pytest suites: `test_technical`, `test_fundamental`, `test_risk`, `test_alerts_and_models`, `test_cache`, `test_data_pipeline`
- Fixtures: `sample_data.py` with reproducible synthetic price/tick/fundamental generators

#### Infrastructure
- `Makefile` — Unified `make install | test | lint | fmt | run | clean`
- `scripts/start_backend.sh` — Erlang gateway launcher with API key guidance
- `scripts/start_terminal.sh` — UI launcher with gateway health check and fallback notice
- `.pre-commit-config.yaml` — ruff, ruff-format, mypy, bandit, erlfmt, standard hooks
- `docs/README.md` — Setup, architecture overview, environment variables, development workflow
- `docs/architecture.md` — Full system architecture with ASCII component diagram
- `docs/api_contracts.md` — WebSocket message schema reference
- `docs/data_dictionary.md` — Energy terminology, series IDs, unit definitions

### Instruments Tracked
Crude (WTI, Brent) · Natural Gas (Henry Hub) · RBOB Gasoline · ULSD ·
Energy ETFs (XLE, ICLN) · Majors (XOM, CVX, BP, Shell, TotalEnergies) ·
FX (EUR/USD, USD Index) · Corn/Soy (biofuel crossover)

### Data Sources
Yahoo Finance (OHLCV) · US EIA Open Data (weekly petroleum/gas) ·
IEA Open Data (global balance) · Open-Meteo (weather/HDD-CDD) ·
Federal Reserve FRED (macro indicators)

---

[Unreleased]: https://github.com/your-org/energy-terminal/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/energy-terminal/releases/tag/v0.1.0

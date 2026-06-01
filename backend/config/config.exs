import Config

config :energy_gateway,
  ws_port: 8765,
  cache_ttl_secs: 60,
  poll_interval_ms: 30_000,
  rate_limits: [
    yahoo_finance: 60,
    iea: 10,
    eia: 60,
    open_meteo: 100,
    fred: 120
  ],
  feeds_enabled: [:yahoo_finance, :eia, :open_meteo, :fred],
  instruments: [
    "CL=F", "BZ=F", "NG=F", "RB=F", "HO=F", "ICLN", "XLE",
    "EURUSD=X", "DX-Y.NYB", "XOM", "CVX", "BP", "SHEL", "TTE"
  ],
  http_client: EnergyGateway.HttpClient

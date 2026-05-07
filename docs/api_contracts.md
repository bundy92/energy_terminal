# WebSocket API Contracts

Gateway endpoint: `ws://localhost:8765/ws`

All messages are JSON-encoded UTF-8 text frames.

---

## Client → Server Commands

### ping
```json
{ "cmd": "ping" }
```
Response: `pong` message.

### subscribe
```json
{ "cmd": "subscribe", "symbols": ["CL=F", "NG=F", "BZ=F"] }
```
Filter events to a subset of symbols. Pass `"all"` as a string to
receive all symbols (default on connect).

### unsubscribe
```json
{ "cmd": "unsubscribe" }
```
Stop receiving events. Connection remains open.

### get_cache
```json
{ "cmd": "get_cache", "key": "tick:CL=F" }
```
Retrieve a cached value directly from ETS.

Key format: `"{type}:{symbol}"`
Valid types: `tick` · `fundamental` · `weather` · `macro`

---

## Server → Client Events

All server messages share this envelope:

```json
{
  "type":      "<event_type>",
  "source":    "<data_source>",
  "symbol":    "<ticker_or_series_id>",
  "timestamp": 1710000000000,
  "payload":   { }
}
```

### type: "tick"
Source: `yahoo_finance`

```json
{
  "type":      "tick",
  "source":    "yahoo_finance",
  "symbol":    "CL=F",
  "timestamp": 1710000000000,
  "payload": {
    "open":       84.20,
    "high":       86.15,
    "low":        83.80,
    "close":      85.50,
    "volume":     142000,
    "change":     1.30,
    "change_pct": 1.54
  }
}
```

### type: "fundamental"
Sources: `eia` · `iea`

```json
{
  "type":      "fundamental",
  "source":    "eia",
  "symbol":    "PET.WCRSTUS1.W",
  "timestamp": 1710000000000,
  "payload": {
    "series": "PET.WCRSTUS1.W",
    "value":  429500.0,
    "period": "2024-03-08"
  }
}
```

### type: "weather"
Source: `open_meteo`

```json
{
  "type":      "weather",
  "source":    "open_meteo",
  "symbol":    "New York",
  "timestamp": 1710000000000,
  "payload": {
    "location":    "New York",
    "temp_c":      4.2,
    "hdd":         14.1,
    "cdd":         0.0,
    "forecast_7d": [4.2, 5.1, 6.8, 5.3, 3.9, 2.1, 1.5]
  }
}
```

### type: "macro"
Source: `fred`

```json
{
  "type":      "macro",
  "source":    "fred",
  "symbol":    "DTWEXBGS",
  "timestamp": 1710000000000,
  "payload": {
    "series": "DTWEXBGS",
    "value":  106.42,
    "date":   "2024-03-10"
  }
}
```

### type: "pong"
Response to a `ping` command.

```json
{
  "type":      "pong",
  "timestamp": 1710000000000
}
```

### type: "cache_hit" / "cache_miss"
Response to a `get_cache` command.

```json
{ "type": "cache_hit",  "key": "tick:CL=F", "payload": { ... } }
{ "type": "cache_miss", "key": "tick:UNKNOWN" }
```

### type: "error"
```json
{ "type": "error", "message": "unknown command" }
```

---

## Data Sources Reference

| Source ID       | Name                          | Frequency     | Auth Required |
|----------------|-------------------------------|---------------|---------------|
| `yahoo_finance` | Yahoo Finance v7 Quote API    | 30 seconds    | No            |
| `eia`           | US Energy Information Admin.  | Weekly / daily| `EIA_API_KEY` |
| `iea`           | Intl. Energy Agency Open Data | Monthly       | `IEA_API_KEY` |
| `open_meteo`    | Open-Meteo Weather API        | 3 hours       | No            |
| `fred`          | Federal Reserve FRED          | Daily         | `FRED_API_KEY`|
| `direct`        | yfinance fallback (Python)    | 30 seconds    | No            |

---

## EIA Series Reference

| Series ID                   | Description                        | Unit             |
|-----------------------------|------------------------------------|------------------|
| `PET.WCRSTUS1.W`            | US crude oil stocks (PADD total)   | Thousand barrels |
| `PET.WCRFPUS2.W`            | US crude oil field production      | Thousand bbl/day |
| `PET.WCRRIUS2.W`            | US crude inputs to refineries      | Thousand bbl/day |
| `PET.WPULEUS2.W`            | US refinery utilisation rate       | Percent          |
| `NG.NW2EUS_EPG0_SWO_BCF.W` | US working gas in storage          | Billion cu. ft.  |

## FRED Series Reference

| Series ID              | Description                        | Frequency |
|------------------------|------------------------------------|-----------|
| `DTWEXBGS`             | Nominal Broad USD Index            | Daily     |
| `CPIAUCSL`             | CPI All Urban Consumers            | Monthly   |
| `REAINTRATREARAT10Y`   | 10-year real interest rate         | Daily     |
| `INDPRO`               | Industrial Production Index        | Monthly   |
| `DCOILWTICO`           | WTI crude spot price (FRED)        | Daily     |

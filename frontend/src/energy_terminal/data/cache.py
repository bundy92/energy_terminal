"""Local DuckDB time-series cache.

Provides persistent, queryable storage of OHLCV bars and fundamental
readings so the terminal operates in offline mode and avoids redundant
API calls on restart.

Schema
------
``ohlcv``
    time-series table for price bars (one row per bar per symbol).

``fundamental``
    time-series table for EIA / IEA / FRED fundamental readings.

``weather``
    latest weather reading per location.

``audit_log``
    append-only record of every data write (source, key, timestamp).

Examples
--------
>>> cache = TimeSeriesCache()
>>> cache.write_ohlcv("CL=F", bars)
>>> df = cache.read_ohlcv("CL=F", days=30)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
import pandas as pd
import structlog

from energy_terminal.config import settings

if TYPE_CHECKING:
    from energy_terminal.data.models import FundamentalReading, OHLCVBar, WeatherReading

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS ohlcv (
    symbol    VARCHAR NOT NULL,
    ts_ms     BIGINT  NOT NULL,
    open      DOUBLE,
    high      DOUBLE,
    low       DOUBLE,
    close     DOUBLE,
    volume    BIGINT,
    source    VARCHAR,
    PRIMARY KEY (symbol, ts_ms)
);

CREATE TABLE IF NOT EXISTS fundamental (
    series    VARCHAR NOT NULL,
    period    VARCHAR NOT NULL,
    value     DOUBLE,
    unit      VARCHAR,
    source    VARCHAR,
    fetched_ms BIGINT,
    PRIMARY KEY (series, period)
);

CREATE TABLE IF NOT EXISTS weather (
    location  VARCHAR PRIMARY KEY,
    temp_c    DOUBLE,
    hdd       DOUBLE,
    cdd       DOUBLE,
    forecast_json VARCHAR,
    fetched_ms BIGINT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY,
    action      VARCHAR,
    target_key  VARCHAR,
    source      VARCHAR,
    ts_ms       BIGINT
);
"""


class TimeSeriesCache:
    """DuckDB-backed persistent time-series cache.

    Parameters
    ----------
    db_path : Path, optional
        Filesystem path for the DuckDB database file.  Defaults to
        ``settings.cache_db_path``.

    Notes
    -----
    A single DuckDB connection is used.  DuckDB is not thread-safe for
    writes; callers must use ``write_ohlcv`` / ``write_fundamental``
    only from the asyncio event loop or a serialised worker.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or settings.cache_db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._path))
        self._initialise_schema()
        log.info("TimeSeriesCache opened", path=str(self._path))

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _initialise_schema(self) -> None:
        """Create tables if they don't exist."""
        self._conn.execute(_DDL)

    # ------------------------------------------------------------------
    # OHLCV
    # ------------------------------------------------------------------

    def write_ohlcv(self, symbol: str, bars: list[OHLCVBar], source: str = "direct") -> int:
        """Insert or replace OHLCV bars for a symbol.

        Parameters
        ----------
        symbol : str
            Instrument ticker.
        bars : list[OHLCVBar]
            Bars to upsert (keyed on ``symbol, ts_ms``).
        source : str
            Data source label for audit trail.

        Returns
        -------
        int
            Number of rows written.
        """
        if not bars:
            return 0
        rows = [
            (symbol, b.timestamp, b.open, b.high, b.low, b.close, b.volume, source)
            for b in bars
        ]
        self._conn.executemany(
            """
            INSERT INTO ohlcv (symbol, ts_ms, open, high, low, close, volume, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (symbol, ts_ms) DO UPDATE SET
                open   = excluded.open,
                high   = excluded.high,
                low    = excluded.low,
                close  = excluded.close,
                volume = excluded.volume,
                source = excluded.source
            """,
            rows,
        )
        self._audit("write_ohlcv", symbol, source)
        return len(rows)

    def read_ohlcv(self, symbol: str, days: int = 365) -> pd.DataFrame:
        """Read OHLCV bars for a symbol.

        Parameters
        ----------
        symbol : str
            Instrument ticker.
        days : int
            Number of calendar days of history to return.

        Returns
        -------
        pd.DataFrame
            DataFrame with columns ``[ts_ms, open, high, low, close, volume]``
            indexed by ``ts_ms`` ascending, or empty DataFrame if no data.
        """
        cutoff_ms = int((time.time() - days * 86_400) * 1000)
        df = self._conn.execute(
            """
            SELECT ts_ms, open, high, low, close, volume
            FROM   ohlcv
            WHERE  symbol = ? AND ts_ms >= ?
            ORDER  BY ts_ms ASC
            """,
            [symbol, cutoff_ms],
        ).df()
        return df

    def latest_close(self, symbol: str) -> float | None:
        """Return the most recent closing price for a symbol.

        Parameters
        ----------
        symbol : str
            Instrument ticker.

        Returns
        -------
        float or None
            Latest close price, or ``None`` if no data is cached.
        """
        row = self._conn.execute(
            "SELECT close FROM ohlcv WHERE symbol = ? ORDER BY ts_ms DESC LIMIT 1",
            [symbol],
        ).fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------
    # Fundamental
    # ------------------------------------------------------------------

    def write_fundamental(self, reading: FundamentalReading) -> None:
        """Upsert a single fundamental reading.

        Parameters
        ----------
        reading : FundamentalReading
            Validated fundamental observation.
        """
        self._conn.execute(
            """
            INSERT INTO fundamental (series, period, value, unit, source, fetched_ms)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (series, period) DO UPDATE SET
                value      = excluded.value,
                fetched_ms = excluded.fetched_ms
            """,
            [
                reading.series, reading.period, reading.value,
                reading.unit, reading.source.value,
                int(time.time() * 1000),
            ],
        )

    def read_fundamental(self, series: str, periods: int = 52) -> pd.DataFrame:
        """Read the most recent N periods for a fundamental series.

        Parameters
        ----------
        series : str
            EIA / FRED series identifier.
        periods : int
            Number of most-recent periods to return.

        Returns
        -------
        pd.DataFrame
            DataFrame with columns ``[series, period, value, unit]``.
        """
        return self._conn.execute(
            """
            SELECT series, period, value, unit
            FROM   fundamental
            WHERE  series = ?
            ORDER  BY period DESC
            LIMIT  ?
            """,
            [series, periods],
        ).df()

    # ------------------------------------------------------------------
    # Weather
    # ------------------------------------------------------------------

    def write_weather(self, reading: WeatherReading) -> None:
        """Upsert a weather reading for a location.

        Parameters
        ----------
        reading : WeatherReading
            Validated weather observation.
        """
        import json
        self._conn.execute(
            """
            INSERT INTO weather (location, temp_c, hdd, cdd, forecast_json, fetched_ms)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (location) DO UPDATE SET
                temp_c        = excluded.temp_c,
                hdd           = excluded.hdd,
                cdd           = excluded.cdd,
                forecast_json = excluded.forecast_json,
                fetched_ms    = excluded.fetched_ms
            """,
            [
                reading.location, reading.temp_c, reading.hdd, reading.cdd,
                json.dumps(reading.forecast_7d), int(time.time() * 1000),
            ],
        )

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def _audit(self, action: str, target_key: str, source: str) -> None:
        """Append a record to the audit log."""
        self._conn.execute(
            "INSERT INTO audit_log (action, target_key, source, ts_ms) VALUES (?,?,?,?)",
            [action, target_key, source, int(time.time() * 1000)],
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._conn.close()
        log.info("TimeSeriesCache closed")

    def __enter__(self) -> "TimeSeriesCache":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

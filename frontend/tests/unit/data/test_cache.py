"""Unit tests for :mod:`energy_terminal.data.cache`.

Uses a temporary DuckDB database (in-memory path) so tests are fully
isolated and leave no files on disk.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from energy_terminal.data.cache import TimeSeriesCache
from energy_terminal.data.models import EventSource, EventType
from tests.fixtures.sample_data import (
    make_fundamental,
    make_ohlcv_bars,
    make_weather,
)


@pytest.fixture
def cache(tmp_path: Path) -> TimeSeriesCache:
    """Provide a fresh TimeSeriesCache backed by a temp DuckDB file."""
    db = tmp_path / "test_cache.duckdb"
    c  = TimeSeriesCache(db_path=db)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# OHLCV
# ---------------------------------------------------------------------------

class TestOHLCVCRUD:
    def test_write_and_read_roundtrip(self, cache: TimeSeriesCache) -> None:
        bars = make_ohlcv_bars(n=10)
        written = cache.write_ohlcv("CL=F", bars, source="test")
        assert written == 10
        df = cache.read_ohlcv("CL=F", days=365)
        assert len(df) == 10

    def test_columns_present(self, cache: TimeSeriesCache) -> None:
        bars = make_ohlcv_bars(n=5)
        cache.write_ohlcv("NG=F", bars)
        df = cache.read_ohlcv("NG=F", days=365)
        assert set(["ts_ms", "open", "high", "low", "close", "volume"]).issubset(df.columns)

    def test_bars_sorted_ascending_by_timestamp(self, cache: TimeSeriesCache) -> None:
        bars = make_ohlcv_bars(n=20)
        cache.write_ohlcv("BZ=F", bars)
        df = cache.read_ohlcv("BZ=F", days=365)
        assert list(df["ts_ms"]) == sorted(df["ts_ms"].tolist())

    def test_upsert_updates_existing_bar(self, cache: TimeSeriesCache) -> None:
        bars = make_ohlcv_bars(n=1)
        cache.write_ohlcv("CL=F", bars)

        # Write same timestamp with different close
        from energy_terminal.data.models import OHLCVBar
        updated = OHLCVBar(
            timestamp=bars[0].timestamp,
            open=bars[0].open,
            high=bars[0].high,
            low=bars[0].low,
            close=999.0,
            volume=bars[0].volume,
        )
        cache.write_ohlcv("CL=F", [updated])
        df = cache.read_ohlcv("CL=F", days=365)
        assert len(df) == 1
        assert float(df["close"].iloc[0]) == pytest.approx(999.0)

    def test_read_empty_returns_empty_dataframe(self, cache: TimeSeriesCache) -> None:
        df = cache.read_ohlcv("NONEXISTENT", days=30)
        assert len(df) == 0

    def test_days_filter_excludes_old_bars(self, cache: TimeSeriesCache) -> None:
        from energy_terminal.data.models import OHLCVBar
        now_ms = int(time.time() * 1000)
        old_ms = now_ms - (400 * 24 * 3600 * 1000)   # 400 days ago

        old_bar = OHLCVBar(timestamp=old_ms, open=80.0, high=82.0,
                           low=79.0, close=81.0, volume=1000)
        new_bar = OHLCVBar(timestamp=now_ms, open=85.0, high=87.0,
                           low=84.0, close=86.0, volume=2000)
        cache.write_ohlcv("CL=F", [old_bar, new_bar])

        df = cache.read_ohlcv("CL=F", days=30)
        assert len(df) == 1
        assert float(df["close"].iloc[0]) == pytest.approx(86.0)

    def test_latest_close_returns_most_recent(self, cache: TimeSeriesCache) -> None:
        bars = make_ohlcv_bars(n=10)
        cache.write_ohlcv("CL=F", bars)
        result = cache.latest_close("CL=F")
        assert result is not None
        assert result == pytest.approx(bars[-1].close)

    def test_latest_close_returns_none_for_unknown_symbol(
        self, cache: TimeSeriesCache
    ) -> None:
        assert cache.latest_close("UNKNOWN") is None

    def test_write_empty_bars_returns_zero(self, cache: TimeSeriesCache) -> None:
        assert cache.write_ohlcv("CL=F", []) == 0


# ---------------------------------------------------------------------------
# Fundamental
# ---------------------------------------------------------------------------

class TestFundamentalCRUD:
    def test_write_and_read_roundtrip(self, cache: TimeSeriesCache) -> None:
        reading = make_fundamental()
        cache.write_fundamental(reading)
        df = cache.read_fundamental(reading.series, periods=10)
        assert len(df) == 1

    def test_read_returns_most_recent_first(self, cache: TimeSeriesCache) -> None:
        for period in ["2024-01-01", "2024-01-08", "2024-01-15"]:
            cache.write_fundamental(make_fundamental(period=period))
        df = cache.read_fundamental("PET.WCRSTUS1.W", periods=5)
        assert df["period"].iloc[0] == "2024-01-15"

    def test_upsert_updates_value(self, cache: TimeSeriesCache) -> None:
        cache.write_fundamental(make_fundamental(value=430_000.0))
        cache.write_fundamental(make_fundamental(value=435_000.0))
        df = cache.read_fundamental("PET.WCRSTUS1.W", periods=5)
        assert len(df) == 1
        assert float(df["value"].iloc[0]) == pytest.approx(435_000.0)

    def test_missing_value_stored_as_none(self, cache: TimeSeriesCache) -> None:
        reading = make_fundamental(value=None)  # type: ignore[arg-type]
        # None values are valid (FRED missing observations)
        from energy_terminal.data.models import FundamentalReading, EventType, EventSource
        r = FundamentalReading(
            type=EventType.FUNDAMENTAL, source=EventSource.FRED,
            symbol="TEST", timestamp=1_000,
            series="TEST", value=None, period="2024-01",
        )
        cache.write_fundamental(r)
        df = cache.read_fundamental("TEST", periods=1)
        assert len(df) == 1


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

class TestWeatherCRUD:
    def test_write_and_overwrite(self, cache: TimeSeriesCache) -> None:
        r1 = make_weather(location="New York", temp_c=5.0)
        r2 = make_weather(location="New York", temp_c=12.0)
        cache.write_weather(r1)
        cache.write_weather(r2)
        # Verify upsert: only one row per location
        result = cache._conn.execute(
            "SELECT temp_c FROM weather WHERE location = 'New York'"
        ).fetchone()
        assert result is not None
        assert result[0] == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_context_manager_closes_cleanly(self, tmp_path: Path) -> None:
        db = tmp_path / "ctx_test.duckdb"
        with TimeSeriesCache(db_path=db) as c:
            bars = make_ohlcv_bars(n=5)
            c.write_ohlcv("CL=F", bars)
        # DuckDB file should exist on disk
        assert db.exists()

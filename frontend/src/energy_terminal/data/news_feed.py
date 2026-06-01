"""News RSS feed aggregator for EIA, IEA, and OPEC release calendars.

The adapter fetches RSS feeds asynchronously and normalizes items into a
common model for display in the terminal.
"""

from __future__ import annotations

import aiohttp
import email.utils
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import datetime, timezone

import structlog

log = structlog.get_logger(__name__)

NEWS_FEEDS: dict[str, str] = {
    "EIA": "https://www.eia.gov/rss/pressreleases.xml",
    "IEA": "https://www.iea.org/newsroom/rss.xml",
    "OPEC": "https://www.opec.org/opec_web/en/rss.xml",
}


class NewsItem:
    """A normalized RSS news item."""

    def __init__(
        self,
        source: str,
        title: str,
        summary: str,
        link: str,
        published: str,
        timestamp: int,
    ) -> None:
        self.source = source
        self.title = title
        self.summary = summary
        self.link = link
        self.published = published
        self.timestamp = timestamp

    def __repr__(self) -> str:
        return (
            f"NewsItem(source={self.source!r}, title={self.title!r}, "
            f"published={self.published!r})"
        )


class NewsFeedAdapter:
    """Asynchronous aggregator for provider RSS feeds."""

    @classmethod
    def supported_sources(cls) -> list[str]:
        return sorted(NEWS_FEEDS)

    @classmethod
    async def fetch_items(
        cls,
        sources: Iterable[str] | None = None,
        limit: int = 50,
    ) -> list[NewsItem]:
        sources = [s for s in (sources or cls.supported_sources()) if s in NEWS_FEEDS]
        if not sources:
            return []

        items: list[NewsItem] = []
        async with aiohttp.ClientSession() as session:
            for source in sources:
                url = NEWS_FEEDS[source]
                try:
                    async with session.get(url, timeout=20) as resp:
                        if resp.status != 200:
                            log.warning("NewsFeedAdapter bad status", source=source, status=resp.status)
                            continue
                        text = await resp.text()
                except Exception as exc:  # noqa: BLE001
                    log.warning("NewsFeedAdapter fetch failed", source=source, exc=str(exc))
                    continue

                items.extend(cls._parse_rss(source, text))

        items.sort(key=lambda item: item.timestamp, reverse=True)
        return items[:limit]

    @classmethod
    def _parse_rss(cls, source: str, xml_text: str) -> list[NewsItem]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            log.warning("NewsFeedAdapter parse error", source=source)
            return []

        items: list[NewsItem] = []
        for node in root.findall(".//item"):
            title = cls._safe_text(node.findtext("title"), "Untitled")
            summary = cls._safe_text(node.findtext("description"), "")
            link = cls._safe_text(node.findtext("link"), "")
            published = cls._safe_text(
                node.findtext("pubDate")
                or node.findtext("pubdate")
                or node.findtext("{http://purl.org/dc/elements/1.1/}date"),
                "",
            )
            timestamp = cls._parse_published(published)
            items.append(NewsItem(source, title, summary, link, published, timestamp))
        return items

    @classmethod
    def _parse_published(cls, published: str) -> int:
        if not published:
            return 0
        try:
            dt = email.utils.parsedate_to_datetime(published)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except (TypeError, ValueError, OverflowError):
            try:
                dt = datetime.fromisoformat(published)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1000)
            except Exception:
                return int(time.time() * 1000)

    @staticmethod
    def _safe_text(value: str | None, default: str) -> str:
        return value.strip() if value and value.strip() else default

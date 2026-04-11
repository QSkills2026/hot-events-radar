"""Nasdaq trading halts RSS adapter.

Trading halts are a very early signal of breaking corporate news — when a
stock is halted under T1/T12/M codes it usually means a material announcement
is imminent (or just released). The halt RSS feed is public and updated in
near-real-time.

Key halt reason codes (from nasdaqtrader.com):
    T1    News Pending
    T2    News Released
    T12   Additional Information Requested
    M     Volatility Trading Pause (single-stock circuit breaker)
    LUDP  Limit Up-Limit Down
    H10   SEC Trading Suspension
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.etree import ElementTree as ET

import httpx

from hot_events_radar.schema import CandidateEvent, CompanySubtype, EventSource

logger = logging.getLogger(__name__)

NASDAQ_HALTS_URL = "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts"

# Halt reason → (authority, display_name). T1/T12 are the most predictive
# of material news; M is often transient volatility.
REASON_WEIGHT: dict[str, tuple[float, str]] = {
    "T1": (0.95, "News Pending"),
    "T2": (0.90, "News Released"),
    "T12": (0.95, "Additional Info Requested"),
    "H10": (1.00, "SEC Trading Suspension"),
    "M": (0.60, "Volatility Pause"),
    "LUDP": (0.55, "Limit Up-Limit Down"),
}


async def fetch_halts(
    window_hours: int = 24,
    watchlist: Optional[list[str]] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> list[CandidateEvent]:
    """Fetch recent trading halts from Nasdaq RSS.

    Returns empty list on any error.
    """
    close_client = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=10.0,
        headers={"User-Agent": "hot-events-radar/0.1"},
    )
    try:
        resp = await client.get(NASDAQ_HALTS_URL)
        if resp.status_code != 200:
            logger.warning("Nasdaq halts feed returned %d", resp.status_code)
            return []
        return parse_halts_rss(resp.text, window_hours=window_hours, watchlist=watchlist)
    except Exception as e:
        logger.warning("Nasdaq halts fetch failed: %s", type(e).__name__)
        return []
    finally:
        if close_client:
            await client.aclose()


def parse_halts_rss(
    rss_xml: str,
    window_hours: int = 24,
    watchlist: Optional[list[str]] = None,
    now: Optional[datetime] = None,
) -> list[CandidateEvent]:
    """Parse Nasdaq halts RSS XML.

    The feed is RSS 2.0 with Nasdaq-custom elements. We use raw ElementTree
    to avoid namespace pain, and extract ticker/reason from the <description>
    field (HTML table). `now` is injectable for testing.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    watchset = {t.upper() for t in watchlist} if watchlist else None
    events: list[CandidateEvent] = []

    try:
        root = ET.fromstring(rss_xml)
    except ET.ParseError as e:
        logger.warning("halts RSS parse error: %s", e)
        return []

    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        desc = (item.findtext("description") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = item.findtext("pubDate") or ""
        ts = _parse_rss_date(pub_date)
        if ts < cutoff:
            continue

        ticker = _extract_halt_ticker(title, desc)
        if not ticker:
            continue
        if watchset and ticker.upper() not in watchset:
            continue

        reason = _extract_reason_code(title, desc)
        authority, reason_name = REASON_WEIGHT.get(reason, (0.70, reason or "Unknown"))
        source = EventSource(
            name="nasdaq_halts",
            authority=authority,
            url=link,
            timestamp=ts,
            raw_snippet=title[:300],
        )
        events.append(
            CandidateEvent(
                source=source,
                subtype=CompanySubtype.HALT.value,
                headline=f"{ticker} halted: {reason_name}",
                summary=_strip_html(desc)[:400],
                primary_tickers=[ticker.upper()],
                extra={"reason_code": reason, "reason_name": reason_name},
            )
        )
    return events


def _parse_rss_date(s: str) -> datetime:
    """Parse RFC 822 date from RSS pubDate field."""
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _extract_halt_ticker(title: str, desc: str) -> Optional[str]:
    """Extract the halted ticker from title or description."""
    # Title form: "Trading Halt - NVDA" or "NVDA - Trading Halt"
    for match in re.findall(r"\b([A-Z]{1,5})\b", title):
        if match not in ("RSS", "HTTP", "LLC", "INC", "CO"):
            return match
    # Fallback: scan description for first ticker-looking token
    for match in re.findall(r"\b([A-Z]{1,5})\b", desc):
        if match not in ("RSS", "HTTP", "LLC", "INC", "CO"):
            return match
    return None


def _extract_reason_code(title: str, desc: str) -> Optional[str]:
    """Extract halt reason code."""
    combined = f"{title} {desc}".upper()
    for code in REASON_WEIGHT:
        if re.search(rf"\b{re.escape(code)}\b", combined):
            return code
    return None


def _strip_html(html: str) -> str:
    """Minimal HTML stripping for RSS description fields."""
    return re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").strip()

"""Press wire RSS adapter (Business Wire + PR Newswire).

Press wires carry official corporate announcements: guidance updates,
product launches, contract wins, FDA actions, etc. Feeds are public.
Less authoritative than SEC 8-K but faster and catches non-8-K news.
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

# Publicly-documented generic RSS endpoints. Both feeds are keyed to publish
# firehoses that may include hundreds of releases per day.
BW_URL = "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeEVtRXA=="
PRN_URL = "https://www.prnewswire.com/rss/news-releases-list.rss"

# Ticker blacklist to suppress common false positives.
TICKER_STOPWORDS = {
    "A", "I", "ON", "OR", "BY", "IT", "IN", "AN", "IS", "AS", "AT", "BE", "DO",
    "GO", "IF", "NO", "OF", "SO", "TO", "UP", "US", "USA", "CEO", "CFO", "COO",
    "FDA", "SEC", "NYSE", "IPO", "ESG", "LLC", "INC", "CO", "LP", "LTD",
    "THE", "AND", "FOR", "WILL", "NEW", "OLD", "ALL", "ANY", "HIS", "HER",
    "OUR", "OUT", "HOW", "WHY", "WHO", "YOU", "CAN", "ITS", "HAS", "HAD",
    "BUT", "NOT", "DID", "GET", "LET", "MAY", "NOW", "ONE", "TWO", "TOP",
    "END", "EPS", "ETF", "ESG", "IPO", "WAS", "ARE", "THIS", "THAT", "WITH",
    "FROM", "HAVE", "BEEN", "WERE", "MORE", "OVER", "SAID", "SAYS", "ALSO",
    "PLAN", "NEWS",
}

# Keyword → subtype for classifying press releases
KEYWORD_MAP: list[tuple[re.Pattern, CompanySubtype, str]] = [
    (re.compile(r"\b(acqui(re|res|sition)|merger|merges)\b", re.I), CompanySubtype.MNA, "M&A"),
    (re.compile(r"\b(FDA|phase\s*(1|2|3|i|ii|iii)|PDUFA|approval)\b", re.I), CompanySubtype.FDA, "FDA"),
    (re.compile(r"\b(guidance|outlook|forecast|raises|lowers|cuts)\b", re.I), CompanySubtype.GUIDANCE, "guidance"),
    (re.compile(r"\b(earnings|quarterly results|Q[1-4])\b", re.I), CompanySubtype.EARNINGS, "earnings"),
]


async def fetch_press_releases(
    window_hours: int = 24,
    watchlist: Optional[list[str]] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> list[CandidateEvent]:
    """Fetch press releases from Business Wire + PR Newswire."""
    close_client = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=10.0,
        headers={"User-Agent": "hot-events-radar/0.1"},
    )
    events: list[CandidateEvent] = []
    try:
        for url, source_name, authority in [
            (BW_URL, "business_wire", 0.85),
            (PRN_URL, "pr_newswire", 0.85),
        ]:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.debug("%s returned %d", source_name, resp.status_code)
                    continue
                events.extend(
                    parse_pr_feed(
                        resp.text,
                        source_name=source_name,
                        authority=authority,
                        window_hours=window_hours,
                        watchlist=watchlist,
                    )
                )
            except Exception as e:
                logger.debug("%s fetch failed: %s", source_name, type(e).__name__)
    finally:
        if close_client:
            await client.aclose()
    return events


def parse_pr_feed(
    feed_xml: str,
    source_name: str,
    authority: float,
    window_hours: int = 24,
    watchlist: Optional[list[str]] = None,
    now: Optional[datetime] = None,
) -> list[CandidateEvent]:
    """Parse RSS 2.0 press-wire feed using stdlib ElementTree.

    Handles Business Wire and PR Newswire RSS 2.0 formats. `now` injectable
    for deterministic testing.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    watchset = {t.upper() for t in watchlist} if watchlist else None
    events: list[CandidateEvent] = []

    try:
        root = ET.fromstring(feed_xml)
    except ET.ParseError as e:
        logger.warning("PR feed parse error (%s): %s", source_name, e)
        return []

    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        summary = (item.findtext("description") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = item.findtext("pubDate") or ""
        ts = _parse_rfc822(pub_date)
        if ts < cutoff:
            continue

        combined = f"{title} {summary}"
        tickers = _extract_tickers(combined)
        if watchset:
            tickers = [t for t in tickers if t in watchset]
            if not tickers:
                continue

        subtype, hint = _classify(combined)
        source = EventSource(
            name=source_name,
            authority=authority,
            url=link,
            timestamp=ts,
            raw_snippet=title[:300],
        )
        events.append(
            CandidateEvent(
                source=source,
                subtype=subtype.value,
                headline=title,
                summary=_strip_html(summary)[:400],
                primary_tickers=tickers,
                extra={"hint": hint, "source_feed": source_name},
            )
        )
    return events


def _parse_rfc822(s: str) -> datetime:
    """Parse RSS pubDate (RFC 822) to UTC-aware datetime."""
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _extract_tickers(text: str) -> list[str]:
    """Extract ticker-looking tokens, filter stopwords.

    Prefers explicit "(NASDAQ: XYZ)" or "(NYSE: XYZ)" patterns; falls back to
    bare 1-5 uppercase words.
    """
    # Explicit exchange markers first
    explicit = re.findall(
        r"\((?:NASDAQ|NYSE|AMEX|OTC)\s*:\s*([A-Z]{1,5})\)", text
    )
    if explicit:
        return list(dict.fromkeys(explicit))  # dedupe preserving order

    # Fallback: bare uppercase
    tickers = []
    for match in re.findall(r"\b([A-Z]{2,5})\b", text):
        if match in TICKER_STOPWORDS:
            continue
        tickers.append(match)
        if len(tickers) >= 3:
            break
    return list(dict.fromkeys(tickers))


def _classify(text: str) -> tuple[CompanySubtype, str]:
    for pattern, subtype, hint in KEYWORD_MAP:
        if pattern.search(text):
            return subtype, hint
    return CompanySubtype.OTHER_PR, "generic"


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").strip()

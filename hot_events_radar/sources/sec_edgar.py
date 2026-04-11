"""SEC EDGAR 8-K RSS adapter.

Pulls recent 8-K filings from the public EDGAR atom feed. 8-K filings are
legally-mandated disclosures for material corporate events — the most
authoritative signal available for company-level events.

Key 8-K Items (most relevant for event detection):
    1.01  Entry into material definitive agreement
    1.02  Termination of material definitive agreement
    2.01  Completion of acquisition/disposition of assets
    2.02  Results of operations (earnings)
    2.04  Triggering event / debt acceleration
    5.02  Departure/appointment of officers/directors
    7.01  Regulation FD disclosure
    8.01  Other events (catch-all for material news)

No API key needed. SEC requires a descriptive User-Agent.
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

SEC_USER_AGENT = "hot-events-radar/0.1 (contact@example.com)"
SEC_RECENT_8K_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcompany&type=8-K&dateb=&owner=include&count=40&output=atom"
)
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Item → (subtype, magnitude_hint). Used to classify 8-K filings by content.
ITEM_MAP: dict[str, tuple[CompanySubtype, str]] = {
    "1.01": (CompanySubtype.MATERIAL_8K, "material agreement"),
    "1.02": (CompanySubtype.MATERIAL_8K, "agreement termination"),
    "2.01": (CompanySubtype.MNA, "acquisition/disposition"),
    "2.02": (CompanySubtype.EARNINGS, "earnings release"),
    "2.04": (CompanySubtype.MATERIAL_8K, "debt/triggering event"),
    "5.02": (CompanySubtype.MATERIAL_8K, "officer/director change"),
    "7.01": (CompanySubtype.OTHER_PR, "Reg FD disclosure"),
    "8.01": (CompanySubtype.MATERIAL_8K, "other material event"),
}

ITEM_PATTERN = re.compile(r"Item\s+(\d+\.\d+)", re.IGNORECASE)


async def fetch_8k(
    window_hours: int = 24,
    watchlist: Optional[list[str]] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> list[CandidateEvent]:
    """Fetch recent 8-K filings from EDGAR atom feed.

    Args:
        window_hours: only return filings within last N hours
        watchlist: if provided, filter to filings for these tickers only
        http_client: optional shared httpx client

    Returns:
        List of CandidateEvent (empty on any error — graceful degrade)
    """
    close_client = http_client is None
    client = http_client or httpx.AsyncClient(
        headers={"User-Agent": SEC_USER_AGENT},
        timeout=10.0,
    )
    try:
        resp = await client.get(SEC_RECENT_8K_URL)
        if resp.status_code != 200:
            logger.warning("SEC 8-K feed returned %d", resp.status_code)
            return []
        return parse_8k_atom(resp.text, window_hours=window_hours, watchlist=watchlist)
    except Exception as e:
        # Only catch network errors; let programming bugs surface in tests.
        logger.warning("SEC 8-K fetch failed: %s", type(e).__name__)
        return []
    finally:
        if close_client:
            await client.aclose()


ATOM_NS = "{http://www.w3.org/2005/Atom}"


def parse_8k_atom(
    atom_xml: str,
    window_hours: int = 24,
    watchlist: Optional[list[str]] = None,
    now: Optional[datetime] = None,
) -> list[CandidateEvent]:
    """Parse SEC 8-K atom feed XML into CandidateEvents.

    Uses stdlib ElementTree for zero-dependency parsing. `now` is injectable
    for testing.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    watchset = {t.upper() for t in watchlist} if watchlist else None
    events: list[CandidateEvent] = []

    try:
        root = ET.fromstring(atom_xml)
    except ET.ParseError as e:
        logger.warning("8-K atom parse error: %s", e)
        return []

    # Atom entries are either namespaced or not depending on feed.
    # Try both paths.
    entries = root.findall(f"{ATOM_NS}entry")
    if not entries:
        entries = root.findall("entry")

    for entry in entries:
        ts = _atom_entry_timestamp(entry)
        if ts < cutoff:
            continue

        title = _atom_text(entry, "title")
        summary = _atom_text(entry, "summary")
        link = _atom_link(entry)

        tickers = _extract_tickers_from_title(title)
        if watchset and not (set(tickers) & watchset):
            continue

        subtype, hint = _classify_8k(title + " " + summary)
        source = EventSource(
            name="sec_edgar",
            authority=1.0,
            url=link,
            timestamp=ts,
            raw_snippet=title[:300],
        )
        events.append(
            CandidateEvent(
                source=source,
                subtype=subtype.value,
                headline=title,
                summary=f"{hint}: {summary[:400]}",
                primary_tickers=tickers,
                extra={"hint": hint},
            )
        )
    return events


def _atom_text(entry, tag: str) -> str:
    """Get text of a child element, trying namespaced and bare tag."""
    el = entry.find(f"{ATOM_NS}{tag}")
    if el is None:
        el = entry.find(tag)
    return (el.text or "").strip() if el is not None else ""


def _atom_link(entry) -> str:
    """Get href from <link> element (atom style) or text of <link> (rss style)."""
    el = entry.find(f"{ATOM_NS}link")
    if el is None:
        el = entry.find("link")
    if el is None:
        return ""
    return el.attrib.get("href") or (el.text or "").strip()


def _atom_entry_timestamp(entry) -> datetime:
    """Parse ISO-8601 timestamp from <updated> or <published>."""
    for tag in ("updated", "published"):
        text = _atom_text(entry, tag)
        if not text:
            continue
        try:
            # Handle trailing Z or fractional seconds
            normalized = text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _extract_tickers_from_title(title: str) -> list[str]:
    """Extract ticker symbols from SEC 8-K entry title.

    SEC titles look like: "8-K - APPLE INC (0000320193) (Filer)"
    or "8-K - NVIDIA CORP (NVDA) (Filer)". We grep for 1-5 uppercase letters
    in parentheses, excluding pure digits.
    """
    tickers = []
    for match in re.findall(r"\(([A-Z]{1,5})\)", title):
        if match and not match.isdigit():
            tickers.append(match)
    return tickers


def _classify_8k(text: str) -> tuple[CompanySubtype, str]:
    """Classify 8-K by scanning for Item X.YY markers in title/summary."""
    match = ITEM_PATTERN.search(text)
    if match:
        item = match.group(1)
        if item in ITEM_MAP:
            return ITEM_MAP[item]
    # Fallback — heuristic keyword scan
    low = text.lower()
    if any(k in low for k in ("merger", "acquisition", "acquire", "acquires")):
        return CompanySubtype.MNA, "M&A keyword"
    if any(k in low for k in ("earnings", "quarterly results", "q1", "q2", "q3", "q4")):
        return CompanySubtype.EARNINGS, "earnings keyword"
    return CompanySubtype.MATERIAL_8K, "generic 8-K"

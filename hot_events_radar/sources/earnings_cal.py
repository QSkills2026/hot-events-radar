"""Finnhub earnings calendar adapter.

Finnhub offers a free-tier earnings calendar with upcoming + historical
beat/miss data. Requires FINNHUB_API_KEY env var; gracefully returns []
when missing.

API docs: https://finnhub.io/docs/api/earnings-calendar
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from hot_events_radar.schema import CandidateEvent, CompanySubtype, EventSource

logger = logging.getLogger(__name__)

FINNHUB_EARNINGS_URL = "https://finnhub.io/api/v1/calendar/earnings"


async def fetch_upcoming_and_recent(
    window_hours: int = 24,
    watchlist: Optional[list[str]] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> list[CandidateEvent]:
    """Fetch earnings calendar events covering the last `window_hours` and
    next 7 days.

    Returns [] if FINNHUB_API_KEY is not set.
    """
    api_key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not api_key:
        logger.debug("FINNHUB_API_KEY not set, skipping earnings calendar")
        return []

    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(hours=window_hours)).date()
    to_date = (now + timedelta(days=7)).date()

    close_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=10.0)
    try:
        resp = await client.get(
            FINNHUB_EARNINGS_URL,
            params={
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "token": api_key,
            },
        )
        if resp.status_code != 200:
            logger.warning("Finnhub earnings returned %d", resp.status_code)
            return []
        payload = resp.json()
    except Exception as e:
        logger.warning("Finnhub earnings fetch failed: %s", type(e).__name__)
        return []
    finally:
        if close_client:
            await client.aclose()

    return parse_earnings_payload(
        payload, now=now, window_hours=window_hours, watchlist=watchlist
    )


def parse_earnings_payload(
    payload: dict,
    now: Optional[datetime] = None,
    window_hours: int = 24,
    watchlist: Optional[list[str]] = None,
) -> list[CandidateEvent]:
    """Parse Finnhub earnings JSON into CandidateEvents.

    Filters:
      - watchlist: if provided, only include tickers in set
      - window: recent (within past N hours) OR upcoming (within next 7 days)

    Surprise scoring: |actual - estimate| / |estimate| when actual is present.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    watchset = {t.upper() for t in watchlist} if watchlist else None
    events: list[CandidateEvent] = []

    calendar = payload.get("earningsCalendar") or payload.get("data") or []
    for row in calendar:
        ticker = (row.get("symbol") or "").upper()
        if not ticker:
            continue
        if watchset and ticker not in watchset:
            continue

        date_str = row.get("date") or ""
        try:
            earnings_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        actual = row.get("epsActual")
        estimate = row.get("epsEstimate")
        is_recent = cutoff <= earnings_date <= now and actual is not None
        is_upcoming = earnings_date > now and earnings_date <= now + timedelta(days=7)
        if not (is_recent or is_upcoming):
            continue

        surprise_pct: Optional[float] = None
        if actual is not None and estimate is not None and estimate != 0:
            try:
                surprise_pct = abs(float(actual) - float(estimate)) / abs(float(estimate))
            except (TypeError, ValueError):
                surprise_pct = None

        if is_recent:
            direction = "beat" if (actual and estimate and actual >= estimate) else "miss"
            headline = (
                f"{ticker} earnings {direction}: "
                f"actual={actual} vs est={estimate}"
            )
            summary = f"Reported EPS {actual} against estimate {estimate}"
        else:
            headline = f"{ticker} earnings upcoming on {date_str}"
            summary = f"Scheduled earnings release on {date_str} ({row.get('hour', 'unknown')})"

        source = EventSource(
            name="finnhub",
            authority=0.9,
            url=f"https://finnhub.io/api/v1/calendar/earnings?symbol={ticker}",
            timestamp=earnings_date,
            raw_snippet=headline[:300],
        )
        events.append(
            CandidateEvent(
                source=source,
                subtype=CompanySubtype.EARNINGS.value,
                headline=headline,
                summary=summary,
                primary_tickers=[ticker],
                extra={
                    "eps_actual": actual,
                    "eps_estimate": estimate,
                    "surprise_pct": surprise_pct,
                    "is_recent": is_recent,
                    "is_upcoming": is_upcoming,
                    "earnings_date": date_str,
                },
            )
        )
    return events

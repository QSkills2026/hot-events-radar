"""Public API entry points for hot-events-radar.

Two entry points:
    get_events(types, ...) — unified, routes to requested detector types
    get_company_events(...) — convenience shortcut for the MVP use case

All async because source fetches are network-bound.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from hot_events_radar.detectors.company import detect_company_events
from hot_events_radar.schema import EventType, HotEvent

logger = logging.getLogger(__name__)


async def get_events(
    types: Optional[list[EventType]] = None,
    watchlist: Optional[list[str]] = None,
    window_hours: int = 24,
    min_score: float = 3.0,
    http_client: Optional[httpx.AsyncClient] = None,
) -> list[HotEvent]:
    """Unified event entry point.

    MVP: only EventType.COMPANY is implemented. Requesting MACRO or SOCIAL
    will log a warning and skip those detectors (does not raise — callers
    should be forward-compatible when V2/V3 land).

    Args:
        types: list of EventType to run. Defaults to [COMPANY].
        watchlist: ticker filter; None = all tickers
        window_hours: lookback window
        min_score: drop events below this threshold
        http_client: optional shared httpx client

    Returns:
        Sorted list of HotEvent (highest score first).
    """
    if types is None:
        types = [EventType.COMPANY]

    all_events: list[HotEvent] = []
    for t in types:
        if t == EventType.COMPANY:
            all_events.extend(
                await detect_company_events(
                    watchlist=watchlist,
                    window_hours=window_hours,
                    min_score=min_score,
                    http_client=http_client,
                )
            )
        elif t == EventType.MACRO:
            logger.info("EventType.MACRO requested but not implemented (V2)")
        elif t == EventType.SOCIAL:
            logger.info("EventType.SOCIAL requested but not implemented (V3)")
        else:
            logger.warning("unknown EventType: %s", t)

    all_events.sort(key=lambda e: e.score, reverse=True)
    return all_events


async def get_company_events(
    watchlist: Optional[list[str]] = None,
    window_hours: int = 24,
    min_score: float = 3.0,
    http_client: Optional[httpx.AsyncClient] = None,
) -> list[HotEvent]:
    """Convenience: fetch only company events. Same signature as detector."""
    return await detect_company_events(
        watchlist=watchlist,
        window_hours=window_hours,
        min_score=min_score,
        http_client=http_client,
    )

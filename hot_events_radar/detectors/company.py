"""Company event detector — the MVP orchestrator.

Pulls candidates from all four company-level sources in parallel, deduplicates,
scores, filters, and returns sorted HotEvents.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from hot_events_radar.dedupe import cluster_candidates
from hot_events_radar.schema import CandidateEvent, HotEvent
from hot_events_radar.scorer import score_company_cluster
from hot_events_radar.sources import earnings_cal, halts, pr_wire, sec_edgar

logger = logging.getLogger(__name__)


async def detect_company_events(
    watchlist: Optional[list[str]] = None,
    window_hours: int = 24,
    min_score: float = 3.0,
    http_client: Optional[httpx.AsyncClient] = None,
    similarity_threshold: float = 0.5,
) -> list[HotEvent]:
    """Detect company-level events from all configured sources.

    Pipeline:
        1. Parallel fetch from SEC 8-K, Nasdaq halts, Finnhub earnings, PR wires
        2. Flatten candidates
        3. Cluster by ticker + headline similarity
        4. Score each cluster → HotEvent
        5. Filter by min_score, sort by score desc

    Args:
        watchlist: optional ticker filter — sources honor this to reduce noise
        window_hours: look back window
        min_score: drop events scoring below this
        http_client: optional shared httpx.AsyncClient for connection reuse
        similarity_threshold: dedupe headline Jaccard threshold

    Returns:
        HotEvents sorted by score desc. Empty list on total failure (graceful).
    """
    close_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=15.0)
    try:
        results = await asyncio.gather(
            sec_edgar.fetch_8k(window_hours=window_hours, watchlist=watchlist, http_client=client),
            halts.fetch_halts(window_hours=window_hours, watchlist=watchlist, http_client=client),
            earnings_cal.fetch_upcoming_and_recent(
                window_hours=window_hours, watchlist=watchlist, http_client=client
            ),
            pr_wire.fetch_press_releases(
                window_hours=window_hours, watchlist=watchlist, http_client=client
            ),
            return_exceptions=True,
        )
    finally:
        if close_client:
            await client.aclose()

    # Flatten, tolerating per-source exceptions
    candidates: list[CandidateEvent] = []
    source_names = ("sec_edgar", "nasdaq_halts", "finnhub_earnings", "pr_wire")
    for name, result in zip(source_names, results):
        if isinstance(result, Exception):
            logger.warning("source %s raised: %s", name, type(result).__name__)
            continue
        if result:
            candidates.extend(result)
            logger.debug("source %s returned %d candidates", name, len(result))

    if not candidates:
        return []

    clusters = cluster_candidates(candidates, similarity_threshold=similarity_threshold)
    events = [score_company_cluster(c) for c in clusters if c]
    events = [e for e in events if e.score >= min_score]
    events.sort(key=lambda e: e.score, reverse=True)
    return events

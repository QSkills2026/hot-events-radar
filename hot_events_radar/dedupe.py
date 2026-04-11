"""Deduplication and clustering for CandidateEvents.

Strategy (ordered):
  1. Group by primary_ticker intersection (most events concern specific tickers)
  2. Within each ticker group, merge near-duplicate headlines (token Jaccard > threshold)
  3. Merge events from different sources that describe the same underlying event

For events without tickers (rare for company events), fall back to headline
token similarity only.

We use token-set Jaccard rather than MinHash to avoid the datasketch dependency
being strictly required — the volume of candidates per detector run is small
(tens, not millions), so O(n²) comparison is fine.
"""

from __future__ import annotations

import re
from collections import defaultdict

from hot_events_radar.schema import CandidateEvent

_TOKEN_RE = re.compile(r"[A-Za-z0-9]{3,}")
_STOP = {
    "the", "and", "for", "from", "with", "inc", "corp", "corporation", "llc",
    "ltd", "company", "announces", "announced", "news", "release", "report",
    "reports", "reported", "today", "2024", "2025", "2026", "quarter",
    "fiscal", "year", "ceo", "cfo", "results",
}


def tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in _STOP}


def headline_similarity(a: str, b: str) -> float:
    """Token-set Jaccard similarity on headline + first-line summary."""
    ta = tokens(a)
    tb = tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def cluster_candidates(
    candidates: list[CandidateEvent],
    similarity_threshold: float = 0.5,
) -> list[list[CandidateEvent]]:
    """Cluster candidates into groups representing the same underlying event.

    Clustering strategy (ordered):
      1. Group by (primary_ticker, subtype) — same ticker + same subtype is
         strong evidence of same event; these always cluster together.
      2. Within the same ticker but different subtype (e.g. earnings vs halt),
         only cluster if headline similarity is high.
      3. Events without tickers cluster purely by headline similarity.

    The subtype-aware rule prevents merging unrelated events about the same
    ticker (e.g. "AAPL earnings beat" should not cluster with "AAPL CEO
    resigns" because the subtypes differ).

    Returns a list of clusters (each cluster is a list of CandidateEvent).
    """
    if not candidates:
        return []

    # Step 1: group by (ticker, subtype) — strong clustering signal
    by_key: dict[tuple[str, str], list[CandidateEvent]] = defaultdict(list)
    no_ticker: list[CandidateEvent] = []
    for c in candidates:
        if c.primary_tickers:
            key = (sorted(c.primary_tickers)[0], c.subtype)
            by_key[key].append(c)
        else:
            no_ticker.append(c)

    # Everything in the same (ticker, subtype) bucket becomes one cluster
    clusters: list[list[CandidateEvent]] = [list(group) for group in by_key.values()]

    # Ticker-less events: headline-similarity clustering as fallback
    if no_ticker:
        clusters.extend(_merge_by_similarity(no_ticker, similarity_threshold))

    return clusters


def _merge_by_similarity(
    events: list[CandidateEvent], threshold: float
) -> list[list[CandidateEvent]]:
    """Greedy single-linkage clustering by headline similarity."""
    clusters: list[list[CandidateEvent]] = []
    for event in events:
        placed = False
        for cluster in clusters:
            if any(
                headline_similarity(event.headline, e.headline) >= threshold
                for e in cluster
            ):
                cluster.append(event)
                placed = True
                break
        if not placed:
            clusters.append([event])
    return clusters

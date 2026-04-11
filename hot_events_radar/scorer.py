"""Company event scoring and HotEvent construction.

Company event score (0..10) is a weighted sum of five signals:

  authority      0.30  max(source.authority) — how trustworthy is the source
  magnitude      0.25  subtype-based prior — M&A > earnings > halt > generic PR
  surprise       0.20  earnings beat/miss % (0 when not applicable)
  source_count   0.15  additional corroborating sources
  recency_decay  0.10  exp(-age_hours / 12)

Each component is normalized to [0, 1] before weighting, so final score is in [0, 10].
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone

from hot_events_radar.schema import (
    CandidateEvent,
    CompanySubtype,
    EventType,
    HotEvent,
)

# Subtype → magnitude prior (0..1). Tuned so high-impact subtypes lead.
SUBTYPE_MAGNITUDE: dict[str, float] = {
    CompanySubtype.MNA.value: 1.00,
    CompanySubtype.MATERIAL_8K.value: 0.80,
    CompanySubtype.EARNINGS.value: 0.70,
    CompanySubtype.FDA.value: 0.75,
    CompanySubtype.GUIDANCE.value: 0.65,
    CompanySubtype.HALT.value: 0.60,
    CompanySubtype.OTHER_PR.value: 0.40,
}

WEIGHTS = {
    "authority": 0.30,
    "magnitude": 0.25,
    "surprise": 0.20,
    "source_count": 0.15,
    "recency_decay": 0.10,
}


def score_company_cluster(
    cluster: list[CandidateEvent],
    now: datetime | None = None,
) -> HotEvent:
    """Convert a cluster of CandidateEvents into a single scored HotEvent.

    The cluster's dominant subtype comes from the highest-authority source.
    Sources are all merged into the HotEvent.sources list.
    """
    if not cluster:
        raise ValueError("empty cluster")
    now = now or datetime.now(timezone.utc)

    # Pick the authoritative candidate as canonical (it supplies headline/summary)
    canonical = max(cluster, key=lambda c: c.source.authority)

    # Merge sources & tickers across the cluster
    all_sources = [c.source for c in cluster]
    primary_tickers = _unique(
        [t for c in cluster for t in c.primary_tickers]
    )
    related_tickers = _unique(
        [t for c in cluster for t in c.related_tickers]
    )

    # Score components
    authority = max((s.authority for s in all_sources), default=0.0)
    magnitude = SUBTYPE_MAGNITUDE.get(canonical.subtype, 0.5)
    surprise = _compute_surprise(cluster)
    source_count = min(len(all_sources) / 3.0, 1.0)  # saturates at 3 sources
    age_hours = max(
        (now - min(s.timestamp for s in all_sources)).total_seconds() / 3600.0,
        0.0,
    )
    recency = math.exp(-age_hours / 12.0)

    breakdown = {
        "authority": authority,
        "magnitude": magnitude,
        "surprise": surprise,
        "source_count": source_count,
        "recency_decay": recency,
    }
    total = sum(WEIGHTS[k] * v for k, v in breakdown.items()) * 10.0

    # Stable id: hash of canonical subtype + primary ticker + date-bucket
    event_id = _make_event_id(
        event_type="company",
        subtype=canonical.subtype,
        primary=primary_tickers[0] if primary_tickers else canonical.headline[:20],
        ts=canonical.source.timestamp,
    )

    return HotEvent(
        id=event_id,
        type=EventType.COMPANY,
        subtype=canonical.subtype,
        headline=canonical.headline,
        summary=canonical.summary,
        primary_tickers=primary_tickers,
        related_tickers=related_tickers,
        factors=[],
        score=round(total, 2),
        score_breakdown={k: round(v, 4) for k, v in breakdown.items()},
        sources=all_sources,
        started_at=min(s.timestamp for s in all_sources),
        updated_at=now,
    )


def _compute_surprise(cluster: list[CandidateEvent]) -> float:
    """Extract max earnings surprise across cluster candidates.

    Returns 0 if no candidate has a surprise_pct. Caps at 1.0 (100% surprise).
    """
    max_surprise = 0.0
    for c in cluster:
        val = c.extra.get("surprise_pct")
        if val is not None:
            try:
                max_surprise = max(max_surprise, min(abs(float(val)), 1.0))
            except (TypeError, ValueError):
                continue
    return max_surprise


def _unique(items: list[str]) -> list[str]:
    """Dedupe preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _make_event_id(
    event_type: str, subtype: str, primary: str, ts: datetime
) -> str:
    """Generate a stable 16-char hex id from event components."""
    # Bucket timestamp to 6-hour windows so minor re-fetches produce the same id
    bucket = int(ts.timestamp()) // (6 * 3600)
    raw = f"{event_type}|{subtype}|{primary}|{bucket}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

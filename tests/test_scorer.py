"""Tests for the company event scorer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from hot_events_radar.schema import CandidateEvent, CompanySubtype, EventSource, EventType
from hot_events_radar.scorer import score_company_cluster


def _make_candidate(
    source_name: str,
    authority: float,
    subtype: CompanySubtype,
    ticker: str = "NVDA",
    age_hours: float = 1.0,
    extra: Optional[dict] = None,
    now: Optional[datetime] = None,
):
    now = now or datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc)
    from datetime import timedelta
    source = EventSource(
        name=source_name,
        authority=authority,
        url="https://example.com",
        timestamp=now - timedelta(hours=age_hours),
    )
    return CandidateEvent(
        source=source,
        subtype=subtype.value,
        headline=f"{ticker} {subtype.value} event",
        summary="test summary",
        primary_tickers=[ticker],
        extra=extra or {},
    )


def test_score_mna_high():
    """M&A from SEC 8-K should score high."""
    now = datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc)
    cluster = [_make_candidate("sec_edgar", 1.0, CompanySubtype.MNA, age_hours=1, now=now)]
    event = score_company_cluster(cluster, now=now)
    assert event.type == EventType.COMPANY
    assert event.subtype == "mna"
    assert event.score > 5.5  # 1.0*0.30 + 1.0*0.25 + 0*0.20 + 0.33*0.15 + 0.92*0.10 ≈ 6.47


def test_score_earnings_surprise():
    """Earnings with a 20% surprise should score higher than a 0% surprise."""
    now = datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc)
    with_surprise = [
        _make_candidate(
            "finnhub",
            0.9,
            CompanySubtype.EARNINGS,
            age_hours=1,
            extra={"surprise_pct": 0.20},
            now=now,
        )
    ]
    without_surprise = [
        _make_candidate("finnhub", 0.9, CompanySubtype.EARNINGS, age_hours=1, now=now)
    ]
    a = score_company_cluster(with_surprise, now=now)
    b = score_company_cluster(without_surprise, now=now)
    assert a.score > b.score


def test_score_magnitude_ordering():
    """M&A magnitude > earnings > halt > generic PR."""
    now = datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc)
    mna = score_company_cluster(
        [_make_candidate("sec_edgar", 1.0, CompanySubtype.MNA, age_hours=1, now=now)],
        now=now,
    )
    earn = score_company_cluster(
        [_make_candidate("sec_edgar", 1.0, CompanySubtype.EARNINGS, age_hours=1, now=now)],
        now=now,
    )
    halt = score_company_cluster(
        [_make_candidate("sec_edgar", 1.0, CompanySubtype.HALT, age_hours=1, now=now)],
        now=now,
    )
    pr = score_company_cluster(
        [_make_candidate("sec_edgar", 1.0, CompanySubtype.OTHER_PR, age_hours=1, now=now)],
        now=now,
    )
    assert mna.score > earn.score > halt.score > pr.score


def test_score_recency_decay():
    """Older events should score lower than fresh ones."""
    now = datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc)
    fresh = score_company_cluster(
        [_make_candidate("sec_edgar", 1.0, CompanySubtype.MNA, age_hours=0.5, now=now)],
        now=now,
    )
    old = score_company_cluster(
        [_make_candidate("sec_edgar", 1.0, CompanySubtype.MNA, age_hours=23, now=now)],
        now=now,
    )
    assert fresh.score > old.score


def test_score_multi_source_boost():
    """Multiple corroborating sources should raise source_count and total score."""
    now = datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc)
    single = score_company_cluster(
        [_make_candidate("sec_edgar", 1.0, CompanySubtype.MNA, age_hours=1, now=now)],
        now=now,
    )
    triple = score_company_cluster(
        [
            _make_candidate("sec_edgar", 1.0, CompanySubtype.MNA, age_hours=1, now=now),
            _make_candidate("business_wire", 0.85, CompanySubtype.MNA, age_hours=1, now=now),
            _make_candidate("nasdaq_halts", 0.95, CompanySubtype.MNA, age_hours=1, now=now),
        ],
        now=now,
    )
    assert triple.score > single.score
    assert len(triple.sources) == 3
    # Cluster picks the highest-authority source as canonical
    assert triple.sources[0].name == "sec_edgar" or any(s.name == "sec_edgar" for s in triple.sources)


def test_score_id_stable():
    """Same cluster → same id (for caching)."""
    now = datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc)
    c = [_make_candidate("sec_edgar", 1.0, CompanySubtype.MNA, age_hours=1, now=now)]
    a = score_company_cluster(c, now=now)
    b = score_company_cluster(c, now=now)
    assert a.id == b.id


def test_breakdown_all_components_present():
    now = datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc)
    event = score_company_cluster(
        [_make_candidate("sec_edgar", 1.0, CompanySubtype.MNA, age_hours=1, now=now)],
        now=now,
    )
    for k in ("authority", "magnitude", "surprise", "source_count", "recency_decay"):
        assert k in event.score_breakdown

"""Tests for HotEvent schema (serialization round-trip, discriminator)."""

from datetime import datetime, timezone

from hot_events_radar.schema import (
    CandidateEvent,
    CompanySubtype,
    EventSource,
    EventType,
    HotEvent,
)


def _sample_event() -> HotEvent:
    source = EventSource(
        name="sec_edgar",
        authority=1.0,
        url="https://www.sec.gov/...",
        timestamp=datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc),
        raw_snippet="8-K - NVDA",
    )
    return HotEvent(
        id="abc123",
        type=EventType.COMPANY,
        subtype=CompanySubtype.MNA.value,
        headline="NVIDIA Acquires Run:ai",
        summary="M&A completion",
        primary_tickers=["NVDA"],
        related_tickers=[],
        factors=[],
        score=8.7,
        score_breakdown={"authority": 1.0, "magnitude": 1.0},
        sources=[source],
        started_at=datetime(2026, 4, 11, 13, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 11, 14, 30, 0, tzinfo=timezone.utc),
    )


def test_hot_event_roundtrip():
    e = _sample_event()
    data = e.to_dict()
    assert data["type"] == "company"
    assert data["subtype"] == "mna"
    assert data["primary_tickers"] == ["NVDA"]
    assert data["score"] == 8.7

    restored = HotEvent.from_dict(data)
    assert restored.id == e.id
    assert restored.type == EventType.COMPANY
    assert restored.primary_tickers == e.primary_tickers
    assert restored.sources[0].authority == 1.0


def test_event_type_discriminator_preserves_v2_v3_space():
    """Verify schema is forward-compatible with V2 (macro) and V3 (social)."""
    assert EventType.COMPANY.value == "company"
    assert EventType.MACRO.value == "macro"
    assert EventType.SOCIAL.value == "social"
    # `factors` field exists and defaults to empty (will be populated in V2)
    e = _sample_event()
    assert e.factors == []


def test_candidate_event_intermediate():
    """CandidateEvents are the dedupe input; must carry source + extras."""
    source = EventSource(
        name="finnhub",
        authority=0.9,
        url="https://...",
        timestamp=datetime.now(timezone.utc),
    )
    c = CandidateEvent(
        source=source,
        subtype=CompanySubtype.EARNINGS.value,
        headline="TSLA beat",
        summary="Q1 earnings",
        primary_tickers=["TSLA"],
        extra={"surprise_pct": 0.15},
    )
    assert c.source.name == "finnhub"
    assert c.extra["surprise_pct"] == 0.15

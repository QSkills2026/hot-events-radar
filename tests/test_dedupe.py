"""Tests for dedupe / cluster logic."""

from datetime import datetime, timezone

from hot_events_radar.dedupe import (
    cluster_candidates,
    headline_similarity,
    tokens,
)
from hot_events_radar.schema import CandidateEvent, CompanySubtype, EventSource


def _candidate(source_name: str, authority: float, headline: str, tickers: list[str]):
    source = EventSource(
        name=source_name,
        authority=authority,
        url="https://...",
        timestamp=datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc),
    )
    return CandidateEvent(
        source=source,
        subtype=CompanySubtype.MNA.value,
        headline=headline,
        summary=headline,
        primary_tickers=tickers,
    )


def test_tokens_filter_stopwords():
    ts = tokens("NVIDIA Corp acquires Run:ai for $700M")
    assert "nvidia" in ts
    assert "acquires" in ts
    # "corp" is a stopword
    assert "corp" not in ts


def test_headline_similarity_duplicate_stories():
    """Two sources reporting the same event should have measurable overlap."""
    a = "NVIDIA Corporation announces acquisition of Run labs technology"
    b = "NVIDIA announces acquisition of Run labs technology completed"
    # Jaccard on shared tokens after stopword filter
    assert headline_similarity(a, b) > 0.5


def test_headline_similarity_unrelated():
    a = "NVIDIA acquires Run:ai Labs"
    b = "Ford cuts full-year guidance"
    assert headline_similarity(a, b) < 0.1


def test_cluster_groups_same_ticker_same_subtype():
    """Same ticker + same subtype → one cluster (the strong clustering rule)."""
    candidates = [
        _candidate("sec_edgar", 1.0, "NVIDIA acquires Run:ai Labs", ["NVDA"]),
        _candidate("business_wire", 0.85, "NVIDIA completes Run acquisition", ["NVDA"]),
        _candidate("sec_edgar", 1.0, "Ford lowers guidance", ["F"]),
    ]
    # The Ford event is a different ticker so it must have different subtype too
    candidates[2] = CandidateEvent(
        source=candidates[2].source,
        subtype=CompanySubtype.GUIDANCE.value,
        headline=candidates[2].headline,
        summary=candidates[2].summary,
        primary_tickers=["F"],
    )
    clusters = cluster_candidates(candidates)
    # NVDA pair merged into 1 cluster, F alone
    assert len(clusters) == 2
    nvda_cluster = [c for c in clusters if "NVDA" in c[0].primary_tickers][0]
    assert len(nvda_cluster) == 2


def test_cluster_keeps_different_subtypes_separate():
    """Same ticker but different subtypes (earnings vs halt) must stay separate."""
    candidates = [
        CandidateEvent(
            source=EventSource(
                name="sec_edgar", authority=1.0, url="https://...",
                timestamp=datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc),
            ),
            subtype=CompanySubtype.EARNINGS.value,
            headline="AAPL earnings beat expectations",
            summary="Q1 results",
            primary_tickers=["AAPL"],
        ),
        CandidateEvent(
            source=EventSource(
                name="sec_edgar", authority=1.0, url="https://...",
                timestamp=datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc),
            ),
            subtype=CompanySubtype.HALT.value,
            headline="AAPL trading halted",
            summary="halt notice",
            primary_tickers=["AAPL"],
        ),
    ]
    clusters = cluster_candidates(candidates)
    assert len(clusters) == 2


def test_cluster_empty():
    assert cluster_candidates([]) == []

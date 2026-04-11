"""Tests for SEC 8-K atom feed parser (offline fixture)."""

from datetime import datetime, timezone

from hot_events_radar.schema import CompanySubtype
from hot_events_radar.sources.sec_edgar import (
    _classify_8k,
    _extract_tickers_from_title,
    parse_8k_atom,
)


def test_extract_tickers_from_title():
    """SEC titles like '(AAPL)' should yield the ticker."""
    title = "8-K - APPLE INC (AAPL) (Filer)"
    assert _extract_tickers_from_title(title) == ["AAPL"]
    # Multiple parens — prefer single uppercase
    title2 = "8-K - NVIDIA CORP (NVDA) (0001045810) (Filer)"
    assert _extract_tickers_from_title(title2) == ["NVDA"]


def test_classify_8k_items():
    """Item numbers map to the right subtype."""
    sub, _ = _classify_8k("Item 5.02 Departure of officer")
    assert sub == CompanySubtype.MATERIAL_8K
    sub, _ = _classify_8k("Item 2.01 Completion of Acquisition")
    assert sub == CompanySubtype.MNA
    sub, _ = _classify_8k("Item 2.02 Results of Operations")
    assert sub == CompanySubtype.EARNINGS
    # Fallback on keywords
    sub, _ = _classify_8k("No item number but mentions merger")
    assert sub == CompanySubtype.MNA


def test_parse_8k_atom_returns_recent_only(fixture_8k_xml, reference_now):
    """Entries older than window_hours should be filtered out."""
    events = parse_8k_atom(fixture_8k_xml, window_hours=24, now=reference_now)
    # Expect 3 recent entries (AAPL, NVDA, TSLA) — OLD is 6 days old, excluded
    assert len(events) == 3
    tickers = {t for e in events for t in e.primary_tickers}
    assert tickers == {"AAPL", "NVDA", "TSLA"}


def test_parse_8k_atom_watchlist_filter(fixture_8k_xml, reference_now):
    """Watchlist should narrow results to matching tickers."""
    events = parse_8k_atom(
        fixture_8k_xml, window_hours=24, watchlist=["NVDA"], now=reference_now
    )
    assert len(events) == 1
    assert events[0].primary_tickers == ["NVDA"]
    assert events[0].subtype == CompanySubtype.MNA.value


def test_parse_8k_atom_authority_is_one(fixture_8k_xml, reference_now):
    """SEC is the most authoritative source, should be 1.0."""
    events = parse_8k_atom(fixture_8k_xml, window_hours=24, now=reference_now)
    for e in events:
        assert e.source.authority == 1.0
        assert e.source.name == "sec_edgar"


def test_parse_8k_atom_large_window_includes_old(fixture_8k_xml, reference_now):
    """With a huge window, OLD filing should also come through."""
    events = parse_8k_atom(fixture_8k_xml, window_hours=24 * 365, now=reference_now)
    tickers = {t for e in events for t in e.primary_tickers}
    assert "OLD" in tickers

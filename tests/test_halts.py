"""Tests for Nasdaq halts RSS parser."""

from hot_events_radar.schema import CompanySubtype
from hot_events_radar.sources.halts import (
    _extract_halt_ticker,
    _extract_reason_code,
    parse_halts_rss,
)


def test_extract_halt_ticker():
    assert _extract_halt_ticker("GME - Trading Halt - T1", "") == "GME"
    assert _extract_halt_ticker("Trading Halt - AMC", "") == "AMC"


def test_extract_reason_code():
    assert _extract_reason_code("GME - T1", "") == "T1"
    assert _extract_reason_code("XYZ - M", "Market volatility pause") == "M"
    assert _extract_reason_code("", "T12 info requested") == "T12"


def test_parse_halts_rss(fixture_halts_xml, reference_now):
    events = parse_halts_rss(fixture_halts_xml, window_hours=24, now=reference_now)
    # Three halt items in fixture
    assert len(events) == 3
    tickers = {e.primary_tickers[0] for e in events}
    assert tickers == {"GME", "AMC", "XYZ"}

    # All should be HALT subtype
    for e in events:
        assert e.subtype == CompanySubtype.HALT.value
        assert e.source.name == "nasdaq_halts"


def test_parse_halts_authority_by_code(fixture_halts_xml, reference_now):
    """T1/T12 should be high-authority; M (volatility pause) lower."""
    events = parse_halts_rss(fixture_halts_xml, window_hours=24, now=reference_now)
    by_ticker = {e.primary_tickers[0]: e for e in events}
    assert by_ticker["GME"].source.authority >= 0.9  # T1
    assert by_ticker["AMC"].source.authority >= 0.9  # T12
    assert by_ticker["XYZ"].source.authority <= 0.7  # M


def test_parse_halts_watchlist_filter(fixture_halts_xml, reference_now):
    events = parse_halts_rss(
        fixture_halts_xml, window_hours=24, watchlist=["GME"], now=reference_now
    )
    assert len(events) == 1
    assert events[0].primary_tickers == ["GME"]

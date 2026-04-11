"""Tests for Business Wire / PR Newswire RSS parser."""

from hot_events_radar.schema import CompanySubtype
from hot_events_radar.sources.pr_wire import (
    _classify,
    _extract_tickers,
    parse_pr_feed,
)


def test_extract_tickers_explicit_exchange():
    """Prefer (NASDAQ: XYZ) / (NYSE: XYZ) form when present."""
    text = "NVIDIA Corporation (NASDAQ: NVDA) Announces New Product"
    assert _extract_tickers(text) == ["NVDA"]
    text2 = "Pfizer (NYSE: PFE) Receives FDA Approval"
    assert _extract_tickers(text2) == ["PFE"]


def test_extract_tickers_filters_stopwords():
    """Common uppercase words should not be mistaken for tickers."""
    text = "THE CEO OF AN INC WILL RESIGN"
    result = _extract_tickers(text)
    for stop in ("THE", "CEO", "AN", "INC"):
        assert stop not in result


def test_classify_mna():
    sub, _ = _classify("NVIDIA to acquire Run:ai for $700M")
    assert sub == CompanySubtype.MNA


def test_classify_fda():
    sub, _ = _classify("Company receives FDA approval for phase 3 trial")
    assert sub == CompanySubtype.FDA


def test_classify_guidance():
    sub, _ = _classify("Ford lowers full-year guidance on supply disruptions")
    assert sub == CompanySubtype.GUIDANCE


def test_classify_generic():
    sub, _ = _classify("Random corporate update with no keywords")
    assert sub == CompanySubtype.OTHER_PR


def test_parse_bw_feed(fixture_bw_xml, reference_now):
    events = parse_pr_feed(
        fixture_bw_xml,
        source_name="business_wire",
        authority=0.85,
        window_hours=24,
        now=reference_now,
    )
    assert len(events) == 3
    tickers = {e.primary_tickers[0] for e in events}
    assert tickers == {"NVDA", "PFE", "F"}

    # Subtype classification
    by_ticker = {e.primary_tickers[0]: e for e in events}
    assert by_ticker["NVDA"].subtype == CompanySubtype.MNA.value
    assert by_ticker["PFE"].subtype == CompanySubtype.FDA.value
    assert by_ticker["F"].subtype == CompanySubtype.GUIDANCE.value


def test_parse_bw_watchlist_filter(fixture_bw_xml, reference_now):
    events = parse_pr_feed(
        fixture_bw_xml,
        source_name="business_wire",
        authority=0.85,
        window_hours=24,
        watchlist=["NVDA"],
        now=reference_now,
    )
    assert len(events) == 1
    assert events[0].primary_tickers == ["NVDA"]

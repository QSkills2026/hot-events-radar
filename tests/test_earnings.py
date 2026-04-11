"""Tests for Finnhub earnings calendar parser."""

from hot_events_radar.schema import CompanySubtype
from hot_events_radar.sources.earnings_cal import parse_earnings_payload


def test_parse_recent_and_upcoming(fixture_earnings_json, reference_now):
    """Should include both recent (with actual) and upcoming (within 7 days)."""
    events = parse_earnings_payload(
        fixture_earnings_json,
        now=reference_now,
        window_hours=24,
    )
    tickers = {e.primary_tickers[0] for e in events}
    # TSLA and F are "recent" with actuals; AAPL is upcoming.
    # MSFT from 2025-11-01 is way too old, should be excluded.
    assert "TSLA" in tickers
    assert "F" in tickers
    assert "AAPL" in tickers
    assert "MSFT" not in tickers


def test_surprise_percent_computation(fixture_earnings_json, reference_now):
    """TSLA beat: |1.85 - 1.60| / 1.60 = 0.15625"""
    events = parse_earnings_payload(
        fixture_earnings_json, now=reference_now, window_hours=24
    )
    tsla = next(e for e in events if e.primary_tickers[0] == "TSLA")
    assert tsla.extra["surprise_pct"] is not None
    assert abs(tsla.extra["surprise_pct"] - 0.15625) < 0.001
    assert tsla.extra["is_recent"] is True


def test_upcoming_has_no_surprise(fixture_earnings_json, reference_now):
    """Upcoming AAPL has no epsActual yet → surprise_pct should be None."""
    events = parse_earnings_payload(
        fixture_earnings_json, now=reference_now, window_hours=24
    )
    aapl = next(e for e in events if e.primary_tickers[0] == "AAPL")
    assert aapl.extra["surprise_pct"] is None
    assert aapl.extra["is_upcoming"] is True


def test_watchlist_filter(fixture_earnings_json, reference_now):
    events = parse_earnings_payload(
        fixture_earnings_json, now=reference_now, window_hours=24, watchlist=["TSLA"]
    )
    assert len(events) == 1
    assert events[0].primary_tickers == ["TSLA"]
    assert events[0].subtype == CompanySubtype.EARNINGS.value


def test_empty_payload():
    """Graceful handling of empty/missing data."""
    assert parse_earnings_payload({}) == []
    assert parse_earnings_payload({"earningsCalendar": []}) == []

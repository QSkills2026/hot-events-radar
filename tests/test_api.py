"""End-to-end API test with mocked sources.

Uses monkeypatch to replace the four source fetch functions so we can test
get_events / get_company_events without any network calls.
"""

from datetime import datetime, timezone

import pytest

from hot_events_radar import EventType, get_company_events, get_events
from hot_events_radar.schema import CandidateEvent, CompanySubtype, EventSource


def _candidate(source_name: str, authority: float, subtype: CompanySubtype, ticker: str):
    source = EventSource(
        name=source_name,
        authority=authority,
        url="https://example.com",
        timestamp=datetime(2026, 4, 11, 13, 30, 0, tzinfo=timezone.utc),
    )
    return CandidateEvent(
        source=source,
        subtype=subtype.value,
        headline=f"{ticker} {subtype.value}",
        summary="test",
        primary_tickers=[ticker],
    )


@pytest.mark.asyncio
async def test_get_company_events_end_to_end(monkeypatch):
    """Mock all four sources; verify clustering, scoring, sorting."""

    async def fake_sec(**kwargs):
        return [_candidate("sec_edgar", 1.0, CompanySubtype.MNA, "NVDA")]

    async def fake_halts(**kwargs):
        return [_candidate("nasdaq_halts", 0.95, CompanySubtype.HALT, "GME")]

    async def fake_earnings(**kwargs):
        return [_candidate("finnhub", 0.9, CompanySubtype.EARNINGS, "TSLA")]

    async def fake_pr(**kwargs):
        return [_candidate("business_wire", 0.85, CompanySubtype.OTHER_PR, "MSFT")]

    from hot_events_radar.sources import earnings_cal, halts, pr_wire, sec_edgar
    monkeypatch.setattr(sec_edgar, "fetch_8k", fake_sec)
    monkeypatch.setattr(halts, "fetch_halts", fake_halts)
    monkeypatch.setattr(earnings_cal, "fetch_upcoming_and_recent", fake_earnings)
    monkeypatch.setattr(pr_wire, "fetch_press_releases", fake_pr)

    events = await get_company_events(window_hours=24, min_score=0.0)
    assert len(events) == 4
    # Sorted by score desc; M&A from SEC should lead
    assert events[0].primary_tickers == ["NVDA"]
    assert events[0].subtype == CompanySubtype.MNA.value


@pytest.mark.asyncio
async def test_get_events_skips_unimplemented(monkeypatch, caplog):
    """Requesting MACRO/SOCIAL should log but not crash."""

    async def fake_sec(**kwargs):
        return []

    async def fake_halts(**kwargs):
        return []

    async def fake_earnings(**kwargs):
        return []

    async def fake_pr(**kwargs):
        return []

    from hot_events_radar.sources import earnings_cal, halts, pr_wire, sec_edgar
    monkeypatch.setattr(sec_edgar, "fetch_8k", fake_sec)
    monkeypatch.setattr(halts, "fetch_halts", fake_halts)
    monkeypatch.setattr(earnings_cal, "fetch_upcoming_and_recent", fake_earnings)
    monkeypatch.setattr(pr_wire, "fetch_press_releases", fake_pr)

    events = await get_events(
        types=[EventType.COMPANY, EventType.MACRO, EventType.SOCIAL]
    )
    assert events == []


@pytest.mark.asyncio
async def test_get_events_min_score_filter(monkeypatch):
    """High threshold should filter everything out."""

    async def fake_sec(**kwargs):
        return [_candidate("sec_edgar", 1.0, CompanySubtype.OTHER_PR, "XYZ")]

    async def fake_halts(**kwargs):
        return []

    async def fake_earnings(**kwargs):
        return []

    async def fake_pr(**kwargs):
        return []

    from hot_events_radar.sources import earnings_cal, halts, pr_wire, sec_edgar
    monkeypatch.setattr(sec_edgar, "fetch_8k", fake_sec)
    monkeypatch.setattr(halts, "fetch_halts", fake_halts)
    monkeypatch.setattr(earnings_cal, "fetch_upcoming_and_recent", fake_earnings)
    monkeypatch.setattr(pr_wire, "fetch_press_releases", fake_pr)

    events = await get_company_events(min_score=9.0)
    assert events == []

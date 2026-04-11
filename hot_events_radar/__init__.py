"""hot-events-radar: Detect hot financial events from authoritative sources.

MVP focus: company-level events (SEC 8-K, exchange halts, earnings calendar,
press wire). Macro and social detectors are stubbed for V2/V3.

Public API:
    get_events(types, watchlist, window_hours, min_score) -> list[HotEvent]
    get_company_events(watchlist, window_hours, min_score) -> list[HotEvent]

Schema:
    HotEvent, EventType, CompanySubtype, EventSource
"""

from hot_events_radar.schema import (
    CompanySubtype,
    EventSource,
    EventType,
    HotEvent,
)
from hot_events_radar.api import get_company_events, get_events

__version__ = "0.1.0"

__all__ = [
    "get_events",
    "get_company_events",
    "HotEvent",
    "EventType",
    "CompanySubtype",
    "EventSource",
    "__version__",
]

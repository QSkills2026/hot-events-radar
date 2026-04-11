"""HotEvent schema with type discriminator for MVP (company) + V2 (macro) + V3 (social).

The discriminator design lets downstream consumers treat all event types uniformly
while retaining per-type subtype information. V2 and V3 only need to add new
subtype enums and populate type-specific fields — schema itself stays stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    """Top-level event discriminator."""

    COMPANY = "company"  # MVP: earnings, M&A, 8-K, halts, guidance
    MACRO = "macro"      # V2: geopolitical, monetary policy, fiscal, trade
    SOCIAL = "social"    # V3: Reddit/StockTwits crowd signals


class CompanySubtype(str, Enum):
    """Subtypes for EventType.COMPANY (MVP)."""

    EARNINGS = "earnings"
    MNA = "mna"
    MATERIAL_8K = "material_8k"
    HALT = "halt"
    GUIDANCE = "guidance"
    FDA = "fda"
    OTHER_PR = "other_pr"


@dataclass
class EventSource:
    """One source attestation for an event.

    Multiple sources can corroborate the same event (merged during dedupe/cluster).
    The `authority` score drives source-weighted scoring.
    """

    name: str                    # "sec_edgar", "nasdaq_halts", "finnhub", "business_wire"
    authority: float             # 0..1, higher = more authoritative
    url: str
    timestamp: datetime          # when this source published
    raw_snippet: str = ""        # short excerpt for display/debugging


@dataclass
class HotEvent:
    """Canonical event record emitted by all detectors.

    The `type` field is the discriminator; `subtype` is type-specific enum
    (CompanySubtype for MVP). `factors` is reserved for V2 macro events
    (VIX/DXY/oil/rates exposure strings) — empty in MVP.
    """

    id: str                              # stable hash(type + primary_entity + started_at)
    type: EventType
    subtype: Optional[str]               # CompanySubtype value (or MacroSubtype/SocialSubtype in V2/V3)
    headline: str
    summary: str                         # <= 500 chars
    primary_tickers: list[str] = field(default_factory=list)
    related_tickers: list[str] = field(default_factory=list)
    factors: list[str] = field(default_factory=list)  # V2 macro: ["VIX","DXY","oil"]
    score: float = 0.0                   # 0..10
    score_breakdown: dict[str, float] = field(default_factory=dict)
    sources: list[EventSource] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict for caching / API responses."""
        return {
            "id": self.id,
            "type": self.type.value if isinstance(self.type, EventType) else self.type,
            "subtype": self.subtype,
            "headline": self.headline,
            "summary": self.summary,
            "primary_tickers": list(self.primary_tickers),
            "related_tickers": list(self.related_tickers),
            "factors": list(self.factors),
            "score": self.score,
            "score_breakdown": dict(self.score_breakdown),
            "sources": [
                {
                    "name": s.name,
                    "authority": s.authority,
                    "url": s.url,
                    "timestamp": s.timestamp.isoformat(),
                    "raw_snippet": s.raw_snippet,
                }
                for s in self.sources
            ],
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HotEvent":
        """Deserialize from JSON dict."""
        return cls(
            id=data["id"],
            type=EventType(data["type"]),
            subtype=data.get("subtype"),
            headline=data["headline"],
            summary=data.get("summary", ""),
            primary_tickers=list(data.get("primary_tickers", [])),
            related_tickers=list(data.get("related_tickers", [])),
            factors=list(data.get("factors", [])),
            score=float(data.get("score", 0.0)),
            score_breakdown=dict(data.get("score_breakdown", {})),
            sources=[
                EventSource(
                    name=s["name"],
                    authority=float(s["authority"]),
                    url=s["url"],
                    timestamp=datetime.fromisoformat(s["timestamp"]),
                    raw_snippet=s.get("raw_snippet", ""),
                )
                for s in data.get("sources", [])
            ],
            started_at=datetime.fromisoformat(data["started_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


@dataclass
class CandidateEvent:
    """Intermediate event before dedupe/scoring.

    Each source emits a list of CandidateEvents; dedupe merges them into
    clusters, then scorer produces HotEvent objects.
    """

    source: EventSource
    subtype: str                # CompanySubtype value
    headline: str
    summary: str
    primary_tickers: list[str] = field(default_factory=list)
    related_tickers: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)  # source-specific metadata (e.g. earnings beat %)

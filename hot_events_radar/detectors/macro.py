"""Macro / geopolitical event detector — V2 stub.

V2 scope (not implemented in MVP):
  - Whitelist authoritative sources: Reuters, Bloomberg, AP, FT, WSJ, Fed,
    State Dept, ECB, BOJ
  - LLM classifier for {geopolitical_conflict, monetary_policy, fiscal,
    trade_war, regulatory, pandemic, natural_disaster}
  - Cross-market confirmation: VIX z-score, DXY move, TLT/gold movement
  - Factor mapping: event → {VIX, DXY, oil, rates, defense, gold} exposure

The factor-based impact analysis in V2 will populate HotEvent.factors
so position-impact-analyst can compute portfolio exposure through macro
channels (not just direct ticker matches).
"""

from __future__ import annotations

from typing import Optional

from hot_events_radar.schema import HotEvent


async def detect_macro_events(
    window_hours: int = 24,
    min_score: float = 3.0,
    **kwargs,
) -> list[HotEvent]:
    """V2 placeholder. Raises NotImplementedError."""
    raise NotImplementedError(
        "Macro event detection is planned for V2. "
        "MVP only supports company events."
    )

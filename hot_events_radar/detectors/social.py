"""Social / crowd sentiment detector — V3 stub.

V3 scope (not implemented in MVP):
  - Sources: r/wallstreetbets, r/stocks, r/options, r/investing top daily +
    comments; StockTwits trending; HN firebase
  - Ticker extraction with stopword filter + validation against ticker dict
  - Scoring: mention_count_24h, mention_z_score (vs 30d baseline), velocity,
    sentiment (FinBERT or LLM), quality_weight (upvotes/comment length)
  - Rank by z-score, not raw count — NVDA being discussed daily is not news;
    small-cap jumping from 5 to 500 mentions is
  - Output: top 10 by z-score with crowding warnings for risk report

V3 is the latest to implement because signal value is loosest (noise >> info).
"""

from __future__ import annotations

from typing import Optional

from hot_events_radar.schema import HotEvent


async def detect_social_events(
    window_hours: int = 24,
    min_score: float = 3.0,
    **kwargs,
) -> list[HotEvent]:
    """V3 placeholder. Raises NotImplementedError."""
    raise NotImplementedError(
        "Social sentiment detection is planned for V3. "
        "MVP only supports company events."
    )

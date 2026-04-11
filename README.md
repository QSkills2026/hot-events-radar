# hot-events-radar

> Detect hot financial events from authoritative sources — SEC 8-K filings,
> exchange halts, earnings calendar, press wires — with a pluggable
> source/detector architecture ready for macro and social signals in V2/V3.

```
pip install hot-events-radar
```

---

## What it does

Given an optional ticker watchlist and time window, this library pulls
candidate events from multiple authoritative sources in parallel, deduplicates
them, scores them on a 5-signal rubric, and returns sorted `HotEvent` objects.

**Input:** watchlist (optional), window in hours, minimum score
**Output:** scored `HotEvent` list, sorted by score descending

Unlike news aggregators, this focuses on **actionable material events** —
the kind that move a stock 5% on the day: M&A announcements, earnings
beats/misses, trading halts with pending news, FDA actions, material 8-K
filings.

---

## Quick start

```python
import asyncio
from hot_events_radar import get_company_events

async def main():
    events = await get_company_events(
        watchlist=["AAPL", "NVDA", "TSLA", "MSFT"],
        window_hours=24,
        min_score=3.0,
    )
    for e in events:
        print(f"{e.score:4.1f}  {e.subtype:14s}  {e.primary_tickers}  {e.headline[:60]}")

asyncio.run(main())
```

Sample output:

```
 8.7  mna             ['NVDA']   NVIDIA to Acquire Run:ai for $700M
 7.2  earnings        ['TSLA']   TSLA earnings beat: actual=1.85 vs est=1.60
 6.1  halt            ['GME']    GME halted: News Pending
 5.4  material_8k     ['AAPL']   8-K - APPLE INC — Item 5.02 Departure of Officer
```

---

## Architecture

```
hot_events_radar/
├── api.py                      # get_events() / get_company_events()
├── schema.py                   # HotEvent (type discriminator for V2/V3)
├── detectors/
│   ├── company.py              # MVP — orchestrates all company sources
│   ├── macro.py                # V2 stub (Reuters/Fed/Bloomberg + factors)
│   └── social.py               # V3 stub (Reddit/StockTwits)
├── sources/
│   ├── sec_edgar.py            # SEC 8-K atom feed (authority=1.0)
│   ├── halts.py                # Nasdaq trading halts RSS
│   ├── earnings_cal.py         # Finnhub earnings calendar (beat/miss)
│   └── pr_wire.py              # Business Wire + PR Newswire RSS
├── dedupe.py                   # Jaccard token clustering
└── scorer.py                   # 5-signal weighted score → HotEvent
```

## Scoring rubric (company events)

| Signal | Weight | Meaning |
|---|---|---|
| `authority` | 0.30 | max(source.authority) — 8-K = 1.0, halt = 0.95, wire = 0.85 |
| `magnitude` | 0.25 | subtype prior — M&A > 8-K > earnings > halt > generic PR |
| `surprise` | 0.20 | earnings beat/miss %, 0 when N/A |
| `source_count` | 0.15 | corroborating sources, saturates at 3 |
| `recency_decay` | 0.10 | exp(-age_hours / 12) |

Final score is in **[0, 10]**. Default threshold is 3.0.

## Data sources

| Source | Authority | Key required | Notes |
|---|---|---|---|
| SEC EDGAR 8-K | 1.00 | No | Legally mandated, ~8 min delay, most authoritative |
| Nasdaq trading halts | 0.55-1.00 | No | RSS, T1/T12 codes precede news |
| Finnhub earnings calendar | 0.90 | `FINNHUB_API_KEY` (free tier) | Beat/miss + upcoming 7d |
| Business Wire / PR Newswire | 0.85 | No | Firehose — ticker-filtered |

Set `FINNHUB_API_KEY` in your env for earnings data. Other sources work without any key.

## V2 / V3 roadmap

Macro and social detectors are stubbed but not yet implemented:

- **V2: Macro** — Reuters/Bloomberg/Fed whitelisted sources + LLM topic
  classifier + factor exposure (VIX/DXY/oil/rates)
- **V3: Social** — Reddit/StockTwits with z-score ticker trend detection and
  crowding warnings (not raw mention count — z-score vs 30d baseline)

The `HotEvent` schema reserves the `factors` field (V2) and the `EventType`
enum has `MACRO` / `SOCIAL` placeholders, so downstream code works unchanged
when new detectors land.

## Companion skill

For event → portfolio impact assessment, pair this with
[position-impact-analyst](https://github.com/QSkills2026/position-impact-analyst),
which consumes `HotEvent` + a list of positions and produces structured
`ImpactAssessment` via an LLM using configurable `risk` / `opportunity`
personas.

## Requirements

- Python 3.10+
- `httpx>=0.27`
- `feedparser>=6.0`

## License

MIT

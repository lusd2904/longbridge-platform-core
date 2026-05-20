# Sentiment Center GitHub Adoption Plan

Date: 2026-05-21

## Goal

Build a dedicated sentiment center for market news, symbol-linked public opinion, and quant-consumable sentiment signals.

The first implementation should reuse the existing `sentiment-service` boundary and current AI gateway settings instead of introducing a new model or secret system.

## Current Platform Baseline

- `apps/market/sentiment-service` exists and is now the native boundary for the first read-only sentiment contract.
- `api-gateway` already tracks `sentiment-service` as a platform dependency.
- `/finance-news` already displays finance briefing style content.
- `/recommendations`, `/ai-analysis`, `/strategy`, and scheduler tasks can consume structured sentiment fields later.
- AI settings already exist through `LONGBRIDGE_AI_*` and Docker `sub2api`.

## GitHub Candidates Reviewed

| Project | Useful Ideas | Direct Adoption Risk | Recommendation |
|---|---|---|---|
| `FinNLP` | Financial news collection patterns, event extraction concepts, downstream evaluation ideas | Broad toolkit rather than a ready-made platform; ingestion assumptions still need local validation | Reference collection and evaluation patterns only |
| `FinBERT` / `FinABSA` | Optional local sentiment scoring models for offline or fallback scoring | Model fit and label taxonomies must be checked against current markets and language mix | Optional local scoring reference only |
| `FinGPT` | Finance-domain LLM prompting and market-language adaptation ideas | Can drift into generic generation patterns if copied without guardrails | Reference prompt and adaptation patterns only |
| `AI News Tracker` | News-centric ingestion and alert framing | Integration style may not match current service boundaries or licensing posture | Reference news pipeline shape only |
| `DISC-FinLLM` | Financial LLM evaluation and benchmark framing | Benchmark-heavy; not a turnkey implementation plan | Reference evaluation contract only |
| `CFGPT` | Finance-oriented generation and summary ideas | Needs careful license and scope review before any code reuse | Reference summary structure only |
| `amitpatole/tickerpulse-ai` | Multi-source stock/news monitoring, source adapters, ticker-centric AI research workflow | GPL-3.0 license risk for direct code copy; source scraping durability unknown | Architecture reference only; do not vendor |
| `BettaFish` | Market news aggregation and insight presentation patterns | GPL code must not be vendored into this repository | Architecture reference only; no vendoring |
| `shirosaidev/stocksight` | VADER/TextBlob sentiment scoring, Elasticsearch-backed query model, Twitter/news pipeline | Older stack and Twitter API assumptions; likely heavy operational footprint | Reference scoring/storage ideas only |
| `awsdataarchitect/financial-signals-dashboard` | News/social sentiment to AI alpha signal, signal dashboard framing | Depends on Bright Data/Strands and external services; not aligned with current local stack | Reference signal contract only |
| `koala73/worldmonitor` / related market radar projects | News radar information architecture, local model friendly summarization | Scope and license constraints need careful review before reuse | Reference UI/information architecture only |
| `dragon1086/prism-insight` | News agent and AI stock analysis workflow | Contains broader automated trading concepts that must not enter this platform | Reference news analysis prompt/contract only; do not import trading parts |

Decision: do not vendor or directly copy these projects in phase one. Use them as design references while implementing a narrow native sentiment center on the existing service boundary.
TickerPulse and BettaFish are architecture references only because of GPL constraints; neither project should be vendored into this repository.

## AI Configuration Rule

All AI summarization, event extraction, and quant signal synthesis must reuse the current OpenAI-compatible sub2api path:

- `LONGBRIDGE_AI_BASE_URL`
- `LONGBRIDGE_AI_URL`
- `LONGBRIDGE_AI_API_STYLE`
- `LONGBRIDGE_AI_API_KEY`
- `LONGBRIDGE_AI_MODEL`
- `LONGBRIDGE_AI_MODEL_SCAN_FAST`
- `LONGBRIDGE_AI_MODEL_SCAN_FINAL`

Default route:

- fast extraction / clustering: `gpt-5.4`
- final synthesis / portfolio impact: `gpt-5.5`
- base URL in Docker: `http://sub2api:8080/v1`

No new AI key, base URL, model registry, or frontend-visible secret should be added.
The implementation should keep using the existing `LONGBRIDGE_AI_*` contract and the `sub2api` gateway rather than introducing a separate sentiment-specific AI path.

## Phase-One Sentiment Contract

Dedicated page: `/sentiment-center`

Minimum read model:

```json
{
  "asOf": "2026-05-20T15:00:00Z",
  "marketMood": {
    "score": 62,
    "label": "risk-on",
    "confidence": 0.72,
    "drivers": ["AI chips", "rates", "earnings"]
  },
  "symbols": [
    {
      "symbol": "NVDA.US",
      "name": "NVIDIA",
      "sentimentScore": 78,
      "sentimentLabel": "positive",
      "heat": 91,
      "trend": "rising",
      "riskFlags": ["crowded long"],
      "quantSignal": {
        "bias": "bullish",
        "strength": 0.68,
        "horizon": "1-3d"
      },
      "evidence": [
        {
          "source": "finance-news",
          "title": "headline",
          "url": "",
          "publishedAt": "2026-05-20T14:30:00Z"
        }
      ]
    }
  ],
  "events": [
    {
      "eventType": "earnings",
      "severity": "medium",
      "symbols": ["NVDA.US"],
      "summary": "short summary",
      "quantImpact": "watch volatility"
    }
  ]
}
```

## Quant Integration

Sentiment must feed quant as structured evidence, not as an execution command.

Allowed integrations:

- Show sentiment score and heat beside recommendation candidates.
- Provide `quantSignal.bias`, `strength`, and `horizon` as read-only features for strategy review.
- Link from sentiment events to `/ai-analysis`, `/strategy`, `/recommendations`, and `/symbol/:symbol`.
- Let scheduled analysis include sentiment evidence in prompts.

Forbidden integrations:

- No order submission.
- No auto-buy or auto-sell.
- No position mutation.
- No direct strategy execution triggered by sentiment.
- Quant outputs are read-only evidence only and must not trigger trades, execution jobs, or broker-side side effects.

## Implementation Slices

1. Backend native contract

- Extend `apps/market/sentiment-service/src/main.py` with read-only `GET /api/v1/sentiment/overview`.
- Return deterministic placeholder/read-model data first, shaped exactly like the phase-one contract.
- Later replace placeholder internals with collectors and AI synthesis while keeping response fields stable.

2. Frontend independent page

- Add `apps/frontend/web-portal/src/views/MarketSentiment.vue` behind the `/sentiment-center` route.
- Add route `/sentiment-center`, menu seed, and capability such as `market.sentiment.view`.
- Keep it dense and operational: market mood, symbol heat table, event/risk list, quant-consumable signal panel.

3. API wrapper

- Add sentiment methods to the existing frontend API layer or a small `src/api/sentiment.js`.
- Route through gateway `/svc/sentiment/api/v1/sentiment/overview`.

4. Tests

- Backend contract test for `overview` shape.
- Frontend unit smoke for page rendering and quant links.
- Browser smoke route entry once wired into menu.

Phase-one verification is complete:

- `tests/python/test_sentiment_service_contract.py` covers the sentiment overview/bootstrap contract, GitHub adoption metadata, AI config reuse, and read-only quant policy.
- `tests/unit/market-sentiment.spec.js` covers the `/sentiment-center` page render, GitHub adoption card, and quant/navigation links.
- Authenticated gateway smoke passed for `/svc/sentiment/api/v1/sentiment/bootstrap` and `/svc/sentiment/api/v1/sentiment/overview?market=US`.
- Browser smoke passed for `/sentiment-center` with no console/runtime errors.

## Non-blocking Product Decisions

The phase-one sentiment center is implemented as a read-only contract and standalone page. These are product hardening decisions for later iterations:

- Whether sentiment persistence gets a new table or reuses existing briefing/content caches.
- Which collectors are allowed for local use: RSS/news only first, then optional Reddit/StockTwits if credentials and rate limits are acceptable.
- Whether `gpt-5.4` extraction runs synchronously on demand or only through scheduler.

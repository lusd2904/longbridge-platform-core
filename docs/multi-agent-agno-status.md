# Multi-Agent Agno Status

Date: 2026-05-20

## Summary

Agno is integrated as a review-only sidecar for watchlist reviews. The current chain is:

`scheduler-service -> analysis-service -> Agno sidecar -> agent governance tables -> task center review UI`

This integration is intentionally advisory. It must not place orders, cancel orders, modify holdings, or write trade execution state.

## Runtime

- Agno runs outside Docker as a host `screen + venv` process.
- Sidecar health endpoint: `http://127.0.0.1:3200/health`.
- Containers reach the sidecar through `REF_AGNO_SIDECAR_URL=http://host.docker.internal:3200`.
- Backend Docker ports are published by `docker-compose.yml`; backend images intentionally do not declare `EXPOSE`.

## Implemented Scope

- Watchlist pre-open review: `watchlist_pre_open_review`.
- Watchlist post-close review: `watchlist_post_close_review`.
- Governance tables:
  - `agent_runs`
  - `agent_steps`
  - `agent_human_overrides`
- Analysis APIs:
  - `GET /api/v1/analysis/agent/runs`
  - `GET /api/v1/analysis/agent/runs/{run_id}`
  - `POST /api/v1/analysis/agent/runs/{run_id}/override`
  - `POST /api/v1/analysis/agent/watchlist-review`
- Task center UI displays latest Agent review summaries, opens a result drawer, and records human review actions.
- Watchlist reviews now resolve users from `user_watchlist_stocks` for the selected session flag (`scan_before_open` / `scan_after_close`) and skip cleanly when there are no eligible targets. They no longer fall back to a fixed bootstrap user.
- System market AI scans no longer call `DailyMarketScanService.refresh_all_markets(user_id=1)` from scheduler-service. Manual runs use the requesting user, and background runs resolve an explicit task execution user from policy/env/active-user fallback instead of a hardcoded id.

## Safety Boundary

Human override actions are limited to:

- `acknowledged`
- `needs_review`
- `dismissed`

Trade-like actions are rejected. The Agent workflow is not allowed to call order submission, order cancellation, order modification, holdings mutation, or trade execution state writers.

## External Review Result

Gemini and NotebookLM both accepted the sidecar PoC direction and agreed on the same priorities:

- Keep the first phase review-only.
- Preserve the governance and human review trail.
- Do not turn the Agent chain into a trade execution path.
- Next focus areas are sidecar containerization, broader notification/risk consumption, and replacing the remaining legacy scheduler defaults that still use bootstrap ids outside the Agno watchlist path.

## Verification

- `tests/python/test_agent_watchlist_scope.py` covers:
  - requested watchlist users are resolved through the authenticated session scope;
  - empty watchlists skip before creating Agent runs or workers;
  - scheduler watchlist user selection uses the session flag, excludes disabled/locked users, orders by target count, and has no empty-watchlist fallback;
  - listed watchlist users are called one by one;
  - market AI scan scheduler paths no longer hardcode `user_id=1`.
- Python compile passed for the touched backend modules.
- Frontend production build passed.
- Frontend unit tests passed: 15 files, 49 tests.
- API smoke passed through `http://127.0.0.1:3100/svc/*` for representative read-only endpoints across user, analysis, scheduler, market, strategy, risk, trade, and sentiment.
- Agent run APIs passed:
  - list runs
  - get run detail
  - record `acknowledged`
  - reject trade-like override action
- Dedicated `watchlist_post_close_review` smoke passed:
  - scheduler manual run returned `200`
  - generated `agentRunId=11`
  - agent run detail returned `scene=watchlist_post_close_review`
  - persisted run status was `succeeded`
- Browser UI smoke passed for `http://127.0.0.1:3100/scheduler-center`:
  - task center renders
  - Agent review summaries render
  - result drawer opens
  - signals, risks, review advice, evidence, steps, and human records are visible
  - no browser console errors were observed
- Docker direct health checks passed:
  - `8101` user-center
  - `8102` market-service
  - `8103` analysis-service
  - `8107` scheduler-service

## Remaining Work

1. Containerize the Agno sidecar so deployment and rollback do not depend on host `screen`.
2. Replace the in-process analysis-service worker with a durable queue or add stranded-run recovery/cleanup for queued and running Agent runs after process restarts.
3. Add scheduler idempotency and notification de-duplication for repeated manual watchlist review triggers within the same time window.
4. Expand notifications and risk consumption beyond the initial Agent notification feed, including persistent projection, review deadlines, and cross-entry status consistency.
5. Audit the remaining non-Agno legacy scheduler classes (`FinanceBriefingScheduler`, `MarketInsightScheduler`, `RecommendationScheduler`, and similar host-era runners) for bootstrap-id defaults. The scheduler-service market AI scan path has been moved off `user_id=1`; the remaining legacy classes are outside the current Agno watchlist integration.

# Multi-Agent Agno Status

Date: 2026-05-21

## Summary

Agno is integrated as a review-only sidecar for watchlist reviews. The current chain is:

`scheduler-service -> analysis-service -> Agno sidecar -> agent governance tables -> task center review UI`

This integration is intentionally advisory. It must not place orders, cancel orders, modify holdings, or write trade execution state.

## Runtime

- Agno sidecar is now containerized for deployment and rollback.
- Sidecar health endpoint: `http://127.0.0.1:3200/health`.
- Containers reach the sidecar through `REF_AGNO_SIDECAR_URL=http://agno-sidecar:3200` by default, and analysis-service resolves the sidecar through that setting instead of a host-only assumption.
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
- Manual watchlist review triggers are idempotent within the review window, so repeated requests reuse the same logical review run instead of creating duplicate side effects.
- Startup cleanup now scans for stranded queued/running Agent runs and advances or closes them before new review work is accepted.
- The Agno-compatible team endpoint accepts the existing `application/x-www-form-urlencoded` analysis-service call shape and also receives the full serialized review payload for structured context.
- System market AI scans no longer call `DailyMarketScanService.refresh_all_markets(user_id=1)` from scheduler-service. Manual runs use the requesting user, and background runs resolve an explicit task execution user from policy/env/active-user fallback instead of a hardcoded id.
- Notification review lifecycle is tracked end to end, from generation to human acknowledgement, dismissal, or follow-up review, so review state can be rechecked without creating new execution work.

## Safety Boundary

Human override actions are limited to:

- `acknowledged`
- `needs_review`
- `dismissed`

Trade-like actions are rejected. The Agent workflow is read-only with respect to trading and is not allowed to call order submission, order cancellation, order modification, holdings mutation, or trade execution state writers.

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
  - market AI scan scheduler paths no longer hardcode `user_id=1`;
  - analysis-service includes the structured payload in the form-encoded Agno call;
  - Agno sidecar parses the form-encoded team endpoint without adding `python-multipart`;
  - user-facing stock pool paths no longer include bootstrap-user fallback clauses.
- `tests/python/test_notifications_read_model_fallback.py` covers review lifecycle fields, SLA deadlines, human acknowledgement/dismissal labels, and excluded inactive Agent risk scores.
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
  - `3200` Agno sidecar
  - `8101` user-center
  - `8102` market-service
  - `8103` analysis-service
  - `8106` sentiment-service
  - `8107` scheduler-service
- Current verification also includes:
  - targeted Python tests: `62 passed`;
  - targeted frontend unit tests: `2 files / 8 tests passed`;
  - frontend production build succeeded;
  - `docker compose config` renders the sidecar and risk-service as separate services;
  - `docker compose up -d --no-build agno-sidecar sentiment-service analysis-service market-service api-gateway web-portal` kept all target services healthy;
  - authenticated gateway smoke passed for `/svc/sentiment/api/v1/sentiment/bootstrap`, `/svc/sentiment/api/v1/sentiment/overview?market=US`, and `/svc/risk/api/v1/notifications?type=risk&limit=10`;
  - analysis-service watchlist review smoke passed through `/svc/analysis/api/v1/analysis/agent/watchlist-review` with `accepted=true` and `agentRunId=23`;
  - sidecar form-urlencoded smoke passed on `/api/v1/agent/watchlist-review` and returned a `gpt-5.5` review-only result;
  - browser smoke passed for `/sentiment-center` and `/notifications` with `errors=0`.

Note: a normal `docker compose build` was attempted, but Docker Hub metadata requests for `node:20-alpine`, `nginx:1.27-alpine`, and `python:3.11-slim` still failed with EOF. Runtime verification used the already-built local images via `--no-build`.

## Non-blocking Follow-ups

The requested implementation scope is complete. These items are future hardening work and are not blockers for the current delivery:

1. Validate stranded-run cleanup after a real process restart against live queued/running Agent rows.
2. Load-test concurrent watchlist review submissions against the idempotency key window.
3. Add persistent notification projections if product needs review lifecycle state outside the current read-model response.
4. Continue auditing host-era scheduler runners outside the Agno path for bootstrap-id defaults as they are migrated into service runtime.

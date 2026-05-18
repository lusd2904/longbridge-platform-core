# Multi-Agent Agno Status

Date: 2026-05-19

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
- Next focus areas are async execution, sidecar containerization, multi-user scheduling, and notification/risk consumption.

## Verification

- Python compile passed for the touched backend modules.
- Frontend production build passed.
- Frontend unit tests passed: 15 files, 49 tests.
- API smoke passed through `http://127.0.0.1:3100/svc/*` for representative read-only endpoints across user, analysis, scheduler, market, strategy, risk, trade, and sentiment.
- Agent run APIs passed:
  - list runs
  - get run detail
  - record `acknowledged`
  - reject trade-like override action
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
2. Move long Agent runs out of the synchronous request path.
3. Replace the `user_id=1` bootstrap assumption with explicit multi-user scheduling.
4. Connect notifications and risk consumption to the structured Agent governance data.
5. Add a separate successful smoke for `watchlist_post_close_review`; it is registered and uses the same runner as pre-open.

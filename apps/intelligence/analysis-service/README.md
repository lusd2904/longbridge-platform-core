# Analysis Service

Analysis Service 是 AI 研究与 Agent 治理服务，默认端口 `8103`。

## 做了什么

- AI 模型计划和分析 bootstrap。
- 持仓/标的 AI 研判。
- 趋势批量扫描、最新标的分析、智能推荐。
- 财经快讯 read model。
- Agent run 列表、详情和人工 override。
- Watchlist pre-open/post-close review：异步接受、idempotency、空 watchlist 跳过、stranded run cleanup。
- Watchlist review 可接收 scheduler 的 `autoBuy` 参数；默认 `dryRun=true` 只写复核结果，显式开启时会抽取机会股并调用量化交易服务，仍受账户、权限、现金、重复下单和仓位控制约束。
- 调用 Agno sidecar 时发送 form payload 和完整结构化上下文。

## 主要接口

- `GET /health`
- `GET /api/v1/analysis/bootstrap`
- `GET /api/v1/analysis/models`
- `POST /api/v1/analysis/analyze-positions`
- `GET /api/v1/analysis/trend-scans`
- `GET /api/v1/analysis/symbols/{symbol}/latest`
- `GET /api/v1/analysis/recommendations`
- `POST /api/v1/analysis/recommendations/refresh`
- `POST /api/v1/analysis/agent/watchlist-review`
- `GET /api/v1/analysis/agent/runs`
- `GET /api/v1/analysis/agent/runs/{run_id}`
- `POST /api/v1/analysis/agent/runs/{run_id}/override`
- `GET /api/v1/analysis/finance-briefings`

## 使用

```bash
cd apps/intelligence/analysis-service
./run.sh
```

通过 Web Portal 代理触发 watchlist review：

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"session":"post_close","targets":["AAPL.US"],"triggerSource":"manual","dryRun":true}' \
  http://127.0.0.1:3100/svc/analysis/api/v1/analysis/agent/watchlist-review
```

## 依赖

- MySQL：AI history、recommendation runs、agent runs、agent steps、human overrides。
- Redis：AI cache 和热点 read model。
- Market shared helpers：quote、indicator、market snapshot。
- Agno sidecar：默认 `REF_AGNO_SIDECAR_URL=http://agno-sidecar:3200`。
- AI gateway：`LONGBRIDGE_AI_*` / `sub2api`。

## 验证

```bash
curl -fsS http://127.0.0.1:8103/health
.venv/bin/python -m pytest -q tests/python/test_agent_watchlist_scope.py
```

# Agno Sidecar

Agno Sidecar 是一个 Agno-compatible 的只读复核服务，默认端口 `3200`。它位于 `analysis-service` 后面，用现有 AI gateway 生成 watchlist review 结果。

## 做了什么

- 接受 Agno team run 风格请求：`/teams/sub2api-team/runs`。
- 接受 watchlist review 请求：`/api/v1/agent/watchlist-review`、`/api/v1/watchlist-review`、`/watchlist-review`。
- 支持 `application/x-www-form-urlencoded` 和 JSON。
- 从 `payload` 中读取结构化上下文。
- 调用 `LONGBRIDGE_AI_URL`，默认模型 `LONGBRIDGE_AI_MODEL_SCAN_FINAL` 或本地 AI 网关映射名 `gpt-5.5`。
- AI 不可用时返回 degraded 只读复核结果。

## 安全边界

- 只输出 summary、signals、riskFlags、reviewAdvice、evidence、confidence、status。
- 不提交订单。
- 不撤单、改单。
- 不修改持仓。
- 不写交易执行状态。

## 主要接口

- `GET /health`
- `POST /teams/sub2api-team/runs`
- `POST /api/v1/agent/watchlist-review`
- `POST /api/v1/watchlist-review`
- `POST /watchlist-review`

## 使用

Docker compose：

```bash
docker compose up -d agno-sidecar analysis-service
curl -fsS http://127.0.0.1:3200/health
```

本机直启：

```bash
REF_AGNO_SIDECAR_PORT=3200 python3 apps/intelligence/agno-sidecar/src/main.py
```

Smoke：

```bash
curl -fsS -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'message=smoke review-only validation' \
  --data-urlencode 'payload={"runId":"smoke-direct","scene":"watchlist_post_close_review","targets":[{"symbol":"AAPL.US","market":"US"}],"dryRun":true}' \
  http://127.0.0.1:3200/api/v1/agent/watchlist-review
```

如果外部 AI gateway 不可用，review 端点仍会返回只读安全降级结果，并在响应中标记 degraded / fallback 语义；它不会改仓、下单或写交易执行状态。

## 依赖

- `LONGBRIDGE_AI_BASE_URL`
- `LONGBRIDGE_AI_URL`
- `LONGBRIDGE_AI_API_KEY`
- `LONGBRIDGE_AI_MODEL`
- `LONGBRIDGE_AI_MODEL_SCAN_FINAL`
- `LONGBRIDGE_AI_SCAN_REASONING_EFFORT`

`gpt-5.5` 是当前 `sub2api` / OpenAI-compatible gateway 使用的逻辑模型名；如果本机网关映射不同，改 `LONGBRIDGE_AI_MODEL_SCAN_FINAL` 即可。

## 验证

```bash
python3 -m py_compile apps/intelligence/agno-sidecar/src/main.py
curl -fsS http://127.0.0.1:3200/health
```

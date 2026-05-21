# Scheduler Service

Scheduler Service 是调度和系统任务服务，默认端口 `8107`。

## 做了什么

- Scheduler bootstrap 和 runtime 状态。
- 启停调度 runtime。
- 系统任务列表、策略更新、手动触发。
- 执行记录列表。
- 市场历史回填、市场 AI 扫描、watchlist review 调度。
- Watchlist review 只选择有目标的用户，不再 fallback 到 bootstrap user。
- Market AI scan 不再硬编码 `user_id=1`。
- 自选股盘前/盘后复核支持任务策略里的机会股自动买入开关，默认关闭，并携带最多标的数、单标预算、单票仓位上限、最低置信度给 analysis-service。
- `quant_trading` 用户任务现在调用自选池量化策略扫描，不再从全市场推荐结果里挑自动买入标的。

## 主要接口

- `GET /health`
- `GET /api/v1/scheduler/bootstrap`
- `GET /api/v1/scheduler/runtime`
- `POST /api/v1/scheduler/runtime/start`
- `POST /api/v1/scheduler/runtime/stop`
- `GET /api/v1/scheduler/tasks`
- `PUT /api/v1/scheduler/tasks/{task_key}`
- `POST /api/v1/scheduler/tasks/{task_key}/run`
- `GET /api/v1/scheduler/jobs`

## 使用

```bash
cd apps/operations/scheduler-service
./run.sh
```

通过 Web Portal 代理：

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:3100/svc/scheduler/api/v1/scheduler/tasks
```

手动触发 watchlist post-close review：

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"dryRun":true}' \
  http://127.0.0.1:3100/svc/scheduler/api/v1/scheduler/tasks/watchlist_post_close_review/run
```

自动买入控制：

- 入口：Web Portal `/scheduler-center`，任务 `watchlist_pre_open_review` / `watchlist_post_close_review`。
- 默认：`autoBuyEnabled=false`，只生成 AI 建议，不执行交易。
- 开启：scheduler 会向 analysis-service 发送 `dryRun=false` 和 `autoBuy` 参数。
- 风控参数：`autoBuyMaxSymbols`、`autoBuyMaxAmount`、`autoBuyMaxPositionRatio`、`autoBuyMinConfidence`。

自选池量化任务：

- 任务 key：`quant_trading`。
- 手动触发：`POST /api/v1/scheduler/tasks/quant_trading/run`。
- 数据范围：仅当前用户自选股池。
- 执行边界：默认扫描不下单；自动执行仍依赖用户量化配置、账户权限、仓位预算、重复决策保护和长桥 CLI 模拟账户保护。

## 依赖

- MySQL：系统任务、任务执行记录、用户 watchlist。
- Analysis Service：watchlist review 请求入口。
- Market Service：市场回填和用户标的。

## 验证

```bash
curl -fsS http://127.0.0.1:8107/health
.venv/bin/python -m pytest -q tests/python/test_agent_watchlist_scope.py
```

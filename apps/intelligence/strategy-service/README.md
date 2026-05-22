# Strategy Service

Strategy Service 是策略与回测服务，默认端口 `8104`。

## 做了什么

- 策略 bootstrap 和 runtime 状态。
- 策略列表、模板、创建、更新、删除。
- 回测列表和创建。
- 策略监控 summary、alerts、手动 run。
- 量化状态和手动试跑。
- 自选股池量化策略扫描：只读取当前用户 `user_watchlist_stocks`，基于趋势、突破、均值回归、AI 趋势扫描和波动风险做多因子评分。
- 受控自动下单：当请求显式 `execute=true` 且 `AI_QUANT_TRADING_ENABLED=true` 时，候选机会股会交给 `QuantTradingService.execute_watchlist_opportunities()`，继续执行账户权限、持仓、现金、重复决策、单票预算和仓位上限校验。
- 美股开盘 AI 自动交易扫描记录：`watchlist_us_open_ai_trade_runs` 专门记录每次任务启动、跳过、完成、失败、候选、机会、下单提交和仓位控制快照。
- GitHub 策略参考：借鉴 QuantConnect Lean 的事件分层、Microsoft Qlib 的多因子评分、vn.py 的交易/风控分层、PyPortfolioOpt 的轻量仓位预算思想；backtrader/Freqtrade 只借鉴 dry-run、白名单、回测思想，不复制 GPL 代码、不 vendoring 外部仓库。

## 主要接口

- `GET /health`
- `GET /api/v1/strategy/bootstrap`
- `GET /api/v1/strategy/runtime`
- `GET /api/v1/strategy/strategies`
- `GET /api/v1/strategy/templates`
- `POST /api/v1/strategy/strategies`
- `PUT /api/v1/strategy/strategies/{strategy_id}`
- `DELETE /api/v1/strategy/strategies/{strategy_id}`
- `GET /api/v1/strategy/backtests`
- `POST /api/v1/strategy/backtests`
- `GET /api/v1/strategy/monitor/summary`
- `POST /api/v1/strategy/monitor/run`
- `GET /api/v1/strategy/monitor/alerts`
- `GET /api/v1/strategy/quant/status`
- `POST /api/v1/strategy/quant/run`
- `GET /api/v1/strategy/quant/watchlist/history`
- `GET /api/v1/strategy/quant/watchlist/us-open-ai-trade/runs`
- `POST /api/v1/strategy/quant/watchlist/run`
- `POST /api/v1/strategy/quant/watchlist/backtest`

## 使用

```bash
cd apps/intelligence/strategy-service
./run.sh
```

通过 Web Portal 代理：

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:3100/svc/strategy/api/v1/strategy/bootstrap
```

扫描自选池量化候选：

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"profile":"balanced","execute":false,"minConfidence":72,"maxSymbols":2,"maxAmount":2000,"maxPositionRatio":0.08}' \
  http://127.0.0.1:3100/svc/strategy/api/v1/strategy/quant/watchlist/run
```

查询最近扫描历史：

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:3100/svc/strategy/api/v1/strategy/quant/watchlist/history?limit=12"
```

查询美股开盘 AI 自动交易扫描记录：

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:3100/svc/strategy/api/v1/strategy/quant/watchlist/us-open-ai-trade/runs?limit=50"
```

单标的策略复盘：

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"symbol":"AAPL.US","profile":"balanced","lookbackDays":90,"minConfidence":72}' \
  http://127.0.0.1:3100/svc/strategy/api/v1/strategy/quant/watchlist/backtest
```

这里的“策略复盘”指历史价格回放：服务用相同评分规则扫描过去一段日线，输出信号次数、胜率、5 日后收益均值和评分路径。它不是 Agent review，也不会写人工复核状态。

## GitHub 借鉴落地

这部分只记录设计借鉴，不把外部项目当作运行时依赖。

| 借鉴来源 | 这里的落点 | 不做的事情 |
| --- | --- | --- |
| Lean | 把扫描、打分、候选和执行分成清晰阶段 | 不实现完整事件驱动引擎 |
| Qlib | 把多因子评分和历史复盘做成结构化输出 | 不引入重量级研究框架 |
| vn.py | 保持策略、风控、执行的边界分离 | 不让策略页直接写 broker 状态 |
| PyPortfolioOpt | 只保留轻量预算和仓位控制思路 | 不增加独立优化服务 |

如果后续要增加更复杂的组合优化或 factor registry，需要先补 ADR，再改实现。

## 执行前置条件

受控下单使用 `POST /api/v1/strategy/quant/watchlist/run`，将 `execute` 设为 `true`。服务端仍要求同时满足：

- 当前用户已绑定可用交易账户。
- 当前用户已开通量化交易 API，且角色允许量化交易。
- 全局配置 `AI_QUANT_TRADING_ENABLED=true`。
- 候选标的仍属于当前用户自选股池。
- 标的无已有持仓，且 60 分钟内没有同向本地决策。
- 券商当日委托查询成功，且没有同标的同方向未完成委托；该实时查询是当前防重权威源，前端和策略页缓存不参与当日订单防重。
- 现金、单票预算、单票仓位上限和最低评分阈值全部通过。

## 返回字段

`watchlist/run` 返回核心字段：

```json
{
  "cycleId": "qt-20260521190845000000",
  "strategyProfile": "balanced",
  "targetCount": 12,
  "evaluatedCount": 12,
  "opportunityCount": 2,
  "candidates": [],
  "opportunities": [],
  "autoTrade": {
    "enabled": false,
    "executed": false,
    "reason": "not-requested",
    "submittedCount": 0,
    "skipped": []
  },
  "positionControl": {
    "maxSymbols": 2,
    "maxAmount": 2000,
    "maxPositionRatio": 0.08,
    "minConfidence": 72
  },
  "history": {
    "saved": true,
    "runId": 101
  }
}
```

`watchlist/backtest` 返回 `summary` 和 `points`。`summary.signalCount` 是历史窗口内达到阈值的买入信号次数，`points[].forward5dReturn` 是该日信号后 5 个交易日的收益回放，用于复盘策略稳定性，不代表未来收益。

`watchlist/us-open-ai-trade/runs` 返回 `items[]`，核心字段包括 `cycleId`、`status`、`reason`、`targetCount`、`evaluatedCount`、`opportunityCount`、`submittedCount`、`settings`、`autoTrade`、`positionControl`、`candidates`、`opportunities`、`skipped`、`startedAt`、`finishedAt`。

## 依赖

- `backend-server/src/core/analysis/StrategyMonitorService.py`
- `backend-server/src/core/analysis/QuantTradingService.py`
- `backend-server/src/core/analysis/HistoricalMarketDataService.py`
- `backend-server/src/core/analysis/IndicatorSnapshotService.py`
- `backend-server/src/core/analysis/DailySymbolTrendScanService.py`
- Market Service 的自选池目标。
- Analysis service 的研究结果和市场 read model。
- Trade Service 的执行边界和订单状态投影。

## 验证

```bash
curl -fsS http://127.0.0.1:8104/health
.venv/bin/python -m pytest -q tests/python/test_watchlist_quant_strategy.py
npm --prefix apps/frontend/web-portal run smoke:web:critical
```

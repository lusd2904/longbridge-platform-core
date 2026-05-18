# Strategy Service

职责：

- 策略编排
- 风控联动
- 回测任务

迁移来源：

- `backend-server/src/strategy/`
- `web/src/views/Strategy.vue`
- `web/src/views/Backtest.vue`

当前状态：

- 已在 `8104` 落地为 refactor-v2 live service
- 已复用 `StrategyMonitorService` 和 `QuantTradingService`
- 已开放策略管理、回测、监控摘要/告警、量化状态与手动试跑接口

当前接口：

- `GET /health`
- `GET /api/v1/strategy/bootstrap`
- `GET /api/v1/strategy/strategies`
- `GET /api/v1/strategy/templates`
- `POST /api/v1/strategy/strategies`
- `PUT /api/v1/strategy/strategies/{strategy_id}`
- `DELETE /api/v1/strategy/strategies/{strategy_id}`
- `GET /api/v1/strategy/backtests`
- `POST /api/v1/strategy/backtests`
- `GET /api/v1/strategy/monitor/summary`
- `POST /api/v1/strategy/monitor/run`
- `GET /api/v1/strategy/quant/status`
- `POST /api/v1/strategy/quant/run`

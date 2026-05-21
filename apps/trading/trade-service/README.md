# Trade Service

Trade Service 是交易执行与券商账户服务，默认端口 `8105`。它是平台唯一的交易写动作边界。

## 做了什么

- 券商账户读取、创建、测试、默认账户设置。
- Longbridge / Tiger 账户配置。
- 资产、账户状态、持仓、订单读取。
- 下单、撤单、订单投影。
- outbox / saga 事件查询、重试、死信清理。
- `/health` 暴露 Longbridge observability。

Trade Service 也是平台唯一的交易写动作边界。分析、舆情、策略、Agno review 和任务中心都只能把建议送到这里，不能自己写 broker 状态。

## 主要接口

- `GET /health`
- `GET /api/v1/trade/bootstrap`
- `GET /api/v1/trade/runtime`
- `GET /api/v1/trade/accounts`
- `GET /api/v1/trade/brokers/bootstrap`
- `GET /api/v1/trade/brokers/providers`
- `POST /api/v1/trade/brokers/longbridge`
- `POST /api/v1/trade/brokers/tiger`
- `GET /api/v1/trade/accounts/default`
- `GET /api/v1/trade/accounts/{account_id}/account`
- `GET /api/v1/trade/accounts/{account_id}/summary`
- `GET /api/v1/trade/accounts/{account_id}/positions`
- `GET /api/v1/trade/accounts/{account_id}/state`
- `GET /api/v1/trade/orders`
- `GET /api/v1/trade/orders/projection`
- `POST /api/v1/trade/orders/submit`
- `POST /api/v1/trade/orders/cancel`
- `GET /api/v1/trade/outbox/events`
- `GET /api/v1/trade/outbox/sagas`
- `POST /api/v1/trade/outbox/requeue`
- `POST /api/v1/trade/outbox/sagas/requeue`

## 使用

```bash
cd apps/trading/trade-service
./run.sh
```

通过 Web Portal 代理：

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:3100/svc/trade/api/v1/trade/bootstrap
```

## 依赖

- MySQL：账户、订单、outbox、saga、审计投影。
- `legacy_trade_service`：旧交易运行时显式包化复用。
- Longbridge CLI/配置：长桥账户和交易执行。

## 安全边界

- 只有本服务允许交易写动作。
- 舆情、AI、Agno、策略输出默认只是证据或建议，不能绕过本服务写交易状态。
- 量化策略借鉴 Lean / Qlib / vn.py / PyPortfolioOpt 的是边界设计和信号组织方式，不是把这些框架的执行层搬进来。
- `trade-service` 负责把外部建议收敛成可审计的订单状态投影；它不负责策略评分，也不负责资金分配模型。

## 订单边界

这里的订单处理关注两层状态：

- 券商侧状态：Longbridge / Tiger 返回的原始订单状态。
- 平台侧状态：用于 UI、outbox 和审计的规范化投影。

平台侧状态投影的目标是让订单生命周期可追踪、可重放、可审计。它不是一个独立交易引擎，也不替代券商原始状态。

对于自选池量化自动执行，这个服务只接受来自上游的受控下单请求，并继续应用账户、权限、现金、重复委托和仓位边界。若任一条件不满足，订单不进入 broker 写动作。

## 验证

```bash
curl -fsS http://127.0.0.1:8105/health
npm --prefix apps/frontend/web-portal run trade:regression
```

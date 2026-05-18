# Trade Service

职责：

- 下单
- 撤单
- 持仓
- 订单投影

迁移来源：

- `legacy_trade_service/main.py`

当前状态：

- 已在 `8105` 落地为 refactor-v2 live service
- 已通过显式包 `legacy_trade_service` 复用旧交易运行时的订单提交 / 撤单 / saga / outbox 能力
- 已补充账户、默认账户、持仓和账户状态接口，供新前端直接接入

当前接口：

- `GET /health`
- `GET /api/v1/trade/bootstrap`
- `GET /api/v1/trade/accounts`
- `GET /api/v1/trade/accounts/default`
- `GET /api/v1/trade/accounts/{account_id}/state`
- `POST /api/v1/trade/orders/submit`
- `POST /api/v1/trade/orders/cancel`
- `POST /api/v1/trade/outbox/repair`
- `GET /api/v1/trade/outbox/events`
- `GET /api/v1/trade/outbox/sagas`
- `POST /api/v1/trade/outbox/requeue`
- `POST /api/v1/trade/outbox/sagas/requeue`
- `POST /api/v1/trade/outbox/dead-letter/purge`
- `POST /api/v1/trade/outbox/sagas/dead-letter/purge`

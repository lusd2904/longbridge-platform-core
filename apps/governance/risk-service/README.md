# Risk Service

Risk Service 是风控和通知服务，默认端口 `8108`。

## 做了什么

- 风控 bootstrap、overview、snapshot。
- 风险限额读取和更新。
- 风险事件列表。
- 可用策略开关。
- 止损/止盈保护单创建和取消。
- 通知 bootstrap、列表、已读、全读、删除、清空。
- Agent review 风险通知读模型，包含 review status、SLA、deadline、overdue、review action。

## 主要接口

- `GET /health`
- `GET /api/v1/risk/bootstrap`
- `GET /api/v1/risk/overview`
- `GET /api/v1/risk/overview/snapshot`
- `GET /api/v1/risk/limits`
- `PUT /api/v1/risk/limits`
- `GET /api/v1/risk/events`
- `GET /api/v1/risk/strategies/enabled`
- `GET /api/v1/risk/stoploss`
- `POST /api/v1/risk/stoploss`
- `POST /api/v1/risk/stoploss/cancel`
- `GET /api/v1/risk/takeprofit`
- `POST /api/v1/risk/takeprofit`
- `POST /api/v1/risk/takeprofit/cancel`
- `GET /api/v1/notifications/bootstrap`
- `GET /api/v1/notifications`
- `POST /api/v1/notifications/read`
- `POST /api/v1/notifications/read-all`
- `POST /api/v1/notifications/delete`
- `POST /api/v1/notifications/clear`

## 使用

```bash
cd apps/governance/risk-service
./run.sh
```

通过 Web Portal 代理：

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:3100/svc/risk/api/v1/notifications?type=risk&limit=10'
```

## 依赖

- MySQL：交易订单、保护单、风险事件、Agent run 治理表。
- Trade Service：账户、订单和交易状态 read model。
- Analysis Service：Agent run 与复核记录。

## 验证

```bash
curl -fsS http://127.0.0.1:8108/health
.venv/bin/python -m pytest -q tests/python/test_notifications_read_model_fallback.py
```

# Trading Module

交易模块负责券商账户、资产、持仓、订单、outbox 和 saga。它是唯一允许触达交易执行语义的服务域。

## 服务

| 服务 | 端口 | 职责 |
| --- | --- | --- |
| `trade-service` | `8105` | 券商账户、持仓、订单、投影、outbox/saga 管理 |

## 启动

```bash
cd apps/trading
./run.sh
```

单服务：

```bash
cd apps/trading/trade-service
./run.sh
```

## 安全边界

- 舆情、AI 研判、Agno review 只能输出只读证据。
- 实际下单、撤单、账户状态写入必须通过 `trade-service` 的显式接口。
- 长桥/Tiger 配置由用户登录态隔离，默认账户和交易能力按用户读取。

## 验证

```bash
curl -fsS http://127.0.0.1:8105/health
npm --prefix apps/frontend/web-portal run trade:regression
```

更多说明见 [Trade Service](./trade-service/README.md)。

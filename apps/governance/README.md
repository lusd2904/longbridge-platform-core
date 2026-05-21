# Governance Module

治理模块负责风控、限额、保护单、风险事件和通知中心。它把交易风险、Agent 复核风险和系统通知统一成可读、可确认、可忽略的 read model。

## 服务

| 服务 | 端口 | 职责 |
| --- | --- | --- |
| `risk-service` | `8108` | 风控总览、风险限额、保护单、通知中心 |

## 启动

```bash
cd apps/governance
./run.sh
```

单服务：

```bash
cd apps/governance/risk-service
./run.sh
```

## 已完成能力

- 风控 overview/bootstrap。
- 用户风险限额读取和更新。
- 止损/止盈保护单创建和取消。
- 通知中心，支持交易、风控、系统和 Agent review 通知。
- Agent 风险通知生命周期：待复核、已确认、已忽略、需复核、失败、取消、超期。

## 验证

```bash
curl -fsS http://127.0.0.1:8108/health
.venv/bin/python -m pytest -q tests/python/test_notifications_read_model_fallback.py
```

更多说明见 [Risk Service](./risk-service/README.md)。

# Apps

`apps/` 是 Refactor V2 的模块化服务目录。目录按业务域分组，每个大模块可以独立启动，每个具体服务也可以单独运行。

## 模块布局

| 模块 | 服务 | 端口 | 说明 |
| --- | --- | --- | --- |
| `frontend` | `web-portal` | `3100` | Vue 3 工作台，承载 Web、移动端和桌面端入口 |
| `platform` | `user-center` | `8101` | 登录、用户、角色、菜单、配置 |
| `platform` | `api-gateway` | `5101` | 服务目录、依赖探测和观测入口 |
| `market` | `market-service` | `8102` | 行情、股票池、自选池、历史数据、Longbridge quote/push |
| `market` | `sentiment-service` | `8106` | 市场舆情中心、GitHub 选型、量化只读情绪信号 |
| `intelligence` | `analysis-service` | `8103` | AI 研判、趋势扫描、推荐、财经快讯、Agent run |
| `intelligence` | `strategy-service` | `8104` | 策略配置、回测、监控、量化试跑 |
| `intelligence` | `agno-sidecar` | `3200` | Agno-compatible 只读复核 sidecar |
| `trading` | `trade-service` | `8105` | 券商账户、持仓、订单、outbox/saga |
| `governance` | `risk-service` | `8108` | 风控、限额、保护单、通知中心 |
| `operations` | `scheduler-service` | `8107` | 系统任务、调度运行态、手动触发 |

## 启动

推荐使用根目录 Docker compose：

```bash
docker compose up -d
```

按模块启动：

```bash
cd apps/frontend && ./run.sh
cd apps/platform && ./run.sh
cd apps/market && ./run.sh
cd apps/intelligence && ./run.sh
cd apps/trading && ./run.sh
cd apps/governance && ./run.sh
cd apps/operations && ./run.sh
```

按服务启动：

```bash
cd apps/platform/user-center && ./run.sh
cd apps/platform/api-gateway && ./run.sh
cd apps/market/market-service && ./run.sh
cd apps/market/sentiment-service && ./run.sh
cd apps/intelligence/analysis-service && ./run.sh
cd apps/intelligence/strategy-service && ./run.sh
cd apps/intelligence/agno-sidecar && ./run.sh
cd apps/trading/trade-service && ./run.sh
cd apps/governance/risk-service && ./run.sh
cd apps/operations/scheduler-service && ./run.sh
```

`agno-sidecar` 也可以在根目录用裸 Python 直启：

```bash
REF_AGNO_SIDECAR_PORT=3200 python3 apps/intelligence/agno-sidecar/src/main.py
```

## 运行依赖

- Python 服务共用根目录 `.venv`、`requirements.services.txt`、`backend-server/src` legacy core。
- 前端工作台使用 `apps/frontend/web-portal/package.json`。
- Docker 运行需要外部 `deploy_sub2api-network`，AI 默认指向 `http://sub2api:8080/v1`。
- 长桥能力通过 `longbridge` CLI 和本地 `~/.longbridge` 配置接入。

## 文档索引

- [Frontend](./frontend/README.md)
- [Platform](./platform/README.md)
- [Market](./market/README.md)
- [Intelligence](./intelligence/README.md)
- [Trading](./trading/README.md)
- [Governance](./governance/README.md)
- [Operations](./operations/README.md)

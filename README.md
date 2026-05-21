# Refactor V2

Refactor V2 是一个本地优先的量化交易与研究平台。它把旧单体能力拆成前端工作台、平台账号、市场数据、AI 研究、策略、交易、风控、调度和舆情服务；Web Portal 通过 nginx/Vite 的 `/svc/*` 代理直连各服务，API Gateway 则提供服务目录、依赖探测和观测入口。

当前主线已经不是“占位工程”：核心微服务、交易/市场/AI/风控/调度页面、舆情中心、Agno 只读复核链路、通知复核生命周期都已接入并可在本机运行。

## 已完成内容

- 统一前端工作台：登录、仪表盘、交易台、持仓、订单、股票池、自选池、实时行情、历史 K 线、智能推荐、市场舆情、财经快讯、AI 研判、策略、回测、风控、通知、任务中心、用户和系统设置。
- 微服务拆分：`user-center`、`market-service`、`analysis-service`、`strategy-service`、`trade-service`、`sentiment-service`、`scheduler-service`、`risk-service`、`api-gateway`、`agno-sidecar`。
- 自选股票池：`/watchlist-pool` 已改成台账列表，支持按标的进入 `/watchlist-pool/:symbol/scan-result` 查看最近趋势扫描和 AI 研判。
- 实时行情边界：`/market`、`/stock-pool`、`/watchlist-pool`、标的详情和交易台的当前价、盘前、盘中、盘后、夜盘价统一走 Longbridge quote/push；`quote-snapshots` 只保留给历史趋势、历史扫描和显式快照回看。
- 舆情中心：`/sentiment-center` 页面，`sentiment-service` 提供市场/标的情绪、GitHub 选型、AI 配置复用、量化只读边界。
- Agno sidecar：通过现有 `LONGBRIDGE_AI_*` / `sub2api` / OpenAI-compatible gateway 做 watchlist review，默认只生成观察、风险和人工复核建议；只有在任务中心显式开启机会股自动买入时，才会经量化交易服务按仓位控制尝试下单。
- 自选池量化策略：`/strategy` 增加自选池多因子扫描，吸收 Lean/Qlib/vn.py/PyPortfolioOpt 的事件分层、因子评分、风控分层和轻量仓位预算思想，不引入重依赖、不 vendoring 外部仓库；自动执行只接受当前用户自选股池标的，并继续走长桥 CLI/交易边界。
- 风控通知生命周期：Agent 风险通知支持待复核、已确认、已忽略、需复核、超期等状态。
- 用户隔离修补：目标读路径移除 bootstrap 用户 fallback；历史覆盖、股票池、自选池等按登录用户读取。
- 历史 K 线策略：禁用 Longbridge SDK 历史 K 线直拉路径，优先使用本地存储和 skshare/回填链路。
- Docker compose 运行态：本地服务容器化，`web-portal` 暴露 `3100`，后端服务暴露 `5101/8101-8108/3200`。

## 目录地图

| 路径 | 说明 |
| --- | --- |
| `apps/frontend/web-portal` | Vue 3 + Element Plus 前端工作台，含 Web、移动端 Capacitor、Electron 桌面壳脚本 |
| `apps/platform/user-center` | 登录、用户、角色、菜单、平台配置、用户 bootstrap |
| `apps/platform/api-gateway` | 服务目录、依赖探测和观测入口；Web Portal 可通过 `/svc/gateway/...` 访问 |
| `apps/market/market-service` | 行情、历史、股票池、自选池、Longbridge quote/push、市场扫描 |
| `apps/market/sentiment-service` | 舆情中心 read model、GitHub 参考项目选型、量化只读信号 |
| `apps/intelligence/analysis-service` | AI 研判、趋势扫描、推荐、财经快讯、Agent run 治理 |
| `apps/intelligence/strategy-service` | 策略 CRUD、回测、策略监控、自选池量化扫描和受控量化试跑 |
| `apps/intelligence/agno-sidecar` | Agno-compatible 只读复核 sidecar，调用现有 AI 网关 |
| `apps/trading/trade-service` | 券商账户、资产、持仓、订单、outbox/saga 管理 |
| `apps/governance/risk-service` | 风控总览、限额、保护单、通知中心 |
| `apps/operations/scheduler-service` | 系统任务、调度运行态、手动触发、watchlist review 调度 |
| `backend-server/src` | 重构期共享 legacy 核心服务与数据访问边界 |
| `scripts` | 本机启动、停止、验证、CLI adapter、数据库 bootstrap 脚本 |
| `docs` | 架构、Agno、舆情选型、迁移和决策文档 |

每个模块都有自己的 README：

- [Apps 总览](./apps/README.md)
- [Frontend](./apps/frontend/README.md)
- [Web Portal](./apps/frontend/web-portal/README.md)
- [Platform](./apps/platform/README.md)
- [User Center](./apps/platform/user-center/README.md)
- [API Gateway](./apps/platform/api-gateway/README.md)
- [Market](./apps/market/README.md)
- [Market Service](./apps/market/market-service/README.md)
- [Sentiment Service](./apps/market/sentiment-service/README.md)
- [Intelligence](./apps/intelligence/README.md)
- [Analysis Service](./apps/intelligence/analysis-service/README.md)
- [Strategy Service](./apps/intelligence/strategy-service/README.md)
- [Agno Sidecar](./apps/intelligence/agno-sidecar/README.md)
- [Trading](./apps/trading/README.md)
- [Trade Service](./apps/trading/trade-service/README.md)
- [Governance](./apps/governance/README.md)
- [Risk Service](./apps/governance/risk-service/README.md)
- [Operations](./apps/operations/README.md)
- [Scheduler Service](./apps/operations/scheduler-service/README.md)

架构与联动说明：

- [整体架构与微服务联动图](./docs/system-architecture-and-linkage.md)
- [量化策略 GitHub 借鉴落地 ADR](./docs/adr-quant-github-patterns-20260522.md)
- [架构联动评估记录](./docs/architecture-linkage-review-20260521.md)
- [架构概览](./docs/architecture-overview.md)
- [Phase 1 Stack](./docs/phase1-stack.md)

## 阅读顺序

首次接手建议按这条路径阅读：

1. 先读本 README，确认当前能力、启动方式和安全边界。
2. 再读 [整体架构与微服务联动图](./docs/system-architecture-and-linkage.md)，理解 Web Portal、各服务、AI/交易边界如何串联。
3. 按负责模块进入对应 README，例如 [Strategy Service](./apps/intelligence/strategy-service/README.md)、[Market Service](./apps/market/market-service/README.md)、[Trade Service](./apps/trading/trade-service/README.md)。
4. 需要追溯量化策略借鉴决策或外部评估和采纳项时，阅读 [量化策略 GitHub 借鉴落地 ADR](./docs/adr-quant-github-patterns-20260522.md)、[README 评估记录](./docs/readme-review-20260521.md) 和 [架构联动评估记录](./docs/architecture-linkage-review-20260521.md)。

## 运行方式

### Docker compose 推荐路径

```bash
cd <PROJECT_ROOT>
docker network create deploy_sub2api-network 2>/dev/null || true
docker compose up -d
docker compose ps
```

访问：

- Web Portal: `http://127.0.0.1:3100`
- API Gateway: `http://127.0.0.1:5101`
- Agno sidecar: `http://127.0.0.1:3200/health`
- User Center: `http://127.0.0.1:8101/health`
- Market Service: `http://127.0.0.1:8102/health`
- Analysis Service: `http://127.0.0.1:8103/health`
- Strategy Service: `http://127.0.0.1:8104/health`
- Trade Service: `http://127.0.0.1:8105/health`
- Sentiment Service: `http://127.0.0.1:8106/health`
- Scheduler Service: `http://127.0.0.1:8107/health`
- Risk Service: `http://127.0.0.1:8108/health`

注意：如果 Docker Hub metadata 请求返回 EOF，可以先复用本地镜像运行：

```bash
docker compose up -d --no-build
```

### 本机脚本路径

```bash
cp .env.example .env
REF_SENTIMENT_ENABLED=true ./scripts/start_phase1_stack.sh
./scripts/check_platform_health.py
```

如果只想启动默认 Phase 1 服务、不启用舆情服务，可以直接运行：

```bash
./scripts/start_phase1_stack.sh
./scripts/check_platform_health.py
```

Docker compose 默认包含 `sentiment-service`，因此 `/sentiment-center` 可直接访问。本机脚本路径为了轻量默认不启动舆情服务；如果使用脚本并需要舆情页，请按上面的命令带 `REF_SENTIMENT_ENABLED=true` 启动，或单独启动 `apps/market/sentiment-service`。未启用时不是前端缺页，其他页面仍可运行，但舆情页会显示服务不可用或空态。

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

停止：

```bash
./scripts/stop_phase1_stack.sh
```

## 登录与页面

默认本地 smoke 账号：

- 用户名：`admin`
- 密码：`admin123`

关键页面：

- `/dashboard`：平台总览；服务状态墙读取 Gateway observability + catalog，展示各服务端口、basePath 和告警数
- `/market`：实时行情
- `/stock-pool`、`/watchlist-pool`：股票池和自选池；自选池为台账列表，点击“扫描结果”进入 `/watchlist-pool/:symbol/scan-result`
- `/sentiment-center`：市场舆情中心；Docker compose 默认可用，本机脚本路径需启用 `REF_SENTIMENT_ENABLED=true`
- `/ai-analysis`：AI 研判
- `/recommendations`：智能推荐
- `/strategy`、`/backtest`：策略、回测、自选池量化策略扫描和受控下单入口
- `/trading`、`/positions`、`/orders`：交易工作台
- `/risk`、`/notifications`：风控和通知
- `/scheduler-center`：系统任务与 Agent review

## 核心配置

主要配置来自 `.env` 和 Docker compose 环境变量：

- 端口：`REF_WEB_PORTAL_PORT`、`REF_GATEWAY_PORT`、`REF_*_SERVICE_PORT`、`REF_AGNO_SIDECAR_PORT`
- 数据库：`REF_DB_HOST`、`REF_DB_NAME`、`REF_DB_USER`、`REF_DB_PASSWORD`
- Redis：`REF_REDIS_HOST`、`REF_REDIS_PORT`
- AI 网关：`LONGBRIDGE_AI_BASE_URL`、`LONGBRIDGE_AI_URL`、`LONGBRIDGE_AI_MODEL*`
- Agno sidecar：`REF_AGNO_SIDECAR_URL`
- skshare：`REF_SKSHARE_BASE_URL` / `DOCKER_SKSHARE_BASE_URL`
- 长桥 CLI：`LONGBRIDGE_CLI_BIN`、`LONGBRIDGE_REGION`

舆情、分析、Agno sidecar 都复用 `LONGBRIDGE_AI_*`，不新增单独 AI 密钥体系。自选股盘前/盘后复核的自动买入默认关闭，可在任务中心开启，并受最多标的数、单标预算、单票仓位上限和最低置信度控制。策略页的自选池量化扫描默认只预览候选，只有用户显式点击受控下单且 `AI_QUANT_TRADING_ENABLED` 开启时，才会把候选作为订单意图交给 `trade-service`，再由 `trade-service` 通过 Longbridge/Tiger 适配层执行。

## 验证命令

```bash
python3 -m py_compile \
  apps/intelligence/analysis-service/src/main.py \
  apps/intelligence/agno-sidecar/src/main.py \
  apps/intelligence/strategy-service/src/main.py \
  apps/market/market-service/src/main.py \
  apps/market/sentiment-service/src/main.py \
  backend-server/src/core/analysis/QuantTradingService.py \
  apps/governance/risk-service/src/main.py

.venv/bin/python -m pytest -q \
  tests/python/test_service_edges_contract.py \
  tests/python/test_agent_watchlist_scope.py \
  tests/python/test_watchlist_quant_strategy.py \
  tests/python/test_notifications_read_model_fallback.py \
  tests/python/test_sentiment_service_contract.py \
  tests/python/test_skshare_history_and_sub2api.py \
  tests/python/test_market_live_cache.py

npm --prefix apps/frontend/web-portal run test:unit -- \
  tests/unit/api-health.spec.js \
  tests/unit/dashboard-shell.spec.js \
  tests/unit/app-bootstrap.spec.js \
  tests/unit/market-sentiment.spec.js \
  tests/unit/finance-news-notifications.spec.js

npm --prefix apps/frontend/web-portal run build
SMOKE_PAGE_FILTER=sentiment-center,notifications npm --prefix apps/frontend/web-portal run smoke:web
python3 scripts/check_platform_health.py
```

## 外部评估工作流

本项目保留两个本机评估入口：

- Antigravity CLI adapter：`python3 scripts/antigravity_cli_adapter.py probe`
- NotebookLM CLI：`nlm --help`、`nlm notebook ...`、`nlm source ...`、`nlm query ...`

`scripts/antigravity_cli_adapter.py run` 会优先调用 Antigravity CLI；如果输出显示 OAuth、登录、授权或凭据阻塞，并且本机 `gemini` 可用，会自动降级到 Gemini CLI 的 `--prompt` 非交互模式继续评估。可用 `REF_AGENT_CLI_DISABLE_GEMINI_FALLBACK=true` 临时关闭该兜底。

建议评估流程：

1. 生成或更新 README。
2. 把根 README 和模块 README 打包给 Antigravity CLI 做工程审阅；如果 Antigravity 需要重新授权，adapter 会自动改用 Gemini CLI。
3. 把同一批 README 加入 NotebookLM notebook，让 NotebookLM 从文档一致性、上手路径和缺口角度审阅。
4. 汇总意见，分成“接受”“待定”“拒绝”。
5. 对接受项建立待办清单，再拆给智能体按模块逐步处理。

本轮评估结果和采纳项见 [docs/readme-review-20260521.md](./docs/readme-review-20260521.md)。

## 安全边界

- 舆情始终是量化复核的只读证据；Agno watchlist review 默认只生成建议，不触发交易。只有任务中心显式开启机会股自动买入时，才会经 analysis/quant/trade 链路按仓位控制尝试下单。
- 自选池量化策略只扫描 `user_watchlist_stocks`，自动买入入口会再次校验标的仍属于当前用户自选池；非自选标的即使来自 AI 结果也会被跳过。
- 交易动作只允许通过 `trade-service` 的显式接口发生。
- Agent override 仅支持人工复核语义：`acknowledged`、`needs_review`、`dismissed`。
- 不直接 vendor GPL 舆情项目；GitHub 项目仅作为架构、采集或评估参考。

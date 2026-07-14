# 平台优化待办（Optimization Backlog）

> 生成日期：2026-06-22 · 分支 `codex/macos-desktop-web-name`
> 排序原则：价值 / 风险 / 工作量。Tier 1 低风险可立即做，Tier 3 需单独立项。
>
> 背景：平台已具备连接池（`backend-server/src/utils/DbUtil.py` 的 `DatabasePool`）、
> AI 结果缓存（`AICache` + redis TTL）、阻塞 DB 调用有 21 处 `to_thread` 兜底，
> 因此常见“新手平台”大坑基本不存在。以下是真正剩余的优化空间。

---

## ✅ 已完成（本轮）

- [x] **Docker 镜像瘦身** — 后端镜像移除 `build-essential`（~250MB，所有依赖均为 manylinux wheel），bytecode 预编译。`Dockerfile`
- [x] **compose 可靠性** — 全部 12 个服务加 `restart: unless-stopped` + json-file 日志轮转（10m×3）。`docker-compose.yml`
- [x] **nginx 优化** — gzip、hash 资源不可变缓存 + SPA 壳 no-cache、安全响应头、市场/交易 WebSocket 反代超时 3600s。`apps/frontend/web-portal/nginx.conf`
- [x] **指标层回归测试** — 给 RSI/MACD/BOLL/ATR/EMA/SMA/KDJ/OBV/ROC/CCI/支撑阻力补 golden-master 测试（此前零覆盖）。`tests/python/test_indicator_util_characterization.py`（303 测试全绿）
- [x] **Tier 1 #1 收敛端口暴露面** — 移除 9 个内部服务（user-center/market/analysis/agno/strategy/trade/sentiment/scheduler/risk）的 `ports:` 映射，仅保留 `web-portal`(3100) 和 `api-gateway`(5101)。所有客户端（Web/Electron/Capacitor）均走 nginx `/svc/*` 反代或网关，无需直连后端端口。`docker-compose.yml`
- [x] **Tier 1 #2 依赖健康门** — 所有 12 个服务添加 `redis` 依赖（`condition: service_healthy`）；全部 `depends_on` 从 `service_started` 改为 `service_healthy`，确保启动时下游服务和 Redis 均已就绪。无依赖环。`docker-compose.yml`
- [x] **Tier 1 #3 资源上限** — 全部 12 个服务添加 `mem_limit` / `cpus`，按服务画像分三档：轻量 256MB/0.25CPU、中等 512MB/0.5CPU、AI 分析 1GB/1CPU。总上限 ~4.25GB RAM / 3.5 vCPU。`docker-compose.yml`
- [x] **Tier 2 #4 可观测性** — 创建 `apps/runtime_shared/metrics.py`：Prometheus 中间件自动收集 HTTP 请求计数/延迟直方图，暴露 `/metrics` 端点（Prometheus text format）。集成到 `create_service_app` 后所有 10 个后端服务零改动即可获得指标。提供 `record_ai_call`/`record_redis_op`/`record_db_query`/`inc_ws_connections` 等辅助函数。支持 `prometheus-client` 缺失时的优雅降级。`tests/python/test_metrics.py`（12 测试全绿）
- [x] **Tier 2 #5 DB 访问收口** — `KLineDataFetcher` 移除 `pymysql` 裸连接和死代码 `connect_db`/`close_db`，所有写操作经 `DbUtil.execute_sql` → `DatabasePool`。`tests/python/test_kline_db_access.py`（7 测试全绿）

---

## 🔴 Tier 1 — 高价值 / 低风险 / 可立即做并验证

### [x] 1. 收敛端口暴露面（安全）
- **现状**：`docker-compose.yml` 把 **11 个服务端口全部映射到宿主机**（8101–8108、3200、5101、3100）。
- **问题**：nginx 已通过 `/svc/*` 反代到各服务、网关在内网聚合，内部服务端口无需对宿主机暴露——多余的攻击面。
- **动作**：仅保留 `web-portal`(3100)（必要时加 `api-gateway`(5101)）的 `ports:`，其余服务删除 host 端口映射，仅留 `refactor-v2` 内网互通。
- **前置检查**：确认桌面/移动端（`VITE_*_API_BASE_URL`、`REFV2_DESKTOP_API_BASE`）不直连服务端口，而是走网关/nginx。
- **验证**：`docker compose config` + 起栈后 `/svc/*` 与 `/health` 仍可达。
- **风险**：低 ｜ **工作量**：S

### [x] 2. 依赖健康门（可靠性）
- **现状**：所有 `depends_on` 用 `condition: service_started`；且**无任何服务等待 redis**（均连 `REDIS_HOST=redis`）。
- **动作**：关键边（gateway/web-portal → 下游、用 redis 的服务 → redis）改为 `condition: service_healthy`；redis 已有 healthcheck，直接挂依赖门。
- **注意**：`x-backend-service` 锚点无法承载 `depends_on`（服务各自覆盖），需逐服务在既有 `depends_on` 块内追加；不要制造依赖环。
- **验证**：`docker compose config`；冷启动期 `/health` 偶发 5xx 消失。
- **风险**：低-中 ｜ **工作量**：M

### [x] 3. 资源上限（隔离）
- **现状**：compose 中 **零 `mem_limit`/`cpus`**，单个服务失控（如 analysis 加载 pandas/numpy + 跑 AI）可拖垮整机。
- **动作**：经 `x-backend-service` 锚点给每个服务加 `mem_limit` / `cpus`（或 compose `deploy.resources.limits`），按服务画像分档。
- **验证**：`docker stats` 观察上限生效。
- **风险**：低 ｜ **工作量**：S

---

## 🟡 Tier 2 — 高价值 / 中等工作量

### [x] 4. 可观测性（Prometheus 指标）
- **现状**：仅网关里手写 `latencyMs` + 一个 `/observability` 端点（`apps/platform/api-gateway/src/main.py`），**无 metrics 导出**。
- **动作**：各服务挂 `/metrics`（请求数 / 延迟分位 / 错误率 / AI 调用耗时与花费 / WS 连接数），加 Prometheus + Grafana 面板。
- **价值**：会自动（纸面）交易的平台没有指标面板是真正的盲区。
- **风险**：低（纯新增）｜ **工作量**：M

### [x] 5. DB 访问收口
- **现状**：`KLineDataFetcher` 已移除 `pymysql.connect` 裸连接和 `connect_db`/`close_db` 死代码。
- **动作**：✅ 已完成 — 统一收口到 `DatabasePool`，所有 SQL 操作经 `DbUtil`。
- **风险**：中 ｜ **工作量**：M

---

## 🟢 Tier 3 — 战略级 / 单独立项

### [x] 6. 拆分巨型文件
- **现状**：`apps/market/market-service/src/main.py` ~3348 行、`apps/intelligence/analysis-service/src/main.py` ~2898 行。
- **动作**：按路由/领域拆模块（routers / services / schemas）。运行时无收益，但显著改善可维护性与迭代速度。
- **风险**：中（大面积改动，需测试护航）｜ **工作量**：L

### [ ] 7. numpy 2.x 迁移 + 引入量化框架
- **背景**：pandas-ta-classic 需要 `numpy>=2.0`，平台锁 `numpy==1.26.2`；10 服务共用一镜像一份 `requirements.services.txt`，升级是全平台动作。业务代码本身仅 1 处 import numpy、0 处用已删别名，**风险集中在三方依赖链**（pandas 跨大版本 + akshare/yfinance/longbridge 重验）。
- **动作**：作为独立项目——先全平台升 numpy 2.x / pandas，回归通过后再评估是否用 TA-Lib（需 C 库，会让镜像重新需要编译链）/ pandas-ta 替换 `IndicatorUtil`。
- **护栏**：迁移时用 `tests/python/test_indicator_util_characterization.py` 锁住指标输出不漂移。
- **风险**：高 ｜ **工作量**：XL ｜ **当前不建议**

---

## 建议执行顺序
先做 **Tier 1（1→2→3）**：安全面 + 可靠性 + 隔离，低风险、`docker compose config` 当场可验，与本轮 Docker 收尾同一条线。再视需要上 **Tier 2 的 #4 监控**。

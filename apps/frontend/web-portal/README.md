# Web Portal

Web Portal 是 Refactor V2 的统一前端工作台，默认端口 `3100`。它使用 Vue 3、Vite、Element Plus、ECharts、Vue Router，并提供 Web、Capacitor 移动端和 Electron 桌面端入口。

## 做了什么

- 登录、会话、动态菜单、平台能力控制。
- App 启动时刷新平台 bootstrap，避免新增菜单被旧 `localStorage.platform_bootstrap` 缓存隐藏。
- 市场中心：实时行情、股票池、自选池、AI 交易扫描记录、标的详情、历史 K 线、智能推荐、市场舆情、财经快讯。
- 研究中心：AI 研判、策略管理、策略回测、自选池量化策略扫描。
- 交易中心：交易台、持仓、订单、券商连接。
- 治理中心：风控、通知中心、任务中心、系统设置、用户管理。
- 移动端：Android/iOS Capacitor 工程和 live reload 调试脚本。
- 桌面端：Electron 本地壳。

## 关键页面

- `/login`
- `/dashboard`
- `/market`
- `/stock-pool`
- `/watchlist-pool`
- `/watchlist-pool/:symbol/scan-result`
- `/watchlist-ai-trade-runs`
- `/symbol/:symbol`
- `/kline`
- `/recommendations`
- `/sentiment-center`
- `/finance-news`
- `/ai-analysis`
- `/strategy`
- `/backtest`
- `/trading`
- `/positions`
- `/orders`
- `/risk`
- `/notifications`
- `/scheduler-center`
- `/settings`
- `/user-management`
- `/profile`
- `/broker-management`

## 使用

```bash
cd apps/frontend/web-portal
npm install
npm run dev
```

或从模块入口：

```bash
cd apps/frontend
./run.sh
```

Docker compose 访问：

```text
http://127.0.0.1:3100
```

默认本地 smoke 账号：

- `admin`
- `admin123`

## API 访问模式

前端默认通过 nginx 或 Vite dev server 的 `/svc/*` 代理访问后端。除 `/svc/gateway/...` 外，这些路径会直连对应服务：

- `/svc/user/...`
- `/svc/market/...`
- `/svc/sentiment/...`
- `/svc/analysis/...`
- `/svc/strategy/...`
- `/svc/trade/...`
- `/svc/scheduler/...`
- `/svc/risk/...`
- `/svc/gateway/...`

请求层会自动附加 `Authorization: Bearer <token>`。

## 行情来源规则

- 当前价、盘前、盘中、盘后、夜盘价只展示 Longbridge quote/push 返回值；WebSocket 首帧也标记为长桥订阅首帧，不再叫数据库快照。
- `/api/v1/market/quote-snapshots` 只用于历史趋势、历史扫描、推荐快照等回看场景，不作为股票池、实时行情、自选池台账或交易台当前价兜底。
- 如果长桥实时行情暂未返回，页面显示“等待长桥实时”，不回退到股票底库 `current_price`。

## 常用命令

```bash
npm run dev
npm run build
npm run test:unit
npm run smoke:web
npm run smoke:web:mobile
npm run smoke:web:ai:mobile
npm run smoke:web:critical
npm run trade:regression
npm run verify:platform
```

Web smoke 的规范报告路径是 `apps/runtime/smoke/web-portal-smoke-report.json`。根目录下旧的 `runtime/smoke/...` 只可能是历史遗留产物，不作为当前验证依据。

移动端：

```bash
npm run assets:generate
npm run mobile:prepare
npm run android:debug
npm run ios:debug
npm run mobile:build
```

桌面端：

```bash
npm run desktop:dev
npm run desktop:smoke
```

## 舆情中心

入口：

```text
/sentiment-center
```

页面读取：

- `getSentimentBootstrap()`
- `getSentimentOverview()`

展示：

- 市场情绪摘要。
- 标的热度表。
- 风险词。
- AI 配置复用信息。
- GitHub 参考项目和量化只读边界。

## 自选股票池

入口：

```text
/watchlist-pool
/watchlist-pool/:symbol/scan-result
```

展示：

- 自选标的台账列表，包含市场、类型、Longbridge 实时价、盘前/盘后/夜盘价、添加时间、扫描目标、最新扫描、盘前/盘后扫描开关。
- 点击“扫描结果”进入二级页面，展示该标的最近趋势扫描、风险等级、技术评分、指标和最新 AI 研判。
- 点击“AI研判”可跳转到 AI 研判页继续分析。

相关任务：

- `/scheduler-center` 中的自选股盘前/盘后复核任务提供“机会股自动买入”开关。
- 自动买入默认关闭；开启后仍受最多标的数、单标预算、单票仓位上限、最低置信度控制。
- `/watchlist-ai-trade-runs` 展示美股开盘 AI 自动交易任务的每次启动记录，包含跳过/完成/失败状态、候选、机会、下单提交和仓位控制快照。

## 自选池量化策略

入口：

```text
/strategy
```

展示：

- 自选池量化策略卡片，支持均衡、动量、突破、回归四种扫描 profile。
- 多因子评分表：标的、评分、价格、策略标签、风险等级、命中原因。
- 扫描默认不下单；点击“受控下单”后，后端仍校验量化开关、账户权限、自选池范围、重复决策、预算和仓位上限。

## 服务状态墙

入口：

```text
/dashboard
```

页面读取：

- `getApiHealth()`
- `/svc/gateway/api/v1/system/observability`
- `/svc/gateway/api/v1/system/catalog`

展示：

- Gateway 观测来源和 catalog 同步状态。
- `user-center`、`market-service`、`analysis-service`、`strategy-service`、`trade-service`、`sentiment-service`、`scheduler-service`、`risk-service`、`agno-sidecar` 的状态、端口、basePath 和告警数。

## 验证

```bash
npm run test:unit -- \
  tests/unit/api-health.spec.js \
  tests/unit/dashboard-shell.spec.js \
  tests/unit/app-bootstrap.spec.js \
  tests/unit/market-sentiment.spec.js \
  tests/unit/watchlist-pool.spec.js \
  tests/unit/watchlist-scan-result.spec.js \
  tests/unit/watchlist-ai-trade-runs.spec.js \
  tests/unit/scheduler-center-agent-run.spec.js \
  tests/unit/finance-news-notifications.spec.js

npm run build
SMOKE_PAGE_FILTER=sentiment-center,notifications npm run smoke:web
```

## 注意事项

- 如果 Docker Hub metadata EOF 导致镜像无法正常 rebuild，可先 `npm run build`，再把 `dist` 同步到当前 nginx 容器验证运行态。
- 新增菜单或权限后，刷新页面会触发 `getUsersBootstrap()` 自动更新本地 `localStorage.platform_bootstrap`；一般不再需要手动清缓存。

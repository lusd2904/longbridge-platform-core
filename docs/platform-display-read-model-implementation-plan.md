# 平台展示主数据读库化实施方案

## 1. 目标与边界

本次改造分三步推进，目标是把“门户展示”与“交易执行”彻底拆开：

1. 先把平台展示主数据切到读库为主。
2. 再补 4 张高价值快照/缓存表，承接账户、持仓、风控、内容数据。
3. 最后只给交易相关页面加“前台实时覆盖”，不把整个门户做成强实时站点。

本方案完全按当前仓库目录组织，默认数据库仍为 MySQL，现有服务边界保持不变：

- 前端：`apps/web-portal`
- 网关：`apps/api-gateway`
- 行情服务：`apps/market-service`
- 分析服务：`apps/analysis-service`
- 交易服务：`apps/trade-service`
- 风控服务：`apps/risk-service`
- 调度服务：`apps/risk-service/scheduler`
- 共享数据库能力：`backend-server/src/utils/DbUtil.py`

## 2. 当前主数据与页面现状

### 2.1 需要切到读库为主的 6 类主数据

| 业务名 | 当前实际表/表组 | 当前主要服务 | 当前主要页面 |
|---|---|---|---|
| market_insight | `market_insight_snapshots` | `apps/market-service` | `/dashboard` `/market` `/symbol/:symbol` `/trading` |
| recommendation | `recommendation_runs` + `recommendation_items` | `apps/analysis-service` | `/dashboard` `/recommendations` |
| finance_briefing | `finance_briefings` | `apps/analysis-service` | `/dashboard` |
| trend_scan | `symbol_ai_trend_scans` | `apps/analysis-service` | `/ai-analysis` `/symbol/:symbol` |
| historical_market_data | `market_price_history_daily` | `apps/market-service` | `/kline` `/symbol/:symbol` |
| indicator_snapshot | `symbol_indicator_snapshots` | `apps/market-service` | `/kline` `/symbol/:symbol` `/ai-analysis` |

### 2.2 当前仍偏“实时拉取”的区域

| 页面 | 当前来源 | 问题 |
|---|---|---|
| `/dashboard` | `getDashboardSummary` `getPositions` `getOrders` 走 `trade-service` 实时账户态 | 门户首页也会打到券商，成本高且不稳定 |
| `/trading` | 券商实时账户、订单、报价、盘口、逐笔 | 应保留，但仅限交易页 |
| `/positions` | 券商实时持仓 | 应保留实时覆盖，但需要先有读库底座 |
| `/orders` | 券商实时订单 | 应保留实时覆盖，但需要订单投影/快照兜底 |
| `/risk` | 风控总览实时拼装 + 实时报价补距离 | 应改成“快照为主 + 关键字段覆盖” |
| `/market` `/symbol/:symbol` | 目前也用了 WebSocket/实时补价 | 不应继续扩散成全站强实时 |

### 2.3 四层数据分层确认版

按“平台展示优先”重排后，页面数据统一分成 4 层：

| 层级 | 默认模式 | 典型数据 | 适用页面 | 当前仓库对应任务/表 |
|---|---|---|---|---|
| 第一层：平台展示主数据 | 必须定时入库，前端默认读库 | 市场底库、历史行情、技术指标快照、市场级分析、市场 AI 扫描、逐股趋势扫描、推荐结果、财经简报 | `/dashboard` `/market` `/stock-pool` `/symbol/:symbol` `/kline` `/ai-analysis` `/recommendations` `/finance-news` | `market_universe_daily_sync` `historical_market_data_daily_sync` `market_history_universe_backfill` `symbol_indicator_daily_refresh` `market_insight_refresh` `daily_market_ai_scan` `daily_symbol_trend_ai_scan` `recommendation_refresh` `finance_briefing_refresh` |
| 第二层：账户与风控展示快照 | 建议定时快照入库，前端允许局部实时覆盖 | 账户资产、持仓、风控总览、用户级量化运行结果 | `/dashboard` `/profile` `/positions` `/risk` `/strategy` `/scheduler-center` | `account_asset_snapshots` `position_snapshots` `risk_overview_snapshots`；用户级结果建议结合 `position_monitor` `quant_trading` 单独固化 |
| 第三层：内容缓存 | 建议内容缓存入库，减少页面直接依赖外部接口 | 公告、新闻、话题、外链摘要、重点标的行情缓存 | `/symbol/:symbol` `/finance-news` `/trading` `/dashboard` | `symbol_content_cache`；`quote_snapshots` 作为可选增强项，当前仓库尚未落表 |
| 第四层：实时/事件驱动 | 不适合用定时抓取存库作为主读 | 下单、撤单、订单推进、实时盘口、逐笔成交、L2 深度、券商连通性 | `/trading` `/orders` `/symbol/:symbol` 实时区块 | `trade-service` 实时接口、WebSocket 推送、broker 直连能力 |

补充判断：

- `HistoricalMarketDataService` + `IndicatorSnapshotService` 这一组，本身就已经是“数据库主读”的设计方向。
- `daily_symbol_trend_ai_scan` 非常适合作为 [`apps/web-portal/src/views/AIAnalysis.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/AIAnalysis.vue) 默认数据源；用户手动扫描只是在默认结果上追加一条即时记录。
- 财经页不应继续由前端临时拼多个外部源，应该统一走 `finance_briefings` 和 `symbol_content_cache`。

### 2.4 各层数据详细归类

#### 第一层：必须定时入库，前端默认读库

| 数据域 | 适用页面 | 内容 | 建议频率 | 当前仓库落点 |
|---|---|---|---|---|
| 市场底库 | `/market` `/stock-pool` `/symbol/:symbol` `/kline` | 股票/ETF 基础信息、市场清单、标的池 | 每日 1 次全量，盘中少量增量 | `market_universe_daily_sync` |
| 历史行情 | `/kline` `/symbol/:symbol` `/ai-analysis` `/recommendations` | 日线/周线/月线、成交量、复权数据 | 每日收盘后增量，历史回补独立跑 | `historical_market_data_daily_sync` `market_history_universe_backfill` |
| 技术指标快照 | `/market` `/ai-analysis` `/symbol/:symbol` `/stock-pool` | MA、MACD、RSI、布林带、趋势标签、动量分 | 每日收盘后 1 次；如需短周期可另加 15 分钟级快照 | `symbol_indicator_daily_refresh` |
| 市场级分析结果 | `/dashboard` `/market` `/finance-news` | 美股/A股/港股摘要、基准指数评分、regime、headline/summary | 盘中 10-15 分钟，非交易时段 30-60 分钟 | `market_insight_refresh` -> `market_insight_snapshots` |
| 市场 AI 技术扫描 | `/market` `/finance-news` `/dashboard` | 各市场广度、技术分、风险状态、摘要 | 每日 1-2 次，建议收盘后为主 | `daily_market_ai_scan` |
| 逐股趋势扫描 | `/ai-analysis` `/symbol/:symbol` `/stock-pool` | symbol 级趋势方向、强度、技术说明、信号 | 每日批量；重点池盘中可 30-60 分钟加刷 | `daily_symbol_trend_ai_scan` |
| 推荐结果 | `/recommendations` `/dashboard` | 推荐批次、推荐项、summary、stats、理由、风险 | 每 30 分钟到 2 小时，按 profile 分组刷新 | `recommendation_refresh` + `recommendation_runs` `recommendation_items` |
| 财经简报/资讯聚合 | `/finance-news` `/dashboard` | 市场动态、技术扫描摘要、推荐关注、外部 RSS 资讯 | 每 15-30 分钟 | `finance_briefing_refresh` -> `finance_briefings` |

补充判断：

- 从 [`HistoricalMarketDataService.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/core/analysis/HistoricalMarketDataService.py) 与 [`IndicatorSnapshotService.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/core/analysis/IndicatorSnapshotService.py) 的调用关系看，这一组本来就应该继续沿着“数据库主读”推进，而不是回到页面直拉实时行情。
- [`apps/web-portal/src/views/AIAnalysis.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/AIAnalysis.vue) 的默认数据源应优先落在 `symbol_ai_trend_scans` 与 AI 历史记录；用户手动扫描只是即时执行并追加一条新记录。

#### 第二层：建议定时快照入库，但前端允许实时覆盖

| 数据域 | 适用页面 | 内容 | 建议频率 | 建议新增表/结果 |
|---|---|---|---|---|
| 账户资产快照 | `/dashboard` `/profile` | 总资产、现金、持仓市值、当日盈亏、净值曲线 | 盘中每 5-15 分钟，收盘后补 1 条日终快照 | `account_asset_snapshots` |
| 持仓快照 | `/positions` `/dashboard` `/risk` | symbol、数量、成本、现价、市值、盈亏、仓位占比 | 盘中每 5-15 分钟 | `position_snapshots` |
| 风控总览快照 | `/risk` `/dashboard` | 风险分、最大单仓、回撤、触发次数、保护单数量 | 盘中每 10-30 分钟 | `risk_overview_snapshots` |
| 用户级量化运行结果 | `/strategy` `/scheduler-center` `/profile` | 每次监控/量化运行的输入、结果、告警、候选动作 | 由任务触发时自动入库 | 建议新增 `user_quant_run_results` 一类结果表 |

第二层的原则不是做成强实时账户页，而是让页面先有稳定底座，再按需补局部实时字段。

#### 第三层：建议做内容缓存入库，减少外部接口依赖

| 数据域 | 适用页面 | 内容 | 建议频率 | 建议新增表 |
|---|---|---|---|---|
| 公告/资讯/讨论缓存 | `/symbol/:symbol` `/finance-news` `/trading` | 公告、新闻、话题、外链摘要 | 热门标的 15-30 分钟，普通标的按访问触发 + 缓存 6-24 小时 | `symbol_content_cache` |
| 行情快照缓存 | `/market` `/dashboard` `/symbol/:symbol` | 重点指数、热门股票池、用户持仓、推荐候选的 last price / change / volume | 盘中每 1-5 分钟 | `quote_snapshots` |

约束说明：

- `quote_snapshots` 只抓展示需要的子集，不抓全市场 tick，不把它做成 L2 或逐笔替代品。
- 财经快讯页应完全改成后台统一聚合，前端不再临时拼多个外部源。

#### 第四层：不建议定时抓取存库为主，应继续实时或事件驱动

| 数据域 | 适用页面 | 原则 |
|---|---|---|
| 下单、改单、撤单 | `/trading` `/orders` | 以 broker / trade-service 实时结果为准，数据库负责留痕与审计 |
| 实时盘口、逐笔成交、L2 深度 | `/trading` `/symbol/:symbol` | 以 WebSocket / 实时接口为主，数据库最多只做短期缓存 |
| 券商连接状态、连通性测试 | `/profile` `/broker-connections` | 实时检查为主，只保留最后一次检测结果 |
| 角色、菜单权限、用户绑定 | `/users` `/profile` | 属于配置型数据，变更即写库，不需要定时抓取 |

## 3. 实施原则

- 读写分离只落在公共数据库层，业务服务不重复造连接逻辑。
- 展示接口默认读从库；写入、补数、调度、下单、撤单统一走主库。
- 门户页默认展示“最近一次可用快照”，允许分钟级延迟。
- 页面默认策略统一改为“先出底座，再决定是否覆盖”。
- 交易页采用“两层模型”：
  - 底座先读快照/投影表
  - 局部字段再被实时行情、实时账户、实时订单覆盖
- 不做“整站 WebSocket 常驻订阅”，但允许行情查看页和标的详情页只覆盖最新价/盘口/逐笔这类实时字段。
- 展示页的“实时”只覆盖最值钱的查看字段，不把整页数据源切回 broker/live API。

## 4. 任务清单

## 4.1 阶段 A：先补读写分离基础设施

- [ ] 在 [`.env.example`](/Users/lusd/Documents/New project/refactor-v2/.env.example) 增加读库配置。
  - 建议新增：`REF_DB_READ_ENABLED` `REF_DB_READ_HOST` `REF_DB_READ_PORT` `REF_DB_READ_NAME` `REF_DB_READ_USER` `REF_DB_READ_PASSWORD` `REF_DB_READ_CHARSET`
- [ ] 在 [`backend-server/src/config/settings.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/config/settings.py) 增加主库/读库双配置读取。
- [ ] 在 [`shared/bootstrap.py`](/Users/lusd/Documents/New project/refactor-v2/shared/bootstrap.py) 增加 `REF_DB_READ_* -> DB_READ_*` 环境映射。
- [ ] 在 [`backend-server/src/utils/DbUtil.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/utils/DbUtil.py) 实现双连接池。
  - `execute/execute_sql/execute_insert` 固定走主库
  - `fetch_one/fetch_all/query_one/query_all` 默认走读库
  - 保留强制走主库开关，给“写后立刻读”场景使用
- [ ] 不改表名，不改服务边界，只改底层读路由。

## 4.2 阶段 B：把 6 类平台展示主数据切到“读库为主”

### B1. market_insight

- [ ] 保持写入入口不变：
  - [`backend-server/src/core/analysis/MarketInsightService.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/core/analysis/MarketInsightService.py)
  - [`apps/risk-service/scheduler/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/risk-service/scheduler/src/main.py)
- [ ] 让以下读接口明确按读库模型运行：
  - [`apps/market-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/market-service/src/main.py) 的 `/api/v1/market/insights`
  - [`apps/market-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/market-service/src/main.py) 的 `/api/v1/market/insights/history`
- [ ] 前端页面默认只读快照，不再对 `/market` `/dashboard` `/symbol/:symbol` 做持续实时市场脉冲刷新。

### B2. recommendation

- [ ] 保持写入入口不变：
  - [`backend-server/src/core/analysis/RecommendationService.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/core/analysis/RecommendationService.py)
  - [`apps/risk-service/scheduler/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/risk-service/scheduler/src/main.py)
- [ ] 读取改为稳定读库：
  - [`apps/analysis-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/analysis-service/src/main.py) `/api/v1/analysis/recommendations`
- [ ] `/dashboard` 和 `/recommendations` 都只显示最近一次生成结果。
- [ ] “立即刷新”仍走主库写入，刷新后本次请求允许强制回主读一次。

### B3. finance_briefing

- [ ] 保持写入入口不变：
  - [`backend-server/src/core/analysis/FinanceBriefingService.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/core/analysis/FinanceBriefingService.py)
- [ ] 读取接口固定读快照：
  - [`apps/analysis-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/analysis-service/src/main.py) `/api/v1/analysis/finance-briefings`
- [ ] `/dashboard` 只读库，不做页面级强刷新。

### B4. trend_scan

- [ ] 保持写入入口不变：
  - [`backend-server/src/core/analysis/DailySymbolTrendScanService.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/core/analysis/DailySymbolTrendScanService.py)
- [ ] 读取接口固定读库：
  - [`apps/analysis-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/analysis-service/src/main.py) `/api/v1/analysis/trend-scans`
  - [`apps/market-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/market-service/src/main.py) `/api/v1/market/symbols/{symbol}/overview`
- [ ] `/ai-analysis` 默认先加载最近扫描结果，不再为了“看列表”直接依赖实时持仓以外的数据。

### B5. historical_market_data

- [ ] 保持写入入口不变：
  - [`backend-server/src/core/analysis/HistoricalMarketDataService.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/core/analysis/HistoricalMarketDataService.py)
- [ ] 读取接口固定读库：
  - [`apps/market-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/market-service/src/main.py) `/api/v1/market/history`
  - [`apps/market-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/market-service/src/main.py) `/api/v1/market/history/compare`
- [ ] `/kline` `/symbol/:symbol` 只读历史表，不走实时行情回补 K 线。

### B6. indicator_snapshot

- [ ] 保持写入入口不变：
  - [`backend-server/src/core/analysis/IndicatorSnapshotService.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/core/analysis/IndicatorSnapshotService.py)
- [ ] 读取接口固定读库：
  - [`apps/market-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/market-service/src/main.py) `/api/v1/market/symbols/{symbol}/overview`
  - [`apps/market-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/market-service/src/main.py) `/api/v1/market/history/compare`
- [ ] `/kline` `/symbol/:symbol` `/ai-analysis` 的指标展示统一来自指标快照表。

## 4.3 阶段 C：新增 4 张核心表，并补 2 个增量能力

### C1. account_asset_snapshots

- [ ] 新建快照表，承接账户资产摘要，作为工作台和个人中心的默认底座。
- [ ] 写入来源：
  - `trade-service` 主动拉券商
  - `scheduler-service` 定时刷新
- [ ] 刷新频率：
  - 盘中 5-15 分钟
  - 收盘后补 1 条日终快照
- [ ] 主要服务改造点：
  - [`apps/trade-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/trade-service/src/main.py)
  - [`apps/risk-service/scheduler/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/risk-service/scheduler/src/main.py)
  - [`backend-server/src/core/platform/SystemTaskService.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/core/platform/SystemTaskService.py)
- [ ] 消费页面：
  - `/dashboard`
  - `/profile`
  - `/trading` 的底座数据

### C2. position_snapshots

- [ ] 新建持仓快照表，替代旧 `positions` 表的临时兜底角色，并支持仓位变化回看。
- [ ] 写入来源：
  - `trade-service` 拉券商持仓后批量落库
  - `scheduler-service` 定时刷新
- [ ] 刷新频率：
  - 盘中 5-15 分钟
- [ ] 主要服务改造点：
  - [`apps/trade-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/trade-service/src/main.py)
  - [`backend-server/src/api/data_routes.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/api/data_routes.py) 中所有 `_load_position_snapshot` 相关逻辑
- [ ] 消费页面：
  - `/dashboard`
  - `/positions`
  - `/risk`
  - `/ai-analysis` 的 positions 数据源底座
  - `/trading` 的卖出可用仓位与账户概览底座

### C3. risk_overview_snapshots

- [ ] 新建风控总览快照表，把风险分、仓位压力、回撤、保护单数量、事件摘要固化。
- [ ] 写入来源：
  - `risk-service` 组装后落库
  - `scheduler-service` 定时刷新
- [ ] 刷新频率：
  - 盘中 10-30 分钟
- [ ] 主要服务改造点：
  - [`apps/risk-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/risk-service/src/main.py)
  - [`backend-server/src/api/data_routes.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/api/data_routes.py) `_build_risk_overview`
- [ ] 消费页面：
  - `/risk`
  - `/dashboard` 后续如要显示风控摘要也可直接复用
  - `/notifications` 可引用快照摘要文案

### C4. symbol_content_cache

- [ ] 新建标的内容缓存表，承接公告、资讯、讨论与统一摘要。
- [ ] 写入来源：
  - `market-service` 内容接口首次 miss 时回源长桥并写库
  - `scheduler-service` 可做热门标的预热
- [ ] 刷新策略：
  - 热门标的每 15-30 分钟预热
  - 普通标的按访问触发，缓存 6-24 小时
- [ ] 主要服务改造点：
  - [`apps/market-service/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/market-service/src/main.py)
  - [`apps/risk-service/scheduler/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/risk-service/scheduler/src/main.py)
- [ ] 消费页面：
  - `/symbol/:symbol`
  - `/finance-news`
  - `/trading` 右侧资讯区

### C5. quote_snapshots（可选增强，不作为首批硬依赖）

- [ ] 新建轻量行情快照表，但只承接“展示需要的子集”。
- [ ] 写入范围：
  - 重点指数
  - 热门股票池
  - 用户持仓
  - 推荐候选
  - 工作台卡片标的
- [ ] 刷新频率：
  - 盘中每 1-5 分钟
- [ ] 约束：
  - 不抓全市场 tick
  - 不替代 WebSocket depth / trades / L2
  - 只为展示页提供更稳的价格底座

### C6. 用户级量化运行结果固化

- [ ] 为 `position_monitor` `quant_trading` 增加“每次执行结果”落库，不只保留任务状态。
- [ ] 建议固化内容：
  - 输入持仓/账户上下文
  - 命中规则与分析摘要
  - 告警、候选动作、最终执行状态
- [ ] 主要服务改造点：
  - [`backend-server/src/core/platform/SystemTaskService.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/core/platform/SystemTaskService.py)
  - [`apps/risk-service/scheduler/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/risk-service/scheduler/src/main.py)
  - `position_monitor` `quant_trading` 对应执行链路
- [ ] 消费页面：
  - `/strategy`
  - `/scheduler-center`
  - `/profile`

## 4.4 阶段 D：只给“实时查看字段”做前台覆盖

- [ ] 强实时交易页继续保留：
  - `/trading`
  - `/positions`
  - `/orders`
  - `/risk`
- [ ] 平台展示页默认读库，但允许局部实时覆盖：
  - `/dashboard`
    - 只覆盖当前账户资产、最新持仓、最新订单
  - `/market`
    - 只覆盖最新价、涨跌幅、重点指数报价
  - `/symbol/:symbol`
    - 只覆盖最新价、盘口、逐笔成交
- [ ] 纯展示页继续只读库：
  - `/kline`
  - `/recommendations`
  - `/finance-news`
  - `/ai-analysis`
- [ ] WebSocket/推送订阅继续复用 [`apps/web-portal/src/composables/useWebSocket.js`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/composables/useWebSocket.js)，但必须按页面能力分层：
  - 展示页只允许 quote/depth/trades 这种局部覆盖
  - 交易页允许账户、持仓、订单、报价联合覆盖
- [ ] 门户页其余区块统一保留“最近更新时间 + 手动刷新”。

## 5. 表结构清单

## 5.1 既有主数据表

| 业务名 | 表名 | 主写入端 | 主读取端 |
|---|---|---|---|
| 市场动态 | `market_insight_snapshots` | `MarketInsightService.refresh_all_markets` | `market-service` |
| 智能推荐 | `recommendation_runs` `recommendation_items` | `RecommendationService.refresh` | `analysis-service` |
| 财经简报 | `finance_briefings` | `FinanceBriefingService.refresh_all_markets` | `analysis-service` |
| 趋势扫描 | `symbol_ai_trend_scans` | `DailySymbolTrendScanService.run_batch` | `analysis-service` `market-service` |
| 历史行情 | `market_price_history_daily` | `HistoricalMarketDataService` | `market-service` |
| 指标快照 | `symbol_indicator_snapshots` | `IndicatorSnapshotService` | `market-service` |

## 5.2 新增表 DDL 建议

以下 DDL 分成两类：

- 核心新增表：`account_asset_snapshots` `position_snapshots` `risk_overview_snapshots` `symbol_content_cache`
- 增量建议表：`quote_snapshots` `user_quant_run_results`

### account_asset_snapshots

```sql
CREATE TABLE IF NOT EXISTS account_asset_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    account_id INT NOT NULL,
    broker_type VARCHAR(32) DEFAULT NULL,
    currency VARCHAR(16) DEFAULT 'USD',
    total_assets DECIMAL(18, 4) DEFAULT 0,
    cash DECIMAL(18, 4) DEFAULT 0,
    market_value DECIMAL(18, 4) DEFAULT 0,
    buying_power DECIMAL(18, 4) DEFAULT 0,
    maintenance_margin DECIMAL(18, 4) DEFAULT 0,
    today_pnl DECIMAL(18, 4) DEFAULT 0,
    today_pnl_percent DECIMAL(10, 4) DEFAULT 0,
    snapshot_at DATETIME NOT NULL,
    source VARCHAR(32) DEFAULT 'broker',
    payload_json JSON DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_user_account_snapshot (user_id, account_id, snapshot_at),
    INDEX idx_user_account_time (user_id, account_id, snapshot_at),
    INDEX idx_snapshot_at (snapshot_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

用途：

- 工作台账户概览
- 个人中心账户概览
- 交易页底座账户状态

### position_snapshots

```sql
CREATE TABLE IF NOT EXISTS position_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    account_id INT NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    market VARCHAR(10) NOT NULL,
    name VARCHAR(160) DEFAULT NULL,
    quantity DECIMAL(18, 4) DEFAULT 0,
    available_quantity DECIMAL(18, 4) DEFAULT 0,
    avg_price DECIMAL(18, 4) DEFAULT 0,
    current_price DECIMAL(18, 4) DEFAULT 0,
    market_value DECIMAL(18, 4) DEFAULT 0,
    pnl DECIMAL(18, 4) DEFAULT 0,
    pnl_percent DECIMAL(10, 4) DEFAULT 0,
    weight DECIMAL(10, 4) DEFAULT 0,
    snapshot_at DATETIME NOT NULL,
    source VARCHAR(32) DEFAULT 'broker',
    payload_json JSON DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_account_symbol_snapshot (account_id, symbol, snapshot_at),
    INDEX idx_user_account_time (user_id, account_id, snapshot_at),
    INDEX idx_symbol_time (symbol, snapshot_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

用途：

- 持仓页展示底座
- 风控总览持仓统计
- AIAnalysis 的持仓源
- 交易页卖出仓位参考

### risk_overview_snapshots

```sql
CREATE TABLE IF NOT EXISTS risk_overview_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    account_id INT DEFAULT NULL,
    risk_score DECIMAL(10, 4) DEFAULT 0,
    score_label VARCHAR(32) DEFAULT NULL,
    score_description VARCHAR(255) DEFAULT NULL,
    high_risk_count INT DEFAULT 0,
    medium_risk_count INT DEFAULT 0,
    max_weight DECIMAL(10, 4) DEFAULT 0,
    position_limit DECIMAL(10, 4) DEFAULT 0,
    drawdown DECIMAL(10, 4) DEFAULT 0,
    drawdown_limit DECIMAL(10, 4) DEFAULT 0,
    protection_count INT DEFAULT 0,
    stop_loss_count INT DEFAULT 0,
    take_profit_count INT DEFAULT 0,
    position_count INT DEFAULT 0,
    snapshot_at DATETIME NOT NULL,
    overview_json JSON DEFAULT NULL,
    events_json JSON DEFAULT NULL,
    source VARCHAR(32) DEFAULT 'risk-service',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_user_account_snapshot (user_id, account_id, snapshot_at),
    INDEX idx_user_account_time (user_id, account_id, snapshot_at),
    INDEX idx_snapshot_at (snapshot_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

用途：

- 风控管理页主卡片
- 风险事件时间线底座
- Dashboard 后续风控摘要扩展

### symbol_content_cache

```sql
CREATE TABLE IF NOT EXISTS symbol_content_cache (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    market VARCHAR(10) NOT NULL,
    content_type VARCHAR(24) NOT NULL,
    source_name VARCHAR(64) NOT NULL,
    source_item_id VARCHAR(128) DEFAULT NULL,
    title VARCHAR(255) NOT NULL,
    summary TEXT,
    source_link VARCHAR(500) DEFAULT NULL,
    published_at DATETIME DEFAULT NULL,
    fetched_at DATETIME NOT NULL,
    expires_at DATETIME DEFAULT NULL,
    content_hash VARCHAR(64) DEFAULT NULL,
    payload_json JSON DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_symbol_content (symbol, content_type, source_name, source_item_id),
    INDEX idx_symbol_type_time (symbol, content_type, published_at),
    INDEX idx_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

用途：

- 标的详情页公告/资讯/讨论
- 财经快讯页内容列表
- 交易页右侧内容区

### quote_snapshots

```sql
CREATE TABLE IF NOT EXISTS quote_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    market VARCHAR(10) NOT NULL,
    snapshot_group VARCHAR(32) NOT NULL,
    price DECIMAL(18, 4) DEFAULT 0,
    change_amount DECIMAL(18, 4) DEFAULT 0,
    change_percent DECIMAL(10, 4) DEFAULT 0,
    volume BIGINT DEFAULT 0,
    source VARCHAR(32) DEFAULT 'longbridge',
    snapshot_at DATETIME NOT NULL,
    payload_json JSON DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_symbol_group_snapshot (symbol, snapshot_group, snapshot_at),
    INDEX idx_group_time (snapshot_group, snapshot_at),
    INDEX idx_symbol_time (symbol, snapshot_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

用途：

- 工作台卡片标的价格底座
- 实时行情页重点标的价格兜底
- 标的详情页最新价的缓存参考

### user_quant_run_results

```sql
CREATE TABLE IF NOT EXISTS user_quant_run_results (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    task_name VARCHAR(64) NOT NULL,
    account_id INT DEFAULT NULL,
    run_id VARCHAR(64) DEFAULT NULL,
    symbol_count INT DEFAULT 0,
    status VARCHAR(32) NOT NULL,
    summary VARCHAR(255) DEFAULT NULL,
    alerts_json JSON DEFAULT NULL,
    candidates_json JSON DEFAULT NULL,
    input_payload JSON DEFAULT NULL,
    result_payload JSON DEFAULT NULL,
    started_at DATETIME DEFAULT NULL,
    finished_at DATETIME DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_task_time (user_id, task_name, created_at),
    INDEX idx_run_id (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

用途：

- 策略执行结果回看
- 任务中心排障
- 用户级量化运行审计

## 6. 页面对应关系

## 6.1 展示页：默认读库，按字段决定是否覆盖

| 路由 | 页面文件 | 基础数据来源 | 目标模式 |
|---|---|---|---|
| `/dashboard` | [`apps/web-portal/src/views/Dashboard.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/Dashboard.vue) | `market_insight_snapshots` `recommendation_*` `finance_briefings` `risk_overview_snapshots` `account_asset_snapshots` `position_snapshots` `trade_order_projections` `user_quant_run_results` | 默认读库；市场动态、推荐、财经简报、风险摘要、最近任务状态先出库，账户资产、最新持仓、最新订单可局部实时覆盖 |
| `/market` | [`apps/web-portal/src/views/MarketData.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/MarketData.vue) | 市场底库 + `market_insight_snapshots` + `symbol_indicator_snapshots` + 可选 `quote_snapshots` | 默认读库；历史分析时点、技术指标和底库稳定展示，最新价、涨跌幅、重点指数可实时覆盖 |
| `/kline` | [`apps/web-portal/src/views/Kline.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/Kline.vue) | `market_price_history_daily` + `symbol_indicator_snapshots` | 纯读库 |
| `/recommendations` | [`apps/web-portal/src/views/Recommendations.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/Recommendations.vue) | `recommendation_runs` `recommendation_items` | 读库快照页 |
| `/finance-news` | [`apps/web-portal/src/views/FinanceNews.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/FinanceNews.vue) | `finance_briefings` + `symbol_content_cache` + 市场扫描快照 | 全部读库，由后台任务统一生成和聚合 |
| `/symbol/:symbol` | [`apps/web-portal/src/views/SymbolDetail.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/SymbolDetail.vue) | `market_price_history_daily` `symbol_indicator_snapshots` `market_insight_snapshots` `symbol_ai_trend_scans` `symbol_content_cache` + 可选 `quote_snapshots` | 默认读库；历史K线、指标、市场扫描、AI历史、公告新闻缓存先读库，最新价、盘口、逐笔可实时覆盖 |
| `/ai-analysis` | [`apps/web-portal/src/views/AIAnalysis.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/AIAnalysis.vue) | `symbol_ai_trend_scans` + `position_snapshots` + AI 历史记录 | 默认读库；手动扫描即时执行并写入历史表 |
| `/stock-pool` | [`apps/web-portal/src/views/StockPool.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/StockPool.vue) | 市场底库 + 指标快照 + 推荐标签 + 趋势标签 + 可选 `quote_snapshots` | 默认读库；底库、指标、推荐标签、趋势标签先展示，最新价可实时覆盖 |

## 6.2 交易页：快照底座 + 前台实时覆盖

| 路由 | 页面文件 | 底座数据 | 实时覆盖范围 |
|---|---|---|---|
| `/trading` | [`apps/web-portal/src/views/Trading.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/Trading.vue) | `account_asset_snapshots` `position_snapshots` `market_insight_snapshots` `symbol_content_cache` | 当前标的 quote/depth/trades、下单回执、最新订单状态 |
| `/positions` | [`apps/web-portal/src/views/Positions.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/Positions.vue) | `position_snapshots` | 当前账户持仓价格、盈亏、仓位变化 |
| `/orders` | [`apps/web-portal/src/views/Orders.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/Orders.vue) | 订单投影表/现有 trade 投影 | 下单后状态推进、撤单结果 |
| `/risk` | [`apps/web-portal/src/views/RiskManagement.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/RiskManagement.vue) | `risk_overview_snapshots` `position_snapshots` | 风险总览先读快照，止损止盈距离、最新事件、保护单状态再局部实时覆盖 |
| `/notifications` | [`apps/web-portal/src/views/Notifications.vue`](/Users/lusd/Documents/New project/refactor-v2/apps/web-portal/src/views/Notifications.vue) | 通知聚合表/状态表 | 新交易通知、新风控通知追加 |

## 6.3 策略/任务/结果页：数据库为主

- `/strategy`
- `/backtest`
- `/risk`
- `/scheduler-center`
- `/profile`

这些页面本质上展示的是规则、结果、记录、状态，不应该退化成 broker 实时流页面；其中 `/strategy` `/scheduler-center` `/profile` 后续应优先消费 `user_quant_run_results` 一类结果表。

## 6.4 不建议继续扩大实时化范围的页面

- `/kline`
- `/recommendations`
- `/finance-news`
- `/ai-analysis`

这些页面统一保留“刷新按钮 + 最近更新时间”，不做常驻推送。

## 7. 建议新增的调度任务

需要在 [`backend-server/src/core/platform/SystemTaskService.py`](/Users/lusd/Documents/New project/refactor-v2/backend-server/src/core/platform/SystemTaskService.py) 和 [`apps/risk-service/scheduler/src/main.py`](/Users/lusd/Documents/New project/refactor-v2/apps/risk-service/scheduler/src/main.py) 追加 5 个系统级任务，并补 1 类结果固化链路：

- `account_asset_snapshot_refresh`
  - 周期建议：盘中 5-15 分钟，收盘后补日终快照
  - 负责写 `account_asset_snapshots`
- `position_snapshot_refresh`
  - 周期建议：盘中 5-15 分钟
  - 负责写 `position_snapshots`
- `risk_overview_snapshot_refresh`
  - 周期建议：盘中 10-30 分钟
  - 负责写 `risk_overview_snapshots`
- `symbol_content_cache_refresh`
  - 周期建议：热门标的 15-30 分钟，普通标的按访问触发
  - 负责热门标的公告/资讯/讨论预热
- `quote_snapshot_refresh`
  - 周期建议：1-5 分钟
  - 只抓重点指数、热门股票池、用户持仓、推荐候选、工作台卡片标的
  - 当前属于建议增量，不建议一开始就把全市场 tick 全量入库

另一个值得补的方向：

- 用户级量化运行结果固化
  - 触发源：`position_monitor` `quant_trading`
  - 建议内容：每次执行输入、命中规则、分析结果、告警、候选动作、最终执行状态
  - 用途：`/strategy` `/scheduler-center` `/profile` 的结果回看与排障

## 8. 开发落地顺序

### 第 1 批

- 读写分离底层能力
- 第一层主数据统一切换为“前端默认读库”
- `market_insight` `recommendation` `finance_briefing` 改读库

### 第 2 批

- `historical_market_data` `indicator_snapshot` `trend_scan` 改读库
- 新增 `symbol_content_cache`
- `finance-news` 停止前端临时拼多源，统一改走读库聚合

### 第 3 批

- 新增 `account_asset_snapshots`
- 新增 `position_snapshots`
- 新增 `risk_overview_snapshots`
- 补用户级量化运行结果固化

### 第 4 批

- 前端页面切换数据来源
- 把实时覆盖收口到“交易页 + 行情查看页的少数字段”
- 视需要新增 `quote_snapshots` 作为展示价缓存增强
- 其中：
  - `/trading` `/positions` `/orders` `/risk` 允许完整实时覆盖
  - `/dashboard` `/market` `/symbol/:symbol` 只允许局部实时覆盖

## 9. 验收标准

- 门户类页面在券商断连时仍可正常打开，展示最近一次可用快照。
- `market_insight` `recommendation` `finance_briefing` `trend_scan` `historical_market_data` `indicator_snapshot` 默认查询不打主库。
- `/dashboard` 不再依赖券商实时账户数据才能首屏可用。
- `/market` `/symbol/:symbol` 只为最新价/盘口/逐笔等局部字段保留实时覆盖，不回退为整页 live API 页面。
- `/finance-news` 不再由前端直接拼多个外部内容源，而是统一读取后台聚合结果。
- `/trading` `/positions` `/orders` `/risk` 仍能看到实时变化，但首屏先出快照。
- 新增核心 4 张表可独立被查询、回放、排查，并具备明确索引；如果启用 `quote_snapshots` 与量化结果表，也应遵循同样原则。

# 重构迁移路线图

## 设计前提

- 当前根目录项目继续作为旧版备份和回退基线。
- 新项目在 `refactor-v2/` 内独立推进。
- 不强制一次性迁移，按模块逐步替换。
- 舆情模块先只留服务边界，不先做采集实现。

## 阶段拆分

### 阶段 0：骨架期

目标：

- 确立目录结构
- 固化服务边界
- 固化独立端口
- 落舆情占位服务

产物：

- `refactor-v2/README.md`
- `refactor-v2/.env.example`
- `refactor-v2/docs/service-map.yaml`
- `refactor-v2/apps/sentiment-service`

### 阶段 1：用户与会话中心

建议先迁移：

- 登录 / 用户资料
- 用户配置
- 自选标的
- 关注列表

旧代码来源：

- `backend-server/src/api/user_routes.py`
- `backend-server/src/core/platform/PlatformAccessService.py`
- `web/src/views/Profile.vue`
- `web/src/views/UserManagement.vue`

### 阶段 2：行情与指标中心

建议先迁移：

- 标的基础信息
- 历史行情
- 技术指标快照
- 市场扫描结果

旧代码来源：

- `backend-server/src/core/analysis/HistoricalMarketDataService.py`
- `backend-server/src/core/analysis/IndicatorSnapshotService.py`
- `backend-server/src/api/data_routes.py`

### 阶段 3：AI 分析中心

建议迁移：

- 单标的 AI 分析
- 批量趋势扫描
- 最终结论生成
- 结果缓存与结果表

旧代码来源：

- `backend-server/src/api/ai_routes.py`
- `backend-server/src/core/analysis/DailySymbolTrendScanService.py`
- `web/src/views/AIAnalysis.vue`

### 阶段 4：策略与风控中心

建议迁移：

- 策略运行入口
- 风控规则
- 风控事件
- 回测任务
- 通知中心

### 阶段 5：交易执行中心

建议迁移：

- 下单
- 撤单
- 持仓
- 订单查询

旧代码来源：

- `services/trade-service/`
- `backend-server/src/api` 中交易代理相关部分

### 阶段 6：舆情中心

先不实现抓取，但已经预留：

- 服务名：`sentiment-service`
- 端口：`8106`
- 接口前缀：`/api/v1/sentiment`

后续可接入：

- 新闻源抓取
- 文本清洗
- 情绪打分
- 事件抽取
- 标的情绪汇总

## 迁移策略

1. 新模块优先读旧库，先不强制新建整套库表。
2. 接口稳定后，再逐步把旧前端页面迁到新网关。
3. 每次只替换一个业务域，避免全站级联风险。

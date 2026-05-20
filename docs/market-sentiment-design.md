# 市场舆情补全设计

## 目标

在不触碰交易写路径、不新增独立 AI 密钥体系的前提下，补齐平台现有“舆情 / 情绪 / 新闻 / 资讯”能力，提供独立页面、只读后端 contract，并与量化分析、策略研究、智能推荐形成结构化联动。

## 现状结论

- `apps/market/sentiment-service` 原先仅为占位服务。
- 前端已有：
  - `/finance-news`：财经快讯 / market briefing 聚合
  - `/recommendations`：推荐结果与理由
  - `/ai-analysis`：逐股 AI 研判 / 趋势扫描
  - `/strategy`：策略管理与监控
- 后端已有可复用数据源：
  - `finance_briefings`
  - `symbol_ai_trend_scans`
  - `recommendation_runs` / `recommendation_items`
  - `ai_analysis_history`
  - `symbol_content_cache`
- AI 配置体系已经统一到 `LONGBRIDGE_AI_*` / `sub2api`：
  - `AI_BASE_URL=http://sub2api:8080/v1`
  - `AI_URL=http://sub2api:8080/v1/chat/completions`
  - 模型默认 `gpt-5.5`，扫描与轻量总结使用 `gpt-5.4`

## 业务能力补全范围

本轮优先补只读展示与结构化 contract：

1. 情绪指标
- `sentiment_score`
- `sentiment_label`
- `confidence`
- `heat_score`
- `positive_ratio`
- `negative_ratio`

2. 舆情来源
- 财经快讯 / 市场简报
- 内容缓存中的 `news / topics / announcements`
- 趋势扫描文本与 AI 历史结论中的风险 / 情绪提示

3. 标的关联
- symbol 级舆情聚合
- market 级聚合摘要
- 关联到 `/ai-analysis`、`/recommendations`、`/strategy`

4. 风险词
- 监管
- 盈利
- 流动性
- 波动
- 事件

5. 量化可消费字段
- `sentiment_score`
- `heat_score`
- `trend_direction`
- `trend_strength`
- `technical_score`
- `ai_confidence`
- `ai_bias`
- `expected_return`
- `recommended`

6. AI 摘要 / 证据
- 复用 `ai_analysis_history` 与 `finance_briefings`
- 明确说明 AI 配置继承自 `LONGBRIDGE_AI_*`
- 不新增单独模型、单独 API key、单独 provider 配置

## 新增 contract

`sentiment-service` 提供：

- `GET /api/v1/sentiment/config`
- `GET /api/v1/sentiment/bootstrap`
- `GET /api/v1/sentiment/overview`
- `GET /api/v1/sentiment/universe`
- `GET /api/v1/sentiment/symbol/{symbol}`

原则：

- 只读
- 不触发交易
- 不写入外部内容采集结果
- 允许未来替换为真实采集链路，但前端 contract 保持稳定

## 前端独立页

路由：

- `/sentiment-center`
- `/market-sentiment` 作为兼容重定向保留

页面内容：

- AI / 模型继承状态
- 分市场情绪摘要
- 风险词热度
- 标的舆情联动表
- 跳转入口：
  - `AIAnalysis`
  - `Recommendations`
  - `Strategy`

## GitHub 候选评估

### `amitpatole/tickerpulse-ai`
- 许可证：GPL-3.0
- 技术栈：Flask + BeautifulSoup + `yfinance`
- 适合：参考多源数据抓取范围、舆情指标设计、研究型多智能体分工
- 风险：GPL 传染性强；若直接复制 / vendoring 到主仓，许可风险高
- 结论：`参考实现，不直接集成`

### `shirosaidev/stocksight`
- 许可证：需再次核对仓库当前 License 文本
- 技术栈：Elasticsearch + Twitter + VADER / TextBlob
- 适合：参考“新闻 + 社媒 + 情绪分数 + 存储模型”
- 风险：技术栈偏旧；Twitter/Elasticsearch 引入成本高
- 结论：`参考实现，不直接引入旧栈`

### `awsdataarchitect/financial-signals-dashboard`
- 许可证：需按仓库当前声明核对
- 技术栈：dashboard + AI alpha signal，依赖 Bright Data MCP / Strands
- 适合：参考“舆情 -> alpha signal -> risk/recommendation”链路
- 风险：外部付费依赖、集成复杂度高
- 结论：`只参考信息架构与联动 contract`

### `koala73/worldmonitor` / `FutureSpeakAI/worldmonitor-agent-friday`
- 许可证：需按仓库当前声明核对
- 技术栈：AI 新闻聚合 / 本地 LLM / dashboard
- 适合：参考 dashboard 信息架构
- 风险：项目范围大、授权与边界复杂
- 结论：`只参考 IA，不直接接入`

### `dragon1086/prism-insight`
- 许可证：需按仓库当前声明核对
- 技术栈：AI 股票分析、多 agent
- 适合：参考 news analysis agent 的 prompt / contract
- 风险：包含自动交易能力，存在越界风险
- 结论：`仅参考 news analysis agent，绝不引入交易执行部分`

## 最终策略

- 不直接 vendoring 外部仓库
- 不新增外部依赖
- 不复制 GPL 代码
- 采用“参考实现 + 本地轻量聚合 contract”
- AI 配置完全复用当前 `sub2api` / `LONGBRIDGE_AI_*`

## 最小实现文件列表

- `apps/market/sentiment-service/src/main.py`
- `apps/frontend/web-portal/src/utils/api.js`
- `apps/frontend/web-portal/src/api/sentiment.js`
- `apps/frontend/web-portal/src/views/MarketSentiment.vue`
- `apps/frontend/web-portal/src/router/index.js`
- `apps/frontend/web-portal/src/utils/auth.js`
- `apps/frontend/web-portal/src/components/layout/MobileNav.vue`
- `backend-server/src/core/platform/PlatformAccessService.py`
- `docs/market-sentiment-design.md`

## 剩余风险

- 当前 symbol 级舆情仍依赖已存在内容缓存和财经简报，不是完整实时采集系统。
- 部分 GitHub 候选仓库的许可证细节需要正式引入前再次逐仓核对。
- 若未来要接真实社媒 / 论坛源，需要单独评估合规、频控和缓存策略。

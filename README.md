# Refactor V2

`refactor-v2/` 是新一轮重构的独立工作区，构建了一个完整的量化交易系统。

当前根目录下的旧项目已经收纳到 `refactor-v1/` 作为备份与参考源；新的重构项目不直接覆盖旧目录，而是在独立文件夹内完成全部工程收敛。后续可复用的代码、配置和脚本优先复制进 `refactor-v2/`，旧项目可以停止运行，不作为新平台的长期运行依赖。

## 项目架构

### 微服务架构

本项目采用现代化的微服务架构，包含以下核心服务：

| 服务名称 | 端口 | 状态 | 主要职责 |
|----------|------|------|----------|
| Web Portal | 3100 | ✅ 已运行 | 统一用户界面、路由编排、图表和分析视图 |
| API Gateway | 5101 | ✅ 已运行 | 认证聚合、服务路由、统一响应包装 |
| User Center | 8101 | ✅ 已运行 | 登录、个人资料、监单列表、用户偏好 |
| Market Service | 8102 | ✅ 已运行 | 市场宇宙、价格历史、指标快照、市场扫描数据集 |
| Analysis Service | 8103 | ✅ 已运行 | AI分析、趋势批量扫描、结论生成 |
| Strategy Service | 8104 | ✅ 已运行 | 策略配置、风险规则协调、回测编排 |
| Trade Service | 8105 | ✅ 已运行 | 订单执行、持仓查询、订单投射 |
| Sentiment Service | 8106 | 🟡 占位中 | 情感摄取、情感评分、事件提取、标的情感摘要 |
| Scheduler Service | 8107 | ✅ 已运行 | 线程状态/任务策略/执行记录 |
| Risk Service | 8108 | ✅ 已运行 | 风控总览/保护单/通知中心 |

### 技术栈

#### 前端
- **Vue 3**：最新版本，性能优秀
- **Element Plus**：成熟的UI组件库
- **ECharts**：专业的图表库
- **Pinia**：现代状态管理
- **Vite**：快速构建工具
- **Vue Router**：路由管理

#### 后端
- **Python**：适合量化计算
- **Redis**：缓存与会话管理
- **InfluxDB**：时序数据存储
- **Kafka**：消息队列（规划中）

#### 券商接口
- **长桥API**：已集成
- **老虎API**：已集成

## 当前原则

1. 老项目保留在 `refactor-v1/`，不作为本轮重构的编辑主目录。
2. 新项目的工程文件、配置与运行依赖应尽量全部收敛在 `refactor-v2/` 内。
3. 可复用能力优先采用“复制迁入”方式，而不是跨目录直接依赖旧项目。
4. 新项目默认使用独立数据库 `quant_trade_refactor`，需要时可从 `refactor-v1` 的源库初始化一次。
5. 新平台内部保留模块级、终端级、角色级手工开关能力，用于控制新能力启用。
6. 舆情模块暂不实现抓取链路，只保留服务占位和接口契约。

## 核心功能

### 1. 交易管理
- **交易台**：实时交易界面
- **持仓管理**：持仓查询与监控
- **订单管理**：订单查询与管理
- **券商连接**：支持长桥、老虎券商API

### 2. 市场数据
- **股票池**：多市场股票筛选（美股、港股、A股）
- **实时行情**：WebSocket实时推送
- **历史K线**：历史数据分析
- **市场扫描**：自动扫描市场机会

### 3. AI分析
- **AI研判**：智能分析决策
- **智能推荐**：基于策略的股票推荐
- **财经快讯**：实时财经新闻
- **趋势扫描**：批量趋势分析

### 4. 量化策略
- **策略管理**：策略配置与监控
- **策略回测**：历史数据回测
- **量化交易调度**：自动化交易执行

### 5. 风控管理
- **风控总览**：风险监控仪表盘
- **保护单**：止损止盈设置
- **通知中心**：风险预警通知

### 6. 系统管理
- **用户管理**：用户权限管理
- **任务中心**：调度任务管理
- **系统设置**：配置管理
- **审计日志**：操作记录追踪

## 目录说明

- `docs/`
  - 重构路线图
  - 服务映射与迁移边界
  - 架构概览文档
- `apps/`
  - 各新模块的独立目录，现已按类别分组
  - `frontend/web-portal/`：前端门户
  - `platform/api-gateway/`：API网关
  - `platform/user-center/`：用户中心
  - `market/market-service/`：市场服务
  - `market/sentiment-service/`：舆情服务（占位）
  - `intelligence/analysis-service/`：分析服务
  - `intelligence/strategy-service/`：策略服务
  - `trading/trade-service/`：交易服务
  - `governance/risk-service/`：风控服务
  - `operations/scheduler-service/`：调度服务
  - 旧的平铺路径仍保留为兼容链接，例如 `apps/web-portal`、`apps/trade-service`
  - 每个大模块都提供独立入口：`apps/<category>/run.sh`
- `backend-server/src/`
  - 从旧项目复制进来的后端核心模块，作为重构期内部运行依赖
- `legacy_trade_service/`
  - 从旧交易运行时复制并显式包化后的执行域运行依赖
- `scripts/`
  - 新项目专属启动脚本

## 舆情模块现状

舆情抓取先不落真实实现，但已经预留：

- 独立服务目录：`apps/market/sentiment-service/`
- 默认端口：`8106`
- 基础健康检查：`GET /health`
- 预留接口前缀：`/api/v1/sentiment/*`

后续你把抓数方案定下来后，可以直接在这个目录接入真实抓取器和分析流水线。

## 快速启动

### 启动服务

第一批实时可用服务已经落地，可直接启动：

```bash
./scripts/start_phase1_stack.sh
```

也可以按大模块单独启动：

```bash
cd apps/frontend && ./run.sh
cd apps/platform && ./run.sh
cd apps/market && ./run.sh
cd apps/intelligence && ./run.sh
cd apps/trading && ./run.sh
cd apps/governance && ./run.sh
cd apps/operations && ./run.sh
```

每个具体服务目录也都提供独立入口，例如：

```bash
cd apps/platform/api-gateway && ./run.sh
cd apps/market/market-service && ./run.sh
cd apps/trading/trade-service && ./run.sh
```

### 访问应用

启动后，可通过以下地址访问：
- **Web Portal**：http://localhost:3100
- **API Gateway**：http://localhost:5101
- **User Center**：http://localhost:8101

### 测试API

项目提供了API测试脚本，可验证服务是否正常运行：

```bash
node test_all_api.js
```

测试报告将生成在 `api_test_report.json` 文件中。

## 下一步建议

1. 把 `web-portal` 接到 `5101/8101/8102/8103` 这批新服务，而不是继续直连老后端。
2. 继续把 `scheduler` 从“可用调度面板”推进到“多服务编排中枢”。
3. 实现舆情服务的抓取和分析功能。
4. 增加监控告警机制，提高系统可靠性。
5. 完善测试覆盖，包括单元测试和集成测试。
6. 等新目录链路稳定后，再决定是否替换现有根目录项目。

## 系统状态

- ✅ 核心微服务已部署运行
- ✅ 前端门户已实现基本功能
- ✅ API接口测试通过
- ✅ 券商连接已配置
- 🟡 舆情服务待实现
- 🟡 监控告警待完善
- 🟡 测试覆盖待加强

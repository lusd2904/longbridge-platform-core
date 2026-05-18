# 兼容边界分域拆分设计

## 背景

当前重构目录中，[shared/legacy_compat.py](/Users/lusd/Documents/New%20project/refactor-v2/shared/legacy_compat.py) 承担了迁移期兼容适配层职责，但它已经演化成一个跨服务的总入口，混合了以下 4 类能力：

- `market`：股票池表配置、标的规范化、股票池统计
- `analysis`：券商行情回退、市场快照、降级分析拼装
- `risk`：风险总览、通知中心、风控设置、保护单查询
- `trade`：券商账户脱敏、默认账户选择、账户配置包装

它的直接问题不是“文件大”，而是“边界错位”：

- 多个服务通过同一个兼容文件访问旧实现，服务边界被重新耦合
- 健康检查和运行态仍把这层总适配器视作系统级依赖
- `backend-server/src` 无法继续拆除，因为 `legacy_compat` 是旧实现进入新工程的统一入口

## 目标

- 拆掉 `shared/legacy_compat.py` 这个总适配器
- 按服务域拆成独立模块，做到“每个服务只 import 自己那一域”
- 保持现有对外接口与健康检查字段兼容，不做接口破坏式改名
- 为下一阶段移除 `bootstrap` 对 `backend-server/src` 的注入创造条件

## 非目标

- 本轮不移除 [shared/bootstrap.py](/Users/lusd/Documents/New%20project/refactor-v2/shared/bootstrap.py) 中对 `backend-server/src` 的注入
- 本轮不处理 [apps/trade-service/src/main.py](/Users/lusd/Documents/New%20project/refactor-v2/apps/trade-service/src/main.py) 对 [services/trade-service/src/main.py](/Users/lusd/Documents/New%20project/refactor-v2/services/trade-service/src/main.py) 的动态加载
- 本轮不重写 `backend-server/src/api/*` 与 `backend-server/src/core/*` 的旧实现，只调整新工程中的边界接入方式

## 设计原则

- 先拆边界，再拆实现；先消灭“总入口”，再消灭“旧实现依赖”
- 服务目录因使用连字符命名，无法直接作为稳定 Python 包导入路径，因此“服务拥有的域模块”统一落在仓库根目录新包中
- 新模块只按职责分域，不再按“兼容层”概念组织
- 健康检查继续返回 `legacyCompat` 字段，但其来源改为新的边界运行态模块，而不是旧总适配器

## 目标结构

新增顶层包 `service_boundaries/`：

- `service_boundaries/__init__.py`
- `service_boundaries/_legacy_loader.py`
- `service_boundaries/runtime.py`
- `service_boundaries/market_boundary.py`
- `service_boundaries/analysis_boundary.py`
- `service_boundaries/risk_boundary.py`
- `service_boundaries/trade_boundary.py`

职责划分如下：

### `_legacy_loader.py`

- 负责 `bootstrap_runtime()`
- 负责 `legacy_compat_enabled()` 判定
- 提供 `data_routes()`、`ai_routes()`、`broker_routes()` 三个惰性加载器
- 这是唯一允许直接触达旧 `api.*` 模块的边界入口

### `runtime.py`

- 提供 `legacy_boundary_status(boundary_name)` 统一运行态描述
- 对外仍使用 `legacyCompat` 语义，但底层不再依赖 `shared.legacy_compat`

### `market_boundary.py`

- 承载 `iter_stock_pool_tables`
- 承载 `build_stock_pool_stats`
- 承载 `resolve_stock_pool_table`
- 承载 `fetch_stock_pool_rows`
- 承载 `normalize_market_symbol`

### `analysis_boundary.py`

- 承载 `get_quote_from_broker`
- 承载 `get_quotes_from_broker`
- 承载 `build_market_snapshot`
- 承载 `build_indicator_context_with_fallback`
- 承载 `build_degraded_analysis_result`
- 承载 `detect_market`
- 承载 `extract_position_quote_fallback`

### `risk_boundary.py`

- 承载 `build_risk_overview`
- 承载 `collect_notifications`
- 承载 `upsert_notification_states`
- 承载 `load_risk_limits`
- 承载 `ensure_risk_control_tables`
- 承载 `load_risk_orders`
- 复用 `normalize_market_symbol`

### `trade_boundary.py`

- 承载 `get_user_broker_account`
- 承载 `build_masked_broker_config`
- 承载 `ensure_default_selection`
- 承载 `enrich_broker_account`
- 承载 `mask_account_id`

## 应用层改造方式

### market-service

- [apps/market-service/src/main.py](/Users/lusd/Documents/New%20project/refactor-v2/apps/market-service/src/main.py) 改为只从 `service_boundaries.market_boundary` 导入股票池相关能力
- [apps/market-service/src/stock_pool_query.py](/Users/lusd/Documents/New%20project/refactor-v2/apps/market-service/src/stock_pool_query.py) 改为只从 `service_boundaries.market_boundary` 导入 `iter_stock_pool_tables`
- 健康检查改为从 `service_boundaries.runtime` 导入状态函数

### analysis-service

- [apps/analysis-service/src/main.py](/Users/lusd/Documents/New%20project/refactor-v2/apps/analysis-service/src/main.py) 改为只从 `service_boundaries.analysis_boundary` 导入分析回退能力
- 健康检查改为从 `service_boundaries.runtime` 导入状态函数

### risk-service

- [apps/risk-service/src/main.py](/Users/lusd/Documents/New%20project/refactor-v2/apps/risk-service/src/main.py) 改为只从 `service_boundaries.risk_boundary` 导入风险域能力
- [apps/risk-service/scheduler/src/main.py](/Users/lusd/Documents/New%20project/refactor-v2/apps/risk-service/scheduler/src/main.py) 改为只从 `service_boundaries.risk_boundary` 导入 `build_risk_overview`
- 健康检查改为从 `service_boundaries.runtime` 导入状态函数

### trade-service

- [apps/trade-service/src/main.py](/Users/lusd/Documents/New%20project/refactor-v2/apps/trade-service/src/main.py) 改为只从 `service_boundaries.trade_boundary` 导入券商账户域能力
- 健康检查改为从 `service_boundaries.runtime` 导入状态函数

## 删除策略

当上述服务全部完成导入替换后，直接删除 [shared/legacy_compat.py](/Users/lusd/Documents/New%20project/refactor-v2/shared/legacy_compat.py)。

删除后系统仍保留两条未拆完链路：

- `shared/bootstrap.py` 仍负责旧路径注入
- `apps/trade-service/src/main.py` 仍动态加载 `services/trade-service/src/main.py`

这意味着本轮的完成标准是“拆掉总适配器”，不是“彻底移除全部旧代码”

## 验证策略

本轮采用“结构测试 + 语法校验”双层验证：

### 结构测试

新增 `pytest` 架构测试，覆盖：

- `service_boundaries/` 包存在
- 四个分域边界模块存在
- 关键服务文件不再出现 `shared.legacy_compat` import
- [shared/legacy_compat.py](/Users/lusd/Documents/New%20project/refactor-v2/shared/legacy_compat.py) 已被删除

### 语法校验

- 对新增边界模块与改动后的服务入口执行 `python3 -m py_compile`

## 风险与回退

### 风险

- 若遗漏某个服务入口 import，运行时会出现 `ImportError`
- 若分域模块搬迁时漏掉某个函数，会导致对应服务局部功能失效
- 健康检查若仍依赖旧 `compat_status`，删除旧文件后会直接报错

### 回退

- 本轮改造是“引入新分域模块 + 切换 import + 删除旧总适配器”
- 如果验证失败，可临时恢复 `shared/legacy_compat.py` 并让服务重新指向旧入口
- 由于本轮不改对外 API，不涉及数据迁移与前端回退问题

## 本轮完成定义

满足以下条件即可视为本轮完成：

- `shared.legacy_compat` 在应用代码中零引用
- `shared/legacy_compat.py` 文件被删除
- `service_boundaries/` 分域包建立完成
- `pytest` 架构测试通过
- `py_compile` 语法校验通过


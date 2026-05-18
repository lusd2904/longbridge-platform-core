# 最近重构方向与计划汇总

## 文档目的

这份文档集中记录 `Refactor V2` 在最近一轮中的实际重构方向、已完成事项和下一阶段计划，避免信息只散落在多份 `spec / plan` 文档中。

适用范围：

- 工程重构跟进
- 架构收口
- 后续任务排期
- 查找最近一轮重构主线

## 最近重构的总体方向

最近一轮重构不是在“继续堆功能”，而是在先清理平台底座中的高耦合、高隐式依赖问题，主线可以概括为四条：

1. 去掉跨目录、动态加载、`sys.path` 注入等运行时魔法依赖。
2. 把旧实现从“大文件 + 总适配器”逐步拆成可控边界。
3. 保持现有 HTTP 契约和业务行为尽量稳定，优先做结构性收敛。
4. 让后续前端平台壳层、角色权限、菜单编排建立在更稳定的后端运行边界之上。

## 最近已经完成的重构方向

### 1. 兼容边界分域拆分

已完成：

- 拆掉 `shared.legacy_compat` 总适配器。
- 新增 `service_boundaries/`，按 `market / analysis / risk / trade` 分域暴露兼容边界。
- 各服务入口已切换到分域边界模块。

结果：

- 兼容层不再是一个总入口文件。
- 各服务只依赖自己所属的边界模块。
- 健康检查统一读取新的运行态状态函数。

对应文档：

- [2026-03-27-legacy-compat-domain-split-design.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/specs/2026-03-27-legacy-compat-domain-split-design.md)
- [2026-03-27-legacy-compat-domain-split.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-27-legacy-compat-domain-split.md)

### 2. Bootstrap 去注入与显式旧包入口

已完成：

- 去掉 `shared/bootstrap.py` 对 `backend-server/src` 的全局 `sys.path` 注入。
- 新增根级显式旧包入口：
  - `api`
  - `config`
  - `core`
  - `database`
  - `market`
  - `social`
  - `strategy`
  - `utils`

结果：

- 旧代码仍可导入，但依赖方式变成显式兼容包，而不是运行时路径魔法。
- `backend-server/src` 仍是旧实现承载目录，但已经不再是隐式全局导入源。

对应文档：

- [2026-03-27-bootstrap-explicit-legacy-packages-design.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/specs/2026-03-27-bootstrap-explicit-legacy-packages-design.md)
- [2026-03-27-bootstrap-explicit-legacy-packages.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-27-bootstrap-explicit-legacy-packages.md)

### 3. 交易运行时显式包化

已完成：

- 把 `apps/trade-service` 对旧交易运行时的依赖，从动态文件路径加载改成显式包导入。
- 新增 `legacy_trade_service/` 作为显式交易运行包。
- 删除 `services/trade-service/` 旧运行时目录。

结果：

- `apps/trade-service/src/main.py` 不再依赖 `importlib.util` 和路径字符串。
- 交易运行时的第一层“文件路径依赖”已经解除。

对应文档：

- [2026-03-27-trade-runtime-explicit-package-design.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/specs/2026-03-27-trade-runtime-explicit-package-design.md)
- [2026-03-27-trade-runtime-explicit-package.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-27-trade-runtime-explicit-package.md)

### 4. 交易运行时内部模块拆分

已完成：

- 从 `legacy_trade_service/main.py` 中拆出：
  - `models.py`
  - `outbox.py`
  - `account_views.py`
- `main.py` 已退化为更薄的运行入口与装配层。

结果：

- `legacy_trade_service/main.py` 已从约 `2088` 行降到约 `1039` 行。
- `OutboxRelay`、`schema / saga / projection`、账户与订单视图逻辑都不再直接定义在 `main.py` 中。
- 交易运行时已经从“显式包化”进入“内部边界拆分”阶段。

对应文档：

- [2026-03-27-trade-runtime-internal-module-split-design.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/specs/2026-03-27-trade-runtime-internal-module-split-design.md)
- [2026-03-27-trade-runtime-internal-module-split.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-27-trade-runtime-internal-module-split.md)

### 5. 交易命令编排层拆分

已完成：

- 新增 `legacy_trade_service/trade_commands.py`，专门承接提交/撤单命令编排逻辑。
- 把 `_submit_order`、`_cancel_order` 以及参数校验、参考价加载、风控闸门、券商执行、持久化补偿、响应组装等直接依赖 helper 从 `legacy_trade_service/main.py` 迁出。
- `legacy_trade_service/main.py` 当前改为通过显式导入继续暴露兼容符号，而不再自己承载交易命令编排实现。

结果：

- `legacy_trade_service/main.py` 已从约 `1039` 行进一步收缩到约 `460` 行。
- 交易运行时的提交/撤单主流程已经不再直接混在 FastAPI 装配文件里。
- 当前交易遗留单体的主要复杂度，已经从 `main.py` 收敛到更明确的 `trade_commands.py` 模块。

对应文档：

- [2026-03-28-trade-command-orchestration-split.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-28-trade-command-orchestration-split.md)

### 6. 交易命令行为加固与提交/撤单分流

已完成：

- 补上缺失 `order_id` 时的失败保护，避免继续落投影、返回成功响应或对空订单号做补偿撤单。
- 新增 `tests/python/test_trade_command_behaviors.py`，覆盖提交/撤单关键失败路径。
- 新增 `legacy_trade_service/trade_submit_flow.py` 与 `legacy_trade_service/trade_cancel_flow.py`，把 submit / cancel 专属 helper 继续拆出。
- `legacy_trade_service/trade_commands.py` 当前退化为“公共 helper + 兼容导出层”。

结果：

- `legacy_trade_service/trade_commands.py` 已从约 `862` 行进一步收缩到约 `295` 行。
- `legacy_trade_service/trade_submit_flow.py` 当前约 `539` 行，成为提交主流程编排承载点。
- `legacy_trade_service/trade_cancel_flow.py` 当前约 `139` 行，撤单主流程已独立成单独模块。
- Python 测试总数已提升到 `26` 个，交易命令层不再只有结构测试，开始具备行为回归保护。

对应文档：

- [2026-03-28-trade-command-hardening-and-split.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-28-trade-command-hardening-and-split.md)

### 7. 交易服务重复 Helper 收口与读取路径复用

已完成：

- `apps/trade-service/src/main.py` 已改为复用 `legacy_trade_service._load_account_state` 与 `legacy_trade_service._load_orders_for_account`
- 删除 `apps/trade-service/src/main.py` 中重复存在的 `_serialize_account_info`、`_serialize_position`、`_ensure_broker_connected`、`_ensure_order_projection_schema`、`_get_broker`
- `trade_order_projections` 的 schema ownership 已统一收口到 `legacy_trade_service/outbox.py`
- `legacy_trade_service/outbox.py` 已补齐 `idx_user_status_updated (user_id, status, updated_at)` 索引兜底
- 删除空的 `services/` 目录

结果：

- `apps/trade-service/src/main.py` 不再维护第二套账户状态和订单回填实现，开始真正复用交易运行时已拆出的读取边界
- 订单投影回填路径不再直接自己拿 broker 并序列化订单，而是复用 `legacy_trade_service/account_views.py`
- 订单回填时的动作字段也顺手从错误的 `action` 读取切回了真实存在的 `side`
- Python 测试总数已提升到 `29` 个，针对 trade-service 重复 helper 收口也有了结构测试保护

对应文档：

- [2026-03-28-trade-service-duplicate-helper-consolidation.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-28-trade-service-duplicate-helper-consolidation.md)

## 当前工程判断

截至目前，最近重构已经完成了两类高风险问题的清理：

- 运行时隐式依赖：
  - 总兼容适配器
  - `sys.path` 注入
  - 动态文件加载
- 交易遗留单体结构：
  - 先包化
  - 再按共享模型、事件流、读取视图、命令编排拆边界

这意味着当前工程已从“旧目录仍能跑”推进到“旧实现开始具备明确模块边界”的阶段。

同时，`apps/trade-service` 与 `legacy_trade_service` 之间最明显的一批读取重复实现也已经收口，当前重构不只是“把代码拆开”，而是开始真正删除重复路径和重复 schema 归属。

## 当前仍在推进的主线

### 主线 A：继续收缩交易命令共享 helper 与提交流程复杂度

当前剩余最明显的重构点仍在：

- [legacy_trade_service/trade_submit_flow.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/trade_submit_flow.py) 中的 `_submit_to_broker`
- [legacy_trade_service/trade_submit_flow.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/trade_submit_flow.py) 中的 `_persist_submitted_order`
- [legacy_trade_service/trade_commands.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/trade_commands.py) 中的 `_load_reference_price`
- [legacy_trade_service/trade_commands.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/trade_commands.py) 中的 `_audit_trade`

这些流程虽然已经完成 submit / cancel 分流，但公共 helper 与提交流程仍然偏厚，下一步更适合继续拆成：

- 券商执行网关与错误映射
- 提交后持久化 / 投影 / 补偿处理
- 参考价读取 / 降级回退
- 审计载荷组装与公共失败路径

### 主线 B：继续收缩旧实现承载目录

虽然当前旧导入已经改为显式根级兼容包，但 `backend-server/src` 仍然是主要旧实现承载目录。

后续方向应是：

- 不只“显式导入旧目录”
- 而是按服务域逐步把旧实现搬到真正的新包结构中
- 最终让兼容入口变薄，甚至可删除

当前这条主线在 trade 域里已经出现更明确的下一步目标：

- 收掉 `apps/trade-service/src/main.py` 与 `legacy_trade_service` 之间仍保留的账户列表/默认账户装配重复逻辑
- 继续把“应用层装配”和“交易运行时读取能力”边界拉清
- 评估 `legacy_trade_service/__init__.py` 的 eager import 是否改成更轻的包根入口

### 主线 C：推进前端平台壳层、视角、权限与菜单编排

产品蓝图已经明确要求：

- 多角色
- 角色化菜单
- 视角切换
- 模块级 / 终端级 / 角色级开关

当前已存在但尚未落地完成的实施主线：

- 平台壳层、视角模型与权限编排基础
- 核心工作台页面壳层刷新

对应文档：

- [2026-03-27-platform-shell-view-permission-foundation.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-27-platform-shell-view-permission-foundation.md)
- [2026-03-27-core-workspace-shell-refresh.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-27-core-workspace-shell-refresh.md)
- [2026-03-27-platform-blueprint-design.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/specs/2026-03-27-platform-blueprint-design.md)

## 下一阶段计划

### 第一优先级

- 继续拆 `legacy_trade_service/trade_submit_flow.py` 中仍偏厚的提交执行阶段。
- 把 `trade_commands.py` 中的“参考价加载”“审计写入”“错误细节组装”进一步抽成更清晰的共享支持单元。

### 第二优先级

- 继续把 `backend-server/src` 中仍在被显式兼容入口承接的旧实现按域迁出。
- 优先迁移高频依赖和高耦合模块，而不是做无差别搬迁。

### 第三优先级

- 开始执行前端平台壳层与角色权限基础计划。
- 先落视角、菜单、开关模型，再接入 `Header / Sidebar / MobileNav / MainLayout / Router`。

### 第四优先级

- 持续同步文档，保证蓝图、实施计划、架构总览和实际代码状态一致。

## 推荐阅读顺序

如果要快速理解最近重构，建议按下面顺序阅读：

1. [architecture-overview.md](/Users/lusd/Documents/New project/refactor-v2/docs/architecture-overview.md)
2. [2026-03-27-platform-blueprint-design.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/specs/2026-03-27-platform-blueprint-design.md)
3. [2026-03-27-legacy-compat-domain-split.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-27-legacy-compat-domain-split.md)
4. [2026-03-27-bootstrap-explicit-legacy-packages.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-27-bootstrap-explicit-legacy-packages.md)
5. [2026-03-27-trade-runtime-explicit-package.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-27-trade-runtime-explicit-package.md)
6. [2026-03-27-trade-runtime-internal-module-split.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-27-trade-runtime-internal-module-split.md)
7. [2026-03-28-trade-command-orchestration-split.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-28-trade-command-orchestration-split.md)
8. [2026-03-28-trade-command-hardening-and-split.md](/Users/lusd/Documents/New project/refactor-v2/docs/superpowers/plans/2026-03-28-trade-command-hardening-and-split.md)

## 文档维护说明

后续如果最近重构方向继续推进，这份文档应优先更新：

- 最近完成了什么
- 当前主线切到哪里
- 下一阶段优先级如何调整
- 新增了哪些对应的 `spec / plan`

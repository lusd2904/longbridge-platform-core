# 交易命令编排层拆分实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `legacy_trade_service/main.py` 中的下单/撤单编排流程拆到独立模块，并继续保持现有 FastAPI 路由、兼容导出和 HTTP 返回结构不变。

**Architecture:** 新建 `legacy_trade_service/trade_commands.py`，承接 `_submit_order`、`_cancel_order` 及它们直接依赖的编排辅助逻辑。`legacy_trade_service/main.py` 继续保留应用装配、鉴权、WebSocket 和健康检查，只通过显式导入接回交易命令入口。

**Tech Stack:** Python 3, FastAPI, pytest, py_compile

---

### Task 1: 先写失败中的架构测试

**Files:**
- Create: `tests/python/test_trade_command_orchestration_split.py`

- [x] **Step 1: 写失败测试，锁定新命令编排模块必须存在**

- [x] **Step 2: 写失败测试，锁定 `legacy_trade_service/main.py` 不再直接定义提交/撤单编排函数与辅助逻辑**

- [x] **Step 3: 运行新增测试并确认因为新模块尚不存在、`main.py` 仍承载相关职责而失败**

### Task 2: 建立交易命令编排模块并保持兼容导出

**Files:**
- Create: `legacy_trade_service/trade_commands.py`
- Modify: `legacy_trade_service/main.py`

- [x] **Step 1: 把 `_submit_order` / `_cancel_order` 及其直接依赖的编排辅助逻辑迁到 `trade_commands.py`**

- [x] **Step 2: 在 `trade_commands.py` 内继续拆出校验、参考价、风控、券商执行、持久化补偿等更小的 helper，降低单函数复杂度**

- [x] **Step 3: 让 `main.py` 只保留 FastAPI 装配与显式导入，继续对外暴露 `_submit_order` / `_cancel_order` 兼容符号**

### Task 3: 验证并回填结果

**Files:**
- Modify: `docs/superpowers/plans/2026-03-28-trade-command-orchestration-split.md`
- Modify: `docs/recent-refactor-direction-and-plan.md`
- Modify: `docs/architecture-overview.md`

- [x] **Step 1: 运行新增架构测试**

- [x] **Step 2: 运行 `python3 -m pytest tests/python -q`**

- [x] **Step 3: 运行 `python3 -m py_compile legacy_trade_service/*.py apps/trade-service/src/main.py`**

- [x] **Step 4: 回填本轮执行结果、当前边界和下一步建议**

## 2026-03-28 Red 阶段记录

- 已新增 `tests/python/test_trade_command_orchestration_split.py`
- 已确认 `python3 -m pytest tests/python/test_trade_command_orchestration_split.py -q` 失败，失败点符合预期：
  - `legacy_trade_service/trade_commands.py` 尚不存在
  - `legacy_trade_service/main.py` 仍直接定义提交/撤单编排逻辑
  - `main.py` 尚未显式从新命令模块导入兼容符号

## 2026-03-28 Green 阶段记录

- 已新增 `legacy_trade_service/trade_commands.py`
- 已把 `_submit_order`、`_cancel_order` 以及下列直接依赖的编排辅助逻辑迁出 `main.py`：
  - 参数校验
  - 参考价读取与降级回退
  - 风控校验
  - 券商下单执行
  - 提交后持久化与补偿撤单
  - 审计与返回载荷组装
- `legacy_trade_service/main.py` 当前通过显式导入继续暴露这些兼容符号，而不再自己承载交易命令编排实现
- 已通过定向兼容验证：
  - `python3 -m pytest tests/python/test_trade_command_orchestration_split.py -q`
  - `python3 -m pytest tests/python/test_trade_runtime_internal_module_split.py -q`
  - `python3 -m pytest tests/python/test_trade_runtime_explicit_package.py -q`

## 2026-03-28 执行结果回填

### 已完成

- 已新增 `legacy_trade_service/trade_commands.py`
- 已把提交/撤单主流程及其直接依赖 helper 从 `legacy_trade_service/main.py` 迁出到独立命令编排模块
- 已在 `trade_commands.py` 内把交易命令编排按以下阶段拆开：
  - 请求上下文装配
  - 提交参数校验
  - 参考价读取与快照降级
  - 风控闸门
  - 券商执行
  - 结果持久化与补偿撤单
  - 成功/失败响应组装
- `legacy_trade_service/main.py` 继续通过显式导入保留 `_submit_order`、`_cancel_order` 及相关兼容符号

### 结构结果

- [legacy_trade_service/main.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/main.py) 已从约 `1039` 行进一步收缩到约 `460` 行
- [legacy_trade_service/trade_commands.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/trade_commands.py) 当前承接交易命令编排实现，约 `862` 行
- `main.py` 当前主要保留：
  - FastAPI 装配
  - 鉴权与 WebSocket 入口
  - 健康检查与运行态查询

### 已验证

- `python3 -m pytest tests/python/test_trade_command_orchestration_split.py -q` 通过，当前 `3` 个测试全部通过
- `python3 -m pytest tests/python/test_trade_runtime_internal_module_split.py -q` 通过，当前 `3` 个测试全部通过
- `python3 -m pytest tests/python/test_trade_runtime_explicit_package.py -q` 通过，当前 `4` 个测试全部通过
- `python3 -m pytest tests/python -q` 通过，当前 `17` 个 Python 测试全部通过
- `python3 -m py_compile legacy_trade_service/*.py apps/trade-service/src/main.py` 通过

### 当前边界

- 本轮把“提交/撤单命令编排仍混在 `main.py`”的问题收掉了
- 交易运行时当前的最主要复杂度已从 `main.py` 收缩到 `trade_commands.py`
- 下一轮更适合继续拆 `trade_commands.py` 中仍偏厚的几个阶段：
  - 券商下单执行与错误映射
  - 提交后持久化 / 投影 / 补偿处理
  - 撤单执行与审计载荷组装

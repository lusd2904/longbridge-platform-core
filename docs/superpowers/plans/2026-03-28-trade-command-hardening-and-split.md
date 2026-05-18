# 交易命令编排加固与继续拆分实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐交易命令编排层的关键行为测试，修复缺失 `order_id` 时仍可能走成功路径的风险，再继续把 `trade_commands.py` 拆成更小模块。

**Architecture:** 先新增行为测试文件，锁定提交/撤单关键失败路径与 `order_id` 保护；再在保持 `legacy_trade_service.main` 与 `legacy_trade_service.trade_commands` 兼容导出不变的前提下，把提交流、撤单流与公共辅助逻辑迁到更小的内部模块。

**Tech Stack:** Python 3, FastAPI, pytest, py_compile

---

### Task 1: 先写失败中的行为测试

**Files:**
- Create: `tests/python/test_trade_command_behaviors.py`

- [x] **Step 1: 写失败测试，锁定缺失 `order_id` 时不能继续落投影或返回成功**

- [x] **Step 2: 写失败测试，覆盖提交/撤单关键失败路径**

- [x] **Step 3: 运行新增测试并确认因为保护逻辑缺失、行为测试尚未覆盖而失败**

### Task 2: 修复 `order_id` 保护并让行为测试通过

**Files:**
- Modify: `legacy_trade_service/trade_commands.py`

- [x] **Step 1: 在提交持久化阶段显式校验 `order_id`，缺失时走失败路径**

- [x] **Step 2: 用最小改动补齐行为分支需要的实现**

- [x] **Step 3: 运行新增测试并确认通过**

### Task 3: 继续拆分交易命令模块

**Files:**
- Create: `legacy_trade_service/trade_submit_flow.py`
- Create: `legacy_trade_service/trade_cancel_flow.py`
- Modify: `legacy_trade_service/trade_commands.py`

- [x] **Step 1: 把提交流程 helper 迁到 `trade_submit_flow.py`**

- [x] **Step 2: 把撤单流程 helper 迁到 `trade_cancel_flow.py`**

- [x] **Step 3: 让 `trade_commands.py` 退化为兼容导出层并保持旧导入可用**

### Task 4: 验证并回填结果

**Files:**
- Modify: `docs/superpowers/plans/2026-03-28-trade-command-hardening-and-split.md`
- Modify: `docs/recent-refactor-direction-and-plan.md`
- Modify: `docs/architecture-overview.md`

- [x] **Step 1: 运行新增行为测试**

- [x] **Step 2: 运行 `python3 -m pytest tests/python -q`**

- [x] **Step 3: 运行 `python3 -m py_compile legacy_trade_service/*.py apps/trade-service/src/main.py`**

- [x] **Step 4: 回填本轮执行结果与下一步建议**

## 2026-03-28 Red 阶段记录

- 已新增 `tests/python/test_trade_command_behaviors.py`
- 已补齐提交/撤单关键失败路径的行为测试，包括：
  - 参考价不可用
  - 风控拒绝
  - 券商下单异常
  - 投影写入失败后的补偿撤单
  - 券商撤单失败
- 已确认 `python3 -m pytest tests/python/test_trade_command_behaviors.py -q` 当前为 `1 failed, 5 passed`
- 唯一失败点符合预期：
  - `legacy_trade_service/trade_commands.py` 在缺失 `order_id` 时仍允许 `_persist_submitted_order` 继续落投影并返回成功路径

## 2026-03-28 Green 阶段记录（前两项）

- 已补上缺失 `order_id` 的显式保护：
  - 不再继续落投影
  - 不再误走成功响应
  - 不再对空 `order_id` 执行补偿撤单
- 已新增 `tests/python/test_trade_command_behaviors.py`，当前覆盖以下关键失败路径：
  - 缺失 `order_id`
  - 参考价不可用
  - 风控拒绝
  - 券商下单异常
  - 投影写入失败后的补偿撤单
  - 券商撤单失败
- 已通过定向验证：
  - `python3 -m pytest tests/python/test_trade_command_behaviors.py -q`
  - `python3 -m pytest tests/python/test_trade_command_orchestration_split.py -q`

## 2026-03-28 Red 阶段记录（第三项）

- 已新增 `tests/python/test_trade_command_module_split.py`
- 已确认 `python3 -m pytest tests/python/test_trade_command_module_split.py -q` 当前失败，失败点符合预期：
  - `legacy_trade_service/trade_submit_flow.py` 尚不存在
  - `legacy_trade_service/trade_cancel_flow.py` 尚不存在
  - `legacy_trade_service/trade_commands.py` 仍直接定义提交/撤单流程 helper 与入口函数

## 2026-03-28 Green 阶段记录（第三项）

- 已新增 `legacy_trade_service/trade_submit_flow.py`
- 已新增 `legacy_trade_service/trade_cancel_flow.py`
- 已把 submit/cancel 流程专属 helper 从 `trade_commands.py` 迁到对应新模块
- `trade_commands.py` 当前保留公共 helper 与兼容导出职责，通过显式导入继续暴露旧符号
- 已通过定向验证：
  - `python3 -m pytest tests/python/test_trade_command_module_split.py -q`
  - `python3 -m pytest tests/python/test_trade_command_behaviors.py -q`
  - `python3 -m pytest tests/python/test_trade_command_orchestration_split.py -q`

## 2026-03-28 执行结果回填

### 已完成

- 已新增 `tests/python/test_trade_command_behaviors.py`
- 已新增 `tests/python/test_trade_command_module_split.py`
- 已补上缺失 `order_id` 时的失败保护，避免继续落投影、返回成功响应或对空订单号做补偿撤单
- 已补齐提交/撤单关键失败路径的行为测试
- 已新增 `legacy_trade_service/trade_submit_flow.py`
- 已新增 `legacy_trade_service/trade_cancel_flow.py`
- 已把 submit/cancel 流程专属 helper 从 `trade_commands.py` 迁到对应新模块
- `trade_commands.py` 当前退化为“公共 helper + 兼容导出层”

### 结构结果

- [legacy_trade_service/trade_commands.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/trade_commands.py) 当前约 `295` 行
- [legacy_trade_service/trade_submit_flow.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/trade_submit_flow.py) 当前约 `539` 行
- [legacy_trade_service/trade_cancel_flow.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/trade_cancel_flow.py) 当前约 `139` 行
- [legacy_trade_service/main.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/main.py) 维持约 `460` 行，继续只承担 FastAPI 装配与入口职责

### 已验证

- `python3 -m pytest tests/python/test_trade_command_behaviors.py -q` 通过，当前 `6` 个测试全部通过
- `python3 -m pytest tests/python/test_trade_command_module_split.py -q` 通过，当前 `3` 个测试全部通过
- `python3 -m pytest tests/python/test_trade_command_orchestration_split.py -q` 通过，当前 `3` 个测试全部通过
- `python3 -m pytest tests/python -q` 通过，当前 `26` 个 Python 测试全部通过
- `python3 -m py_compile legacy_trade_service/*.py apps/trade-service/src/main.py` 通过

### 当前边界

- submit 复杂度已集中到 `trade_submit_flow.py`
- cancel 流程已独立到 `trade_cancel_flow.py`
- `trade_commands.py` 仍承载一部分共享 helper，下一步更适合继续把以下公共能力再拆薄：
  - 参考价读取与降级回退
  - 审计写入与失败载荷组装
  - 风控检查与错误细节组装

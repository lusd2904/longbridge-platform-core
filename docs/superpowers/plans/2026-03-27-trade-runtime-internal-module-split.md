# 交易运行时内部模块拆分实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `legacy_trade_service/main.py` 的 `outbox/saga` 与 `账户订单视图` 拆到独立模块，同时保持 `legacy_trade_service.main` 对外兼容导出不变。

**Architecture:** 新建 `models.py`、`outbox.py`、`account_views.py` 三个模块；`main.py` 保留鉴权、风控、交易流程与 FastAPI 装配，通过显式导入复用拆出的实现。

**Tech Stack:** Python 3, FastAPI, pytest, py_compile

---

### Task 1: 先写失败中的架构测试

**Files:**
- Create: `tests/python/test_trade_runtime_internal_module_split.py`

- [x] **Step 1: 写失败测试，锁定内部模块拆分目标**

- [x] **Step 2: 运行测试并确认因为新模块不存在、`main.py` 仍定义旧职责而失败**

### Task 2: 建立共享模型与运行时边界模块

**Files:**
- Create: `legacy_trade_service/models.py`
- Create: `legacy_trade_service/outbox.py`
- Create: `legacy_trade_service/account_views.py`

- [x] **Step 1: 提取共享模型到 `models.py`**

- [x] **Step 2: 提取 `schema / saga / outbox / projection` 到 `outbox.py`**

- [x] **Step 3: 提取账户、持仓、订单读取侧逻辑到 `account_views.py`**

### Task 3: 让 `main.py` 退化为薄入口并保持兼容导出

**Files:**
- Modify: `legacy_trade_service/main.py`

- [x] **Step 1: 删除 `main.py` 中已提取的顶层定义**

- [x] **Step 2: 通过显式导入接回兼容符号与运行时实例**

- [x] **Step 3: 确保路由、lifespan 与交易流程仍调用兼容入口**

### Task 4: 验证并回填结果

**Files:**
- Modify: `docs/superpowers/plans/2026-03-27-trade-runtime-internal-module-split.md`

- [x] **Step 1: 运行新增架构测试**

- [x] **Step 2: 运行 `python3 -m pytest tests/python`**

- [x] **Step 3: 运行 `python3 -m py_compile legacy_trade_service/*.py apps/trade-service/src/main.py`**

- [x] **Step 4: 做导入冒烟并回填执行结果**

## 2026-03-27 执行结果回填

### 已完成

- 已新增 `legacy_trade_service/models.py`
- 已新增 `legacy_trade_service/outbox.py`
- 已新增 `legacy_trade_service/account_views.py`
- 已把 `legacy_trade_service/main.py` 中的共享模型、`outbox/saga/projection`、账户订单视图逻辑迁出到独立模块
- `legacy_trade_service/main.py` 当前已退化为“鉴权 + 参考价/风控 + 下单撤单流程 + FastAPI 路由装配”主入口
- 已通过显式导入方式保留兼容符号，包括：
  - `outbox_relay`
  - `_ensure_trade_schema`
  - `_upsert_projection`
  - `_serialize_order`
  - `_list_orders`
  - `_build_account_summary_payload`
  - `_build_order_stream_event`

### 结构结果

- [legacy_trade_service/main.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/main.py) 从约 `2088` 行降到约 `1039` 行
- `OutboxRelay` 已不再定义于 `main.py`
- 账户、持仓、订单读取侧 helper 已不再定义于 `main.py`
- 新增架构测试已锁定“主文件不再承载这些职责”的边界

### 已验证

- `python3 -m pytest tests/python/test_trade_runtime_internal_module_split.py -q` 通过，当前 `3` 个测试全部通过
- `python3 -m pytest tests/python -q` 通过，当前 `14` 个 Python 测试全部通过
- `python3 -m py_compile legacy_trade_service/models.py legacy_trade_service/outbox.py legacy_trade_service/account_views.py legacy_trade_service/main.py apps/trade-service/src/main.py` 通过
- 导入冒烟通过：
  - `legacy_trade_service.main` 可导入
  - `legacy_trade_service.main.outbox_relay` 存在
  - `legacy_trade_service.main._ensure_trade_schema` 存在
  - `legacy_trade_service.main._serialize_order` 存在
  - `apps/trade-service/src/main.py` 对应模块可导入并暴露 `app`

### 当前边界

- 本轮只拆了共享模型、读取侧视图和 `outbox/saga/projection` 边界
- `_submit_order` 与 `_cancel_order` 仍然较长，是下一轮继续拆交易流程编排的主要目标

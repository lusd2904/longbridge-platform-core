# 交易服务重复 Helper 收口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收掉 `apps/trade-service/src/main.py` 中已经被 `legacy_trade_service` 复用层覆盖的重复 helper，并统一 `trade_order_projections` 的 schema ownership。

**Architecture:** `apps/trade-service/src/main.py` 改为优先复用 `legacy_trade_service.main` 已暴露的账户状态、订单读取和券商访问能力；`legacy_trade_service/outbox.py` 负责 `trade_order_projections` 表结构及索引补齐，避免应用入口重复建表。

**Tech Stack:** Python 3, FastAPI, pytest, py_compile

---

### Task 1: 先写失败中的架构测试

**Files:**
- Create: `tests/python/test_trade_service_duplicate_helper_consolidation.py`

- [x] **Step 1: 写失败测试，锁定 `apps/trade-service/src/main.py` 不再直接定义重复 helper**

- [x] **Step 2: 写失败测试，锁定 `trade_order_projections` schema 归属回到 `legacy_trade_service/outbox.py`**

- [x] **Step 3: 运行新增测试并确认当前重复实现尚未收口而失败**

### Task 2: 收口重复 helper 与 schema ownership

**Files:**
- Modify: `apps/trade-service/src/main.py`
- Modify: `legacy_trade_service/outbox.py`

- [x] **Step 1: 让 `apps/trade-service/src/main.py` 复用 `legacy_trade_service` 的账户状态与订单读取能力**

- [x] **Step 2: 删除本地重复 helper 与重复建表逻辑**

- [x] **Step 3: 在 `legacy_trade_service/outbox.py` 中补齐 `trade_order_projections` 缺失索引**

### Task 3: 验证并回填结果

**Files:**
- Modify: `docs/superpowers/plans/2026-03-28-trade-service-duplicate-helper-consolidation.md`
- Modify: `docs/recent-refactor-direction-and-plan.md`
- Modify: `docs/architecture-overview.md`

- [x] **Step 1: 运行新增 consolidation 测试**

- [x] **Step 2: 运行 `python3 -m pytest tests/python -q`**

- [x] **Step 3: 运行 `python3 -m py_compile legacy_trade_service/*.py apps/trade-service/src/main.py`**

- [x] **Step 4: 回填删除/收口结果与下一步建议**

## 2026-03-28 Red 阶段记录

- 已新增 `tests/python/test_trade_service_duplicate_helper_consolidation.py`
- 已确认 `python3 -m pytest tests/python/test_trade_service_duplicate_helper_consolidation.py -q` 当前失败，失败点符合预期：
  - `apps/trade-service/src/main.py` 仍直接定义 `_serialize_account_info`、`_serialize_position`、`_ensure_broker_connected`、`_ensure_order_projection_schema`、`_get_broker`
  - `trade_order_projections` 的 `CREATE TABLE` 语句仍保留在 `apps/trade-service/src/main.py`

## 2026-03-28 Green 阶段记录

- `apps/trade-service/src/main.py` 已切到 `legacy_trade_service._load_account_state(...)` 与 `legacy_trade_service._load_orders_for_account(...)`
- 已删除本地重复 helper：
  - `_serialize_account_info`
  - `_serialize_position`
  - `_ensure_broker_connected`
  - `_ensure_order_projection_schema`
  - `_get_broker`
- `trade_order_projections` 的 schema ownership 已收口到 `legacy_trade_service/outbox.py`
- `legacy_trade_service/outbox.py` 已补齐 `idx_user_status_updated (user_id, status, updated_at)`，避免应用入口重复建表也避免旧库缺索引
- 空的 `services/` 目录已删除

## 验证结果

- `python3 -m pytest tests/python/test_trade_service_duplicate_helper_consolidation.py -q`
  - `3 passed in 1.32s`
- `python3 -m pytest tests/python -q`
  - `29 passed in 5.69s`
- `python3 -m py_compile legacy_trade_service/*.py apps/trade-service/src/main.py`
  - 通过

## 本轮结果与后续建议

- `apps/trade-service/src/main.py` 不再维护第二套账户状态/订单读取实现，应用层开始真正复用 `legacy_trade_service` 的读取边界
- 订单投影回填路径顺手修正了动作字段来源，改为使用 `legacy_trade_service._load_orders_for_account(...)` 返回的 `side`
- 下一步更值得继续收口的是：
  - `apps/trade-service/src/main.py` 与 `legacy_trade_service` 之间仍重复存在的账户列表/默认账户装配逻辑
  - `legacy_trade_service/__init__.py` 的 eager import 副作用

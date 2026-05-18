# 交易运行时显式包化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `apps/trade-service` 对旧交易运行时的依赖从动态文件加载改为显式包导入，并删除 `services/trade-service/` 旧运行时目录。

**Architecture:** 新建 `legacy_trade_service/` 显式包，复制旧 `services/trade-service/src/main.py` 作为运行时承载；`apps/trade-service/src/main.py` 直接导入该包，不再使用 `importlib.util` 与路径字符串。

**Tech Stack:** Python 3, pytest, py_compile

---

### Task 1: 先写失败中的架构测试

**Files:**
- Create: `tests/python/test_trade_runtime_explicit_package.py`

- [x] **Step 1: 写失败测试，锁定“去动态加载 + 显式交易运行包”目标**

- [x] **Step 2: 运行测试并确认失败**

### Task 2: 建立显式交易运行包并切换导入

**Files:**
- Create: `legacy_trade_service/__init__.py`
- Create: `legacy_trade_service/main.py`
- Modify: `apps/trade-service/src/main.py`

- [x] **Step 1: 建立 `legacy_trade_service/` 包并复制旧运行时**

- [x] **Step 2: 调整复制后的 `legacy_trade_service/main.py` 路径与导入机制**

- [x] **Step 3: 切换 `apps/trade-service/src/main.py` 到显式包导入**

### Task 3: 删除旧运行时目录并做验证

**Files:**
- Delete: `services/trade-service/src/main.py`
- Delete: `services/trade-service/src/blockchain/blockchain_service.py`
- Delete: `services/trade-service/src/risk/auto_stop_loss.py`
- Delete: `services/trade-service/src/risk/risk_manager.py`
- Delete: `services/trade-service/src/utils/__init__.py`
- Delete: `services/trade-service/src/utils/json_logger.py`

- [x] **Step 1: 删除旧运行时目录中的遗留文件**

- [x] **Step 2: 运行架构测试**

- [x] **Step 3: 运行 `tests/python` 全量测试**

- [x] **Step 4: 执行 `py_compile` 与导入冒烟**

- [x] **Step 5: 回填本轮执行结果**

## 2026-03-27 执行结果回填

### 已完成

- 已新增 `legacy_trade_service/` 显式包：
  - `legacy_trade_service/__init__.py`
  - `legacy_trade_service/main.py`
- 已将旧 `services/trade-service/src/main.py` 复制为显式可导入包入口，并调整为依赖当前工程根目录与显式旧包入口
- 已移除 `apps/trade-service/src/main.py` 中的：
  - `importlib.util`
  - `LEGACY_TRADE_PATH`
  - `_load_legacy_trade_module()`
- `apps/trade-service/src/main.py` 已改为 `from legacy_trade_service import main as legacy_trade_service`
- 已删除 `services/trade-service/src/` 下遗留运行时文件

### 已验证

- `python3 -m pytest tests/python/test_trade_runtime_explicit_package.py` 先失败后通过，当前 `4` 个测试全部通过
- `python3 -m pytest tests/python` 通过，当前 `11` 个 Python 架构测试全部通过
- `python3 -m py_compile legacy_trade_service/__init__.py legacy_trade_service/main.py apps/trade-service/src/main.py` 通过，命令无输出且退出码为 `0`
- 导入冒烟通过：
  - `legacy_trade_service.main` 可导入
  - `legacy_trade_service.main.app` 存在
  - `legacy_trade_service.main.outbox_relay` 存在
  - `legacy_trade_service.main._serialize_order` 存在
  - `apps/trade-service/src/main.py` 对应模块可导入并暴露 `app`
- 代码目录全局扫描确认：
  - `apps / legacy_trade_service / shared / service_boundaries / scripts` 中已无 `services/trade-service`
  - 已无 `importlib.util`
  - 已无 `LEGACY_TRADE_PATH`
  - 已无 `_load_legacy_trade_module`

### 当前边界

- 本轮把“动态文件加载”改成了“显式包导入”，但还没有拆旧交易运行时内部的 Saga / Outbox 结构
- `legacy_trade_service/main.py` 仍承载较大体量旧实现，后续可继续按 `relay / order-serialization / legacy-app` 分段拆分

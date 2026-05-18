# 兼容边界分域拆分实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 拆掉 `shared.legacy_compat` 总适配器，把兼容边界按 `market / analysis / risk / trade` 四个服务域拆开，并完成服务入口切换。

**Architecture:** 在仓库根目录新增 `service_boundaries/` 分域包，使用 `_legacy_loader.py` 作为唯一旧模块加载入口。各服务只从自己的域边界模块导入能力，健康检查统一改为读取新的运行态状态模块，最后删除 `shared/legacy_compat.py`。

**Tech Stack:** Python 3, FastAPI, pytest, py_compile

---

### Task 1: 先写失败中的结构测试

**Files:**
- Create: `tests/python/test_legacy_boundary_split.py`

- [x] **Step 1: 写结构测试，锁定目标边界**

- [x] **Step 2: 运行测试并确认失败**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2
python3 -m pytest tests/python/test_legacy_boundary_split.py
```

Expected:

```text
FAILED tests/python/test_legacy_boundary_split.py
```

### Task 2: 建立新的分域边界包

**Files:**
- Create: `service_boundaries/__init__.py`
- Create: `service_boundaries/_legacy_loader.py`
- Create: `service_boundaries/runtime.py`
- Create: `service_boundaries/market_boundary.py`
- Create: `service_boundaries/analysis_boundary.py`
- Create: `service_boundaries/risk_boundary.py`
- Create: `service_boundaries/trade_boundary.py`

- [x] **Step 1: 实现统一旧模块加载器与运行态状态函数**

- [x] **Step 2: 分别实现 market / analysis / risk / trade 四个分域模块**

- [x] **Step 3: 运行结构测试，确认新包已满足存在性约束**

### Task 3: 切换各服务入口到新分域模块

**Files:**
- Modify: `apps/market-service/src/main.py`
- Modify: `apps/market-service/src/stock_pool_query.py`
- Modify: `apps/analysis-service/src/main.py`
- Modify: `apps/risk-service/src/main.py`
- Modify: `apps/risk-service/scheduler/src/main.py`
- Modify: `apps/trade-service/src/main.py`

- [x] **Step 1: 替换 market-service 的 import**

- [x] **Step 2: 替换 analysis-service 的 import**

- [x] **Step 3: 替换 risk-service 与 scheduler 的 import**

- [x] **Step 4: 替换 trade-service 的 import**

- [x] **Step 5: 让健康检查统一使用 `service_boundaries.runtime`**

### Task 4: 删除旧总适配器并做完整验证

**Files:**
- Delete: `shared/legacy_compat.py`

- [x] **Step 1: 删除旧总适配器**

- [x] **Step 2: 再次运行结构测试**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2
python3 -m pytest tests/python/test_legacy_boundary_split.py
```

Expected:

```text
4 passed
```

- [x] **Step 3: 对改动文件做语法校验**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2
python3 -m py_compile \
  service_boundaries/__init__.py \
  service_boundaries/_legacy_loader.py \
  service_boundaries/runtime.py \
  service_boundaries/market_boundary.py \
  service_boundaries/analysis_boundary.py \
  service_boundaries/risk_boundary.py \
  service_boundaries/trade_boundary.py \
  apps/market-service/src/main.py \
  apps/market-service/src/stock_pool_query.py \
  apps/analysis-service/src/main.py \
  apps/risk-service/src/main.py \
  apps/risk-service/scheduler/src/main.py \
  apps/trade-service/src/main.py
```

Expected:

```text
无输出，退出码为 0
```

- [x] **Step 4: 记录这轮拆分结果到后续文档**

## 2026-03-27 执行结果回填

### 已完成

- 已新增 `service_boundaries/` 分域包，包含 `_legacy_loader.py`、`runtime.py`、`market_boundary.py`、`analysis_boundary.py`、`risk_boundary.py`、`trade_boundary.py`
- 已完成 6 个服务入口的 import 切换：
  - `apps/market-service/src/main.py`
  - `apps/market-service/src/stock_pool_query.py`
  - `apps/analysis-service/src/main.py`
  - `apps/risk-service/src/main.py`
  - `apps/risk-service/scheduler/src/main.py`
  - `apps/trade-service/src/main.py`
- 已删除 `shared/legacy_compat.py`
- 健康检查中的 `legacyCompat` 字段已改由 `service_boundaries.runtime.legacy_boundary_status()` 提供

### 已验证

- `python3 -m pytest tests/python/test_legacy_boundary_split.py` 先失败后通过，当前 `4` 个结构测试全部通过
- `python3 -m py_compile ...` 对新增分域模块与改动后的服务入口做了语法校验，命令无输出且退出码为 `0`
- 新分域包做了 import 冒烟验证，`service_boundaries.market_boundary`、`analysis_boundary`、`risk_boundary`、`trade_boundary` 可正常加载
- 全局扫描确认应用代码中已无 `shared.legacy_compat` 残留引用；当前仅文档和结构测试文本中还保留该名称

### 当前边界

- 本轮只拆掉了“总兼容适配器”，尚未拆掉 `shared/bootstrap.py` 对 `backend-server/src` 的注入
- `apps/trade-service/src/main.py` 仍保留对 `services/trade-service/src/main.py` 的动态加载，这会作为下一轮拆分对象

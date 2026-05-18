# Bootstrap 去注入与显式旧包入口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 去掉 `shared/bootstrap.py` 对 `backend-server/src` 的 `sys.path` 注入，并建立根级显式旧包入口，让旧导入能力继续可用但不再依赖运行时魔法。

**Architecture:** 在仓库根目录建立 `api/config/core/database/market/social/strategy/utils` 8 个显式兼容包入口；`shared/bootstrap.py` 只保留环境装配和工程根路径注入。旧实现继续留在 `backend-server/src`，通过根级包的 `__path__` 与必要的旧 `__init__.py` 执行逻辑接出。

**Tech Stack:** Python 3, pytest, py_compile

---

### Task 1: 先写失败中的架构测试

**Files:**
- Create: `tests/python/test_bootstrap_explicit_legacy_packages.py`

- [x] **Step 1: 写失败测试，锁定“去注入 + 旧包仍可导入”目标**

- [x] **Step 2: 运行测试并确认失败**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2
python3 -m pytest tests/python/test_bootstrap_explicit_legacy_packages.py
```

Expected:

```text
FAILED tests/python/test_bootstrap_explicit_legacy_packages.py
```

### Task 2: 建立根级显式旧包入口

**Files:**
- Create: `api/__init__.py`
- Create: `config/__init__.py`
- Create: `core/__init__.py`
- Create: `database/__init__.py`
- Create: `market/__init__.py`
- Create: `social/__init__.py`
- Create: `strategy/__init__.py`
- Create: `utils/__init__.py`

- [x] **Step 1: 建立 8 个根级显式兼容包入口**

- [x] **Step 2: 对 `api` 包兼容旧 `__init__.py` 导出能力**

### Task 3: 调整 bootstrap 行为

**Files:**
- Modify: `shared/bootstrap.py`

- [x] **Step 1: 去掉 `backend-server/src` 的 `sys.path` 注入**

- [x] **Step 2: 在运行态状态里标记显式包入口模式**

### Task 4: 完整验证并回填结果

**Files:**
- Modify: `docs/superpowers/plans/2026-03-27-bootstrap-explicit-legacy-packages.md`

- [x] **Step 1: 再次运行 pytest 架构测试**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2
python3 -m pytest tests/python/test_bootstrap_explicit_legacy_packages.py
```

Expected:

```text
3 passed
```

- [x] **Step 2: 运行全部 Python 架构测试**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2
python3 -m pytest tests/python
```

Expected:

```text
7 passed
```

- [x] **Step 3: 做语法校验与导入冒烟**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2
python3 -m py_compile \
  shared/bootstrap.py \
  api/__init__.py \
  config/__init__.py \
  core/__init__.py \
  database/__init__.py \
  market/__init__.py \
  social/__init__.py \
  strategy/__init__.py \
  utils/__init__.py
```

Expected:

```text
无输出，退出码为 0
```

- [x] **Step 4: 回填本轮执行结果**

## 2026-03-27 执行结果回填

### 已完成

- 已新增 8 个根级显式旧包入口：
  - `api/__init__.py`
  - `config/__init__.py`
  - `core/__init__.py`
  - `database/__init__.py`
  - `market/__init__.py`
  - `social/__init__.py`
  - `strategy/__init__.py`
  - `utils/__init__.py`
- 已调整 `shared/bootstrap.py`：
  - 保留 `.env` 装配
  - 保留工程根目录注入
  - 删除 `backend-server/src` 的 `sys.path` 注入
- 已在 `runtime_profile()` 中新增 `legacyImportMode = "explicit-root-packages"`
- `api` 根级包已兼容执行旧 `backend-server/src/api/__init__.py`，保留 `create_app` 等旧包导出能力

### 已验证

- `python3 -m pytest tests/python/test_bootstrap_explicit_legacy_packages.py` 先失败后通过，当前 `3` 个测试全部通过
- `python3 -m pytest tests/python` 通过，当前 `7` 个 Python 架构测试全部通过
- `python3 -m py_compile shared/bootstrap.py api/__init__.py config/__init__.py core/__init__.py database/__init__.py market/__init__.py social/__init__.py strategy/__init__.py utils/__init__.py` 通过，命令无输出且退出码为 `0`
- 独立 Python 进程导入冒烟通过：
  - `bootstrap_runtime()` 执行后，`backend-server/src` 不在 `sys.path`
  - `api` 包仍暴露 `create_app`
  - `config.settings`
  - `utils.DbUtil`
  - `core.analysis.HistoricalMarketDataService`
  - `database.DbUtil`
  - `api.data_routes`
  - `service_boundaries.runtime`
  均可被解析

### 当前边界

- 本轮解决的是“旧顶层包的导入机制”，不是“旧实现已经迁移完成”
- `backend-server/src` 仍是旧实现承载目录，只是不再通过全局 `sys.path` 直接暴露
- 后续轮次已继续处理 `apps/trade-service/src/main.py` 的动态加载链；本段保留的是本轮完成时的边界说明

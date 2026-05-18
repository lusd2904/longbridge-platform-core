# Bootstrap 去注入与显式旧包入口设计

## 背景

当前工程虽然已经拆掉了 `shared.legacy_compat` 总适配器，但仍保留一个更底层的兼容机制：  
[shared/bootstrap.py](/Users/lusd/Documents/New%20project/refactor-v2/shared/bootstrap.py) 会在运行时把 [backend-server/src](/Users/lusd/Documents/New%20project/refactor-v2/backend-server/src) 注入 `sys.path`。

这带来三个问题：

- `apps/*`、`shared/*`、`scripts/*` 通过 `from core...`、`from utils...`、`from config...` 等导入旧模块时，依赖的是运行时路径魔法，而不是显式工程结构
- 旧导入入口不可见，后续很难判断哪些包还在依赖旧后端目录
- 下一步若要继续按域迁移 `core / utils / config / api`，当前机制会掩盖真实边界

## 目标

- 去掉 `shared/bootstrap.py` 对 `backend-server/src` 的全局 `sys.path` 注入
- 在仓库根目录建立显式旧包入口，替代隐式路径注入
- 保持当前应用层 `from core...`、`from utils...`、`from config...`、`from api...` 等导入基本不变
- 让 `service_boundaries/_legacy_loader.py` 与现有各服务仍可继续工作

## 非目标

- 本轮不迁移 `backend-server/src/core/*` 的实现到新目录
- 本轮不改写应用层大量旧 import 为新命名空间
- 本轮不处理 `apps/trade-service/src/main.py` 对 `services/trade-service/src/main.py` 的动态加载

## 设计原则

- 优先消除“运行时魔法”，再处理“实现搬迁”
- 兼容入口必须显式可见，位于工程根目录
- 旧模块实现仍留在原目录，避免把“去注入”与“整批迁移旧代码”绑在一起
- 兼容层本身尽量薄，只做路径桥接，不承载业务逻辑

## 目标结构

在仓库根目录新增 8 个显式包入口：

- `api/__init__.py`
- `config/__init__.py`
- `core/__init__.py`
- `database/__init__.py`
- `market/__init__.py`
- `social/__init__.py`
- `strategy/__init__.py`
- `utils/__init__.py`

对应关系：

- `api` -> `backend-server/src/api`
- `config` -> `backend-server/src/config`
- `core` -> `backend-server/src/core`
- `database` -> `backend-server/src/database`
- `market` -> `backend-server/src/market`
- `social` -> `backend-server/src/social`
- `strategy` -> `backend-server/src/strategy`
- `utils` -> `backend-server/src/utils`

## 包入口实现方式

### 通用模式

每个根级包都做两件事：

- 显式设置 `__path__` 指向对应旧目录
- 如果旧目录下存在 `__init__.py`，就在当前包上下文里执行它

这样可以同时满足两类需求：

- 对 `core.analysis.*`、`utils.DbUtil` 这类子模块导入，依赖 `__path__`
- 对 `api.create_app` 这类旧包初始化导出的属性，依赖执行旧 `__init__.py`

### 为什么不只挂 `__path__`

`config/utils/database` 的旧 `__init__.py` 为空，单纯挂路径也能工作。  
但 `api/__init__.py` 含有 `create_app()` 等真实逻辑；如果只挂路径，不执行旧初始化文件，`import api` 时就会丢失旧包导出能力。

## bootstrap 调整

[shared/bootstrap.py](/Users/lusd/Documents/New%20project/refactor-v2/shared/bootstrap.py) 本轮只保留两类职责：

- 加载 `.env` 与环境变量映射
- 保证工程根目录在 `sys.path`

不再把 `backend-server/src` 直接插入 `sys.path`。

同时，`runtime_profile()` 中保留 `legacyCompatPath` 字段，但新增可选状态信息，明确当前模式已从“路径注入”转为“显式包入口”。

## 验证策略

本轮采用“失败测试 -> 实现 -> 再验证”方式：

### 架构测试

新增 `pytest` 用例覆盖：

- 根级 8 个兼容包入口存在
- `bootstrap_runtime()` 执行后，`backend-server/src` 不在 `sys.path`
- 通过显式根级包仍能解析：
  - `config.settings`
  - `utils.DbUtil`
  - `core.analysis.HistoricalMarketDataService`
  - `database.DbUtil`
  - `api.data_routes`
- `api` 包仍暴露 `create_app`

### 语法与导入冒烟

- 对新增包入口和改动后的 `shared/bootstrap.py` 执行 `python3 -m py_compile`
- 用独立 Python 进程做导入冒烟，确认不依赖 `backend-server/src` 注入仍可解析关键旧包

## 风险

- 若某个顶层旧包未建立显式入口，移除 `sys.path` 注入后会在运行时报 `ModuleNotFoundError`
- 若 `api/__init__.py` 执行方式不对，`create_app`、蓝图注册等旧包初始化能力可能丢失
- 若显式包入口和旧目录路径映射错误，`service_boundaries` 将无法继续加载旧 `api.*` 模块

## 回退

- 如果这轮失败，可暂时恢复 `shared/bootstrap.py` 中对 `backend-server/src` 的注入
- 根级兼容包可保留，不影响恢复路径注入
- 由于不涉及数据库结构和 HTTP 接口变更，回退只需恢复 import 机制

## 本轮完成定义

满足以下条件即可视为完成：

- `shared/bootstrap.py` 不再注入 `backend-server/src`
- 根级显式旧包入口全部建立
- `pytest` 架构测试通过
- `py_compile` 通过
- 导入冒烟验证通过


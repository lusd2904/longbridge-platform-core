# 交易运行时显式包化设计

## 背景

当前 [apps/trade-service/src/main.py](/Users/lusd/Documents/New%20project/refactor-v2/apps/trade-service/src/main.py) 已不再依赖 `shared.legacy_compat`，也不再依赖 `bootstrap` 对 `backend-server/src` 的全局注入，但仍保留一条更隐蔽的旧链路：

- 通过 `importlib.util.spec_from_file_location(...)`
- 动态加载 [services/trade-service/src/main.py](/Users/lusd/Documents/New%20project/refactor-v2/services/trade-service/src/main.py)
- 再从动态模块上读取 `app`、`outbox_relay`、`_serialize_order`、`_ensure_trade_schema`、`_upsert_projection`

这条链路的问题不是“还能工作”，而是：

- 依赖文件路径字符串，不是显式工程结构
- 运行时动态导入难以静态分析和测试
- `services/trade-service/` 仍作为旧工程残留目录存在，阻碍继续清理

## 目标

- 去掉 `apps/trade-service/src/main.py` 中的 `importlib.util` 动态文件加载
- 把旧交易运行时变成显式根级可导入包
- 保持现有 `trade-service` 对外行为不变
- 让 `services/trade-service/` 从“运行依赖目录”变成“可删除旧残留”

## 非目标

- 本轮不重写旧交易运行时内部 Saga / Outbox 逻辑
- 本轮不把旧交易运行时代码拆成更细的域模块
- 本轮不改动前端或网关对交易服务的 HTTP 契约

## 设计原则

- 先把“动态文件加载”改成“显式包导入”
- 先稳定运行时边界，再继续拆旧实现内部结构
- 能复用的旧实现直接复制到新目录，不在本轮做业务逻辑改写

## 目标结构

新增显式包：

- `legacy_trade_service/__init__.py`
- `legacy_trade_service/main.py`

处理方式：

- 将旧 [services/trade-service/src/main.py](/Users/lusd/Documents/New%20project/refactor-v2/services/trade-service/src/main.py) 复制到 [legacy_trade_service/main.py](/Users/lusd/Documents/New%20project/refactor-v2/legacy_trade_service/main.py)
- 调整复制后的文件：
  - 重新计算 `ROOT_DIR`
  - 删除对 `backend-server/src` 的 `sys.path` 注入
  - 依赖前面已经建立的显式根级旧包入口

## 应用层改造

[apps/trade-service/src/main.py](/Users/lusd/Documents/New%20project/refactor-v2/apps/trade-service/src/main.py) 改为：

- 删除 `importlib.util`
- 删除 `LEGACY_TRADE_PATH`
- 删除 `_load_legacy_trade_module()`
- 改为 `from legacy_trade_service import main as legacy_trade_service`

这样 `apps/trade-service` 对旧运行时仍保持：

- `legacy_trade_service.app`
- `legacy_trade_service.outbox_relay`
- `legacy_trade_service._serialize_order`
- `legacy_trade_service._ensure_trade_schema`
- `legacy_trade_service._upsert_projection`

但依赖方式从“动态文件路径加载”变成“显式 Python 包导入”。

## 删除策略

当显式包导入切换完成后，删除：

- `services/trade-service/src/main.py`
- `services/trade-service/src/blockchain/blockchain_service.py`
- `services/trade-service/src/risk/auto_stop_loss.py`
- `services/trade-service/src/risk/risk_manager.py`
- `services/trade-service/src/utils/__init__.py`
- `services/trade-service/src/utils/json_logger.py`

原因：

- 当前代码运行时只依赖旧 `main.py`
- 复制后的显式包已经接管运行时职责
- 其余文件在当前工程内无运行时引用

## 验证策略

### 架构测试

新增 `pytest` 测试覆盖：

- `legacy_trade_service/` 包存在
- `apps/trade-service/src/main.py` 不再包含 `importlib.util`
- `apps/trade-service/src/main.py` 不再包含 `LEGACY_TRADE_PATH`
- `apps/trade-service/src/main.py` 改为显式导入 `legacy_trade_service`
- `services/trade-service/src/main.py` 已删除

### 语法与导入冒烟

- 对 `legacy_trade_service/main.py` 与 `apps/trade-service/src/main.py` 执行 `py_compile`
- 独立进程导入 `legacy_trade_service.main`，确认：
  - `app` 存在
  - `outbox_relay` 存在
  - `_serialize_order` 存在

## 风险

- 复制后若根路径计算错误，旧交易运行时可能找不到 `.env`
- 若删除旧目录前遗漏某处引用，会产生 `ModuleNotFoundError`
- 旧运行时文件较大，本轮主要风险在“路径调整”和“显式导入切换”，不是业务逻辑本身

## 回退

- 如果验证失败，可临时恢复 `apps/trade-service/src/main.py` 的动态加载逻辑
- 同时保留 `legacy_trade_service/` 不影响回退
- 因为不改协议和库表，回退不涉及数据修复

## 本轮完成定义

- `apps/trade-service/src/main.py` 不再动态加载文件路径
- `legacy_trade_service/` 显式包建立完成
- `services/trade-service/` 旧运行时目录删除
- 架构测试通过
- `py_compile` 与导入冒烟通过


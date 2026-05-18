# 交易运行时内部模块拆分设计

## 背景

上一轮已经把交易运行时从动态文件加载改成了显式包导入，但 [legacy_trade_service/main.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/main.py) 仍然承载了几乎全部旧实现。

当前结构问题已经很明确：

- `legacy_trade_service/main.py` 当前约 `2088` 行
- 其中 `OutboxRelay` 单类约 `468` 行
- `schema / saga / outbox / projection`、`账户与订单视图`、`HTTP API 装配` 仍混在同一文件

这意味着：

- 交易运行时虽已“包化”，但还没有真正形成模块边界
- 后续继续重构时，任何局部修改都需要加载整份大文件上下文
- 架构测试只能验证“显式包存在”，无法约束内部职责是否继续收敛

## 目标

- 把 `legacy_trade_service/main.py` 从 God File 继续拆成更清晰的内部模块
- 先拆出最稳定、最少影响 HTTP 契约的两组职责：
  - `outbox / saga / projection / schema`
  - `账户 / 持仓 / 订单视图与序列化`
- 让 `legacy_trade_service/main.py` 退化为“模型定义 + 交易流程 + FastAPI 路由装配”的薄入口
- 保持现有对外 API、`apps/trade-service` 外壳以及现有测试契约不变

## 非目标

- 本轮不重写 `_submit_order` 和 `_cancel_order` 的业务流程
- 本轮不调整 HTTP 路由路径、请求/响应字段或 WebSocket 协议
- 本轮不把旧 `backend-server/src` 依赖整体迁出

## 设计原则

- 优先按职责聚合，而不是按技术层切碎
- 先拆“低风险稳定逻辑”，保留兼容导出，避免影响上层外壳
- 新模块要能被独立导入、独立测试，而不是仅把代码移动后再回流耦合

## 目标结构

新增模块：

- `legacy_trade_service/models.py`
- `legacy_trade_service/outbox.py`
- `legacy_trade_service/account_views.py`

职责分配：

### `legacy_trade_service/models.py`

承载运行时共享的数据模型：

- `OrderSubmitRequest`
- `OrderCancelRequest`
- `AuthUser`

这样其他模块在需要类型时不必再反向依赖 `main.py`。

### `legacy_trade_service/outbox.py`

承载交易运行时中的持久化与消息职责：

- `_ensure_trade_schema`
- `_ensure_trade_outbox_columns`
- `_serialize_payload`
- `_serialize_datetime`
- `_insert_step`
- `_insert_outbox`
- `_create_saga`
- `_update_saga_status`
- `_record_saga_step`
- `_record_outbox_event`
- `_upsert_projection`
- `OutboxRelay`
- `outbox_relay`

这部分职责天然围绕库表、事件流和投影一致性，适合作为单独边界。

### `legacy_trade_service/account_views.py`

承载账户与订单读取侧能力：

- `_ensure_broker_connected`
- `_load_account_row`
- `_get_broker_for_user`
- `_account_display_name`
- `_serialize_order`
- `_load_orders_for_account`
- `_list_orders`
- `_serialize_account_summary`
- `_serialize_position`
- `_list_accounts`
- `_get_default_account`
- `_load_account_positions`
- `_load_account_state`
- `_build_account_summary_payload`
- `_build_order_stream_event`

这部分职责都属于“把券商 / DB 数据组装成前端与 WebSocket 需要的视图载荷”。

## `main.py` 调整策略

[legacy_trade_service/main.py](/Users/lusd/Documents/New project/refactor-v2/legacy_trade_service/main.py) 保留：

- 环境装配
- 共享服务导入
- JWT / 鉴权
- 行情参考价与风控逻辑
- `_submit_order`
- `_cancel_order`
- FastAPI 路由与 WebSocket 入口

同时从新模块显式导入并继续对外暴露兼容符号：

- `_ensure_trade_schema`
- `_upsert_projection`
- `_serialize_order`
- `_list_orders`
- `_build_account_summary_payload`
- `_build_order_stream_event`
- `OutboxRelay`
- `outbox_relay`

这样可以保证：

- `apps/trade-service/src/main.py` 无需感知内部拆分
- 现有架构测试与导入冒烟只需要小幅增强
- 后续可以继续围绕 `_submit_order` / `_cancel_order` 单独做下一轮流程拆分

## 验证策略

### 架构测试

新增测试锁定以下事实：

- `legacy_trade_service/models.py`
- `legacy_trade_service/outbox.py`
- `legacy_trade_service/account_views.py`

三类模块存在。

并验证：

- `legacy_trade_service/main.py` 顶层不再定义 `OutboxRelay`
- `legacy_trade_service/main.py` 顶层不再定义 `_ensure_trade_schema`
- `legacy_trade_service/main.py` 顶层不再定义 `_serialize_order`
- `legacy_trade_service/main.py` 顶层不再定义 `_list_orders`
- `legacy_trade_service/main.py` 顶层不再定义 `_build_account_summary_payload`
- `legacy_trade_service/main.py` 改为显式导入新模块

### 兼容导入冒烟

验证：

- `legacy_trade_service.outbox.OutboxRelay` 可导入
- `legacy_trade_service.account_views._serialize_order` 可导入
- `legacy_trade_service.main` 仍暴露 `outbox_relay`、`_ensure_trade_schema`、`_serialize_order`

### 全量回归

- `python3 -m pytest tests/python`
- `python3 -m py_compile legacy_trade_service/*.py apps/trade-service/src/main.py`

## 风险

- 若新模块之间形成反向导入，会把“拆分”变成“移动代码但耦合更深”
- 账户视图模块依赖券商管理器，若遗漏共享 helper，会造成运行时异常
- `outbox` 模块既负责 schema 又负责 relay，若导出不完整会影响生命周期钩子与运维接口

## 回退

- 若拆分后导入链不稳定，可把 `main.py` 恢复为单文件实现
- 新建模块即使保留，也不会影响现有库表或外部协议
- 因为本轮不改业务契约，回退只涉及 Python 文件恢复，不涉及数据迁移

## 本轮完成定义

- `legacy_trade_service/main.py` 不再顶层定义 outbox 与账户视图大块实现
- 新增 `models.py / outbox.py / account_views.py`
- `legacy_trade_service.main` 仍保持兼容导出
- 架构测试、全量 Python 测试、`py_compile`、导入冒烟全部通过

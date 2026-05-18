# Risk Service

职责：

- 风控总览
- 风险事件与保护单
- 消息通知中心
- 用户风险参数维护

迁移来源：

- `backend-server/src/api/data_routes.py`
- `backend-server/src/core/analysis/StrategyMonitorService.py`
- `web/src/views/RiskManagement.vue`
- `web/src/views/Notifications.vue`

当前状态：

- 已在 `8108` 落地
- 已复用 legacy 风控与通知 helper
- 已支持 risk/bootstrap、limits、events、保护单和 notifications 全套接口

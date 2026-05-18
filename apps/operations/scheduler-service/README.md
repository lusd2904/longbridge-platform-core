# Scheduler

职责：

- 定时任务编排
- 数据同步恢复
- 调度链路重试与回放
- 任务策略管理与手动触发
- 调度线程运行时状态输出

迁移来源：

- `backend-server/src/core/analysis/`
- `scripts/backend/`
- `backend-server/src/core/platform/SystemTaskService.py`
- `backend-server/src/api/platform_routes.py`

当前状态：

- 已在 `8107` 落地
- 已复用 legacy Scheduler 单例和系统任务策略表
- 已支持 bootstrap / runtime / tasks / jobs / manual run

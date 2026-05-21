# Operations Module

运维模块负责系统任务、调度运行态、任务策略和手动触发。它是市场回填、AI 扫描和 watchlist review 的调度入口。

## 服务

| 服务 | 端口 | 职责 |
| --- | --- | --- |
| `scheduler-service` | `8107` | 调度 runtime、任务策略、手动运行、执行记录 |

## 启动

```bash
cd apps/operations
./run.sh
```

单服务：

```bash
cd apps/operations/scheduler-service
./run.sh
```

## 已完成能力

- Scheduler runtime start/stop。
- 系统任务列表、任务策略更新、手动触发。
- 市场历史回填、市场 AI 扫描、watchlist pre-open/post-close review。
- 调度路径不再硬编码 `user_id=1`；系统任务按策略/env/有效用户解析执行用户。
- 启动脚本仍兼容探测旧 `apps/risk-service/scheduler` 路径；新代码和文档以 `apps/operations/scheduler-service` 为准。

## 验证

```bash
curl -fsS http://127.0.0.1:8107/health
.venv/bin/python -m pytest -q tests/python/test_agent_watchlist_scope.py
```

更多说明见 [Scheduler Service](./scheduler-service/README.md)。

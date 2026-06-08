# Continuous Smoke / Performance Gates

面向持续回归的低风险 gate 复用现有产物，不改业务页面实现。

## 入口

- `npm --prefix apps/frontend/web-portal run smoke:web:critical`
- `npm --prefix apps/frontend/web-portal run smoke:web:ai:retry`
- `npm --prefix apps/frontend/web-portal run perf:api:critical`
- `npm --prefix apps/frontend/web-portal run gate:continuous`

## 覆盖范围

- 关键页面 smoke: `market`、`trading`、`scheduler-center`、`history-coverage`
- AI 研判恢复流: 拦截 `410 expired` 后必须展示 `重新分析`，并能发起第二次分析请求
- Docker API/account probe: 登录、模拟账户、递延分析、缺失 job、风控 stoploss 合约
- 关键只读接口 benchmark: `market-stock-pool`、`market-insights`、`market-history-compare`、`market-history-coverage`、`risk-overview`、`orders-projection`、`positions-projection`
- 平台健康: `npm --prefix apps/frontend/web-portal run verify:platform`

## 产物与阈值

- Web smoke 产物: `apps/runtime/smoke/web-portal-smoke-report.json`
- API benchmark 产物: `.omx/artifacts/benchmarks/admin-benchmark.json`
- Gate 脚本: `scripts/continuous_regression_gate.cjs`

注意：`runtime/smoke/web-portal-smoke-report.json` 是早期遗留路径，可能是旧 schema 或过期数据；排查页面 smoke 时只看 `apps/runtime/smoke/web-portal-smoke-report.json`。

当前阈值偏保守，目标是尽早发现明显退化而不是做严格性能基线：

- 页面 `ready` 默认要求不超过 `6000ms`
- `market` / `trading` / `history-coverage` 页面 `total` 不超过 `20000ms`
- `scheduler-center` 页面 `total` 不超过 `15000ms`
- `market-history-coverage` 接口 `p95` 不超过 `20000ms`
- 其余关键接口 `p95` 不超过 `1000ms` 或 `2000ms`

## 推荐执行顺序

1. `npm --prefix apps/frontend/web-portal run smoke:web:critical`
2. `npm --prefix apps/frontend/web-portal run smoke:web:ai:retry`
3. `npm --prefix apps/frontend/web-portal run perf:api:critical`
4. `npm --prefix apps/frontend/web-portal run gate:continuous`

## Docker 日志门禁

Docker API/account probe 可复跑：

```bash
BASE_URL=http://127.0.0.1:3100 node scripts/verify_docker_api_probe.mjs
```

该脚本会通过 Web proxy 登录，确认只暴露一个 `paper` / `isPaper=true` 账户，验证递延分析 `202`、缺失 job `410 expired`、`memory+redis_snapshot` health，以及 stoploss 行的 `strategyId` 覆盖。报告写入 `tmp/evidence/docker-api-probe.json`，不会持久化 token。

最终 Docker 验证应在干净时间窗口内采集 compose 日志，并运行：

```bash
python scripts/check_platform_logs.py /tmp/refactor-v2-platform.log
```

该脚本将 `5xx`、`Traceback`、`ERROR`、原始超时、连接拒绝、推送轮询异常等视为硬失败。`499` 是浏览器或客户端切页取消请求，默认允许不超过 `5%`；超过阈值时应检查真实用户流量下是否存在慢接口或长连接响应延迟。

AI 研判页的桌面+移动端深度 smoke 使用：

```bash
npm --prefix apps/frontend/web-portal run smoke:web:ai:mobile
```

AI 研判页的 `410 expired` 恢复流使用：

```bash
BASE_URL=http://127.0.0.1:3100 npm --prefix apps/frontend/web-portal run smoke:web:ai:retry
```

该脚本会在真实 Docker Web 页面中拦截第一次 `analyze-positions` 请求为 `410 expired`，验证页面展示 `重新分析`，点击后再确认第二次请求被触发并完成。产物写入 `apps/runtime/smoke/ai-analysis-410-retry-report.json`。

## Redis 终态快照重启验证

递延分析任务的终态 Redis 快照可以用真实 Docker 重启流程验证：

```bash
BASE_URL=http://127.0.0.1:3100 DOCKER_BIN=/Users/lusd/.local/bin/docker node scripts/verify_deferred_redis_restart.mjs
```

该脚本会创建一个超过同步上限的 `analyze-positions` 任务，等待任务进入终态，重启 `redis` 和 `analysis-service`，然后再次读取同一个 job 状态。通过条件是重启前后都返回 `200`，且终态和 `jobId` 一致。产物写入 `tmp/evidence/deferred-redis-restart-report.json`。

# Continuous Smoke / Performance Gates

面向持续回归的低风险 gate 复用现有产物，不改业务页面实现。

## 入口

- `npm --prefix apps/frontend/web-portal run smoke:web:critical`
- `npm --prefix apps/frontend/web-portal run perf:api:critical`
- `npm --prefix apps/frontend/web-portal run gate:continuous`

## 覆盖范围

- 关键页面 smoke: `market`、`trading`、`scheduler-center`、`history-coverage`
- 关键只读接口 benchmark: `market-stock-pool`、`market-insights`、`market-history-compare`、`market-history-coverage`、`risk-overview`、`orders-projection`、`positions-projection`
- 平台健康: `npm --prefix apps/frontend/web-portal run verify:platform`

## 产物与阈值

- Web smoke 产物: `apps/runtime/smoke/web-portal-smoke-report.json`
- API benchmark 产物: `.omx/artifacts/benchmarks/admin-benchmark.json`
- Gate 脚本: `scripts/continuous_regression_gate.cjs`

当前阈值偏保守，目标是尽早发现明显退化而不是做严格性能基线：

- 页面 `ready` 默认要求不超过 `6000ms`
- `market` / `trading` / `history-coverage` 页面 `total` 不超过 `20000ms`
- `scheduler-center` 页面 `total` 不超过 `15000ms`
- `market-history-coverage` 接口 `p95` 不超过 `20000ms`
- 其余关键接口 `p95` 不超过 `1000ms` 或 `2000ms`

## 推荐执行顺序

1. `npm --prefix apps/frontend/web-portal run smoke:web:critical`
2. `npm --prefix apps/frontend/web-portal run perf:api:critical`
3. `npm --prefix apps/frontend/web-portal run gate:continuous`

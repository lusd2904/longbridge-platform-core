# Phase 1 Stack

当前 `refactor-v2` 第一批已经从“可运行骨架”推进到“可调用真实能力”阶段。

## 已落地服务

- `user-center` `8101`
- `market-service` `8102`
- `analysis-service` `8103`
- `strategy-service` `8104`
- `trade-service` `8105`
- `sentiment-service` `8106`
- `scheduler-service` `8107`
- `risk-service` `8108`
- `api-gateway` `5101`
- `web-portal` `3100`

## 启动方式

```bash
./refactor-v2/scripts/start_phase1_stack.sh
```

## 停止方式

```bash
./refactor-v2/scripts/stop_phase1_stack.sh
```

## 核心验证接口

```bash
curl http://127.0.0.1:5101/health
curl http://127.0.0.1:5101/api/v1/bootstrap
curl http://127.0.0.1:5101/api/v1/system/dependencies
curl http://127.0.0.1:3100
curl http://127.0.0.1:3100/svc/gateway/api/v1/system/catalog
curl -X POST http://127.0.0.1:8101/api/v1/auth/login
curl http://127.0.0.1:8101/api/v1/auth/info
curl http://127.0.0.1:8102/api/v1/market/bootstrap
curl http://127.0.0.1:8102/api/v1/market/history?symbol=AAPL.US
curl http://127.0.0.1:8102/api/v1/market/symbols/AAPL.US/overview
curl http://127.0.0.1:8103/api/v1/analysis/bootstrap
curl http://127.0.0.1:8103/api/v1/analysis/trend-scans
curl http://127.0.0.1:8103/api/v1/analysis/recommendations?profile=growth
curl http://127.0.0.1:8104/api/v1/strategy/bootstrap
curl http://127.0.0.1:8104/api/v1/strategy/strategies
curl http://127.0.0.1:8104/api/v1/strategy/monitor/summary
curl http://127.0.0.1:8105/api/v1/trade/bootstrap
curl http://127.0.0.1:8105/api/v1/trade/accounts
curl http://127.0.0.1:8105/api/v1/trade/accounts/default
curl http://127.0.0.1:8106/api/v1/sentiment/config
curl http://127.0.0.1:8107/api/v1/scheduler/bootstrap
curl http://127.0.0.1:8107/api/v1/scheduler/tasks
curl http://127.0.0.1:8107/api/v1/scheduler/jobs
curl http://127.0.0.1:8108/api/v1/risk/bootstrap
curl http://127.0.0.1:8108/api/v1/notifications/bootstrap
```

## 当前定位

这一批已经不只是占位边界：

- `user-center` 已复用老库和老权限体系，能跑登录、刷新令牌、当前用户 bootstrap。
- `user-center` 已补到个人资料、密码修改和用户配置接口，个人中心页已可用。
- `market-service` 已复用老行情与指标服务，能读历史行情、对比序列、标的总览和市场扫描。
- `analysis-service` 已复用老 AI 模型计划、趋势扫描和推荐结果。
- `strategy-service` 已复用老策略监控、回测和量化状态能力。
- `trade-service` 已复用 legacy 交易执行链，并补充账户、持仓和账户状态接口。
- `scheduler-service` 已复用老任务策略与各类 Scheduler，能查看线程状态、任务配置并手动触发。
- `risk-service` 已复用 legacy 风控与通知逻辑，能查看风险总览、保护单和通知中心。
- `web-portal` 已接入这批新服务，提供独立登录页和重构工作台。
- `sentiment-service` 继续保持占位，等你把抓数方案敲定后再接真实采集。

下一步就可以把前端入口逐步切到这批新服务，而不是继续在旧后端里叠功能。

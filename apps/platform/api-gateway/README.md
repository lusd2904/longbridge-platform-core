# API Gateway

API Gateway 是平台服务目录、依赖探测和观测入口，默认端口 `5101`。Web Portal 的 nginx/Vite 代理会把 `/svc/gateway/...` 转到这里；其他 `/svc/<service>/...` 路径由 Web Portal 直连对应服务。

## 做了什么

- 聚合平台 bootstrap、系统依赖、观测状态和服务目录。
- 提供统一服务目录：`user-center`、`market-service`、`analysis-service`、`strategy-service`、`trade-service`、`sentiment-service`、`scheduler-service`、`risk-service`、`agno-sidecar`。
- 对下游服务执行 health probe，返回依赖状态和观测摘要。
- Web Portal 的 `/dashboard` 服务状态墙会合并 `/api/v1/system/observability` 和 `/api/v1/system/catalog`，用这里的目录作为端口和 basePath 来源。
- Docker compose 内部使用服务名路由，例如 `http://sentiment-service:8106`。

## 主要接口

- `GET /health`
- `GET /api/v1/bootstrap`
- `GET /api/v1/system/dependencies`
- `GET /api/v1/system/observability`
- `GET /api/v1/system/catalog`

## 请求流向

| 场景 | 入口 | 说明 |
| --- | --- | --- |
| 业务 API | `http://127.0.0.1:3100/svc/<service>/...` | Web Portal nginx/Vite 代理直连对应服务 |
| Gateway 目录/观测 | `http://127.0.0.1:5101/api/v1/...` | 直接访问 API Gateway |
| 前端访问 Gateway | `http://127.0.0.1:3100/svc/gateway/...` | Web Portal 代理到 API Gateway |

## 使用

```bash
cd apps/platform/api-gateway
./run.sh
```

直接验证 Gateway：

```bash
curl -fsS http://127.0.0.1:5101/api/v1/bootstrap
curl -fsS http://127.0.0.1:5101/api/v1/system/catalog
```

## 依赖

- 下游服务 URL 由 `REF_USER_CENTER_URL`、`REF_MARKET_SERVICE_URL` 等环境变量提供。
- Docker compose 默认注入所有服务地址。

## 验证

```bash
curl -fsS http://127.0.0.1:5101/health
curl -fsS http://127.0.0.1:5101/api/v1/system/catalog
python3 scripts/check_platform_health.py
```

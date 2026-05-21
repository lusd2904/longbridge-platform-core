# Market Service

Market Service 是市场数据与股票池服务，默认端口 `8102`。

## 做了什么

- 市场 bootstrap、Longbridge 实时行情、标的详情。
- 用户级股票池、自选池和 scan target。
- 历史数据、历史覆盖度、历史回填、历史比较。
- 市场 insight、trend scan 读模型。
- Longbridge quote/snapshot/depth/trades/content/push runtime。
- 当前价、盘前、盘中、盘后、夜盘价只能来自 Longbridge quote/push；`quote-snapshots` 是历史/扫描回看接口，不作为当前价兜底。
- 历史 K 线已从 Longbridge SDK 直拉迁移到本地存储和 skshare/回填路径；`longbridge/candlesticks` 标记为迁移兼容。
- 目标用户读取路径移除 `user_id=1` fallback，按登录用户隔离。

## 主要接口

- `GET /health`
- `GET /api/v1/market/bootstrap`
- `GET /api/v1/market/history`
- `GET /api/v1/market/history/coverage`
- `POST /api/v1/market/history/backfill`
- `GET /api/v1/market/history/compare`
- `GET /api/v1/market/insights`
- `GET /api/v1/market/scans`
- `GET /api/v1/market/stock-pool`
- `GET /api/v1/market/watchlist`
- `POST /api/v1/market/watchlist`
- `PUT /api/v1/market/watchlist/{symbol}`
- `DELETE /api/v1/market/watchlist/{symbol}`
- `POST /api/v1/market/watchlist/scan-targets`
- `GET /api/v1/market/symbols/{symbol}/overview`
- `GET /api/v1/market/longbridge/bootstrap`
- `GET /api/v1/market/longbridge/quotes`
- `GET /api/v1/market/longbridge/snapshot`
- `GET /api/v1/market/longbridge/content/news`
- `GET /api/v1/market/longbridge/push/runtime`
- `WS /ws/market/longbridge/push`

## 使用

```bash
cd apps/market/market-service
./run.sh
```

示例：

```bash
curl -fsS http://127.0.0.1:8102/health
```

业务接口需要登录 token，推荐通过 Web Portal 代理调用：

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:3100/svc/market/api/v1/market/bootstrap
```

## 依赖

- MySQL：历史数据、股票池、自选池、扫描结果。
- Redis：部分快照/cache。
- skshare：历史/市场数据补充源。
- Longbridge CLI：实时 quote、content、push 辅助能力。

## 验证

```bash
curl -fsS http://127.0.0.1:8102/health
.venv/bin/python -m pytest -q \
  tests/python/test_market_live_cache.py \
  tests/python/test_skshare_history_and_sub2api.py
```

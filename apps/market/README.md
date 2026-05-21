# Market Module

市场模块负责行情、历史、股票池、自选池和舆情 read model。它给前端市场中心、标的详情、智能推荐、AI 研判和策略提供基础数据。

## 服务

| 服务 | 端口 | 职责 |
| --- | --- | --- |
| `market-service` | `8102` | 股票池、自选池、历史覆盖、Longbridge quote/push、市场扫描 |
| `sentiment-service` | `8106` | 市场舆情中心、GitHub 参考项目选型、量化只读情绪信号 |

## 启动

```bash
cd apps/market
./run.sh
```

单服务：

```bash
cd apps/market/market-service && ./run.sh
cd apps/market/sentiment-service && ./run.sh
```

注意：脚本模块启动仍受 `REF_SENTIMENT_ENABLED` 控制；Docker compose 默认包含 `sentiment-service`。

## 已完成能力

- 用户级股票池、自选池、watchlist scan target。
- 历史 K 线覆盖度、回填任务、历史比较。
- Longbridge quote、snapshot、depth、trades、content、push runtime。
- 历史 K 线读取禁用 Longbridge SDK 直拉，优先本地存储和 skshare/回填链路。
- 舆情中心 `/sentiment-center` 读取 `sentiment-service`，输出市场 mood、标的热度、风险词、GitHub 选型和量化只读信号。

## 验证

```bash
curl -fsS http://127.0.0.1:8102/health
curl -fsS http://127.0.0.1:8106/health

.venv/bin/python -m pytest -q \
  tests/python/test_sentiment_service_contract.py \
  tests/python/test_market_live_cache.py \
  tests/python/test_skshare_history_and_sub2api.py
```

更多说明见：

- [Market Service](./market-service/README.md)
- [Sentiment Service](./sentiment-service/README.md)

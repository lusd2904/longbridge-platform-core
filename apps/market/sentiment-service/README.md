# Sentiment Service

Sentiment Service 是市场舆情 read-model 服务，默认端口 `8106`。它已经不是占位服务：前端 `/sentiment-center` 页面和 Web Portal `/svc/sentiment/...` 代理都会读取这里。

## 做了什么

- 输出市场情绪概览、标的热度、风险词和量化可读字段。
- 把 GitHub 舆情/金融 NLP 项目作为参考 metadata 暴露给前端。
- 明确 GPL 项目只做架构和指标维度参考，不 vendor 代码；当前服务逻辑为自研实现。
- 复用 `LONGBRIDGE_AI_*` 和 `sub2api`，不新增舆情专属 AI key。
- 明确量化边界：只读证据，不下单、不撤单、不改仓、不触发策略执行。

## GitHub 参考项目

- `AI4Finance-Foundation/FinNLP`
- `ProsusAI/finBERT`
- `guijinSON/FinABSA`
- `AI4Finance-Foundation/FinGPT`
- `AlgoETS/AINewsTracker`
- `TickerPulse AI / BettaFish`：GPL family，仅做架构和采集指标维度参考，不复制或内嵌实现。

## 主要接口

- `GET /health`
- `GET /api/v1/sentiment/config`
- `GET /api/v1/sentiment/bootstrap`
- `GET /api/v1/sentiment/overview`
- `GET /api/v1/sentiment/symbol/{symbol}`
- `GET /api/v1/sentiment/universe`

## 使用

```bash
cd apps/market/sentiment-service
./run.sh
```

通过 Web Portal 代理：

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:3100/svc/sentiment/api/v1/sentiment/overview?market=US
```

前端页面：

```text
http://127.0.0.1:3100/sentiment-center
```

## 依赖

- MySQL：当前处于微服务重构过渡态，通过共享 read-model service 层只读访问 finance briefings、trend scans、recommendations、AI history、content cache。
- Analysis/market shared helpers：构建 market snapshot 和量化字段。
- `LONGBRIDGE_AI_*`：只作为配置契约和后续 AI synthesis 入口。

## 验证

```bash
curl -fsS http://127.0.0.1:8106/health
cd ../../.. && .venv/bin/python -m pytest -q tests/python/test_sentiment_service_contract.py
SMOKE_PAGE_FILTER=sentiment-center npm --prefix apps/frontend/web-portal run smoke:web
```

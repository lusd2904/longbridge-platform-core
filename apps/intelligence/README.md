# Intelligence Module

智能模块负责 AI 研判、趋势扫描、智能推荐、策略协调和 Agent 只读复核。

## 服务

| 服务 | 端口 | 职责 |
| --- | --- | --- |
| `analysis-service` | `8103` | AI 分析、趋势扫描、推荐、财经快讯、Agent run 治理 |
| `strategy-service` | `8104` | 策略 CRUD、回测、策略监控、自选池量化扫描和受控量化试跑 |
| `agno-sidecar` | `3200` | Agno-compatible watchlist review，只读调用 AI 网关 |

## 启动

```bash
cd apps/intelligence
./run.sh
```

单服务：

```bash
cd apps/intelligence/analysis-service && ./run.sh
cd apps/intelligence/strategy-service && ./run.sh
cd apps/intelligence/agno-sidecar && ./run.sh
```

Docker compose 会把 `analysis-service` 连接到 `agno-sidecar`：

```bash
REF_AGNO_SIDECAR_URL=http://agno-sidecar:3200
```

`agno-sidecar` 也可以在根目录用裸 Python 直启：

```bash
REF_AGNO_SIDECAR_PORT=3200 python3 apps/intelligence/agno-sidecar/src/main.py
```

## 已完成能力

- AI 模型计划、持仓/标的研判、趋势扫描和推荐。
- Finance briefing / news read model。
- Agent run 列表、详情和人工 override。
- Watchlist pre-open/post-close review，支持 idempotency 和 stranded run cleanup。
- Agno sidecar 复用 `LONGBRIDGE_AI_*` / `sub2api` / `gpt-5.5`，不执行交易。
- Strategy service 提供自选池量化策略扫描，默认只预览候选；显式执行时仍通过量化交易服务和长桥 CLI 安全边界。

## 验证

```bash
curl -fsS http://127.0.0.1:8103/health
curl -fsS http://127.0.0.1:8104/health
curl -fsS http://127.0.0.1:3200/health

.venv/bin/python -m pytest -q \
  tests/python/test_agent_watchlist_scope.py \
  tests/python/test_watchlist_quant_strategy.py
```

更多说明见：

- [Analysis Service](./analysis-service/README.md)
- [Strategy Service](./strategy-service/README.md)
- [Agno Sidecar](./agno-sidecar/README.md)

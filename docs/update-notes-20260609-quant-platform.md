# 2026-06-09 量化因子与平台验证更新说明

## 更新范围

本次更新围绕自选池量化策略、Docker 部署验证、Web 页面自动化测试和安全执行边界收口。

## 核心变更

- 自选池量化策略新增 `watchlist-alpha-factor-v1` 高维因子集，当前真实 Docker API 返回 `3060` 个 OHLCV 派生因子。
- 因子家族覆盖 `lag`、`trend`、`momentum`、`volatility`、`volume_flow`、`price_action`、`range_drawdown`、`liquidity`、`correlation`。
- 保留可解释评分桶，`scoreBreakdown.factorVersion` 仍为 `watchlist-factor-v2`。
- 自动交易执行链路强制纸账户/模拟账户校验，手动自选池量化执行会传入 `require_paper=True`。
- 下单 `strategy_context.factorInputs` 不再透传完整 `factorSet.values`，只保留 `factorSetVersion`、`factorCount`、`factorFamilies` 摘要。
- 历史列表接口默认压缩高维因子载荷，避免列表响应返回数十 MB 级 JSON。
- 顶层量化指标和 JSON 序列化增加 `NaN` / `Infinity` 防护，避免写出非标准 JSON。
- Docker Compose 默认使用本地 Redis 服务，并把 AI 网关默认地址调整为 `https://lucen.cc/v1`；API key 仍只通过环境变量注入，示例文件不包含密钥。
- 增加 Docker/API/UI/日志验证脚本，覆盖真实登录、纸账户状态、异步任务健康、历史 410 行为、页面 smoke 和对比度扫描。

## 验证结果

- `tests/python/test_watchlist_quant_strategy.py`：`34 passed`。
- `bash scripts/verify_platform.sh`：Python `291 passed`，Node `9 passed`，Web unit `118 passed`，live health contract OK。
- Docker 后端镜像已重建并强制重启，`docker compose ps` 显示全部服务 healthy。
- `node scripts/verify_docker_api_probe.mjs`：登录 `200`，账户数 `1`，`tradingMode=paper`，`isPaper=true`。
- 真实策略 API：`execute=false`，`factorCount=3060`，候选保留完整因子值。
- 真实历史 API：`historyHasFactorSet=false`，`historyFactorCount=3060`，单条 history metrics 约 `1806` bytes。
- `npm --prefix apps/frontend/web-portal run smoke:web:mobile`：桌面+移动 `60` 页，`errors=0`。
- `npm --prefix apps/frontend/web-portal run scan:contrast`：`30` 页，`contrastIssues=0`。
- Docker 日志稳定窗口复扫：`ERROR=0`，`Traceback=0`，`server_5xx=0`。
- NotebookLM 交叉检查结论：`GO`，无 must-fix blocker。

## 已知非阻塞项

- 本机 Gemini CLI 仍受 capacity/quota 限制，未能返回独立审查结果。
- Docker Hub 拉取上游 Node/nginx 镜像仍可能 EOF，本次保留增量 Dockerfile 作为本地部署兜底。
- 完整 `factorSet.values` 仍保留在候选和数据库历史明细中用于审计，后续需要观察历史表存储增长。

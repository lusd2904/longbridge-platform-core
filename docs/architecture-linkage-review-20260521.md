# Architecture Linkage Review 2026-05-21

## Scope

本轮评估覆盖：

- `docs/system-architecture-and-linkage.md`
- `README.md`
- `docs/service-map.yaml`
- `docs/phase1-stack.md`
- `docker-compose.yml`
- `apps/frontend/web-portal/nginx.conf`
- `apps/frontend/web-portal/vite.config.js`
- `apps/platform/api-gateway/src/main.py`
- `apps/intelligence/analysis-service/src/main.py`
- `apps/operations/scheduler-service/src/main.py`
- `apps/governance/risk-service/src/main.py`

## External Evaluation

### Antigravity CLI

- 结论：整体架构图与代码实际匹配；Web Portal 业务代理、API Gateway 目录/观测入口的区分正确。
- 采纳：
  - `web-portal` compose `depends_on` 补齐所有直连代理后端。
  - `api-gateway` service registry 增加 `agno-sidecar`，补齐观测盲区。
  - `docs/service-map.yaml` 将 `watchlist` 从 `user-center` 移到 `market-service`。
  - `docs/phase1-stack.md` 区分微服务直连调试与 Web Portal 代理验证。
- 追加完成：
  - `docs/service-map.yaml` 已补全 `service_edges` 机读边清单。
  - `tests/python/test_service_edges_contract.py` 已覆盖内部边、Gateway registry、Portal 代理和 compose 依赖一致性。
  - Web Portal Dashboard 已增加由 `api-gateway` observability + catalog 驱动的服务状态墙。
- 复核限制：
  - `agy --prompt-interactive` 已完成一次 Google OAuth 交互登录并返回 `OK`。
  - 新开 `agy --print` 长任务时仍偶发触发独立 OAuth 窗口；短窗口授权不稳定，因此本轮未把新增反重力复评作为阻塞门禁。
  - `scripts/antigravity_cli_adapter.py` 已补齐授权阻塞 fallback：Antigravity 非交互评估遇到 OAuth/auth/credential 类失败时自动切到本机 Gemini CLI `--prompt`。
  - 当前架构结论以已完成的 Antigravity 评估、NotebookLM 终评、Gemini fallback 可用性、Codex verifier 和本地测试共同作为依据。

### NotebookLM CLI

- 结论：`docs/system-architecture-and-linkage.md` 准确描述当前拓扑、微服务职责、安全边界和主要产品链路。
- 采纳：
  - `api-gateway` 注册 `agno-sidecar`。
  - `web-portal` compose 依赖补齐。
  - `docs/phase1-stack.md` 验证命令分组。
- 追加完成：
  - 完整 `service_edges` 机读清单已写入 `docs/service-map.yaml`。
  - 架构边验证已通过 Python contract test 固化。
  - Dashboard 服务状态墙已展示 Gateway catalog/observability 来源、端口、basePath 和告警数。
- 复核：
  - 首次复核混入旧 source，错误判断 `service-map.yaml` 未修正。
  - 重新上传 `LATEST` source 后复核结果为 PASS：Gateway、compose 依赖、watchlist 归属、验证命令分组、TODO 状态均已闭环。
  - 终问再次上传 `LATEST docs/architecture-overview.md final` 后结果为 PASS：架构图、微服务职责、串联方式和联动建议已闭环；随后按用户要求把 `service_edges`、架构边验证和状态墙从后续项转为已实现项。

### Codex Verifier Agent

- 结论：PASS。
- 复核点：
  - 架构文档覆盖整体拓扑、每个微服务边界、产品调用链和 TODO 状态。
  - README 与模块 README 的服务拆分、`/svc/*` 路由模型、`sentiment-service` 和 `agno-sidecar` 角色一致。
  - `api-gateway`、`docker-compose.yml`、生命周期脚本和测试均已落地 `agno-sidecar` 联动。
- 追加复核点：
  - `service_edges` 已作为架构图与代码联动的机读清单。
  - Web Portal 状态墙已由 Gateway catalog/observability 驱动，并覆盖 `sentiment-service` 与 `agno-sidecar`。

## Implemented TODOs

| Priority | TODO | Status |
| --- | --- | --- |
| P1 | `api-gateway` service catalog / dependency probes include `agno-sidecar` | completed |
| P1 | `web-portal` Docker `depends_on` includes every direct `/svc/*` backend | completed |
| P1 | `docs/service-map.yaml` moves watchlist responsibility to `market-service` | completed |
| P2 | `docs/phase1-stack.md` separates direct service checks from Portal proxy checks | completed |
| P2 | Add full machine-readable `service_edges` inventory | completed |
| P2 | Add full architecture-edge validation tests | completed |
| P2 | Add a Web Portal service status wall backed by `api-gateway` observability | completed |
| P2 | Add Gemini CLI fallback when Antigravity review is blocked by auth | completed |

## Final Linkage Assessment

- 当前联动合理：业务 API 走 Web Portal `/svc/*`，Gateway 做目录和观测，调度/AI/Agno 链路保持只读，交易写动作只通过 `trade-service`。
- 重构过渡期的共享数据库和 legacy helper 复用已经通过 README、架构图、`service_edges` 和边界测试显式标明。
- 如果后续要公网化或外部开放 API，应重新决策 Gateway 是否承担认证、限流、审计和业务转发；当前本地优先拓扑不把它当业务反向代理。

## Verification

- `git diff --check`
- `ruby -ryaml -e 'YAML.load_file("docs/service-map.yaml")'`
- `docker compose config`
- `.venv/bin/python -m py_compile apps/platform/api-gateway/src/main.py`
- `.venv/bin/python -m pytest -q tests/python/test_antigravity_cli_adapter.py`
- `.venv/bin/python -m pytest -q tests/python`
- `.venv/bin/python -m pytest -q tests/python/test_service_edges_contract.py tests/python/test_phase1_lifecycle_contract.py`
- `npm --prefix apps/frontend/web-portal run test:unit -- tests/unit/api-health.spec.js tests/unit/dashboard-shell.spec.js`
- `npm --prefix apps/frontend/web-portal run test:unit -- tests/unit/app-bootstrap.spec.js tests/unit/market-sentiment.spec.js tests/unit/finance-news-notifications.spec.js`
- `npm --prefix apps/frontend/web-portal run build`

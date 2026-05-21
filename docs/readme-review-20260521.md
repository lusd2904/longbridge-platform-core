# README Review 2026-05-21

## Scope

本轮重编覆盖根 README、`apps` 总览 README、各业务模块 README、各服务 README，并补齐 `apps/intelligence/agno-sidecar/README.md`。

## External Evaluation

### Antigravity CLI

- CLI: `python3 scripts/antigravity_cli_adapter.py run --mode print ...`
- 状态：已完成评估；adapter 现已支持 Antigravity OAuth/auth 阻塞时自动降级到本机 Gemini CLI `--prompt` 非交互评估。
- 采纳：
  - 修正 API Gateway 与 Web Portal `/svc/*` 代理职责边界。
  - 去除根 README 的机器硬编码路径，补充 `deploy_sub2api-network` 创建提示。
  - 补齐本机脚本中的 `agno-sidecar` 启动路径，并新增独立 `run.sh`。
  - 修正 sentiment README 的虚拟环境测试命令和数据库过渡态描述。
- 不采纳：
  - `5101/svc/...` 直连 Gateway 示例。当前 `api-gateway` 源码只提供 `/api/v1/*` 目录和观测接口，没有 `/svc` 转发能力。

### NotebookLM CLI

- Notebook: `refactor-v2 README 终评 20260521`
- 状态：已完成终评。
- 采纳：
  - 明确本机脚本默认跳过 `sentiment-service`，`/sentiment-center` 需 Docker compose 或 `REF_SENTIMENT_ENABLED=true`。
  - 在 API Gateway README 增加业务 API、Gateway 直连、前端代理 Gateway 的请求流向表。
  - 强化 GitHub GPL family 项目只做架构和采集指标维度参考，不复制实现。
  - 说明 `gpt-5.5` 是当前本地 AI gateway 的逻辑模型名，可通过 `LONGBRIDGE_AI_MODEL_SCAN_FINAL` 覆盖。
  - 补充 Web Portal 菜单/权限刷新后的 bootstrap 缓存更新场景。
  - 标明 scheduler 旧路径探测只是兼容过渡态，新路径为 `apps/operations/scheduler-service`。

## Agent Tasks

| 任务 | 智能体/评估器 | 状态 |
| --- | --- | --- |
| README 与运行态一致性只读复核 | Codex verifier agent | completed |
| README 外部工程审阅 | Antigravity CLI | completed |
| Antigravity 授权阻塞兜底 | Gemini CLI fallback | completed |
| README 文档一致性终评 | NotebookLM CLI | completed |
| 采纳项修补 | Codex executor | completed |
| 最终只读复审 | Codex verifier agent | completed |

## Completed Fixes

- 20 份 README 已按模块和服务重编。
- 根 README 已补充项目汇总、使用方式、核心配置、验证命令、外部评估工作流和安全边界。
- `api-gateway` 文档已从“业务代理”改为“服务目录、依赖探测和观测入口”。
- `sentiment-service` 文档已说明 GitHub 参考项目、AI 配置复用、只读量化边界和微服务重构过渡态。
- `agno-sidecar` 文档已说明 AI 降级语义、逻辑模型名和严格只读边界。
- 本机启动脚本已补齐 `agno-sidecar`，并新增 `apps/intelligence/agno-sidecar/run.sh`。
- 停止脚本和平台健康检查已补齐 `agno-sidecar`，避免只启动不停止、只运行不验证。
- `.env.example` 已补齐 `REF_AGNO_SIDECAR_PORT=3200`。
- API Gateway service catalog 已去除舆情占位描述。
- `scripts/antigravity_cli_adapter.py` 已补齐 Gemini fallback：Antigravity 非交互评估遇到 OAuth/auth/credential 类失败时自动改用本机 Gemini CLI。

## Verification

- `git diff --check`
- `.venv/bin/python -m pytest -q tests/python/test_antigravity_cli_adapter.py`
- `.venv/bin/python -m py_compile apps/intelligence/agno-sidecar/src/main.py apps/platform/api-gateway/src/main.py`
- `.venv/bin/python -m pytest -q tests/python/test_phase1_lifecycle_contract.py tests/python/test_service_direct_entrypoints.py tests/python/test_service_category_layout.py tests/python/test_module_standalone_entrypoints.py tests/python/test_agent_watchlist_scope.py`
- `.venv/bin/python -m pytest -q tests/python/test_service_direct_entrypoints.py tests/python/test_service_category_layout.py tests/python/test_sentiment_service_contract.py tests/python/test_agent_watchlist_scope.py`

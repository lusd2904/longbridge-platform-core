# 架构概览

更完整的运行拓扑、微服务职责、产品调用链和联动评估见 [system-architecture-and-linkage.md](./system-architecture-and-linkage.md)。

机读拓扑以 [service-map.yaml](./service-map.yaml) 为准，其中 `service_edges` 已覆盖 Web Portal `/svc/*` 代理、API Gateway health probes、scheduler -> analysis -> agno-sidecar -> AI gateway 复核链路，以及 broker / 行情外部依赖。`tests/python/test_service_edges_contract.py` 会验证这些边与 Gateway registry、nginx/Vite 代理和 Docker compose 依赖保持一致。

## 服务列表

根据 `docs/service-map.yaml` 和 `docs/phase1-stack.md`，当前系统包含以下服务：

| 服务名称 | 端口 | 状态 | 主要职责 |
|----------|------|------|----------|
| web-portal | 3100 | 已运行 | 统一用户界面、路由编排、图表和分析视图 |
| api-gateway | 5101 | 已运行 | 服务目录、依赖探测、观测聚合 |
| user-center | 8101 | 已运行 | 登录、个人资料、监单列表、用户偏好 |
| market-service | 8102 | 已运行 | 市场宇宙、价格历史、指标快照、市场扫描数据集 |
| analysis-service | 8103 | 已运行 | AI分析、趋势批量扫描、结论生成 |
| strategy-service | 8104 | 已运行 | 策略配置、风险规则协调、回测编排 |
| trade-service | 8105 | 已运行 | 订单执行、持仓查询、订单投射 |
| sentiment-service | 8106 | 已落地 | 舆情 read model、GitHub 参考项目、只读量化情绪信号 |
| scheduler-service | 8107 | 已落地 | 线程状态/任务策略/执行记录 |
| risk-service | 8108 | 已落地 | 风控总览/保护单/通知中心 |
| agno-sidecar | 3200 | 已落地 | Agno-compatible watchlist review，只读调用 AI 网关 |

## 服务交互关系

```mermaid
graph TD
    %% 前端层
    WP[Web Portal<br/>3100] --> UC[User Center<br/>8101]
    WP --> MS[Market Service<br/>8102]
    WP --> AS[Analysis Service<br/>8103]
    WP --> SS[Strategy Service<br/>8104]
    WP --> TS[Trade Service<br/>8105]
    WP --> SNS[Sentiment Service<br/>8106]
    WP --> SCH[Scheduler Service<br/>8107]
    WP --> RS[Risk Service<br/>8108]
    WP --> AG[API Gateway<br/>5101]
    
    %% API Gateway 只做目录和观测，不转发业务 API
    AG -.health/catalog.-> UC
    AG -.health/catalog.-> MS
    AG -.health/catalog.-> AS
    AG -.health/catalog.-> SS
    AG -.health/catalog.-> TS
    AG -.health/catalog.-> SNS
    AG -.health/catalog.-> SCH
    AG -.health/catalog.-> RS
    AG -.health/catalog.-> AGNO
    
    %% 服务间交互（部分关键交互）
    MS -->|提供市场数据| AS
    SNS -. "提供只读舆情证据" .-> AS
    AS -->|生成分析结果| SS
    SCH -->|调度分析任务| AS
    SCH -->|调度市场扫描| MS
    SCH -->|调度策略监控| SS
    AS --> AGNO[Agno Sidecar<br/>3200]
    AS -. "AI 复核建议" .-> HR[人工复核]
    SS -. "策略/回测建议" .-> HR
    SNS -. "舆情证据" .-> HR
    HR -->|显式交易动作| WP
    WP -->|/svc/trade| TS
    TS -->|查询行情/持仓投射| MS
    UC -->|用户认证/权限| WP
    RS -. "风控通知/保护单" .-> WP
    
    %% 样式定义
    classDef live fill:#d4edda,stroke:#155724;
    classDef gateway fill:#d1ecf1,stroke:#0c5460;
    classDef frontend fill:#fff3cd,stroke:#856404;
    classDef human fill:#fce4ec,stroke:#880e4f;
    
    class WP frontend;
    class AG gateway;
    class UC,MS,AS,SS,TS,SNS,SCH,RS,AGNO live;
    class HR human;
```

## 最近重构方向与计划

最近一轮重构重点不在新增业务功能，而在先清理运行时隐式依赖和交易遗留单体结构，当前主线包括：

- 拆掉总兼容适配器，改为 `service_boundaries/` 分域边界
- 去掉 `shared/bootstrap.py` 对旧目录的全局 `sys.path` 注入，改为显式根级兼容包入口
- 把 `trade-service` 从动态文件加载切到显式 `legacy_trade_service/` 包
- 继续把 `legacy_trade_service/main.py` 往共享模型、`outbox/saga`、账户订单视图三个方向拆薄
- 已把提交/撤单命令编排从 `legacy_trade_service/main.py` 迁到 `legacy_trade_service/trade_commands.py`
- 已进一步把提交流程与撤单流程分流到 `legacy_trade_service/trade_submit_flow.py` 与 `legacy_trade_service/trade_cancel_flow.py`
- `legacy_trade_service/trade_commands.py` 当前退化为公共 helper 与兼容导出层
- `apps/trade-service/src/main.py` 已开始直接复用 `legacy_trade_service/account_views.py` 提供的账户状态与订单读取能力
- `trade_order_projections` 的 schema 与索引补齐当前统一归属在 `legacy_trade_service/outbox.py`
- 为后续前端平台壳层、视角、角色权限和菜单编排打基础

集中汇总文档：

- [recent-refactor-direction-and-plan.md](./recent-refactor-direction-and-plan.md)

当前直接相关的实施计划：

- [2026-03-27-legacy-compat-domain-split.md](./superpowers/plans/2026-03-27-legacy-compat-domain-split.md)
- [2026-03-27-bootstrap-explicit-legacy-packages.md](./superpowers/plans/2026-03-27-bootstrap-explicit-legacy-packages.md)
- [2026-03-27-trade-runtime-explicit-package.md](./superpowers/plans/2026-03-27-trade-runtime-explicit-package.md)
- [2026-03-27-trade-runtime-internal-module-split.md](./superpowers/plans/2026-03-27-trade-runtime-internal-module-split.md)
- [2026-03-28-trade-command-orchestration-split.md](./superpowers/plans/2026-03-28-trade-command-orchestration-split.md)
- [2026-03-28-trade-command-hardening-and-split.md](./superpowers/plans/2026-03-28-trade-command-hardening-and-split.md)
- [2026-03-28-trade-service-duplicate-helper-consolidation.md](./superpowers/plans/2026-03-28-trade-service-duplicate-helper-consolidation.md)
- [2026-03-27-platform-shell-view-permission-foundation.md](./superpowers/plans/2026-03-27-platform-shell-view-permission-foundation.md)
- [2026-03-27-core-workspace-shell-refresh.md](./superpowers/plans/2026-03-27-core-workspace-shell-refresh.md)

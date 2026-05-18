# Apps

这里存放重构版的独立业务模块。

当前目录已经切到“按类别分组”的结构，旧的平铺路径继续保留为兼容链接。

分类布局：

- `frontend/`
  - `web-portal/`
- `platform/`
  - `api-gateway/`
  - `user-center/`
- `market/`
  - `market-service/`
  - `sentiment-service/`
- `intelligence/`
  - `analysis-service/`
  - `strategy-service/`
- `trading/`
  - `trade-service/`
- `governance/`
  - `risk-service/`
- `operations/`
  - `scheduler-service/`

模块启动：

- `apps/frontend/run.sh`
- `apps/platform/run.sh`
- `apps/market/run.sh`
- `apps/intelligence/run.sh`
- `apps/trading/run.sh`
- `apps/governance/run.sh`
- `apps/operations/run.sh`

服务直启：

- 各实际服务目录也都补了自己的 `run.sh`
- 例如：
  - `apps/platform/api-gateway/run.sh`
  - `apps/market/market-service/run.sh`
  - `apps/trading/trade-service/run.sh`

兼容入口：

- `apps/web-portal`
- `apps/api-gateway`
- `apps/user-center`
- `apps/market-service`
- `apps/sentiment-service`
- `apps/analysis-service`
- `apps/strategy-service`
- `apps/trade-service`
- `apps/risk-service`

# Frontend Module

前端模块提供统一交易和研究工作台，目前包含一个主应用：`web-portal`。

## 包含内容

- `web-portal`：Vue 3 + Element Plus + ECharts 工作台。
- `web-portal/android`、`web-portal/ios`：Capacitor 原生壳。
- `web-portal/desktop`：Electron 桌面端入口。
- `web-portal/scripts`：smoke、移动端、构建和调试脚本。

## 已完成能力

- 登录、平台 bootstrap、动态菜单和角色能力读取。
- 市场、股票池、自选池、AI 交易扫描记录、标的详情、历史 K 线。
- 智能推荐、市场舆情、财经快讯、AI 研判。
- 交易台、持仓、订单、券商连接。
- 策略、回测、风控、通知、任务中心、系统设置、用户管理。
- 旧登录态启动时自动刷新平台菜单，避免新增页面被本地 `platform_bootstrap` 缓存隐藏。

## 启动

```bash
cd apps/frontend
./run.sh
```

或进入主应用目录：

```bash
cd apps/frontend/web-portal
npm install
npm run dev
```

默认访问：`http://127.0.0.1:3100`

## 验证

```bash
npm --prefix apps/frontend/web-portal run test:unit -- \
  tests/unit/app-bootstrap.spec.js \
  tests/unit/market-sentiment.spec.js \
  tests/unit/watchlist-ai-trade-runs.spec.js \
  tests/unit/finance-news-notifications.spec.js

npm --prefix apps/frontend/web-portal run build
SMOKE_PAGE_FILTER=sentiment-center,notifications npm --prefix apps/frontend/web-portal run smoke:web
```

更多说明见 [Web Portal README](./web-portal/README.md)。

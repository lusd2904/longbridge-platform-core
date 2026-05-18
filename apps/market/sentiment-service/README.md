# Sentiment Service

当前状态：占位服务

## 本轮目标

- 先预留独立模块目录
- 先预留独立端口 `8106`
- 先固定接口前缀 `/api/v1/sentiment`
- 暂不接入真实外部抓数和情绪打分

## 预留接口

- `GET /health`
- `GET /api/v1/sentiment/config`
- `POST /api/v1/sentiment/collect`
- `POST /api/v1/sentiment/analyze`
- `GET /api/v1/sentiment/symbol/{symbol}`

## 后续接入

等你把舆情数据源和抓数方式确认后，直接在当前目录继续补：

- 抓取器
- 事件清洗
- 情绪评分
- 重要事件抽取
- 标的情绪汇总

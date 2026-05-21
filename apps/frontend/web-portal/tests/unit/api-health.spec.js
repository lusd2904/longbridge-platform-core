import { beforeEach, describe, expect, it, vi } from 'vitest'

const getMock = vi.fn()

vi.mock('../../src/utils/requestPure.js', () => ({
  request: {
    get: getMock
  }
}))

describe('getApiHealth', () => {
  beforeEach(() => {
    getMock.mockReset()
  })

  it('prefers gateway observability payload over direct service probes', async () => {
    getMock.mockImplementation(async (url) => {
      if (url === '/svc/gateway/api/v1/system/observability') {
        return {
          success: true,
          data: {
            service: 'api-gateway',
            status: 'degraded',
            environment: 'staging',
            deps: {
              'user-center': { status: 'healthy', service: 'user-center', version: '0.2.0', observed: { port: 8101 } },
              'market-service': { status: 'healthy', service: 'market-service', version: '0.2.0', observed: { port: 8102 } },
              'analysis-service': { status: 'healthy', service: 'analysis-service', version: '0.2.0', observed: { port: 8103 } },
              'strategy-service': { status: 'healthy', service: 'strategy-service', version: '0.2.0', observed: { port: 8104 } },
              'trade-service': { status: 'degraded', service: 'trade-service', version: '0.2.0', observed: { port: 8105 } },
              'sentiment-service': { status: 'healthy', service: 'sentiment-service', version: '0.2.0', observed: { port: 8106 } },
              'scheduler-service': { status: 'healthy', service: 'scheduler-service', version: '0.2.0', observed: { port: 8107 } },
              'risk-service': { status: 'healthy', service: 'risk-service', version: '0.2.0', observed: { port: 8108 } },
              'agno-sidecar': { status: 'healthy', service: 'agno-sidecar', version: '0.2.0', observed: { port: 3200 } }
            },
            alerts: [
              { service: 'trade-service', code: 'trade-outbox-backlog', level: 'warning', message: '交易积压' }
            ]
          }
        }
      }
      if (url === '/svc/gateway/api/v1/system/catalog') {
        return {
          success: true,
          data: {
            gateway: { port: 5101, baseUrl: 'http://127.0.0.1:5101' },
            services: {
              'user-center': { port: 8101, basePath: '/api/v1/auth', description: '登录、会话和用户引导' },
              'market-service': { port: 8102, basePath: '/api/v1/market', description: '行情、指标、市场扫描和标的总览' },
              'analysis-service': { port: 8103, basePath: '/api/v1/analysis', description: '模型计划、趋势扫描和智能推荐' },
              'strategy-service': { port: 8104, basePath: '/api/v1/strategy', description: '策略规则、回测、监控告警和量化状态' },
              'trade-service': { port: 8105, basePath: '/api/v1/trade', description: '券商账户、订单、持仓和人工交易执行' },
              'sentiment-service': { port: 8106, basePath: '/api/v1/sentiment', description: '舆情 read model' },
              'scheduler-service': { port: 8107, basePath: '/api/v1/scheduler', description: '调度线程、任务策略、执行记录和手动触发' },
              'risk-service': { port: 8108, basePath: '/api/v1/risk', description: '风控总览、保护单和通知中心' },
              'agno-sidecar': { port: 3200, basePath: '/api/v1/agent/watchlist-review', description: 'Agno-compatible watchlist review sidecar' }
            }
          }
        }
      }
      throw new Error(`unexpected url ${url}`)
    })

    const { getApiHealth } = await import('../../src/utils/api.js')
    const result = await getApiHealth()

    expect(getMock).toHaveBeenCalledTimes(2)
    expect(result.data.status).toBe('degraded')
    expect(result.data.environment).toBe('staging')
    expect(result.data.source).toBe('api-gateway-observability')
    expect(result.data.catalog_source).toBe('api-gateway-catalog')
    expect(result.data.services.trade_service.alert_count).toBe(1)
    expect(result.data.services.market_service.port).toBe(8102)
    expect(result.data.services.sentiment_service.basePath).toBe('/api/v1/sentiment')
    expect(result.data.services.agno_sidecar.port).toBe(3200)
  })
})

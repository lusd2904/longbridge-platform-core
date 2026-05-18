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
              'scheduler-service': { status: 'healthy', service: 'scheduler-service', version: '0.2.0', observed: { port: 8107 } },
              'risk-service': { status: 'healthy', service: 'risk-service', version: '0.2.0', observed: { port: 8108 } }
            },
            alerts: [
              { service: 'trade-service', code: 'trade-outbox-backlog', level: 'warning', message: '交易积压' }
            ]
          }
        }
      }
      throw new Error(`unexpected url ${url}`)
    })

    const { getApiHealth } = await import('../../src/utils/api.js')
    const result = await getApiHealth()

    expect(getMock).toHaveBeenCalledTimes(1)
    expect(result.data.status).toBe('degraded')
    expect(result.data.environment).toBe('staging')
    expect(result.data.services.trade_service.alert_count).toBe(1)
    expect(result.data.services.market_service.port).toBe(8102)
  })
})

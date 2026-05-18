import { describe, expect, it } from 'vitest'

import { buildOperationalAlerts, buildRoleWorkflowCards, pickPrimaryFocus } from '../../src/utils/workbench.js'

describe('workbench utils', () => {
  it('prefers recommendation symbol for primary focus', () => {
    expect(pickPrimaryFocus([{ symbol: 'NVDA.US', market: 'US' }], [{ symbol: 'TSLA.US' }])).toMatchObject({
      symbol: 'NVDA.US',
      market: 'US',
      source: 'recommendation'
    })
  })

  it('builds trader workflows with trading and risk actions', () => {
    const cards = buildRoleWorkflowCards({
      roleCode: 'trader',
      access: { canUseQuantTrading: true },
      menuRoutes: ['Trading', 'RiskManagement', 'AIAnalysis', 'SymbolDetail'],
      selectedAccountName: '主账户',
      recommendationItems: [{ symbol: 'AAPL.US', market: 'US' }],
      positions: []
    })

    expect(cards.map((item) => item.id)).toContain('trade-execution')
    expect(cards.map((item) => item.id)).toContain('risk-check')
    expect(cards[0].target).toMatchObject({ name: 'Trading' })
  })

  it('filters workflow cards by visible menus', () => {
    const cards = buildRoleWorkflowCards({
      roleCode: 'admin',
      access: { canUseQuantTrading: true, canManageTasks: true },
      menuRoutes: ['AIAnalysis', 'SymbolDetail'],
      selectedAccountName: '主账户',
      recommendationItems: [{ symbol: 'MSFT.US', market: 'US' }],
      positions: []
    })

    expect(cards.map((item) => item.id)).toEqual(['market-analysis', 'symbol-detail'])
  })

  it('builds operational alerts from health degradations and missing snapshots', () => {
    const alerts = buildOperationalAlerts({
      menuRoutes: ['SchedulerCenter', 'Orders', 'Positions', 'Profile'],
      systemHealth: {
        services: {
          trade_service: {
            status: 'degraded',
            service: 'trade-service',
            details: {
              alerts: [
                {
                  code: 'trade-outbox-backlog',
                  level: 'warning',
                  message: '交易 outbox 存在待发布积压',
                  action: '检查 outbox repair'
                }
              ]
            }
          }
        }
      },
      selectedAccountName: '主账户',
      accountDataMeta: {},
      positionsDataMeta: {},
      recentTradeMeta: {}
    })

    expect(alerts.some((item) => item.id.includes('trade-outbox-backlog'))).toBe(true)
    expect(alerts.some((item) => item.id === 'position-snapshot-missing')).toBe(true)
  })

  it('deduplicates and sorts operational alerts by severity', () => {
    const alerts = buildOperationalAlerts({
      roleCode: 'admin',
      access: { canManageTasks: true },
      menuRoutes: ['SchedulerCenter', 'RiskManagement', 'Orders'],
      systemHealth: {
        services: {
          trade_service: {
            status: 'unhealthy',
            service: 'trade-service',
            details: {
              alerts: [
                { code: 'trade-dead-letter', level: 'critical', message: '交易死信堆积', action: '检查 dead letter' }
              ]
            }
          },
          risk_service: {
            status: 'degraded',
            service: 'risk-service',
            details: {
              alerts: [
                { code: 'risk-delay', level: 'warning', message: '风控快照延迟', action: '查看快照任务' }
              ]
            }
          }
        }
      },
      selectedAccountName: '主账户',
      positionsDataMeta: { snapshotAt: '2026-04-15T00:00:00Z' },
      recentTradeMeta: { snapshotAt: '2026-04-15T00:00:00Z' }
    })

    expect(alerts[0].level).toBe('critical')
    expect(alerts.some((item) => item.id.includes('trade-dead-letter'))).toBe(true)
    expect(alerts.some((item) => item.id === 'service-health')).toBe(true)
  })
})

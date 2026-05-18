import { flushPromises, shallowMount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const pushMock = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: pushMock
  })
}))

vi.mock('../../src/utils/auth.js', () => ({
  getCurrentUser: () => ({ id: 1, username: 'admin', roleCode: 'admin' }),
  getAccess: () => ({
    canUseQuantTrading: true,
    canManageTasks: true,
    capabilities: ['trade.live', 'risk.manage', 'ai.analysis', 'tasks.manage', 'positions.view', 'orders.view', 'profile.view']
  }),
  getMenus: () => ([
    { routeName: 'Trading' },
    { routeName: 'RiskManagement' },
    { routeName: 'AIAnalysis' },
    { routeName: 'SymbolDetail' },
    { routeName: 'SchedulerCenter' },
    { routeName: 'Profile' },
    { routeName: 'Orders' },
    { routeName: 'Positions' }
  ])
}))

vi.mock('../../src/composables/useAdaptiveLayout.js', () => ({
  useAdaptiveLayout: () => ({ isPhoneLayout: ref(false) })
}))

vi.mock('../../src/composables/useTheme.js', () => ({
  useTheme: () => ({ activeTheme: ref('light') })
}))

vi.mock('../../src/composables/useWebSocket.js', () => ({
  useStockQuotes: () => ({ quotes: { value: {} }, isConnected: { value: false } }),
  useOrderStream: () => ({
    orders: { value: [] },
    isConnected: { value: false },
    meta: { value: {} },
    subscriptionAccountId: { value: null },
    subscriptionStatus: { value: '' }
  })
}))

vi.mock('../../src/utils/requestPure.js', () => ({
  getApiBaseUrl: () => 'http://127.0.0.1:3100'
}))

vi.mock('../../src/api/platform.js', () => ({
  getApiHealth: vi.fn(async () => ({
    success: true,
    data: {
      status: 'degraded',
      services: {
        gateway: { status: 'healthy', status_text: '运行正常', service: 'api-gateway', alert_count: 0, details: {} },
        trade_service: {
          status: 'degraded',
          status_text: '部分受限',
          service: 'trade-service',
          alert_count: 1,
          details: {
            alerts: [
              { code: 'trade-outbox-backlog', level: 'warning', message: '交易 outbox 存在待发布积压', action: '检查 outbox repair' }
            ]
          }
        }
      },
      summary: { total: 2, healthy: 1, degraded: 1, unhealthy: 0, alerts: 1 },
      environment: 'development'
    }
  }))
}))

vi.mock('../../src/api/trade.js', () => ({
  getBrokerAccounts: vi.fn(async () => ({ data: [{ id: 7, name: '主账户', isDefault: true }] })),
  getDashboardSummary: vi.fn(async () => ({ success: true, data: { total_assets: 100000, meta: { snapshotAt: '2026-04-15T00:00:00Z', sources: {} } } })),
  getPositionsSnapshot: vi.fn(async () => ({ data: [{ symbol: 'AAPL.US', quantity: 10, avgPrice: 100 }], meta: { snapshotAt: '2026-04-15T00:00:00Z', sources: {} } })),
  getProjectedOrders: vi.fn(async () => ({ data: { list: [{ orderId: 'ord-1', symbol: 'AAPL.US', status: 'submitted' }], meta: { snapshotAt: '2026-04-15T00:00:00Z', count: 1, sources: {} } } })),
  getAssetTrend: vi.fn(async () => ({ data: [] }))
}))

vi.mock('../../src/utils/api.js', async () => {
  const actual = await vi.importActual('../../src/utils/api.js')
  return {
    ...actual,
    getFinanceBriefings: vi.fn(async () => ({ data: [], meta: {} })),
    getRecommendations: vi.fn(async () => ({ data: { items: [{ symbol: 'AAPL.US', market: 'US' }], summary: 'ok' }, meta: {} })),
    getQuoteSnapshots: vi.fn(async () => ({ data: [] })),
    getDashboardMarketInsights: vi.fn(async () => ({ success: true, data: [], meta: {} }))
  }
})

describe('Dashboard shell', () => {
  beforeEach(() => {
    pushMock.mockReset()
  })

  it('keeps desktop status compact and hides removed workflow alert modules', async () => {
    const { default: Dashboard } = await import('../../src/views/Dashboard.vue')
    const wrapper = shallowMount(Dashboard, {
      global: {
        renderStubDefaultSlot: true,
        stubs: {
          VChart: true,
          ElTable: {
            template: '<div><slot /></div>'
          },
          'el-table': {
            template: '<div><slot /></div>'
          },
          ElTableColumn: true,
          'el-table-column': true,
          SectionCardHeader: {
            props: ['title', 'description'],
            template: '<div><span>{{ title }}</span><span>{{ description }}</span><slot /></div>'
          }
        }
      }
    })

    await flushPromises()

    expect(wrapper.text()).toContain('交易服务')
    expect(wrapper.text()).toContain('部分受限')
    expect(wrapper.text()).toContain('1 条告警')
    expect(wrapper.text()).not.toContain('常用入口')
    expect(wrapper.text()).not.toContain('运营告警')
    expect(wrapper.text()).not.toContain('交易执行')
    expect(wrapper.text()).not.toContain('市场 -> 研判')
    expect(wrapper.text()).not.toContain('交易 outbox 存在待发布积压')
  })
})

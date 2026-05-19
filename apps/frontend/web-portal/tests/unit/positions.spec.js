import { flushPromises, shallowMount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Positions from '../../src/views/Positions.vue'

const routerMocks = vi.hoisted(() => ({
  push: vi.fn()
}))

const tradeMocks = vi.hoisted(() => ({
  getAccounts: vi.fn(),
  getPositionsSnapshot: vi.fn()
}))

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: routerMocks.push
  })
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return {
    ...actual,
    ElMessage: {
      success: vi.fn(),
      warning: vi.fn(),
      error: vi.fn()
    }
  }
})

vi.mock('../../src/api/trade.js', () => ({
  getAccounts: tradeMocks.getAccounts,
  getPositionsSnapshot: tradeMocks.getPositionsSnapshot
}))

vi.mock('../../src/composables/useAdaptiveLayout.js', () => ({
  useAdaptiveLayout: () => ({ isPhoneLayout: ref(false) })
}))

vi.mock('../../src/composables/useTheme.js', () => ({
  useTheme: () => ({ activeTheme: ref('light') })
}))

vi.mock('../../src/composables/useWebSocket.js', () => ({
  useStockQuotes: () => ({
    quotes: ref({}),
    isConnected: ref(false)
  })
}))

vi.mock('../../src/utils/auth.js', () => ({
  getCurrentUser: () => ({ id: 1, username: 'tester' })
}))

const mountPositions = () => shallowMount(Positions, {
  global: {
    renderStubDefaultSlot: true,
    stubs: {
      VChart: true,
      PageHero: {
        props: ['title'],
        template: '<section class="page-hero"><span>{{ title }}</span><slot /><slot name="actions" /></section>'
      },
      ReadModelSourceStrip: {
        props: ['label', 'statusText'],
        template: '<div class="read-model-strip">{{ label }} {{ statusText }}</div>'
      },
      MetricStrip: {
        props: ['items'],
        template: '<div class="metric-strip">{{ items.length }}</div>'
      },
      MobileSegmentControl: true,
      SectionCardHeader: {
        props: ['title', 'badge'],
        template: '<header class="section-card-header"><span>{{ title }}</span><span>{{ badge }}</span><slot /><slot name="actions" /></header>'
      },
      'el-select': { template: '<div class="el-select"><slot /></div>' },
      'el-option': true,
      'el-button': {
        props: ['loading', 'disabled', 'type', 'size', 'plain'],
        emits: ['click'],
        template: '<button :data-loading="String(loading)" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
      },
      'el-card': { template: '<section class="el-card"><slot name="header" /><slot /></section>' },
      'el-table': { template: '<div class="el-table"><slot name="empty" /></div>' },
      'el-table-column': true,
      'el-progress': true,
      'el-empty': { props: ['description'], template: '<div class="el-empty">{{ description }}</div>' },
      'el-radio-group': { template: '<div><slot /></div>' },
      'el-radio-button': { template: '<button><slot /></button>' },
      'el-dialog': { template: '<div><slot /></div>' },
      'el-divider': true
    }
  }
})

describe('Positions first paint', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    tradeMocks.getAccounts.mockResolvedValue({
      data: [{ id: 7, name: '主账户', isDefault: true }]
    })
  })

  it('renders the page frame before a slow positions snapshot resolves', async () => {
    const snapshotRequest = deferred()
    tradeMocks.getPositionsSnapshot.mockReturnValue(snapshotRequest.promise)

    const wrapper = mountPositions()
    await flushPromises()

    expect(tradeMocks.getAccounts).toHaveBeenCalledTimes(1)
    expect(tradeMocks.getPositionsSnapshot).toHaveBeenCalledWith(7)
    expect(wrapper.find('.page-hero').exists()).toBe(true)
    expect(wrapper.find('.read-model-strip').exists()).toBe(true)
    expect(wrapper.findAll('.section-card-header')).toHaveLength(2)
    expect(wrapper.text()).toContain('持仓管理')
    expect(wrapper.text()).toContain('持仓状态')
    expect(wrapper.text()).toContain('组合洞察')
    expect(wrapper.text()).toContain('持仓明细')
    expect(wrapper.text()).not.toContain('AAPL.US')

    snapshotRequest.resolve({
      data: [{ symbol: 'AAPL.US', name: 'Apple', quantity: 10, avgPrice: 100, currentPrice: 110, marketValue: 1100, pnl: 100, pnlPercent: 10, weight: 100 }],
      meta: {
        snapshotAt: '2026-05-19T09:30:00Z',
        dataSource: 'snapshot',
        sources: { positions: 'position_snapshots' },
        realtimeOverlay: [],
        positionCount: 1
      }
    })
    await flushPromises()
  })
})

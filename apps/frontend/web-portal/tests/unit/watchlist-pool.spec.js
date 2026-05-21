import { flushPromises, shallowMount } from '@vue/test-utils'
import { defineComponent, h, inject, provide } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const pushMock = vi.fn()
const tableRowKey = Symbol('table-row')
const marketMocks = vi.hoisted(() => ({
  getWatchlist: vi.fn(),
  getWatchlistScanTargets: vi.fn(),
  getStockQuotes: vi.fn(),
  updateWatchlist: vi.fn(),
  removeWatchlist: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock })
}))

vi.mock('../../src/api/market.js', () => marketMocks)

vi.mock('../../src/utils/requestPure.js', () => ({
  request: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
    delete: vi.fn()
  }
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: {
      ...(actual.ElMessage || {}),
      error: vi.fn(),
      success: vi.fn()
    },
    ElMessageBox: {
      confirm: vi.fn()
    }
  }
})

const mountOptions = {
  global: {
    stubs: {
      'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
      'el-card': { template: '<section><slot name="header" /><slot /></section>' },
      'el-icon': { template: '<i><slot /></i>' },
      'el-input': true,
      'el-option': true,
      'el-radio-button': { template: '<button><slot /></button>' },
      'el-radio-group': { template: '<div><slot /></div>' },
      'el-select': { template: '<div><slot /></div>' },
      'el-switch': true,
      'el-tag': { template: '<span><slot /></span>' },
      'el-table': defineComponent({
        props: ['data'],
        setup(props, { slots }) {
          const RowProvider = defineComponent({
            props: ['row'],
            setup(rowProps, rowContext) {
              provide(tableRowKey, rowProps.row)
              return () => h('div', { class: 'table-row' }, rowContext.slots.default?.())
            }
          })
          return () => h('div', (props.data || []).length
            ? (props.data || []).map((row) => h(RowProvider, { row }, () => slots.default?.()))
            : slots.empty?.())
        }
      }),
      'el-table-column': defineComponent({
        props: ['label', 'prop'],
        setup(props, { slots }) {
          const row = inject(tableRowKey, null)
          return () => h('div', [
            props.label ? h('span', props.label) : null,
            slots.default ? slots.default({ row }) : (row && props.prop ? String(row[props.prop] || '') : '')
          ])
        }
      })
    }
  }
}

describe('WatchlistPool ledger', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    marketMocks.getWatchlist.mockResolvedValue({
      data: [
        {
          symbol: 'NVDA.US',
          name: 'NVIDIA',
          market: 'US',
          type: 'stock',
          scan_before_open: true,
          scan_after_close: false,
          added_at: '2026-05-20T08:00:00Z',
          last_scan_at: '2026-05-21T08:30:00Z',
          scan_target_counts: { pre_market: 1, after_market: 0 }
        }
      ]
    })
    marketMocks.getWatchlistScanTargets.mockResolvedValue({
      data: [
        {
          symbol: 'NVDA.US',
          name: 'NVIDIA',
          market: 'US',
          type: 'stock',
          score: 88,
          reason: '趋势增强'
        }
      ],
      meta: { updatedAt: '2026-05-21T08:35:00Z' }
    })
    marketMocks.getStockQuotes.mockResolvedValue({
      data: [
        {
          symbol: 'NVDA.US',
          price: 911.25,
          quoteSource: 'longbridge-live',
          timestamp: '2026-05-21T13:30:00Z',
          preMarketQuote: { price: 909.5, timestamp: '2026-05-21T13:29:00Z' },
          postMarketQuote: { price: 912.1, timestamp: '2026-05-20T23:59:00Z' },
          overnightQuote: { price: 910.2, timestamp: '2026-05-21T08:00:00Z' }
        }
      ]
    })
  })

  it('renders the ledger entry and opens the scan-result route', async () => {
    const { default: WatchlistPool } = await import('../../src/views/WatchlistPool.vue')
    const wrapper = shallowMount(WatchlistPool, mountOptions)

    await flushPromises()

    expect(wrapper.text()).toContain('自选标的台账')
    expect(wrapper.vm.watchlistLedgerRows[0]).toMatchObject({
      symbol: 'NVDA.US',
      market: 'US',
      scanTargetCount: 1,
      preMarketEnabled: true,
      lastScanAt: '2026-05-21T08:30:00Z',
      realtimePrice: 911.25,
      preMarketPrice: 909.5,
      postMarketPrice: 912.1,
      overnightPrice: 910.2
    })
    expect(marketMocks.getStockQuotes).toHaveBeenCalledWith(['NVDA.US'])
    expect(wrapper.text()).toContain('长桥实时 1 / 1')

    wrapper.vm.openScanResult(wrapper.vm.watchlistLedgerRows[0])

    expect(pushMock).toHaveBeenCalledWith({
      name: 'WatchlistScanResult',
      params: { symbol: 'NVDA.US' },
      query: { market: 'US', session: 'pre_market' }
    })
  })
})

import { flushPromises, shallowMount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const getStockPoolMock = vi.fn()
const getMarketInsightHistoryMock = vi.fn()
const getMarketInsightsAtTimeMock = vi.fn()

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

vi.mock('../../src/api/market.js', () => ({
  addStockToPool: vi.fn(async () => ({})),
  getMarketInsightHistory: getMarketInsightHistoryMock,
  getMarketInsightsAtTime: getMarketInsightsAtTimeMock,
  getStockPool: getStockPoolMock
}))

vi.mock('../../src/api/platform.js', () => ({
  runPlatformTask: vi.fn(async () => ({}))
}))

vi.mock('../../src/composables/useWebSocket.js', () => ({
  useStockQuotes: () => ({
    quotes: ref({}),
    isConnected: ref(false)
  })
}))

vi.mock('../../src/composables/useAdaptiveLayout.js', () => ({
  useAdaptiveLayout: () => ({ isPhoneLayout: ref(false) })
}))

vi.mock('../../src/utils/auth.js', () => ({
  getAccess: () => ({}),
  getCurrentUser: () => ({ id: 'tester' })
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() })
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: {
      ...(actual.ElMessage || {}),
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn()
    }
  }
})

const mountOptions = {
  global: {
    stubs: {
      PageHero: { template: '<section><slot name="actions" /></section>' },
      ReadModelSourceStrip: true,
      MetricStrip: true,
      MobileSegmentControl: true,
      SectionCardHeader: { template: '<header><slot name="actions" /></header>' },
      'el-alert': true,
      'el-button': { template: '<button><slot /></button>' },
      'el-card': { template: '<section><slot name="header" /><slot /></section>' },
      'el-empty': true,
      'el-input': { template: '<input />' },
      'el-option': true,
      'el-pagination': true,
      'el-radio-button': { template: '<button><slot /></button>' },
      'el-radio-group': { template: '<div><slot /></div>' },
      'el-select': { template: '<select><slot /></select>' },
      'el-table': { template: '<table><slot /><slot name="empty" /></table>' },
      'el-table-column': true
    }
  }
}

describe('MarketData insight loading', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getStockPoolMock.mockResolvedValue({ data: [], total: 0, meta: {} })
  })

  it('starts latest insight fetch in parallel with history on initial load', async () => {
    const historyRequest = deferred()
    const insightRequest = deferred()

    getMarketInsightHistoryMock.mockReturnValueOnce(historyRequest.promise)
    getMarketInsightsAtTimeMock.mockReturnValueOnce(insightRequest.promise)

    const { default: MarketData } = await import('../../src/views/MarketData.vue')
    shallowMount(MarketData, mountOptions)
    await flushPromises()

    expect(getMarketInsightHistoryMock).toHaveBeenCalledWith({ market: 'US', limit: 24 })
    expect(getMarketInsightsAtTimeMock).toHaveBeenCalledWith({ market: 'US' })

    insightRequest.resolve({
      data: [{ market: 'US', generatedAt: '2026-05-19T10:00:00Z', headline: 'latest' }],
      meta: { snapshotAt: '2026-05-19T10:00:00Z' }
    })
    historyRequest.resolve({
      data: [{ generatedAt: '2026-05-19T10:00:00Z', marketCount: 1 }]
    })

    await flushPromises()
  })

  it('switches market with a fresh latest insight request instead of waiting on history first', async () => {
    getMarketInsightHistoryMock.mockResolvedValue({
      data: [{ generatedAt: '2026-05-19T09:00:00Z', marketCount: 1 }]
    })
    getMarketInsightsAtTimeMock.mockResolvedValue({
      data: [{ market: 'US', generatedAt: '2026-05-19T09:00:00Z' }],
      meta: {}
    })

    const { default: MarketData } = await import('../../src/views/MarketData.vue')
    const wrapper = shallowMount(MarketData, mountOptions)
    await flushPromises()

    const historyRequest = deferred()
    const latestCnRequest = deferred()
    getMarketInsightHistoryMock.mockReturnValueOnce(historyRequest.promise)
    getMarketInsightsAtTimeMock.mockReturnValueOnce(latestCnRequest.promise)

    wrapper.vm.selectedMarket = 'CN'
    wrapper.vm.changeMarket()
    await flushPromises()

    expect(getMarketInsightHistoryMock).toHaveBeenLastCalledWith({ market: 'CN', limit: 24 })
    expect(getMarketInsightsAtTimeMock).toHaveBeenLastCalledWith({ market: 'CN' })

    latestCnRequest.resolve({
      data: [{ market: 'CN', generatedAt: '2026-05-19T11:00:00Z' }],
      meta: {}
    })
    historyRequest.resolve({
      data: [{ generatedAt: '2026-05-19T11:00:00Z', marketCount: 1 }]
    })

    await flushPromises()
  })

  it('clears stale selected insight when history no longer contains that timestamp', async () => {
    getMarketInsightHistoryMock.mockResolvedValue({
      data: [{ generatedAt: '2026-05-19T09:00:00Z', marketCount: 1 }]
    })
    getMarketInsightsAtTimeMock.mockResolvedValue({
      data: [{ market: 'US', generatedAt: '2026-05-19T09:00:00Z' }],
      meta: {}
    })

    const { default: MarketData } = await import('../../src/views/MarketData.vue')
    const wrapper = shallowMount(MarketData, mountOptions)
    await flushPromises()

    wrapper.vm.selectedInsightTime = '2026-05-18T09:00:00Z'
    getMarketInsightHistoryMock.mockResolvedValueOnce({ data: [] })
    getMarketInsightsAtTimeMock.mockResolvedValueOnce({
      data: [{ market: 'US', generatedAt: '2026-05-18T09:00:00Z', headline: 'stale' }],
      meta: { snapshotAt: '2026-05-18T09:00:00Z' }
    })

    await wrapper.vm.loadMarketInsights()
    await flushPromises()

    expect(wrapper.vm.selectedInsightTime).toBe('')
    expect(wrapper.vm.marketInsights).toEqual([])
    expect(wrapper.vm.marketInsightMeta).toEqual({})
  })
})

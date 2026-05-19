import { ref } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  analyzePositions: vi.fn(),
  getAIModels: vi.fn(),
  getLatestTrendScans: vi.fn(),
  getPlatformMarketScans: vi.fn(),
  getStockPool: vi.fn(),
  getWatchlist: vi.fn(),
  getBrokerAccounts: vi.fn(),
  getDefaultBrokerAccount: vi.fn(),
  getPositionsSnapshot: vi.fn(),
  requestGet: vi.fn(),
  message: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn()
  }
}))

vi.mock('../../src/api/analysis.js', () => ({
  analyzePositions: mocks.analyzePositions,
  getAIModels: mocks.getAIModels,
  getLatestTrendScans: mocks.getLatestTrendScans
}))

vi.mock('../../src/api/market.js', () => ({
  getPlatformMarketScans: mocks.getPlatformMarketScans,
  getStockPool: mocks.getStockPool,
  getWatchlist: mocks.getWatchlist
}))

vi.mock('../../src/api/trade.js', () => ({
  getBrokerAccounts: mocks.getBrokerAccounts,
  getDefaultBrokerAccount: mocks.getDefaultBrokerAccount,
  getPositionsSnapshot: mocks.getPositionsSnapshot
}))

vi.mock('../../src/utils/requestPure.js', () => ({
  request: {
    get: mocks.requestGet
  }
}))

vi.mock('../../src/composables/useAdaptiveLayout.js', () => ({
  useAdaptiveLayout: () => ({
    isPhoneLayout: ref(false)
  })
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: {},
    query: {}
  })
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: mocks.message
  }
})

import AIAnalysis from '../../src/views/AIAnalysis.vue'

const createAnalysisResult = () => ({
  symbol: 'NVDA.US',
  finalDecision: '买入',
  finalSignal: 'buy',
  confidence: 91,
  price: 901.25,
  changePercent: 0.021,
  analysisTime: '2026-05-19T09:30:00Z',
  reason: '趋势和量能共振继续强化',
  technicalScore: 88,
  marketScore: 82,
  indicators: {
    trendHint: '趋势延续',
    ma20: 875
  },
  scanLayers: [
    {
      id: 'pulse',
      name: '脉冲扫描',
      decision: '偏多',
      signal: 'buy',
      summary: '脉冲延续，回撤承接稳定',
      highlights: ['量能放大'],
      modelAlias: 'pulse-local',
      modelQuality: '高'
    },
    {
      id: 'final',
      name: '终审',
      decision: '买入',
      signal: 'buy',
      summary: '延续趋势，允许继续跟随',
      highlights: ['风险收益比可接受'],
      modelAlias: 'final-cloud',
      modelQuality: '高'
    }
  ],
  marketSummary: {
    regime: 'risk_on',
    summary: '科技主线仍有承接',
    riskTemperature: '偏暖',
    benchmarks: []
  },
  modelPlan: {
    final: { alias: 'final-cloud' }
  }
})

const mountOptions = {
  global: {
    stubs: {
      'el-alert': { template: '<div class="el-alert"><slot /></div>' },
      'el-autocomplete': { template: '<div class="el-autocomplete"><slot name="prefix" /></div>' },
      'el-button': {
        props: ['disabled', 'loading'],
        emits: ['click'],
        template: '<button :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>'
      },
      'el-empty': true,
      'el-icon': { template: '<i><slot /></i>' },
      'el-option': true,
      'el-radio-button': { template: '<button><slot /></button>' },
      'el-radio-group': { template: '<div class="el-radio-group"><slot /></div>' },
      'el-select': { template: '<div class="el-select"><slot /></div>' }
    }
  }
}

const findButtonByText = (wrapper, text) => {
  return wrapper.findAll('button').find((button) => button.text().includes(text))
}

describe('AIAnalysis scan status', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    mocks.getBrokerAccounts.mockResolvedValue({ data: [{ id: 'acc-1', name: 'Primary' }] })
    mocks.getDefaultBrokerAccount.mockResolvedValue({ id: 'acc-1' })
    mocks.getAIModels.mockResolvedValue({ defaultPlan: { final: { alias: 'final-cloud' } } })
    mocks.getLatestTrendScans.mockResolvedValue({ data: [] })
    mocks.getPlatformMarketScans.mockResolvedValue({ data: [] })
    mocks.getStockPool.mockResolvedValue({ data: [] })
    mocks.getWatchlist.mockResolvedValue({
      data: [
        { symbol: 'NVDA.US', name: 'NVIDIA Corporation', market: 'US', currentPrice: 901.25 }
      ]
    })
    mocks.getPositionsSnapshot.mockResolvedValue({ data: [] })
    mocks.requestGet.mockResolvedValue({ data: [] })
  })

  it('shows running and completed status around a scan trigger', async () => {
    let resolveScan
    mocks.analyzePositions.mockImplementation(() => new Promise((resolve) => {
      resolveScan = resolve
    }))

    const wrapper = shallowMount(AIAnalysis, mountOptions)
    await flushPromises()

    const scanButton = findButtonByText(wrapper, '扫描当前列表')
    expect(scanButton).toBeTruthy()

    await scanButton.trigger('click')
    await flushPromises()

    const runningStatus = wrapper.find('.analysis-scan-status')
    expect(runningStatus.exists()).toBe(true)
    expect(runningStatus.classes()).toContain('is-running')
    expect(runningStatus.text()).toContain('扫描进行中')
    expect(runningStatus.text()).toContain('NVDA.US')

    resolveScan({
      data: [createAnalysisResult()],
      marketSummary: createAnalysisResult().marketSummary,
      modelPlan: createAnalysisResult().modelPlan
    })
    await flushPromises()

    const completedStatus = wrapper.find('.analysis-scan-status')
    expect(completedStatus.classes()).toContain('is-complete')
    expect(completedStatus.text()).toContain('最近一次扫描已完成')
    expect(completedStatus.text()).toContain('已收录 1 个扫描结果')
  })

  it('keeps recoverable scan network failures out of error console noise', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mocks.analyzePositions.mockRejectedValue(new TypeError('Failed to fetch'))

    const wrapper = shallowMount(AIAnalysis, mountOptions)
    await flushPromises()

    const scanButton = findButtonByText(wrapper, '扫描当前列表')
    await scanButton.trigger('click')
    await flushPromises()

    const failedStatus = wrapper.find('.analysis-scan-status')
    expect(failedStatus.classes()).toContain('is-error')
    expect(failedStatus.text()).toContain('最近一次扫描失败')
    expect(consoleErrorSpy).not.toHaveBeenCalledWith(expect.stringContaining('AI 研判失败'), expect.anything())
    expect(consoleWarnSpy).toHaveBeenCalledWith('AI 研判请求未完成:', 'Failed to fetch')

    consoleErrorSpy.mockRestore()
    consoleWarnSpy.mockRestore()
  })
})

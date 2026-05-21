import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const pushMock = vi.fn()
const routeState = {
  params: { symbol: 'NVDA.US' },
  query: { market: 'US', session: 'pre_market' }
}
const getLatestSymbolAnalysisMock = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push: pushMock })
}))

vi.mock('../../src/api/analysis.js', () => ({
  getLatestSymbolAnalysis: getLatestSymbolAnalysisMock
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: {
      ...(actual.ElMessage || {}),
      error: vi.fn()
    }
  }
})

const mountOptions = {
  global: {
    stubs: {
      'el-alert': { template: '<div class="el-alert">{{ title }}</div>', props: ['title'] },
      'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
      'el-card': { template: '<section><slot name="header" /><slot /></section>' },
      'el-tag': { template: '<span><slot /></span>' }
    }
  }
}

describe('WatchlistScanResult', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeState.params = { symbol: 'NVDA.US' }
    routeState.query = { market: 'US', session: 'pre_market' }
    getLatestSymbolAnalysisMock.mockResolvedValue({
      data: {
        symbol: 'NVDA.US',
        latestTrendScan: {
          symbol: 'NVDA.US',
          trendDirection: 'up',
          riskLevel: 'medium',
          technicalScore: 82.5,
          confidence: 0.91,
          summary: '趋势延续，量能稳定',
          generatedAt: '2026-05-21T08:30:00Z',
          indicators: { price: 901.25, rsi: 62 }
        },
        latestAiAnalysis: {
          finalDecision: '买入',
          confidence: 91,
          reason: '趋势和量能共振',
          analysisTime: '2026-05-21T08:32:00Z',
          scanLayers: [
            { id: 'final', name: '决策终审层', decision: '买入', summary: '允许继续跟随' }
          ]
        }
      }
    })
  })

  it('loads and renders latest trend scan and AI analysis', async () => {
    const { default: WatchlistScanResult } = await import('../../src/views/WatchlistScanResult.vue')
    const wrapper = shallowMount(WatchlistScanResult, mountOptions)

    await flushPromises()

    expect(getLatestSymbolAnalysisMock).toHaveBeenCalledWith('NVDA.US')
    expect(wrapper.text()).toContain('最新扫描结果')
    expect(wrapper.text()).toContain('上行')
    expect(wrapper.text()).toContain('中风险')
    expect(wrapper.text()).toContain('趋势延续，量能稳定')
    expect(wrapper.text()).toContain('最新 AI 研判')
    expect(wrapper.text()).toContain('买入')
    expect(wrapper.text()).toContain('趋势和量能共振')

    wrapper.vm.openAIAnalysis()
    expect(pushMock).toHaveBeenCalledWith({
      name: 'AIAnalysis',
      query: { symbol: 'NVDA.US', market: 'US' }
    })
  })
})

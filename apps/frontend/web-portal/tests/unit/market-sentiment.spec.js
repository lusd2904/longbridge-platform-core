import { flushPromises, shallowMount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const getSentimentBootstrapMock = vi.fn()
const getSentimentOverviewMock = vi.fn()
const pushMock = vi.fn()

vi.mock('../../src/api/sentiment.js', () => ({
  getSentimentBootstrap: getSentimentBootstrapMock,
  getSentimentOverview: getSentimentOverviewMock,
  getSentimentUniverse: vi.fn(),
  getSymbolSentiment: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock })
}))

vi.mock('../../src/composables/useAdaptiveLayout.js', () => ({
  useAdaptiveLayout: () => ({ isPhoneLayout: ref(false) })
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: {
      ...(actual.ElMessage || {}),
      error: vi.fn(),
      success: vi.fn()
    }
  }
})

const mountOptions = {
  global: {
    stubs: {
      'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
      'el-card': { template: '<section><slot name="header" /><slot /></section>' },
      'el-input': { template: '<input />' },
      'el-radio-button': { template: '<button><slot /></button>' },
      'el-radio-group': { template: '<div><slot /></div>' },
      'el-table': {
        props: ['data'],
        template: '<div><slot v-for="row in (data || [])" :row="row" /><slot v-if="!(data || []).length" name="empty" /></div>'
      },
      'el-table-column': {
        props: ['prop', 'label'],
        template: '<div><slot /></div>'
      },
      'el-tag': { template: '<span><slot /></span>' }
    }
  }
}

describe('MarketSentiment page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getSentimentBootstrapMock.mockResolvedValue({
      data: {
        aiConfig: {
          provider: 'nvidia',
          baseUrl: 'http://sub2api:8080/v1',
          chatCompletionsUrl: 'http://sub2api:8080/v1/chat/completions',
          models: {
            default: 'gpt-5.5',
            scanPulse: 'gpt-5.4',
            recommendSummary: 'gpt-5.5'
          },
          source: 'LONGBRIDGE_AI_*',
          note: 'reuse sub2api'
        },
        linkedRoutes: {}
      }
    })
    getSentimentOverviewMock.mockResolvedValue({
      data: {
        marketSummaries: [
          {
            market: 'US',
            sentimentScore: 0.31,
            sentimentLabel: 'positive',
            positiveCount: 2,
            negativeCount: 1,
            heat: 0.64,
            topRiskKeywords: ['监管']
          },
          {
            market: 'CN',
            sentimentScore: -0.11,
            sentimentLabel: 'neutral',
            positiveCount: 1,
            negativeCount: 1,
            heat: 0.42,
            topRiskKeywords: ['盈利']
          }
        ],
        topSymbols: [
          {
            symbol: 'NVDA.US',
            market: 'US',
            score: 0.44,
            confidence: 0.91,
            heat: 0.72,
            trend_direction: 'up',
            risk_level: 'medium',
            risk_keywords: ['监管'],
            driver_headlines: ['AI 需求延续'],
            quant_fields: {
              technical_score: 82.5,
              ai_bias: 'bullish',
              expected_return: 0.12,
              recommended: true
            },
            latest_analysis_ref: {
              finalDecision: '买入'
            }
          }
        ],
        riskWordCloud: [
          { keyword: '监管', count: 2 },
          { keyword: '盈利', count: 1 }
        ],
        aiConfig: {
          provider: 'nvidia',
          baseUrl: 'http://sub2api:8080/v1',
          chatCompletionsUrl: 'http://sub2api:8080/v1/chat/completions',
          models: {
            default: 'gpt-5.5',
            scanPulse: 'gpt-5.4',
            recommendSummary: 'gpt-5.5'
          },
          source: 'LONGBRIDGE_AI_*',
          note: 'reuse sub2api'
        }
      },
      meta: {
        market: 'ALL'
      }
    })
  })

  it('loads bootstrap and overview with sub2api config', async () => {
    const { default: MarketSentiment } = await import('../../src/views/MarketSentiment.vue')
    const wrapper = shallowMount(MarketSentiment, mountOptions)

    await flushPromises()

    expect(getSentimentBootstrapMock).toHaveBeenCalledTimes(1)
    expect(getSentimentOverviewMock).toHaveBeenCalledTimes(1)
    expect(getSentimentOverviewMock).toHaveBeenLastCalledWith({})
    expect(wrapper.vm.aiConfig.baseUrl).toBe('http://sub2api:8080/v1')
    expect(wrapper.vm.filteredSymbols).toHaveLength(1)
  })

  it('reloads market-specific overview and keeps routing entrypoints', async () => {
    const { default: MarketSentiment } = await import('../../src/views/MarketSentiment.vue')
    const wrapper = shallowMount(MarketSentiment, mountOptions)

    await flushPromises()

    wrapper.vm.$.setupState.selectedMarket = 'US'
    await wrapper.vm.loadOverview()
    await flushPromises()

    expect(getSentimentOverviewMock).toHaveBeenLastCalledWith({ market: 'US' })

    wrapper.vm.goAI({ symbol: 'NVDA.US', market: 'US' })
    wrapper.vm.goRecommendations()
    wrapper.vm.goStrategy()

    expect(pushMock).toHaveBeenCalledWith({ name: 'AIAnalysis', query: { symbol: 'NVDA.US', market: 'US' } })
    expect(pushMock).toHaveBeenCalledWith({ name: 'Recommendations' })
    expect(pushMock).toHaveBeenCalledWith({ name: 'Strategy' })
  })
})

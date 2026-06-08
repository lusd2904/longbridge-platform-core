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
      MetricStrip: { template: '<div class="metric-strip-stub" />' },
      PageHero: { template: '<section class="page-hero-stub"><slot name="actions" /></section>' },
      SectionCardHeader: {
        props: ['title', 'badge'],
        template: '<div class="section-card-header-stub">{{ title }} {{ badge }}</div>'
      },
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
      'el-tag': {
        props: ['type'],
        template: '<span :data-tag-type="type"><slot /></span>'
      }
    }
  }
}

const bootstrapPayload = {
  aiConfig: {
    provider: 'nvidia',
    baseUrl: 'https://lucen.cc/v1',
    chatCompletionsUrl: 'https://lucen.cc/v1/chat/completions',
    models: {
      default: 'gpt-5.5',
      scanPulse: 'gpt-5.4',
      recommendSummary: 'gpt-5.5'
    },
    source: 'LONGBRIDGE_AI_*',
    note: 'reuse sub2api'
  },
  linkedRoutes: {},
  githubAdoption: {
    decision: 'native-contract-first',
    recommendedStack: ['FinNLP collectors', 'FinBERT optional scoring', 'sub2api synthesis'],
    aiModelPolicy: 'reuse LONGBRIDGE_AI_* / sub2api',
    quantPolicy: '只读证据，不触发交易执行',
    candidates: [
      {
        name: 'FinNLP',
        license: 'MIT',
        fit: '中文金融来源覆盖',
        adoption: 'reference-adapter'
      },
      {
        name: 'TickerPulse AI / BettaFish',
        license: 'GPL family',
        fit: '架构参考',
        adoption: 'do-not-vendor'
      }
    ]
  }
}

const overviewPayload = {
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
    baseUrl: 'https://lucen.cc/v1',
    chatCompletionsUrl: 'https://lucen.cc/v1/chat/completions',
    models: {
      default: 'gpt-5.5',
      scanPulse: 'gpt-5.4',
      recommendSummary: 'gpt-5.5'
    },
    source: 'LONGBRIDGE_AI_*',
    note: 'reuse sub2api'
  }
}

describe('MarketSentiment page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getSentimentBootstrapMock.mockResolvedValue({ data: bootstrapPayload })
    getSentimentOverviewMock.mockResolvedValue({
      data: overviewPayload,
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
    expect(wrapper.vm.aiConfig.baseUrl).toBe('https://lucen.cc/v1')
    expect(wrapper.vm.githubAdoption.decision).toBe('native-contract-first')
    expect(wrapper.vm.githubCandidates).toHaveLength(2)
    expect(wrapper.vm.localizedRecommendedStackText).toContain('FinNLP 采集器')
    expect(wrapper.vm.filteredSymbols).toHaveLength(1)
  })

  it('renders github adoption card details from bootstrap data even after overview refresh', async () => {
    const { default: MarketSentiment } = await import('../../src/views/MarketSentiment.vue')
    const wrapper = shallowMount(MarketSentiment, mountOptions)

    await flushPromises()

    expect(wrapper.text()).toContain('GitHub 选型与量化边界')
    expect(wrapper.text()).toContain('FinNLP 采集器 / 可选 FinBERT 评分 / sub2api 综合')
    expect(wrapper.text()).toContain('复用 LONGBRIDGE_AI_* / sub2api')
    expect(wrapper.text()).toContain('本地契约优先')
    expect(wrapper.text()).toContain('只读证据，不触发交易执行')
    expect(wrapper.text()).toContain('FinNLP')
    expect(wrapper.text()).toContain('TickerPulse AI / BettaFish')
    expect(wrapper.text()).not.toContain('native-contract-first')
    expect(wrapper.text()).not.toContain('FinNLP collectors')
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

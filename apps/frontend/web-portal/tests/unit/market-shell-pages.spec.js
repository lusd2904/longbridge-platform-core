import { flushPromises, shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import Recommendations from '@/views/Recommendations.vue'
import FinanceNews from '@/views/FinanceNews.vue'
import SymbolDetail from '@/views/SymbolDetail.vue'
import Kline from '@/views/Kline.vue'
import Strategy from '@/views/Strategy.vue'
import RiskManagement from '@/views/RiskManagement.vue'

vi.mock('../../src/api/analysis.js', () => ({
  getRecommendations: vi.fn(async () => ({
    data: {
      generated_at: '2026-03-27T08:00:00Z',
      candidate_count: 1,
      profile_label: '成长型',
      summary: '系统已生成推荐摘要。',
      stats: {
        total: 1,
        avg_return: 6.2,
        avg_score: 82.4,
        risk_alerts: 0,
        markets: { US: 1 }
      },
      items: [
        {
          symbol: 'AAPL.US',
          name: 'Apple',
          market: 'US',
          assetType: 'stock',
          aiScore: 82.4,
          expectedReturn: 6.2,
          changePercent: 1.4,
          confidence: 88,
          riskLevel: 2,
          horizon: 'swing',
          thesis: '盈利与现金流质量稳定。',
          reasons: ['盈利质量稳定'],
          isTopPick: true
        }
      ]
    },
    meta: {
      snapshotAt: '2026-03-27T08:00:00Z',
      dataSource: 'recommendation_snapshots'
    }
  })),
  refreshRecommendations: vi.fn(async () => ({
    data: { stats: {}, items: [] },
    meta: {}
  })),
  getStrategies: vi.fn(async () => ({
    data: [
      {
        id: 1,
        name: 'Apple 回撤防守',
        status: 'active',
        type: 'stop_loss',
        executionMode: 'auto',
        scheduleFrequency: 5,
        schedulePeriod: 'minute',
        triggerCount: 2,
        createdAt: '2026-03-27T08:00:00Z',
        lastExecutedAt: '2026-03-27T09:00:00Z',
        params: [{ name: 'threshold', value: 6 }]
      }
    ]
  })),
  getStrategyTemplates: vi.fn(async () => ({
    data: {
      templates: [
        {
          templateCode: 'stop_loss_guard',
          name: '止损保护',
          summary: '浮亏超过阈值后提醒收缩风险。',
          category: 'risk',
          categoryLabel: '风险控制',
          executionMode: 'auto',
          scheduleFrequency: 5,
          schedulePeriod: 'minute',
          featured: true,
          params: { threshold: 6 },
          tags: ['防守']
        }
      ],
      categories: [{ value: 'risk', label: '风险控制' }]
    }
  })),
  createStrategy: vi.fn(async () => ({})),
  updateStrategy: vi.fn(async () => ({})),
  deleteStrategy: vi.fn(async () => ({})),
  getStrategyMonitorSummary: vi.fn(async () => ({
    data: {
      overview: {
        ruleCount: 1,
        activeRuleCount: 1,
        autoRuleCount: 1,
        autoActiveRuleCount: 1,
        manualRuleCount: 0,
        manualActiveRuleCount: 0,
        alertCount: 1,
        status: 'running',
        message: '监控链路健康',
        lastRunAt: '2026-03-27T09:10:00Z'
      },
      alerts: [
        {
          id: 'alert-1',
          symbol: 'AAPL.US',
          strategyName: 'Apple 回撤防守',
          message: '浮亏接近阈值',
          severity: 'medium',
          actionSuggested: '观察',
          createdAt: '2026-03-27T09:10:00Z'
        }
      ]
    }
  })),
  runStrategyMonitor: vi.fn(async () => ({ data: { alertCount: 0 } })),
  getFinanceBriefings: vi.fn(async () => ({
    data: [
      {
        id: 'briefing-1',
        market: 'US',
        headline: '美股盘前扫描',
        summary: '科技龙头延续强势。',
        briefingType: 'market-insight',
        generatedAt: '2026-03-27T09:00:00Z',
        payload: { symbol: 'AAPL.US' }
      }
    ],
    meta: {
      snapshotAt: '2026-03-27T09:00:00Z',
      dataSource: 'finance_briefings'
    }
  }))
}))

vi.mock('../../src/api/market.js', () => ({
  addStockToPool: vi.fn(async () => ({})),
  analyzeStock: vi.fn(async () => ({
    data: {
      final_decision: '观望',
      final_confidence: 71,
      deepseek_analysis: '测试环境下返回的研判摘要。',
      analysis_time: '2026-03-27T09:35:00Z'
    }
  })),
  getMarketHistoryBackfillStatus: vi.fn(async () => ({
    data: {
      coverageRate: 88.4,
      latestTradeDate: '2026-03-26',
      marketCoverage: { US: 1, CN: 1, HK: 1 },
      task: {
        status: 'running',
        message: '历史补数持续回补中'
      }
    }
  })),
  getMarketHistoryCompare: vi.fn(async () => ({
    data: {
      series: [
        {
          symbol: 'AAPL.US',
          items: [
            {
              date: '2026-03-26',
              open: 190,
              high: 195,
              low: 189,
              close: 194,
              volume: 1200000,
              changePercent: 1.2
            }
          ],
          summary: {
            count: 1,
            latestDate: '2026-03-26',
            firstDate: '2026-03-26',
            latestClose: 194,
            periodReturn: 1.2
          }
        }
      ],
      comparison: [
        {
          symbol: 'AAPL.US',
          series: [{ date: '2026-03-26', value: 1.2 }]
        }
      ],
      snapshots: [
        {
          symbol: 'AAPL.US',
          name: 'Apple',
          market: 'US',
          snapshot: {
            trendLabel: '偏强',
            closePrice: 194,
            changePercent: 1.2,
            rsi: 58,
            macdHist: 0.12,
            roc: 1.2,
            supportPrice: 188,
            resistancePrice: 201
          }
        }
      ]
    },
    meta: {
      dataSource: 'market_history_compare',
      snapshotAt: '2026-03-27T09:20:00Z'
    }
  })),
  getQuoteSnapshots: vi.fn(async () => ({ data: [] })),
  getLongbridgeAnnouncements: vi.fn(async () => ({ data: { payload: [] } })),
  getLongbridgeDepth: vi.fn(async () => ({ data: { payload: { bids: [], asks: [] } } })),
  getLongbridgeNews: vi.fn(async () => ({ data: { payload: [] } })),
  getStockQuote: vi.fn(async () => ({ data: { price: 194.5, change_percent: 1.36, timestamp: '2026-03-27T09:31:00Z' } })),
  getLongbridgeTopics: vi.fn(async () => ({ data: { payload: [] } })),
  getLongbridgeTrades: vi.fn(async () => ({ data: { payload: [] } })),
  getSymbolOverview: vi.fn(async () => ({
    data: {
      symbol: 'AAPL.US',
      market: 'US',
      fundamentals: {
        name: 'Apple',
        sector: 'Technology',
        pe_ratio: 28.4,
        market_cap: 3000000000000
      },
      snapshots: {
        daily: {
          trendLabel: '偏强',
          rsi: 58,
          momentumScore: 64,
          supportPrice: 188,
          resistancePrice: 201,
          atr: 4.2,
          closePrice: 194,
          changePercent: 1.1,
          snapshotDate: '2026-03-26'
        }
      },
      quoteSnapshot: {
        price: 194,
        changePercent: 1.1,
        snapshotAt: '2026-03-27T09:30:00Z'
      },
      history: {
        items: [],
        summary: { latestDate: '2026-03-26' }
      },
      latestAiAnalysis: {
        final_decision: '买入',
        final_confidence: 82,
        deepseek_analysis: '趋势保持向上。'
      },
      marketInsight: {
        headline: '美股科技延续强势',
        summary: '龙头科技股继续带动风险偏好。'
      },
      marketScan: {
        headline: '盘前扫描稳定',
        summary: '量能与宽度同步修复。'
      },
      contentCache: {
        dataSource: 'content-cache',
        totalCount: 0,
        announcements: { items: [] },
        news: { items: [] },
        topics: { items: [] }
      },
      meta: {
        snapshotAt: '2026-03-27T09:30:00Z',
        dataSource: 'symbol_overview',
        sources: { content: 'symbol_content_cache' },
        realtimeOverlay: []
      }
    }
  }))
}))

vi.mock('../../src/composables/useTheme.js', async () => {
  const { ref } = await import('vue')
  return {
    useTheme: () => ({ activeTheme: ref('dark') }),
    getThemeValue: (_name, fallback) => fallback
  }
})

vi.mock('../../src/composables/useWebSocket.js', async () => {
  const { ref } = await import('vue')
  return {
    useStockQuotes: () => ({
      quotes: ref({
        'AAPL.US': {
          price: 194,
          last_price: 194
        }
      }),
      isConnected: ref(true)
    }),
    useLongbridgeMarketStream: () => ({
      quotes: ref({}),
      depth: ref({}),
      trades: ref({}),
      isConnected: ref(false)
    })
  }
})

vi.mock('../../src/utils/auth.js', () => ({
  getCurrentUser: () => ({ id: 'user-1' })
}))

vi.mock('../../src/api/risk.js', () => ({
  getRiskOverview: vi.fn(async () => ({
    data: {
      overview: {
        score: 62,
        scoreLabel: '可控',
        scoreDescription: '风险暴露维持在控制线内',
        maxWeight: 22,
        positionLimit: 30,
        drawdown: 4.2,
        drawdownLimit: 8,
        protectionCount: 3,
        stopLossCount: 2,
        takeProfitCount: 1
      },
      events: [
        {
          id: 'risk-1',
          level: 'medium',
          type: '波动提醒',
          message: '单日波动提升',
          timestamp: '2026-03-27T09:00:00Z',
          symbol: 'AAPL.US'
        }
      ],
      stopLossOrders: [
        { id: 'sl-1', symbol: 'AAPL.US', stopPrice: 186, currentPrice: 194, distance: 4.1 }
      ],
      takeProfitOrders: [
        { id: 'tp-1', symbol: 'AAPL.US', profitPrice: 208, currentPrice: 194, distance: 7.2 }
      ],
      snapshotAt: '2026-03-27T09:00:00Z',
      meta: {
        dataSource: 'risk_overview_live',
        snapshotAt: '2026-03-27T09:00:00Z',
        sources: {},
        realtimeOverlay: [],
        eventCount: 1,
        stopLossCount: 1,
        takeProfitCount: 1
      }
    }
  })),
  getRiskOverviewSnapshot: vi.fn(async () => ({
    data: {
      overview: {
        score: 60,
        scoreLabel: '可控',
        scoreDescription: '快照风险概览',
        maxWeight: 20,
        positionLimit: 30,
        drawdown: 4,
        drawdownLimit: 8,
        protectionCount: 2,
        stopLossCount: 1,
        takeProfitCount: 1
      },
      events: [],
      stopLossOrders: [],
      takeProfitOrders: [],
      snapshotAt: '2026-03-27T08:50:00Z',
      meta: {
        dataSource: 'risk_overview_snapshot',
        snapshotAt: '2026-03-27T08:50:00Z',
        sources: {},
        realtimeOverlay: []
      }
    }
  })),
  getRiskLimits: vi.fn(async () => ({
    data: {
      maxPositionSize: 35,
      maxLossPerTrade: 1000,
      maxDailyLoss: 5000,
      maxDrawdown: 20,
      volatilityLimit: 50
    }
  })),
  updateRiskLimits: vi.fn(async () => ({})),
  setStopLoss: vi.fn(async () => ({})),
  setTakeProfit: vi.fn(async () => ({})),
  cancelStopLoss: vi.fn(async () => ({})),
  cancelTakeProfit: vi.fn(async () => ({}))
}))

vi.mock('../../src/api/trade.js', () => ({
  getTradeSnapshotState: vi.fn(async () => ({
    data: {
      positions: [
        { symbol: 'AAPL.US', quantity: 10, currentPrice: 194 }
      ],
      snapshotAt: '2026-03-27T09:00:00Z',
      dataSource: 'trade_snapshot',
      meta: {
        snapshotAt: '2026-03-27T09:00:00Z',
        dataSource: 'trade_snapshot'
      }
    }
  }))
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(() => Promise.resolve()) }),
  useRoute: () => ({ params: { symbol: 'AAPL.US' }, query: {} })
}))

const mountOptions = {
  global: {
    stubs: {
      'el-alert': true,
      'el-button': { template: '<button><slot /></button>' },
      'el-card': { template: '<section class="el-card"><slot name="header" /><slot /></section>' },
      'el-empty': true,
      'el-icon': true,
      'el-input': { template: '<div class="el-input"><slot /><slot name="append" /></div>' },
      'el-pagination': true,
      'el-radio-button': { template: '<button><slot /></button>' },
      'el-radio-group': { template: '<div class="el-radio-group"><slot /></div>' },
      'el-rate': true,
      'el-table': { template: '<div class="el-table"><slot /><slot name="empty" /></div>' },
      'el-table-column': true,
      'el-tag': { template: '<span class="el-tag"><slot /></span>' },
      'el-tab-pane': { template: '<div class="el-tab-pane"><slot /></div>' },
      'el-tabs': { template: '<div class="el-tabs"><slot /></div>' }
    }
  }
}

describe('market shell pages', () => {
  it('uses shared page shell components in recommendations view', async () => {
    const wrapper = shallowMount(Recommendations, mountOptions)
    await flushPromises()

    expect(wrapper.find('page-hero-stub').exists()).toBe(true)
    expect(wrapper.find('metric-strip-stub').exists()).toBe(true)
    expect(wrapper.findAll('section-card-header-stub').length).toBeGreaterThanOrEqual(3)
  })

  it('uses shared page shell components in finance news view', async () => {
    const wrapper = shallowMount(FinanceNews, mountOptions)
    await flushPromises()

    expect(wrapper.find('page-hero-stub').exists()).toBe(true)
    expect(wrapper.find('metric-strip-stub').exists()).toBe(true)
    expect(wrapper.findAll('section-card-header-stub').length).toBeGreaterThanOrEqual(1)
  })

  it('uses shared page shell components in symbol detail view', async () => {
    const wrapper = shallowMount(SymbolDetail, mountOptions)
    await flushPromises()

    expect(wrapper.find('page-hero-stub').exists()).toBe(true)
    expect(wrapper.find('metric-strip-stub').exists()).toBe(true)
    expect(wrapper.findAll('section-card-header-stub').length).toBeGreaterThanOrEqual(4)
  })

  it('uses shared page shell components in kline view', async () => {
    const wrapper = shallowMount(Kline, mountOptions)
    await flushPromises()

    expect(wrapper.find('page-hero-stub').exists()).toBe(true)
    expect(wrapper.find('metric-strip-stub').exists()).toBe(true)
    expect(wrapper.findAll('section-card-header-stub').length).toBeGreaterThanOrEqual(4)
  })

  it('uses shared page shell components in strategy view', async () => {
    const wrapper = shallowMount(Strategy, mountOptions)
    await flushPromises()

    expect(wrapper.find('page-hero-stub').exists()).toBe(true)
    expect(wrapper.find('metric-strip-stub').exists()).toBe(true)
    expect(wrapper.findAll('section-card-header-stub').length).toBeGreaterThanOrEqual(3)
  })

  it('uses shared page shell components in risk management view', async () => {
    const wrapper = shallowMount(RiskManagement, mountOptions)
    await flushPromises()

    expect(wrapper.find('page-hero-stub').exists()).toBe(true)
    expect(wrapper.find('metric-strip-stub').exists()).toBe(true)
    expect(wrapper.findAll('section-card-header-stub').length).toBeGreaterThanOrEqual(2)
  })
})

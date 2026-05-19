import { flushPromises, shallowMount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Trading from '../../src/views/Trading.vue'

const routeState = {
  query: {
    symbol: 'AAPL.US',
    action: ''
  }
}

const marketMocks = vi.hoisted(() => ({
  getDashboardMarketInsights: vi.fn(),
  getLongbridgeAnnouncements: vi.fn(),
  getLongbridgeDepth: vi.fn(),
  getLongbridgeNews: vi.fn(),
  getLongbridgeSnapshot: vi.fn(),
  getLongbridgeTopics: vi.fn(),
  getLongbridgeTrades: vi.fn(),
  getStockQuote: vi.fn(),
  getSymbolOverview: vi.fn()
}))

const tradeMocks = vi.hoisted(() => ({
  buyStock: vi.fn(),
  getBrokerAccounts: vi.fn(),
  getProjectedOrders: vi.fn(),
  getTradeSnapshotState: vi.fn(),
  sellStock: vi.fn()
}))

const analysisMocks = vi.hoisted(() => ({
  getQuantStatus: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState
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

vi.mock('../../src/composables/useAdaptiveLayout.js', () => ({
  useAdaptiveLayout: () => ({ isPhoneLayout: ref(false) })
}))

vi.mock('../../src/composables/useWebSocket.js', () => ({
  useLongbridgeMarketStream: () => ({
    quotes: ref({}),
    depth: ref({}),
    trades: ref({}),
    isConnected: ref(false)
  }),
  useOrderStream: () => ({
    orders: ref([]),
    dataSource: ref(''),
    snapshotAt: ref(''),
    meta: ref({}),
    lastReceivedAt: ref(''),
    subscriptionAccountId: ref(null),
    subscriptionStatus: ref('')
  }),
  useStockQuotes: () => ({
    quotes: ref({}),
    isConnected: ref(false)
  })
}))

vi.mock('../../src/utils/auth.js', () => ({
  getAccess: () => ({ canTradeLive: false }),
  getCurrentUser: () => ({ id: 1, username: 'tester' })
}))

vi.mock('../../src/api/analysis.js', () => analysisMocks)
vi.mock('../../src/api/market.js', () => marketMocks)
vi.mock('../../src/api/trade.js', () => tradeMocks)

const createDeferred = () => {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const baseOverviewPayload = {
  symbol: 'AAPL.US',
  fundamentals: {
    name: 'Apple',
    sector: 'Technology',
    pe_ratio: 29.1,
    market_cap: 3000000000000
  },
  snapshots: {
    daily: {
      closePrice: 189.4,
      prevClose: 188.1,
      changePercent: 0.69,
      openPrice: 188.8,
      highPrice: 190.2,
      lowPrice: 188.4,
      volume: 1234000,
      snapshotDate: '2026-05-19T09:30:00Z'
    }
  },
  quoteSnapshot: {
    price: 189.4,
    prevClose: 188.1,
    changePercent: 0.69,
    session: 'regular',
    snapshotAt: '2026-05-19T09:30:00Z'
  },
  contentCache: {
    dataSource: 'content-cache',
    updatedAt: '2026-05-19T09:29:00Z',
    totalCount: 1,
    announcements: {
      items: [
        {
          id: 'announcement-1',
          title: '缓存公告标题',
          description: '缓存公告摘要',
          published_at: '2026-05-19T09:00:00Z',
          data_source: 'content-cache'
        }
      ]
    },
    news: { items: [] },
    topics: { items: [] }
  }
}

const mountTrading = () => shallowMount(Trading, {
  global: {
    renderStubDefaultSlot: true,
    stubs: {
      PageHero: {
        props: ['title'],
        template: '<section class="page-hero"><span>{{ title }}</span><slot /><slot name="actions" /></section>'
      },
      ReadModelSourceStrip: {
        props: ['statusText', 'detail', 'updatedAt', 'tags'],
        template: '<div class="read-model-strip">{{ statusText }} {{ detail }} {{ updatedAt }} <span v-for="(tag, index) in tags" :key="index">{{ tag.text }}</span></div>'
      },
      SectionCardHeader: {
        props: ['title', 'badge'],
        template: '<header class="section-card-header"><span>{{ title }}</span><span>{{ badge }}</span><slot /><slot name="actions" /></header>'
      },
      MobileSegmentControl: true,
      'el-select': { template: '<div class="el-select"><slot /></div>' },
      'el-option': true,
      'el-form': { template: '<form><slot /></form>' },
      'el-form-item': { template: '<div class="el-form-item"><slot /></div>' },
      'el-input': { template: '<div class="el-input"><slot /><slot name="append" /></div>' },
      'el-button': {
        props: ['loading', 'disabled', 'type', 'size', 'plain', 'link', 'icon'],
        emits: ['click'],
        template: '<button :data-loading="String(loading)" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
      },
      'el-radio-group': { template: '<div class="el-radio-group"><slot /></div>' },
      'el-radio-button': { template: '<button><slot /></button>' },
      'el-input-number': { template: '<input class="el-input-number" />' },
      'el-card': { template: '<section class="el-card"><slot name="header" /><slot /></section>' },
      'el-tag': { template: '<span class="el-tag"><slot /></span>' },
      'el-empty': { props: ['description'], template: '<div class="el-empty">{{ description }}</div>' },
      'el-table': { template: '<div class="el-table"><slot name="empty" /></div>' },
      'el-table-column': { template: '<div class="el-table-column-stub"></div>' },
      'el-icon': { template: '<i><slot /></i>' },
      'el-drawer': { template: '<div class="el-drawer"><slot /></div>' }
    }
  }
})

const findButtonByText = (wrapper, text) => (
  wrapper.findAll('button').find((item) => item.text().includes(text))
)

describe('Trading search performance', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeState.query.symbol = 'AAPL.US'
    routeState.query.action = ''

    analysisMocks.getQuantStatus.mockResolvedValue({
      data: { enabled: false, autoExecute: false, signals: [] }
    })
    marketMocks.getDashboardMarketInsights.mockResolvedValue({ data: [] })
    tradeMocks.getBrokerAccounts.mockResolvedValue({ data: [] })
    tradeMocks.getTradeSnapshotState.mockResolvedValue({ data: {} })
    tradeMocks.getProjectedOrders.mockResolvedValue({ data: { list: [], meta: {} } })
    tradeMocks.buyStock.mockResolvedValue({})
    tradeMocks.sellStock.mockResolvedValue({})
    marketMocks.getLongbridgeAnnouncements.mockResolvedValue({ data: { payload: [] } })
    marketMocks.getLongbridgeNews.mockResolvedValue({ data: { payload: [] } })
    marketMocks.getLongbridgeTopics.mockResolvedValue({ data: { payload: [] } })
    marketMocks.getLongbridgeDepth.mockResolvedValue({ data: { payload: { bids: [], asks: [] } } })
    marketMocks.getLongbridgeTrades.mockResolvedValue({ data: { payload: [] } })
    marketMocks.getStockQuote.mockResolvedValue({ data: {} })
  })

  it('releases quote loading on symbol overview before slow Longbridge snapshot completes', async () => {
    const snapshotDeferred = createDeferred()

    marketMocks.getSymbolOverview.mockResolvedValue({
      data: baseOverviewPayload
    })
    marketMocks.getLongbridgeSnapshot.mockReturnValue(snapshotDeferred.promise)

    const wrapper = mountTrading()
    await flushPromises()

    expect(marketMocks.getSymbolOverview).toHaveBeenCalledWith('AAPL.US')
    expect(findButtonByText(wrapper, '搜索').attributes('data-loading')).toBe('false')
    expect(wrapper.text()).toContain('$189.40')
    expect(wrapper.text()).toContain('行情快照')
    expect(wrapper.text()).toContain('缓存公告标题')
    expect(wrapper.text()).toContain('等待深度')
    expect(wrapper.text()).toContain('等待逐笔')

    snapshotDeferred.resolve({
      data: {
        payload: {
          quote: [{
            symbol: 'AAPL.US',
            name: 'Apple Inc.',
            price: 190.11,
            prev_close: 188.1,
            change_percent: 1.07,
            quoteSource: 'longbridge-cli',
            timestamp: '2026-05-19T09:31:20Z'
          }],
          depth: {
            bids: [{ price: 190.05, volume: 500 }],
            asks: [{ price: 190.2, volume: 600 }]
          },
          trades: [
            {
              trade_id: 't-1',
              price: 190.12,
              volume: 300,
              trade_direction: 'buy',
              timestamp: '2026-05-19T09:31:21Z'
            }
          ],
          sources: { quote: 'longbridge-live', depth: 'longbridge-live', trades: 'longbridge-live' }
        }
      }
    })

    await flushPromises()

    expect(wrapper.text()).toContain('$190.11')
    expect(wrapper.text()).toContain('Longbridge CLI')
    expect(wrapper.text()).toContain('$190.05 / $190.20')
    expect(wrapper.text()).toContain('1 条')
    expect(marketMocks.getLongbridgeDepth).not.toHaveBeenCalled()
    expect(marketMocks.getLongbridgeTrades).not.toHaveBeenCalled()
    expect(marketMocks.getStockQuote).not.toHaveBeenCalled()
  })

  it('uses one Longbridge snapshot request for quote, depth and trades', async () => {
    marketMocks.getSymbolOverview.mockResolvedValue({
      data: baseOverviewPayload
    })
    marketMocks.getLongbridgeSnapshot.mockResolvedValue({
      data: {
        payload: {
          quote: [{ symbol: 'AAPL.US', price: 192.14, prev_close: 188.1, change_percent: 2.15 }],
          depth: { bids: [{ price: 192.1, volume: 100 }], asks: [{ price: 192.2, volume: 120 }] },
          trades: [
          {
            trade_id: 't-1',
            price: 192.16,
            volume: 80,
            trade_direction: 'buy',
            timestamp: '2026-05-19T09:32:21Z'
          }
          ],
          sources: {}
        }
      }
    })

    const wrapper = mountTrading()
    await flushPromises()

    expect(marketMocks.getLongbridgeSnapshot).toHaveBeenCalledWith('AAPL.US', { count: 18 })
    expect(marketMocks.getLongbridgeDepth).not.toHaveBeenCalled()
    expect(marketMocks.getLongbridgeTrades).not.toHaveBeenCalled()
    expect(marketMocks.getStockQuote).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('$192.14')
    expect(wrapper.text()).toContain('$192.10 / $192.20')
    expect(wrapper.text()).toContain('1 条')
  })

  it('keeps content refresh asynchronous when overview cache is empty', async () => {
    const announcementDeferred = createDeferred()
    const newsDeferred = createDeferred()
    const topicsDeferred = createDeferred()

    marketMocks.getSymbolOverview.mockResolvedValue({
      data: {
        ...baseOverviewPayload,
        contentCache: {
          dataSource: 'content-cache-empty',
          updatedAt: '',
          totalCount: 0,
          announcements: { items: [] },
          news: { items: [] },
          topics: { items: [] }
        }
      }
    })
    marketMocks.getLongbridgeSnapshot.mockResolvedValue({
      data: {
        payload: {
          quote: [{
            symbol: 'AAPL.US',
            price: 191.26,
            prev_close: 188.1,
            change_percent: 1.68,
            quoteSource: 'longbridge-cli',
            timestamp: '2026-05-19T09:31:50Z'
          }],
          depth: { bids: [], asks: [] },
          trades: [],
          sources: {}
        }
      }
    })
    marketMocks.getLongbridgeAnnouncements.mockReturnValue(announcementDeferred.promise)
    marketMocks.getLongbridgeNews.mockReturnValue(newsDeferred.promise)
    marketMocks.getLongbridgeTopics.mockReturnValue(topicsDeferred.promise)

    const wrapper = mountTrading()
    await flushPromises()

    expect(findButtonByText(wrapper, '搜索').attributes('data-loading')).toBe('false')
    expect(findButtonByText(wrapper, '回源刷新').attributes('data-loading')).toBe('true')
    expect(marketMocks.getLongbridgeAnnouncements).toHaveBeenCalledWith('AAPL.US')
    expect(marketMocks.getLongbridgeNews).toHaveBeenCalledWith('AAPL.US')
    expect(marketMocks.getLongbridgeTopics).toHaveBeenCalledWith('AAPL.US')

    announcementDeferred.resolve({ data: { payload: [] } })
    newsDeferred.resolve({
      data: {
        payload: [
          {
            id: 'news-1',
            title: '异步资讯标题',
            description: '长桥内容回源后补齐',
            published_at: '2026-05-19T09:15:00Z'
          }
        ],
        dataSource: 'longbridge-content'
      }
    })
    topicsDeferred.resolve({ data: { payload: [] } })

    await flushPromises()

    expect(findButtonByText(wrapper, '回源刷新').attributes('data-loading')).toBe('false')
    expect(wrapper.text()).toContain('异步资讯标题')
    expect(wrapper.text()).toContain('Longbridge CLI')
  })

  it('does not let a slower overview response overwrite a live quote', async () => {
    const overviewDeferred = createDeferred()

    marketMocks.getSymbolOverview.mockReturnValue(overviewDeferred.promise)
    marketMocks.getLongbridgeSnapshot.mockResolvedValue({
      data: {
        payload: {
          quote: [{
            symbol: 'AAPL.US',
            name: 'Apple Inc.',
            price: 193.42,
            prev_close: 188.1,
            change_percent: 2.83,
            quoteSource: 'longbridge-cli',
            timestamp: '2026-05-19T09:32:00Z'
          }],
          depth: { bids: [], asks: [] },
          trades: [],
          sources: {}
        }
      }
    })

    const wrapper = mountTrading()
    await flushPromises()

    expect(wrapper.text()).toContain('$193.42')
    expect(wrapper.text()).toContain('Longbridge CLI')

    overviewDeferred.resolve({
      data: baseOverviewPayload
    })
    await flushPromises()

    expect(wrapper.text()).toContain('$193.42')
    expect(wrapper.text()).toContain('Longbridge CLI')
    expect(wrapper.text()).not.toContain('$189.40')
  })

  it('marks quote as degraded when only the overview fallback succeeds', async () => {
    marketMocks.getSymbolOverview.mockResolvedValue({
      data: baseOverviewPayload
    })
    marketMocks.getLongbridgeSnapshot.mockRejectedValue(new Error('quote unavailable'))

    const wrapper = mountTrading()
    await flushPromises()

    expect(wrapper.text()).toContain('$189.40')
    expect(wrapper.text()).toContain('Quote 降级')
    expect(wrapper.text()).toContain('行情快照')
    expect(wrapper.text()).not.toContain('Quote 失败')
    expect(wrapper.text()).not.toContain('Longbridge CLI')
  })
})

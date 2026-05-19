import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const requestPostMock = vi.fn()

vi.mock('../../src/utils/authPure.js', () => ({
  getTokenLocal: () => ''
}))

vi.mock('../../src/utils/api.js', () => ({
  normalizeOrder: (value) => value
}))

vi.mock('../../src/utils/requestPure.js', () => ({
  getApiBaseUrl: () => 'http://127.0.0.1:3100',
  isDesktopClient: () => false,
  isNativeClient: () => false,
  request: {
    post: requestPostMock
  }
}))

class FakeWebSocket {
  static OPEN = 1
  static instances = []

  constructor(url) {
    this.url = url
    this.readyState = 0
    this.sent = []
    this.onopen = null
    this.onmessage = null
    this.onclose = null
    this.onerror = null
    FakeWebSocket.instances.push(this)
  }

  send(payload) {
    this.sent.push(payload)
  }

  close() {
    this.readyState = 3
    if (this.onclose) {
      this.onclose({})
    }
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    if (this.onopen) {
      this.onopen({})
    }
  }

  emit(payload) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(payload) })
    }
  }
}

const mountHarness = async () => {
  const { useLongbridgeMarketStream } = await import('../../src/composables/useWebSocket.js')
  const Harness = defineComponent({
    setup() {
      const symbols = ref(['AAPL.US'])
      const stream = useLongbridgeMarketStream(symbols, { quoteFlushMs: 0, tradeCount: 5 })
      const setSymbols = (nextSymbols) => {
        symbols.value = nextSymbols
      }
      return {
        symbols,
        setSymbols,
        ...stream
      }
    },
    template: `
      <div>
        <pre class="quotes">{{ JSON.stringify(quotes) }}</pre>
        <pre class="depth">{{ JSON.stringify(depth) }}</pre>
        <pre class="trades">{{ JSON.stringify(trades) }}</pre>
      </div>
    `
  })

  return mount(Harness)
}

describe('useLongbridgeMarketStream', () => {
  let originalWebSocket

  beforeEach(() => {
    vi.clearAllMocks()
    originalWebSocket = globalThis.WebSocket
    globalThis.WebSocket = FakeWebSocket
    FakeWebSocket.instances = []
  })

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket
  })

  it('hydrates quotes, depth, and trades from subscribe snapshots on connect', async () => {
    requestPostMock.mockResolvedValue({
      success: true,
      data: {
        symbols: ['AAPL.US'],
        snapshots: {
          quote: [
            {
              symbol: 'AAPL.US',
              last_price: 189.4,
              prev_close: 188.1,
              timestamp: '2026-05-19T09:30:00Z'
            }
          ],
          depth: {
            'AAPL.US': {
              bids: [{ price: 189.35, volume: 100 }],
              asks: [{ price: 189.45, volume: 200 }]
            }
          },
          trades: {
            'AAPL.US': [
              { trade_id: 't-1', price: 189.41, volume: 50, timestamp: '2026-05-19T09:30:01Z' }
            ]
          }
        }
      }
    })

    const wrapper = await mountHarness()
    FakeWebSocket.instances[0].open()
    await flushPromises()

    expect(requestPostMock).toHaveBeenCalledWith(
      '/svc/market/api/v1/market/longbridge/push/subscribe',
      expect.objectContaining({
        symbols: ['AAPL.US'],
        subTypes: ['quote', 'depth', 'trade', 'brokers'],
        tradeCount: 5
      })
    )
    expect(wrapper.find('.quotes').text()).toContain('"AAPL.US"')
    expect(wrapper.find('.quotes').text()).toContain('"quoteMode":"snapshot"')
    expect(wrapper.find('.depth').text()).toContain('"bids"')
    expect(wrapper.find('.trades').text()).toContain('"trade_id":"t-1"')
  })

  it('keeps the last cached quotes, depth, and trades when a refresh subscribe fails', async () => {
    requestPostMock
      .mockResolvedValueOnce({
        success: true,
        data: {
          symbols: ['AAPL.US'],
          snapshots: {
            quote: [
              {
                symbol: 'AAPL.US',
                last_price: 189.4,
                prev_close: 188.1,
                timestamp: '2026-05-19T09:30:00Z'
              }
            ],
            depth: {
              'AAPL.US': {
                bids: [{ price: 189.35, volume: 100 }]
              }
            },
            trades: {
              'AAPL.US': [
                { trade_id: 't-1', price: 189.41, volume: 50, timestamp: '2026-05-19T09:30:01Z' }
              ]
            }
          }
        }
      })
      .mockResolvedValueOnce({
        success: true,
        data: { symbols: ['AAPL.US'] }
      })
      .mockRejectedValueOnce(new Error('subscribe failed'))

    const wrapper = await mountHarness()
    FakeWebSocket.instances[0].open()
    await flushPromises()

    const initialQuotes = wrapper.find('.quotes').text()
    const initialDepth = wrapper.find('.depth').text()
    const initialTrades = wrapper.find('.trades').text()

    await wrapper.vm.setSymbols(['TSLA.US'])
    await flushPromises()

    expect(requestPostMock).toHaveBeenNthCalledWith(
      2,
      '/svc/market/api/v1/market/longbridge/push/unsubscribe',
      expect.objectContaining({
        symbols: ['AAPL.US'],
        subTypes: ['quote', 'depth', 'trade', 'brokers']
      })
    )
    expect(requestPostMock).toHaveBeenNthCalledWith(
      3,
      '/svc/market/api/v1/market/longbridge/push/subscribe',
      expect.objectContaining({
        symbols: ['TSLA.US'],
        subTypes: ['quote', 'depth', 'trade', 'brokers'],
        tradeCount: 5
      })
    )
    expect(wrapper.find('.quotes').text()).toBe(initialQuotes)
    expect(wrapper.find('.depth').text()).toBe(initialDepth)
    expect(wrapper.find('.trades').text()).toBe(initialTrades)
  })

  it('does not let an older snapshot overwrite a newer pushed quote', async () => {
    requestPostMock
      .mockResolvedValueOnce({
        success: true,
        data: {
          symbols: ['AAPL.US'],
          snapshots: {
            quote: [
              {
                symbol: 'AAPL.US',
                last_price: 189.4,
                prev_close: 188.1,
                timestamp: '2026-05-19T09:30:00Z'
              }
            ],
            depth: {},
            trades: {}
          }
        }
      })
      .mockResolvedValueOnce({
        success: true,
        data: { symbols: ['AAPL.US'] }
      })
      .mockResolvedValueOnce({
        success: true,
        data: {
          symbols: ['AAPL.US'],
          snapshots: {
            quote: [
              {
                symbol: 'AAPL.US',
                last_price: 188.9,
                prev_close: 188.1,
                timestamp: '2026-05-19T09:30:30Z'
              }
            ],
            depth: {},
            trades: {}
          }
        }
      })

    const wrapper = await mountHarness()
    const socket = FakeWebSocket.instances[0]
    socket.open()
    await flushPromises()

    socket.emit({
      type: 'quote',
      symbol: 'AAPL.US',
      timestamp: '2026-05-19T09:31:00Z',
      payload: {
        symbol: 'AAPL.US',
        last_price: 190.6,
        prev_close: 188.1,
        timestamp: '2026-05-19T09:31:00Z'
      }
    })
    await flushPromises()

    await wrapper.vm.setSymbols(['AAPL.US'])
    await flushPromises()

    expect(wrapper.find('.quotes').text()).toContain('"last_price":190.6')
    expect(wrapper.find('.quotes').text()).toContain('"quoteMode":"push"')
  })
})

import { ref, onMounted, onUnmounted, unref, watch } from 'vue'
import { getTokenLocal } from '../utils/authPure.js'
import { normalizeOrder } from '../utils/api.js'
import { getApiBaseUrl, isDesktopClient, isNativeClient, request } from '../utils/requestPure.js'

function resolveServiceOrigin() {
  const baseUrl = String(getApiBaseUrl() || '').trim()
  if (baseUrl) {
    return baseUrl.replace(/\/+$/, '')
  }

  if (typeof window !== 'undefined') {
    return window.location.origin
  }

  return 'http://127.0.0.1:3100'
}

function toWebSocketOrigin(baseUrl = '') {
  try {
    const url = new URL(baseUrl)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = ''
    url.search = ''
    url.hash = ''
    return url.toString().replace(/\/+$/, '')
  } catch {
    return String(baseUrl || '').replace(/^http/i, 'ws').replace(/\/+$/, '')
  }
}

function resolveWebSocketUrl(rawUrl = '') {
  const explicitUrl = String(rawUrl || import.meta.env.VITE_WS_URL || '').trim()
  if (explicitUrl) {
    return explicitUrl
  }

  const token = getTokenLocal()
  if (typeof window !== 'undefined') {
    if (isNativeClient() || isDesktopClient()) {
      const search = token ? `?token=${encodeURIComponent(token)}` : ''
      return `${toWebSocketOrigin(resolveServiceOrigin())}/svc/market/ws/market/longbridge/push${search}`
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const search = token ? `?token=${encodeURIComponent(token)}` : ''
    return `${protocol}//${window.location.host}/svc/market/ws/market/longbridge/push${search}`
  }

  return `ws://127.0.0.1:3100/svc/market/ws/market/longbridge/push${token ? `?token=${encodeURIComponent(token)}` : ''}`
}

function buildServiceWebSocketUrl(path = '') {
  const explicitPath = String(path || '').trim()
  if (!explicitPath) {
    return resolveWebSocketUrl('')
  }
  if (/^wss?:\/\//i.test(explicitPath)) {
    return explicitPath
  }

  const normalizedPath = explicitPath.startsWith('/') ? explicitPath : `/${explicitPath}`
  const token = getTokenLocal()
  const search = token ? `${normalizedPath.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}` : ''

  if (typeof window !== 'undefined') {
    if (isNativeClient() || isDesktopClient()) {
      return `${toWebSocketOrigin(resolveServiceOrigin())}${normalizedPath}${search}`
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}${normalizedPath}${search}`
  }

  return `ws://127.0.0.1:3100${normalizedPath}${search}`
}

async function pushControl(path, payload = {}) {
  const data = await request.post(`/svc/market/api/v1/market/longbridge/push/${path}`, payload)
  if (data?.success === false) {
    const error = new Error(data?.error || 'Push request failed')
    error.data = data
    throw error
  }
  return data
}

function shouldIgnoreStreamError(error) {
  const message = String(error?.message || '')
  const bodyError = String(error?.data?.error || '')
  return (
    message.includes('Failed to fetch') ||
    message.includes('AbortError') ||
    bodyError.includes('Failed to fetch') ||
    bodyError.includes('AbortError')
  )
}

function normalizeQuoteEvent(event = {}) {
  const payload = event?.payload
  if (Array.isArray(payload)) {
    return payload
  }
  if (payload && typeof payload === 'object') {
    return [payload]
  }
  return []
}

function normalizeSymbol(value = '') {
  return String(value || '').trim().toUpperCase()
}

function parseQuoteNumber(value, fallback = 0) {
  if (value === null || value === undefined || value === '') {
    return fallback
  }

  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : fallback
  }

  if (typeof value === 'string') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : fallback
  }

  if (typeof value === 'object') {
    return parseQuoteNumber(
      value.real ?? value.value ?? value.price ?? value.amount ?? value.decimal,
      fallback
    )
  }

  return fallback
}

function hasQuoteValue(value) {
  return value !== null && value !== undefined && value !== ''
}

function resolveFirstQuoteNumber(candidates = [], fallback = null) {
  for (const candidate of candidates) {
    if (!hasQuoteValue(candidate)) {
      continue
    }
    const parsed = parseQuoteNumber(candidate, Number.NaN)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return fallback
}

function resolvePrevClose(row = {}, previousQuote = {}) {
  return resolveFirstQuoteNumber([
    row.prev_close,
    row.prevClose,
    row.previous_close,
    row.previousClose,
    row.pre_market_quote?.prev_close,
    row.pre_market_quote?.prevClose,
    row.post_market_quote?.prev_close,
    row.post_market_quote?.prevClose,
    row.pre_market_prev_close,
    row.post_market_prev_close,
    previousQuote.prev_close,
    previousQuote.prevClose
  ], null)
}

function resolveChangePercent(row = {}, previousQuote = {}, lastPrice = 0, prevClose = null) {
  const explicitChangePercent = resolveFirstQuoteNumber([
    row.change_percent,
    row.change_rate,
    row.changePercent,
    row.changeRate
  ], null)

  if (explicitChangePercent !== null) {
    return explicitChangePercent
  }

  if (Number.isFinite(prevClose) && prevClose !== 0) {
    return ((lastPrice - prevClose) / prevClose) * 100
  }

  return resolveFirstQuoteNumber([
    previousQuote.change_percent,
    previousQuote.changePercent
  ], null)
}

function resolvePayloadSymbol(event = {}, payload = null) {
  const directSymbol = normalizeSymbol(event?.symbol)
  if (directSymbol) {
    return directSymbol
  }
  if (Array.isArray(payload) && payload.length) {
    return normalizeSymbol(payload[0]?.symbol || payload[0]?.security || '')
  }
  if (payload && typeof payload === 'object') {
    return normalizeSymbol(payload.symbol || payload.security || '')
  }
  return ''
}

function toTimestampMs(value) {
  if (value === null || value === undefined || value === '') {
    return 0
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0
  }
  const parsed = Date.parse(String(value))
  return Number.isFinite(parsed) ? parsed : 0
}

function resolveRowTimestamp(row = {}, fallback = '') {
  return (
    row.timestamp ||
    row.updatedAt ||
    row.updated_at ||
    row.receivedAt ||
    row.snapshotAt ||
    row.snapshot_at ||
    fallback ||
    ''
  )
}

function shouldReplaceQuote(previousQuote = {}, nextTimestamp = '', source = 'push') {
  const previousPushTimestamp = toTimestampMs(previousQuote.pushReceivedAt || previousQuote.timestamp)
  const previousSnapshotTimestamp = toTimestampMs(previousQuote.snapshotAt || previousQuote.quoteSnapshotAt)
  const nextTimestampMs = toTimestampMs(nextTimestamp)

  if (!nextTimestampMs) {
    return true
  }

  if (source === 'push') {
    return nextTimestampMs >= previousPushTimestamp
  }

  if (previousPushTimestamp && nextTimestampMs < previousPushTimestamp) {
    return false
  }

  return nextTimestampMs >= previousSnapshotTimestamp
}

function normalizeQuoteRowForState(row = {}, previousQuote = {}, options = {}) {
  const source = String(options?.source || 'push').trim().toLowerCase()
  const isPushSource = source === 'push'
  const eventTimestamp = options?.receivedAt || options?.timestamp || ''
  const timestamp = resolveRowTimestamp(row, eventTimestamp) || new Date().toISOString()
  if (!shouldReplaceQuote(previousQuote, timestamp, source)) {
    return null
  }
  const lastPrice = resolveFirstQuoteNumber(
    [row.last_price, row.last_done, row.price],
    resolveFirstQuoteNumber([previousQuote.last_price, previousQuote.price], 0)
  )
  const prevClose = resolvePrevClose(row, previousQuote)
  const changePercent = resolveChangePercent(row, previousQuote, lastPrice, prevClose)
  const quoteMode = isPushSource ? 'push' : 'snapshot'

  return {
    ...previousQuote,
    ...row,
    last_price: lastPrice,
    price: lastPrice,
    prev_close: prevClose,
    prevClose: prevClose,
    change_percent: changePercent,
    changePercent,
    change: resolveFirstQuoteNumber(
      [row.change, row.change_value, previousQuote.change],
      Number.isFinite(prevClose) && prevClose !== 0 ? lastPrice - prevClose : null
    ),
    volume: Number(resolveFirstQuoteNumber([row.volume, previousQuote.volume], 0)),
    open: resolveFirstQuoteNumber([row.open, previousQuote.open], 0),
    high: resolveFirstQuoteNumber([row.high, previousQuote.high], 0),
    low: resolveFirstQuoteNumber([row.low, previousQuote.low], 0),
    timestamp,
    quoteMode,
    quote_mode: quoteMode,
    quoteSource: isPushSource ? 'longbridge-push' : 'quote-snapshot',
    quote_source: isPushSource ? 'longbridge-push' : 'quote-snapshot',
    isRealtime: isPushSource,
    receivedAt: isPushSource ? timestamp : (previousQuote.receivedAt || timestamp),
    pushReceivedAt: isPushSource ? timestamp : (previousQuote.pushReceivedAt || null),
    snapshotAt: isPushSource ? (previousQuote.snapshotAt || null) : timestamp,
    updatedAt: timestamp,
    pre_market_price: resolveFirstQuoteNumber([row.pre_market_price, previousQuote.pre_market_price], 0),
    post_market_price: resolveFirstQuoteNumber([row.post_market_price, previousQuote.post_market_price], 0),
    after_hours_price: resolveFirstQuoteNumber([row.after_hours_price, previousQuote.after_hours_price], 0),
    session: row.session ?? row.trade_session ?? previousQuote.session ?? '',
    quoteReady: Boolean(
      hasQuoteValue(row.quoteReady)
        ? row.quoteReady
        : hasQuoteValue(previousQuote.quoteReady)
          ? previousQuote.quoteReady
          : timestamp
    ),
    dataStatus: row.dataStatus || row.data_status || previousQuote.dataStatus || previousQuote.data_status || 'ready',
  }
}

function createBatchedQuoteApplier(quotesRef, options = {}) {
  const flushMs = Math.max(0, Number(options.flushMs ?? 120))
  let queuedItems = []
  let flushTimer = null

  const flush = () => {
    flushTimer = null
    if (!queuedItems.length) {
      return
    }

    const items = queuedItems
    queuedItems = []
    const nextQuotes = { ...quotesRef.value }
    let changed = false

    items.forEach(({ row, meta }) => {
      const symbol = normalizeSymbol(row?.symbol)
      if (!symbol) {
        return
      }
      const normalized = normalizeQuoteRowForState(row, nextQuotes[symbol] || {}, meta)
      if (!normalized) {
        return
      }
      nextQuotes[symbol] = normalized
      changed = true
    })

    if (changed) {
      quotesRef.value = nextQuotes
    }
  }

  return (rows = [], meta = {}) => {
    const incomingRows = Array.isArray(rows) ? rows : []
    if (!incomingRows.length) {
      return
    }

    if (flushMs <= 0 || String(meta?.source || '').toLowerCase() === 'snapshot') {
      queuedItems.push(...incomingRows.map((row) => ({ row, meta })))
      flush()
      return
    }

    queuedItems.push(...incomingRows.map((row) => ({ row, meta })))
    if (!flushTimer) {
      flushTimer = window.setTimeout(flush, flushMs)
    }
  }
}

export function useWebSocket(url, options = {}) {
  const {
    autoConnect = true,
    autoReconnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
    heartbeatInterval = 30000,
    heartbeatTimeout = Math.max(heartbeatInterval * 2, heartbeatInterval + 5000),
    onMessage = null,
    onConnect = null,
    onDisconnect = null,
    onError = null
  } = options

  const ws = ref(null)
  const isConnected = ref(false)
  const isConnecting = ref(false)
  const lastMessage = ref(null)
  const lastHeartbeatAt = ref('')
  const error = ref(null)

  let reconnectAttempts = 0
  let reconnectTimer = null
  let heartbeatTimer = null
  let heartbeatTimeoutTimer = null
  let shouldReconnect = autoReconnect

  const clearReconnectTimer = () => {
    if (reconnectTimer) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  const stopHeartbeatTimeout = () => {
    if (heartbeatTimeoutTimer) {
      window.clearTimeout(heartbeatTimeoutTimer)
      heartbeatTimeoutTimer = null
    }
  }

  const resetHeartbeatTimeout = () => {
    stopHeartbeatTimeout()
    if (!shouldReconnect || !heartbeatTimeout) {
      return
    }
    heartbeatTimeoutTimer = window.setTimeout(() => {
      if (!isConnected.value || ws.value?.readyState !== WebSocket.OPEN) {
        return
      }
      error.value = new Error(`WebSocket heartbeat timeout after ${heartbeatTimeout}ms`)
      ws.value.close(4000, 'heartbeat-timeout')
    }, heartbeatTimeout)
  }

  const markHeartbeat = (timestamp = '') => {
    lastHeartbeatAt.value = timestamp || new Date().toISOString()
    resetHeartbeatTimeout()
  }

  const startHeartbeat = () => {
    if (heartbeatTimer) {
      return
    }
    resetHeartbeatTimeout()
    heartbeatTimer = window.setInterval(() => {
      if (isConnected.value && ws.value?.readyState === WebSocket.OPEN) {
        ws.value.send(JSON.stringify({ action: 'ping' }))
      }
    }, heartbeatInterval)
  }

  const stopHeartbeat = () => {
    if (heartbeatTimer) {
      window.clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    stopHeartbeatTimeout()
  }

  const connect = () => {
    if (isConnected.value || isConnecting.value) {
      return
    }

    isConnecting.value = true
    error.value = null
    shouldReconnect = autoReconnect
    clearReconnectTimer()

    try {
      ws.value = new WebSocket(resolveWebSocketUrl(url))
      ws.value.onopen = () => {
        isConnected.value = true
        isConnecting.value = false
        reconnectAttempts = 0
        markHeartbeat()
        startHeartbeat()
        if (onConnect) {
          onConnect()
        }
      }

      ws.value.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          lastMessage.value = data
          const isSystemHeartbeat = data?.type === 'system' && (
            data?.payload?.kind === 'heartbeat' ||
            String(data?.channel || '').endsWith('.heartbeat')
          )
          if (data?.type === 'pong' || isSystemHeartbeat) {
            markHeartbeat(data?.receivedAt || data?.timestamp || '')
            return
          }
          markHeartbeat(data?.receivedAt || data?.timestamp || '')
          if (onMessage) {
            onMessage(data)
          }
        } catch (parseError) {
          lastMessage.value = event.data
          markHeartbeat()
          if (onMessage) {
            onMessage(event.data)
          }
        }
      }

      ws.value.onclose = () => {
        isConnected.value = false
        isConnecting.value = false
        stopHeartbeat()
        if (onDisconnect) {
          onDisconnect()
        }
        if (shouldReconnect && reconnectAttempts < maxReconnectAttempts) {
          reconnectAttempts += 1
          reconnectTimer = window.setTimeout(connect, reconnectInterval)
        }
      }

      ws.value.onerror = (event) => {
        error.value = event
        isConnecting.value = false
        if (onError) {
          onError(event)
        }
      }
    } catch (connectError) {
      error.value = connectError
      isConnecting.value = false
      if (onError) {
        onError(connectError)
      }
    }
  }

  const disconnect = () => {
    shouldReconnect = false
    clearReconnectTimer()
    stopHeartbeat()
    if (ws.value) {
      ws.value.close()
    }
    ws.value = null
    isConnected.value = false
    isConnecting.value = false
  }

  const send = (payload) => {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      return false
    }
    ws.value.send(typeof payload === 'string' ? payload : JSON.stringify(payload))
    return true
  }

  const subscribe = async (symbols, _userId = null, subTypes = ['quote'], extra = {}) => {
    const items = Array.isArray(symbols) ? symbols : [symbols]
    const filtered = items.map((item) => String(item || '').trim().toUpperCase()).filter(Boolean)
    if (!filtered.length) {
      return { success: true, data: { symbols: [], snapshots: {} } }
    }
    return pushControl('subscribe', { symbols: filtered, subTypes, ...extra })
  }

  const unsubscribe = async (symbols, subTypes = ['quote']) => {
    const items = Array.isArray(symbols) ? symbols : [symbols]
    const filtered = items.map((item) => String(item || '').trim().toUpperCase()).filter(Boolean)
    if (!filtered.length) {
      return { success: true, data: { symbols: [] } }
    }
    return pushControl('unsubscribe', { symbols: filtered, subTypes })
  }

  onMounted(() => {
    if (autoConnect) {
      connect()
    }
  })

  onUnmounted(() => {
    disconnect()
  })

  return {
    ws,
    isConnected,
    isConnecting,
    lastMessage,
    lastHeartbeatAt,
    error,
    connect,
    disconnect,
    send,
    subscribe,
    unsubscribe
  }
}

export function useStockQuotes(symbols, options = {}) {
  const quotes = ref({})
  const { userId = null, url = '' } = options
  const wsUrl = resolveWebSocketUrl(url)
  const applyQuoteRows = createBatchedQuoteApplier(quotes, { flushMs: options.quoteFlushMs ?? 120 })

  const {
    subscribe,
    unsubscribe,
    isConnected: wsConnected,
    lastHeartbeatAt
  } = useWebSocket(wsUrl, {
    autoConnect: true,
    onConnect: async () => {
      if (symbols.value && symbols.value.length > 0) {
        try {
          const response = await subscribe(symbols.value, userId, ['quote'])
          const snapshotRows = Array.isArray(response?.data?.snapshots?.quote) ? response.data.snapshots.quote : []
          applyQuoteRows(snapshotRows, { source: 'snapshot' })
        } catch (error) {
          if (!shouldIgnoreStreamError(error)) {
            console.error('订阅实时行情失败:', error)
          }
        }
      }
    },
    onMessage: (data) => {
      if (data?.type === 'quote') {
        applyQuoteRows(normalizeQuoteEvent(data), { source: 'push', receivedAt: data?.receivedAt, timestamp: data?.timestamp })
      }
    }
  })

  watch(
    symbols,
    async (newSymbols, oldSymbols) => {
      if (!wsConnected.value) {
        return
      }
      const nextSymbols = Array.isArray(newSymbols) ? newSymbols : []
      const prevSymbols = Array.isArray(oldSymbols) ? oldSymbols : []

      if (prevSymbols.length) {
        try {
          await unsubscribe(prevSymbols, ['quote'])
        } catch (error) {
          if (!shouldIgnoreStreamError(error)) {
            console.error('取消订阅实时行情失败:', error)
          }
        }
      }

      if (nextSymbols.length) {
        try {
          const response = await subscribe(nextSymbols, userId, ['quote'])
          const snapshotRows = Array.isArray(response?.data?.snapshots?.quote) ? response.data.snapshots.quote : []
          applyQuoteRows(snapshotRows, { source: 'snapshot' })
        } catch (error) {
          if (!shouldIgnoreStreamError(error)) {
            console.error('订阅实时行情失败:', error)
          }
        }
      }
    },
    { deep: true }
  )

  return {
    quotes,
    isConnected: wsConnected,
    lastHeartbeatAt,
    subscribe,
    unsubscribe
  }
}

export function useLongbridgeMarketStream(symbols, options = {}) {
  const {
    userId = null,
    url = '',
    subTypes = ['quote', 'depth', 'trade', 'brokers'],
    tradeCount = 20
  } = options

  const wsUrl = resolveWebSocketUrl(url)
  const quotes = ref({})
  const depth = ref({})
  const brokers = ref({})
  const trades = ref({})
  const latestEvents = ref([])
  const applyQuoteRows = createBatchedQuoteApplier(quotes, { flushMs: options.quoteFlushMs ?? 120 })

  const applyDepthSnapshot = (payload = {}, symbolHint = '') => {
    const symbol = normalizeSymbol(symbolHint || resolvePayloadSymbol({}, payload))
    if (!symbol) {
      return
    }
    depth.value[symbol] = payload || {}
  }

  const applyBrokersSnapshot = (payload = {}, symbolHint = '') => {
    const symbol = normalizeSymbol(symbolHint || resolvePayloadSymbol({}, payload))
    if (!symbol) {
      return
    }
    brokers.value[symbol] = payload || {}
  }

  const applyTradesSnapshot = (payload = [], symbolHint = '') => {
    const rows = Array.isArray(payload) ? payload : payload ? [payload] : []
    const symbol = normalizeSymbol(symbolHint || resolvePayloadSymbol({}, rows))
    if (!symbol) {
      return
    }
    trades.value[symbol] = rows
  }

  const applySnapshotResponse = (response = {}) => {
    const snapshots = response?.data?.snapshots || {}
    const quoteRows = Array.isArray(snapshots.quote) ? snapshots.quote : []
    applyQuoteRows(quoteRows, { source: 'snapshot' })

    const depthMap = snapshots.depth && typeof snapshots.depth === 'object' ? snapshots.depth : {}
    Object.entries(depthMap).forEach(([symbol, payload]) => applyDepthSnapshot(payload, symbol))

    const brokerMap = snapshots.brokers && typeof snapshots.brokers === 'object' ? snapshots.brokers : {}
    Object.entries(brokerMap).forEach(([symbol, payload]) => applyBrokersSnapshot(payload, symbol))

    const tradeMap = snapshots.trades && typeof snapshots.trades === 'object' ? snapshots.trades : {}
    Object.entries(tradeMap).forEach(([symbol, payload]) => applyTradesSnapshot(payload, symbol))
  }

  const pushLatestEvent = (event) => {
    latestEvents.value = [event, ...latestEvents.value].slice(0, 40)
  }

  const { subscribe, unsubscribe, isConnected, isConnecting, lastMessage, lastHeartbeatAt, error, connect, disconnect, send } = useWebSocket(wsUrl, {
    autoConnect: true,
    onConnect: async () => {
      const nextSymbols = Array.isArray(symbols.value) ? symbols.value : []
      if (!nextSymbols.length) {
        return
      }
      try {
        const response = await subscribe(nextSymbols, userId, subTypes, { tradeCount })
        applySnapshotResponse(response)
      } catch (streamError) {
        if (!shouldIgnoreStreamError(streamError)) {
          console.error('订阅 Longbridge 推送失败:', streamError)
        }
      }
    },
    onMessage: (event) => {
      if (!event?.type || event.type === 'system') {
        return
      }
      pushLatestEvent(event)
      if (event.type === 'quote') {
        applyQuoteRows(normalizeQuoteEvent(event), { source: 'push', receivedAt: event?.receivedAt, timestamp: event?.timestamp })
        return
      }
      if (event.type === 'depth') {
        applyDepthSnapshot(event.payload, event.symbol)
        return
      }
      if (event.type === 'brokers') {
        applyBrokersSnapshot(event.payload, event.symbol)
        return
      }
      if (event.type === 'trades') {
        applyTradesSnapshot(event.payload, event.symbol)
      }
    }
  })

  watch(
    symbols,
    async (newSymbols, oldSymbols) => {
      if (!isConnected.value) {
        return
      }

      const nextSymbols = Array.isArray(newSymbols) ? newSymbols.map(normalizeSymbol).filter(Boolean) : []
      const prevSymbols = Array.isArray(oldSymbols) ? oldSymbols.map(normalizeSymbol).filter(Boolean) : []

      if (prevSymbols.length) {
        try {
          await unsubscribe(prevSymbols, subTypes)
        } catch (streamError) {
          if (!shouldIgnoreStreamError(streamError)) {
            console.error('取消 Longbridge 推送订阅失败:', streamError)
          }
        }
      }

      if (nextSymbols.length) {
        try {
          const response = await subscribe(nextSymbols, userId, subTypes, { tradeCount })
          applySnapshotResponse(response)
        } catch (streamError) {
          if (!shouldIgnoreStreamError(streamError)) {
            console.error('更新 Longbridge 推送订阅失败:', streamError)
          }
        }
      }
    },
    { deep: true }
  )

  return {
    quotes,
    depth,
    brokers,
    trades,
    latestEvents,
    isConnected,
    isConnecting,
    lastMessage,
    lastHeartbeatAt,
    error,
    connect,
    disconnect,
    send,
    subscribe,
    unsubscribe
  }
}

export function useNotifications(options = {}) {
  const notifications = ref([])
  const unreadCount = ref(0)
  const wsUrl = resolveWebSocketUrl(options.url)

  const { isConnected } = useWebSocket(wsUrl, {
    autoConnect: true,
    onMessage: (data) => {
      if (data?.type === 'notification') {
        notifications.value.unshift({
          ...data.data,
          id: Date.now(),
          read: false,
          timestamp: data.timestamp
        })
        unreadCount.value += 1
        if (notifications.value.length > 50) {
          notifications.value = notifications.value.slice(0, 50)
        }
      }
    },
    ...options
  })

  const markAsRead = (notificationId) => {
    const notification = notifications.value.find((item) => item.id === notificationId)
    if (notification && !notification.read) {
      notification.read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    }
  }

  const markAllAsRead = () => {
    notifications.value.forEach((item) => {
      item.read = true
    })
    unreadCount.value = 0
  }

  const clearNotifications = () => {
    notifications.value = []
    unreadCount.value = 0
  }

  return {
    notifications,
    unreadCount,
    isConnected,
    markAsRead,
    markAllAsRead,
    clearNotifications
  }
}

export function useOrderStream(accountIdRef, statusRef, options = {}) {
  const orders = ref([])
  const dataSource = ref('order-projection')
  const snapshotAt = ref('')
  const streamMeta = ref({})
  const lastReceivedAt = ref('')
  const subscriptionAccountId = ref(null)
  const subscriptionStatus = ref('')
  const limit = Math.max(1, Math.min(Number(options.limit || 200), 500))
  const wsUrl = buildServiceWebSocketUrl(options.url || '/svc/trade/ws/trade/orders')

  const applyOrderRows = (rows = [], meta = {}) => {
    orders.value = (Array.isArray(rows) ? rows : []).map((item) => normalizeOrder(item))
    dataSource.value = meta?.dataSource || 'order-projection'
    snapshotAt.value = meta?.snapshotAt || ''
    lastReceivedAt.value = meta?.receivedAt || ''
    subscriptionAccountId.value = meta?.accountId ?? null
    subscriptionStatus.value = meta?.status || ''
    const upstreamMeta = meta?.meta && typeof meta.meta === 'object' ? meta.meta : {}
    const query = upstreamMeta?.query && typeof upstreamMeta.query === 'object'
      ? upstreamMeta.query
      : {
          accountId: meta?.accountId ?? null,
          status: meta?.status || '',
          limit
        }
    streamMeta.value = {
      ...upstreamMeta,
      dataSource: meta?.dataSource || upstreamMeta?.dataSource || 'order-projection',
      snapshotAt: meta?.snapshotAt || upstreamMeta?.snapshotAt || '',
      query
    }
  }

  const { isConnected, isConnecting, lastMessage, lastHeartbeatAt, error, connect, disconnect, send } = useWebSocket(wsUrl, {
    autoConnect: true,
    onConnect: () => {
      send({
        action: 'subscribe',
        accountId: unref(accountIdRef) || null,
        status: unref(statusRef) || '',
        limit
      })
    },
    onMessage: (event) => {
      if (event?.type === 'orders') {
        applyOrderRows(event.payload, event)
      }
    }
  })

  watch(
    [accountIdRef, statusRef],
    () => {
      if (!isConnected.value) {
        return
      }
      send({
        action: 'subscribe',
        accountId: unref(accountIdRef) || null,
        status: unref(statusRef) || '',
        limit
      })
    }
  )

  return {
    orders,
    dataSource,
    snapshotAt,
    meta: streamMeta,
    lastReceivedAt,
    subscriptionAccountId,
    subscriptionStatus,
    isConnected,
    isConnecting,
    lastMessage,
    lastHeartbeatAt,
    error,
    connect,
    disconnect,
    send
  }
}

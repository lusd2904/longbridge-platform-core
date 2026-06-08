const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const { resolveBaseUrl } = require('./base_url_helper.cjs')

const ROOT_DIR = path.resolve(__dirname, '..')
const DEFAULT_OUTPUT_PATH = path.join(ROOT_DIR, '.omx/artifacts/benchmarks/admin-benchmark.json')
const HELP_TEXT = `Admin benchmark smoke script

Usage:
  node scripts/admin_benchmark_smoke.cjs
  BENCHMARK_OUTPUT=.omx/artifacts/benchmarks/admin-benchmark.json node scripts/admin_benchmark_smoke.cjs
  BENCHMARK_ITERATIONS=1 BENCHMARK_ONLY=health node scripts/admin_benchmark_smoke.cjs

Environment:
  BENCHMARK_BASE_URL     Base URL for the gateway (default: http://127.0.0.1:3100)
  BENCHMARK_USERNAME     Login username (default: admin)
  BENCHMARK_PASSWORD     Login password (default: admin123)
  BENCHMARK_ITERATIONS   Samples per endpoint (default: 3)
  BENCHMARK_TIMEOUT_MS   Request timeout in ms (default: 15000)
  BENCHMARK_LIMIT        Page/list size for list endpoints (default: 20)
  BENCHMARK_DELAY_MS     Delay between samples in ms (default: 150)
  BENCHMARK_ONLY         Comma-separated endpoint ids to run
  BENCHMARK_OUTPUT       Artifact path for JSON output (default: ${DEFAULT_OUTPUT_PATH})
`

const BASE_URL = resolveBaseUrl('BENCHMARK_BASE_URL', {
  fallback: 'http://127.0.0.1:3100',
  example: 'http://127.0.0.1:3100'
})
const USERNAME = process.env.BENCHMARK_USERNAME || 'admin'
const PASSWORD = process.env.BENCHMARK_PASSWORD || 'admin123'
const ITERATIONS = parsePositiveInt(process.env.BENCHMARK_ITERATIONS, 3)
const TIMEOUT_MS = parsePositiveInt(process.env.BENCHMARK_TIMEOUT_MS, 15000)
const LIMIT = parsePositiveInt(process.env.BENCHMARK_LIMIT, 20)
const OUTPUT_PATH = process.env.BENCHMARK_OUTPUT || DEFAULT_OUTPUT_PATH
const REQUEST_DELAY_MS = parsePositiveInt(process.env.BENCHMARK_DELAY_MS, 150)
const ONLY_SET = parseOnlySet(process.env.BENCHMARK_ONLY || '')
const SHOW_HELP = process.argv.includes('--help') || process.argv.includes('-h')

const DEFAULT_HEADERS = {
  Accept: 'application/json',
  'Content-Type': 'application/json'
}

function parsePositiveInt(rawValue, fallback) {
  const value = Number(rawValue)
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback
}

function parseOnlySet(rawValue) {
  const items = String(rawValue || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
  return items.length ? new Set(items) : null
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function createRequestId() {
  if (typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return crypto.randomBytes(16).toString('hex')
}

function percentile(values, ratio) {
  if (!Array.isArray(values) || values.length === 0) {
    return null
  }
  const sorted = [...values].sort((a, b) => a - b)
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * ratio) - 1))
  return Number(sorted[index].toFixed(2))
}

function roundNumber(value) {
  return Number.isFinite(value) ? Number(value.toFixed(2)) : null
}

function trimText(value, maxLength = 160) {
  const normalized = String(value || '').replace(/\s+/g, ' ').trim()
  if (!normalized) {
    return ''
  }
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1)}…` : normalized
}

function extractErrorBody(data) {
  if (!data || typeof data !== 'object') {
    return trimText(data)
  }
  return trimText(data.error || data.message || data.detail || JSON.stringify(data))
}

function isHtmlResponse(data) {
  if (!data || typeof data !== 'object') {
    return false
  }
  const raw = typeof data.raw === 'string' ? data.raw : ''
  return /^<!doctype html>/i.test(raw.trim()) || /<html[\s>]/i.test(raw)
}

function validateGatewayObservability(payload) {
  if (!payload || typeof payload !== 'object' || isHtmlResponse(payload)) {
    return 'gateway observability did not return JSON'
  }
  const data = payload.data && typeof payload.data === 'object' ? payload.data : payload
  const services = data.services || data.registry
  if (!services || typeof services !== 'object' || Array.isArray(services)) {
    return 'gateway observability missing services registry'
  }
  const status = String(data.status || payload.status || '').trim().toLowerCase()
  if (!status) {
    return 'gateway observability missing status'
  }
  return ''
}

function normalizePath(pathname, query = {}) {
  const url = new URL(pathname, BASE_URL)
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }
    url.searchParams.set(key, String(value))
  })
  return url
}

async function requestJson(method, pathname, options = {}) {
  const url = normalizePath(pathname, options.query || {})
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs || TIMEOUT_MS)
  const startedAt = process.hrtime.bigint()
  const requestId = createRequestId()

  try {
    const response = await fetch(url, {
      method,
      headers: {
        ...DEFAULT_HEADERS,
        ...(options.headers || {}),
        'X-Request-ID': requestId
      },
      body: options.body == null ? undefined : JSON.stringify(options.body),
      signal: controller.signal
    })
    const durationMs = Number(process.hrtime.bigint() - startedAt) / 1e6
    const text = await response.text()
    let data = null
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = { raw: text }
    }
    return {
      ok: response.ok,
      status: response.status,
      durationMs,
      data,
      requestId,
      responseTimeHeader: response.headers.get('x-response-time'),
      url: url.toString()
    }
  } catch (error) {
    const durationMs = Number(process.hrtime.bigint() - startedAt) / 1e6
    return {
      ok: false,
      status: 0,
      durationMs,
      data: { error: error?.message || String(error) },
      requestId,
      responseTimeHeader: null,
      url: url.toString()
    }
  } finally {
    clearTimeout(timeout)
  }
}

function makeAuthHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function createBenchmarkContext(token, authInfo, brokerAccounts = null) {
  const accountId = firstPositiveInt(
    authInfo?.data?.user?.defaultAccountId,
    authInfo?.data?.defaultAccountId,
    authInfo?.data?.accountId,
    findDefaultAccountId(brokerAccounts?.data),
    brokerAccounts?.data?.defaultAccountId,
    brokerAccounts?.data?.accountId
  )
  return {
    token,
    authInfo,
    accountId,
    marketSymbol: 'AAPL.US',
    historySymbols: ['NVDL.US', 'NVDA.US'],
    quoteSymbols: ['AAPL.US', 'TSLA.US', 'NVDA.US'],
    notificationLimit: Math.max(LIMIT, 60),
    orderLimit: Math.max(LIMIT, 20),
    stockPoolPageSize: Math.min(Math.max(LIMIT, 10), 50)
  }
}

function buildSuite(token, authInfo, brokerAccounts = null) {
  const context = createBenchmarkContext(token, authInfo, brokerAccounts)
  const dashboardSummarySpec = context.accountId
    ? {
        id: 'dashboard-summary',
        label: 'Dashboard Summary',
        method: 'GET',
        path: `/svc/trade/api/v1/trade/accounts/${encodeURIComponent(context.accountId)}/summary`,
        headers: makeAuthHeaders(token),
        query: {},
        summarize: (payload) => ({
          available: !isHtmlResponse(payload),
          source: payload?.data?.source || null,
          currency: payload?.data?.currency || null,
          totalAssets: payload?.data?.total_assets ?? payload?.data?.totalAssets ?? null
        })
      }
    : null

  return [
    {
      id: 'auth-info',
      label: 'Auth Info',
      method: 'GET',
      path: '/svc/user/api/v1/auth/info',
      headers: makeAuthHeaders(token),
      summarize: (payload) => ({
        username: payload?.data?.user?.username || payload?.data?.username || null,
        role: payload?.data?.user?.role || payload?.data?.role || null,
        homePath: payload?.data?.navigation?.homePath || null
      })
    },
    {
      id: 'bootstrap',
      label: 'Bootstrap',
      method: 'GET',
      path: '/svc/user/api/v1/users/bootstrap',
      headers: makeAuthHeaders(token),
      summarize: (payload) => ({
        menuCount: Array.isArray(payload?.data?.menus) ? payload.data.menus.length : 0,
        subsystemCount: Array.isArray(payload?.data?.subsystems) ? payload.data.subsystems.length : 0,
        homePath: payload?.data?.navigation?.homePath || null
      })
    },
    {
      id: 'health',
      label: 'Gateway Health',
      method: 'GET',
      path: '/svc/gateway/api/v1/system/observability',
      validate: validateGatewayObservability,
      summarize: (payload) => ({
        status: payload?.data?.status || payload?.status || null,
        serviceCount: payload?.data?.services && typeof payload.data.services === 'object'
          ? Object.keys(payload.data.services).length
          : payload?.services && typeof payload.services === 'object'
            ? Object.keys(payload.services).length
            : 0,
        alertCount: Array.isArray(payload?.data?.alerts) ? payload.data.alerts.length : 0
      })
    },
    {
      id: 'ai-model-catalog',
      label: 'AI Model Catalog',
      method: 'GET',
      path: '/svc/analysis/api/v1/analysis/models',
      headers: makeAuthHeaders(token),
      summarize: (payload) => ({
        modelCount: Array.isArray(payload?.data?.catalog) ? payload.data.catalog.length : 0,
        provider: payload?.data?.provider || null
      })
    },
    dashboardSummarySpec,
    {
      id: 'platform-roles',
      label: 'Platform Roles',
      method: 'GET',
      path: '/svc/user/api/v1/platform/roles',
      headers: makeAuthHeaders(token),
      summarize: (payload) => ({
        roleCount: Array.isArray(payload?.data) ? payload.data.length : 0
      })
    },
    {
      id: 'system-settings',
      label: 'System Settings',
      method: 'GET',
      path: '/svc/user/api/v1/config',
      headers: makeAuthHeaders(token),
      summarize: (payload) => ({
        available: !isHtmlResponse(payload),
        keys: payload?.data && typeof payload.data === 'object' ? Object.keys(payload.data).length : 0,
        systemName: payload?.data?.system_name || payload?.data?.configs?.system_name || null
      })
    },
    {
      id: 'system-logs',
      label: 'System Logs',
      method: 'GET',
      path: '/svc/user/api/v1/system/logs',
      headers: makeAuthHeaders(token),
      query: { limit: LIMIT },
      summarize: (payload) => ({
        itemCount: Array.isArray(payload?.data) ? payload.data.length : 0,
        firstMessage: Array.isArray(payload?.data) && payload.data[0] ? trimText(payload.data[0].message) : ''
      })
    },
    {
      id: 'admin-users',
      label: 'Admin Users',
      method: 'GET',
      path: '/svc/user/api/v1/admin/users',
      headers: makeAuthHeaders(token),
      query: { page: 1, pageSize: LIMIT },
      summarize: (payload) => ({
        userCount: Array.isArray(payload?.data) ? payload.data.length : 0,
        firstUser: Array.isArray(payload?.data) && payload.data[0] ? payload.data[0].username || null : null
      })
    },
    {
      id: 'tasks',
      label: 'Scheduler Tasks',
      method: 'GET',
      path: '/svc/scheduler/api/v1/scheduler/tasks',
      headers: makeAuthHeaders(token),
      summarize: (payload) => ({
        taskCount: Array.isArray(payload?.data) ? payload.data.length : 0,
        firstTask: Array.isArray(payload?.data) && payload.data[0]
          ? payload.data[0].taskKey || payload.data[0].task_key || null
          : null
      })
    },
    {
      id: 'broker-accounts',
      label: 'Broker Accounts',
      method: 'GET',
      path: '/svc/trade/api/v1/trade/accounts',
      headers: makeAuthHeaders(token),
      summarize: (payload) => ({
        accountCount: Array.isArray(payload?.data) ? payload.data.length : 0,
        defaultAccountId: findDefaultAccountId(payload?.data)
      })
    },
    {
      id: 'broker-providers',
      label: 'Broker Providers',
      method: 'GET',
      path: '/svc/trade/api/v1/trade/brokers/providers',
      headers: makeAuthHeaders(token),
      summarize: (payload) => ({
        providerCount: Array.isArray(payload?.data) ? payload.data.length : 0
      })
    },
    {
      id: 'market-stock-pool',
      label: 'Market Stock Pool',
      method: 'GET',
      path: '/svc/market/api/v1/market/stock-pool',
      headers: makeAuthHeaders(token),
      query: {
        market: 'all',
        page: 1,
        page_size: context.stockPoolPageSize
      },
      summarize: (payload) => ({
        itemCount: Array.isArray(payload?.data) ? payload.data.length : 0,
        filteredTotal: payload?.stats?.filtered_total ?? payload?.total ?? null,
        firstSymbol: Array.isArray(payload?.data) && payload.data[0]
          ? payload.data[0].symbol || null
          : null
      })
    },
    {
      id: 'market-stock-pool-search',
      label: 'Market Stock Pool Search',
      method: 'GET',
      path: '/svc/market/api/v1/market/stock-pool',
      headers: makeAuthHeaders(token),
      query: {
        market: 'all',
        search: 'NVDL',
        page: 1,
        page_size: context.stockPoolPageSize
      },
      summarize: (payload) => ({
        itemCount: Array.isArray(payload?.data) ? payload.data.length : 0,
        filteredTotal: payload?.stats?.filtered_total ?? payload?.total ?? null,
        firstSymbol: Array.isArray(payload?.data) && payload.data[0]
          ? payload.data[0].symbol || null
          : null
      })
    },
    {
      id: 'market-insights',
      label: 'Market Insights',
      method: 'GET',
      path: '/svc/market/api/v1/market/insights',
      headers: makeAuthHeaders(token),
      query: { market: 'all' },
      summarize: (payload) => ({
        itemCount: Array.isArray(payload?.data) ? payload.data.length : 0,
        generatedAt: Array.isArray(payload?.data) && payload.data[0]
          ? payload.data[0].generatedAt || payload.data[0].generated_at || null
          : null
      })
    },
    {
      id: 'market-insights-history',
      label: 'Market Insights History',
      method: 'GET',
      path: '/svc/market/api/v1/market/insights/history',
      headers: makeAuthHeaders(token),
      query: { market: 'all', limit: Math.max(LIMIT, 24) },
      summarize: (payload) => ({
        itemCount: Array.isArray(payload?.data) ? payload.data.length : 0,
        latestGeneratedAt: Array.isArray(payload?.data) && payload.data[0]
          ? payload.data[0].generatedAt || payload.data[0].generated_at || null
          : null
      })
    },
    {
      id: 'market-history-compare',
      label: 'Market History Compare',
      method: 'GET',
      path: '/svc/market/api/v1/market/history/compare',
      headers: makeAuthHeaders(token),
      query: {
        symbols: context.historySymbols,
        timeframe: 'daily',
        limit: 180,
        refresh: false
      },
      summarize: (payload) => {
        const series = Array.isArray(payload?.data?.series) ? payload.data.series : []
        const comparison = Array.isArray(payload?.data?.comparison) ? payload.data.comparison : []
        const snapshots = Array.isArray(payload?.data?.snapshots) ? payload.data.snapshots : []
        return {
          symbolCount: Array.isArray(payload?.data?.symbols) ? payload.data.symbols.length : context.historySymbols.length,
          seriesCount: series.length,
          pointCount: series.reduce((sum, item) => sum + (Array.isArray(item?.items) ? item.items.length : 0), 0),
          comparisonCount: comparison.length,
          snapshotCount: snapshots.length,
          snapshotAt: payload?.meta?.snapshotAt || null
        }
      }
    },
    {
      id: 'market-backfill-status',
      label: 'Market Backfill Status',
      method: 'GET',
      path: '/svc/market/api/v1/market/backfill/status',
      headers: makeAuthHeaders(token),
      summarize: (payload) => ({
        available: !isHtmlResponse(payload),
        running: Boolean(payload?.data?.running ?? payload?.data?.isRunning),
        symbolCount: Number(payload?.data?.totalUniverseSymbols ?? payload?.data?.symbolCount ?? payload?.data?.symbol_count ?? 0),
        completedCount: Number(payload?.data?.syncedSymbols ?? payload?.data?.completedCount ?? payload?.data?.completed_count ?? 0),
        coverageRate: Number(payload?.data?.coverageRate ?? 0),
        updatedAt: payload?.data?.updatedAt || payload?.data?.updated_at || null
      })
    },
    {
      id: 'market-history-coverage',
      label: 'Market History Coverage',
      method: 'GET',
      path: '/svc/market/api/v1/market/history/coverage',
      headers: makeAuthHeaders(token),
      query: {
        page: 1,
        page_size: Math.min(context.stockPoolPageSize, 20)
      },
      summarize: (payload) => ({
        total: Number(payload?.data?.total ?? 0),
        itemCount: Array.isArray(payload?.data?.items) ? payload.data.items.length : 0,
        completeCount: Number(payload?.data?.summary?.counts?.complete ?? payload?.data?.summary?.complete ?? payload?.data?.summary?.completeCount ?? 0),
        partialCount: Number(payload?.data?.summary?.counts?.partial ?? payload?.data?.summary?.partial ?? payload?.data?.summary?.partialCount ?? 0),
        missingCount: Number(payload?.data?.summary?.counts?.missing ?? payload?.data?.summary?.missing ?? payload?.data?.summary?.missingCount ?? 0),
        snapshotAt: payload?.meta?.snapshotAt || null
      })
    },
    {
      id: 'market-history-coverage-symbol',
      label: 'Market History Coverage Symbol',
      method: 'GET',
      path: '/svc/market/api/v1/market/history/coverage',
      headers: makeAuthHeaders(token),
      query: {
        search: 'NVDL',
        page: 1,
        page_size: Math.min(context.stockPoolPageSize, 20)
      },
      summarize: (payload) => ({
        total: Number(payload?.data?.total ?? 0),
        itemCount: Array.isArray(payload?.data?.items) ? payload.data.items.length : 0,
        completeCount: Number(payload?.data?.summary?.counts?.complete ?? payload?.data?.summary?.complete ?? payload?.data?.summary?.completeCount ?? 0),
        partialCount: Number(payload?.data?.summary?.counts?.partial ?? payload?.data?.summary?.partial ?? payload?.data?.summary?.partialCount ?? 0),
        missingCount: Number(payload?.data?.summary?.counts?.missing ?? payload?.data?.summary?.missing ?? payload?.data?.summary?.missingCount ?? 0),
        snapshotAt: payload?.meta?.snapshotAt || null
      })
    },
    {
      id: 'longbridge-quotes',
      label: 'Longbridge Quotes',
      method: 'GET',
      path: '/svc/market/api/v1/market/longbridge/quotes',
      headers: makeAuthHeaders(token),
      query: { symbols: context.quoteSymbols },
      summarize: (payload) => {
        const rows = Array.isArray(payload?.data?.payload)
          ? payload.data.payload
          : Array.isArray(payload?.data?.data?.payload)
            ? payload.data.data.payload
            : Array.isArray(payload?.data?.data)
              ? payload.data.data
              : Array.isArray(payload?.data)
                ? payload.data
                : []
        return {
          itemCount: rows.length,
          firstSymbol: rows[0]?.symbol || null
        }
      }
    },
    {
      id: 'longbridge-depth',
      label: 'Longbridge Depth',
      method: 'GET',
      path: '/svc/market/api/v1/market/longbridge/depth',
      headers: makeAuthHeaders(token),
      query: { symbol: context.marketSymbol },
      summarize: (payload) => ({
        bidCount: Array.isArray(payload?.data?.bids) ? payload.data.bids.length : Array.isArray(payload?.data?.bid) ? payload.data.bid.length : 0,
        askCount: Array.isArray(payload?.data?.asks) ? payload.data.asks.length : Array.isArray(payload?.data?.ask) ? payload.data.ask.length : 0
      })
    },
    {
      id: 'longbridge-trades',
      label: 'Longbridge Trades',
      method: 'GET',
      path: '/svc/market/api/v1/market/longbridge/trades',
      headers: makeAuthHeaders(token),
      query: { symbol: context.marketSymbol, count: 18 },
      summarize: (payload) => {
        const rows = Array.isArray(payload?.data?.payload)
          ? payload.data.payload
          : Array.isArray(payload?.data)
            ? payload.data
            : []
        return {
          itemCount: rows.length,
          firstPrice: rows[0]?.price ?? null
        }
      }
    },
    {
      id: 'longbridge-snapshot',
      label: 'Longbridge Snapshot',
      method: 'GET',
      path: '/svc/market/api/v1/market/longbridge/snapshot',
      headers: makeAuthHeaders(token),
      query: { symbol: context.marketSymbol, count: 18 },
      summarize: (payload) => {
        const snapshot = payload?.data?.payload || payload?.data || {}
        const quoteRows = Array.isArray(snapshot?.quote) ? snapshot.quote : []
        const trades = Array.isArray(snapshot?.trades) ? snapshot.trades : []
        const depth = snapshot?.depth || {}
        return {
          symbol: snapshot?.symbol || null,
          quoteCount: quoteRows.length,
          bidCount: Array.isArray(depth?.bids) ? depth.bids.length : Array.isArray(depth?.bid) ? depth.bid.length : 0,
          askCount: Array.isArray(depth?.asks) ? depth.asks.length : Array.isArray(depth?.ask) ? depth.ask.length : 0,
          tradeCount: trades.length
        }
      }
    },
    {
      id: 'symbol-overview',
      label: 'Symbol Overview',
      method: 'GET',
      path: `/svc/market/api/v1/market/symbols/${encodeURIComponent(context.marketSymbol)}/overview`,
      headers: makeAuthHeaders(token),
      summarize: (payload) => ({
        symbol: payload?.data?.symbol || context.marketSymbol,
        name: payload?.data?.name || payload?.data?.security_name || null,
        market: payload?.data?.market || payload?.data?.region || null
      })
    },
    {
      id: 'finance-briefings',
      label: 'Finance Briefings',
      method: 'GET',
      path: '/svc/analysis/api/v1/analysis/finance-briefings',
      headers: makeAuthHeaders(token),
      query: { limit: Math.max(LIMIT, 4) },
      summarize: (payload) => ({
        itemCount: Array.isArray(payload?.data) ? payload.data.length : 0,
        firstTitle: Array.isArray(payload?.data) && payload.data[0]
          ? trimText(payload.data[0].title || payload.data[0].headline || '')
          : ''
      })
    },
    {
      id: 'notifications-all',
      label: 'Notifications All',
      method: 'GET',
      path: '/svc/risk/api/v1/notifications',
      headers: makeAuthHeaders(token),
      query: { limit: context.notificationLimit },
      summarize: (payload) => ({
        itemCount: Array.isArray(payload?.data) ? payload.data.length : 0,
        unreadCount: Array.isArray(payload?.data)
          ? payload.data.filter((item) => item && item.read !== true).length
          : null
      })
    },
    {
      id: 'notifications-trade',
      label: 'Notifications Trade',
      method: 'GET',
      path: '/svc/risk/api/v1/notifications',
      headers: makeAuthHeaders(token),
      query: { limit: context.notificationLimit, type: 'trade' },
      summarize: (payload) => ({
        itemCount: Array.isArray(payload?.data) ? payload.data.length : 0,
        firstType: Array.isArray(payload?.data) && payload.data[0]
          ? payload.data[0].type || null
          : null
      })
    },
    {
      id: 'risk-overview',
      label: 'Risk Overview',
      method: 'GET',
      path: '/svc/risk/api/v1/risk/overview',
      headers: makeAuthHeaders(token),
      summarize: (payload) => ({
        available: !isHtmlResponse(payload),
        status: payload?.data?.status || payload?.status || null,
        alertCount: Number(payload?.data?.alertCount ?? payload?.data?.alert_count ?? payload?.alertCount ?? 0)
      })
    },
    {
      id: 'orders-projection',
      label: 'Orders Projection',
      method: 'GET',
      path: '/svc/trade/api/v1/trade/orders/projection',
      headers: makeAuthHeaders(token),
      query: {
        ...(context.accountId ? { account_id: context.accountId } : {}),
        limit: context.orderLimit
      },
      summarize: (payload) => ({
        itemCount: Array.isArray(payload?.data?.list) ? payload.data.list.length : 0,
        total: payload?.data?.count ?? null,
        dataSource: payload?.data?.dataSource || null
      })
    },
    context.accountId
      ? {
          id: 'positions-snapshot',
          label: 'Positions Snapshot',
          method: 'GET',
          path: `/svc/trade/api/v1/trade/accounts/${encodeURIComponent(context.accountId)}/positions`,
          headers: makeAuthHeaders(token),
          summarize: (payload) => ({
            itemCount: Array.isArray(payload?.data) ? payload.data.length : 0,
            firstSymbol: Array.isArray(payload?.data) && payload.data[0]
              ? payload.data[0].symbol || null
              : null
          })
        }
      : null,
    context.accountId
      ? {
          id: 'positions-projection',
          label: 'Positions Projection',
          method: 'GET',
          path: `/svc/trade/api/v1/trade/accounts/${encodeURIComponent(context.accountId)}/snapshot/state`,
          headers: makeAuthHeaders(token),
          summarize: (payload) => ({
            positionCount: Number(payload?.data?.positionCount ?? payload?.data?.positions?.length ?? 0),
            orderCount: Number(payload?.data?.orderCount ?? payload?.data?.orders?.length ?? 0),
            dataSource: payload?.data?.dataSource || payload?.data?.source || null
          })
        }
      : null
  ].filter(Boolean)
}

function firstPositiveInt(...values) {
  for (const value of values) {
    const parsed = Number(value)
    if (Number.isInteger(parsed) && parsed > 0) {
      return parsed
    }
  }
  return null
}

function findDefaultAccountId(accounts) {
  const rows = Array.isArray(accounts)
    ? accounts
    : Array.isArray(accounts?.data)
      ? accounts.data
      : []
  if (!rows.length) {
    return null
  }
  const found = rows.find((item) => item && (item.is_default || item.isDefault))
  return firstPositiveInt(found?.id, found?.accountId, found?.account_id)
}

async function sampleEndpoint(spec) {
  const samples = []
  let lastResponse = null

  for (let index = 0; index < ITERATIONS; index += 1) {
    const result = await requestJson(spec.method, spec.path, {
      headers: spec.headers,
      query: spec.query,
      body: spec.body
    })
    const validationError = result.ok && typeof spec.validate === 'function'
      ? spec.validate(result.data)
      : ''
    const sample = {
      iteration: index + 1,
      status: result.status,
      ok: result.ok && !validationError,
      durationMs: roundNumber(result.durationMs),
      responseTimeHeader: result.responseTimeHeader,
      requestId: result.requestId,
      error: validationError || (result.ok ? '' : extractErrorBody(result.data))
    }
    samples.push(sample)
    lastResponse = result
    if (REQUEST_DELAY_MS > 0 && index < ITERATIONS - 1) {
      await sleep(REQUEST_DELAY_MS)
    }
  }

  const successDurations = samples.filter((sample) => sample.ok).map((sample) => sample.durationMs)
  const summary = {
    id: spec.id,
    label: spec.label,
    path: spec.path,
    method: spec.method,
    iterations: ITERATIONS,
    okCount: samples.filter((sample) => sample.ok).length,
    failCount: samples.filter((sample) => !sample.ok).length,
    statusCodes: [...new Set(samples.map((sample) => sample.status))],
    p50Ms: percentile(successDurations, 0.5),
    p95Ms: percentile(successDurations, 0.95),
    minMs: successDurations.length ? roundNumber(Math.min(...successDurations)) : null,
    maxMs: successDurations.length ? roundNumber(Math.max(...successDurations)) : null,
    sample: spec.summarize ? spec.summarize(lastResponse?.data || null) : null,
    lastError: lastResponse?.ok ? '' : extractErrorBody(lastResponse?.data),
    unavailable: Boolean(
      lastResponse &&
      (isHtmlResponse(lastResponse.data) || (lastResponse.status === 404 && samples.every((sample) => !sample.ok)))
    ),
    samples
  }

  return summary
}

async function login() {
  const response = await requestJson('POST', '/svc/user/api/v1/auth/login', {
    body: {
      username: USERNAME,
      password: PASSWORD
    },
    timeoutMs: TIMEOUT_MS
  })
  if (!response.ok || !response.data?.success || !response.data?.data?.token) {
    const reason = extractErrorBody(response.data) || `HTTP ${response.status}`
    throw new Error(`login failed: ${reason}`)
  }
  return response
}

function filterSuite(suite) {
  if (!ONLY_SET) {
    return suite
  }
  return suite.filter((spec) => ONLY_SET.has(spec.id))
}

function formatMetric(value) {
  return value == null ? 'n/a' : `${value}ms`
}

function formatConsoleSummary(report) {
  return (Array.isArray(report?.endpoints) ? report.endpoints : []).map((endpoint) => {
    const status = endpoint.okCount > 0 && endpoint.failCount === 0
      ? 'PASS'
      : endpoint.okCount > 0
        ? 'WARN'
        : endpoint.unavailable
          ? 'UNAVAILABLE'
          : 'FAIL'
    const codeText = endpoint.statusCodes?.length ? endpoint.statusCodes.join(',') : 'n/a'
    const errorText = endpoint.lastError ? ` error="${endpoint.lastError}"` : ''
    return [
      `[${status}]`,
      endpoint.id,
      `${endpoint.method} ${endpoint.path}`,
      `ok=${endpoint.okCount}/${endpoint.iterations ?? endpoint.okCount + endpoint.failCount}`,
      `status=${codeText}`,
      `p50=${formatMetric(endpoint.p50Ms)}`,
      `p95=${formatMetric(endpoint.p95Ms)}${errorText}`
    ].join(' ')
  })
}

function printHelp() {
  console.log(HELP_TEXT)
}

async function main() {
  if (SHOW_HELP) {
    printHelp()
    return
  }

  const startedAt = new Date().toISOString()
  const loginResponse = await login()
  const token = loginResponse.data.data.token
  const authInfo = await requestJson('GET', '/svc/user/api/v1/auth/info', {
    headers: makeAuthHeaders(token)
  })

  const brokerAccounts = await requestJson('GET', '/svc/trade/api/v1/trade/accounts', {
    headers: makeAuthHeaders(token)
  })
  const suite = filterSuite(buildSuite(token, authInfo, brokerAccounts.ok ? brokerAccounts.data : null))
  const endpoints = []

  for (const spec of suite) {
    endpoints.push(await sampleEndpoint(spec))
  }

  const report = {
    meta: {
      startedAt,
      finishedAt: new Date().toISOString(),
      baseUrl: BASE_URL,
      username: USERNAME,
      iterations: ITERATIONS,
      timeoutMs: TIMEOUT_MS,
      limit: LIMIT
    },
    login: {
      status: loginResponse.status,
      durationMs: roundNumber(loginResponse.durationMs),
      responseTimeHeader: loginResponse.responseTimeHeader,
      bootstrapHomePath: loginResponse.data?.data?.navigation?.homePath || null,
      role: loginResponse.data?.data?.user?.role || null
    },
    authInfo: authInfo.ok
      ? {
          status: authInfo.status,
          durationMs: roundNumber(authInfo.durationMs),
          responseTimeHeader: authInfo.responseTimeHeader,
          username: authInfo.data?.data?.user?.username || null,
          role: authInfo.data?.data?.user?.role || null
        }
      : {
          status: authInfo.status,
          durationMs: roundNumber(authInfo.durationMs),
          error: extractErrorBody(authInfo.data)
        },
    endpoints
  }

  const json = JSON.stringify(report, null, 2)
  if (OUTPUT_PATH) {
    const target = path.resolve(OUTPUT_PATH)
    fs.mkdirSync(path.dirname(target), { recursive: true })
    fs.writeFileSync(target, json)
    formatConsoleSummary(report).forEach((line) => console.log(line))
    console.log(target)
    return
  }
  console.log(json)
}

module.exports = {
  buildSuiteForTest: ({ token, authInfo, brokerAccounts }) => buildSuite(token, authInfo, brokerAccounts),
  formatConsoleSummaryForTest: formatConsoleSummary
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error?.stack || String(error))
    process.exit(1)
  })
}

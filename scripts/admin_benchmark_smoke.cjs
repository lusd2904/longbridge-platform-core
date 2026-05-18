const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const { resolveBaseUrl } = require('./base_url_helper.cjs')

const DEFAULT_OUTPUT_PATH = '.omx/artifacts/benchmarks/admin-benchmark.json'
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

function buildSuite(token, authInfo) {
  const accountId = firstPositiveInt(
    authInfo?.data?.user?.defaultAccountId,
    authInfo?.data?.defaultAccountId,
    authInfo?.data?.accountId
  )
  const dashboardSummarySpec = accountId
    ? {
        id: 'dashboard-summary',
        label: 'Dashboard Summary',
        method: 'GET',
        path: `/svc/trade/api/v1/trade/accounts/${encodeURIComponent(accountId)}/summary`,
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
      path: '/api/health',
      summarize: (payload) => ({
        status: payload?.status || null,
        services: payload?.services || {}
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
    }
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
  if (!Array.isArray(accounts)) {
    return null
  }
  const found = accounts.find((item) => item && (item.is_default || item.isDefault))
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
    const sample = {
      iteration: index + 1,
      status: result.status,
      ok: result.ok,
      durationMs: roundNumber(result.durationMs),
      responseTimeHeader: result.responseTimeHeader,
      requestId: result.requestId,
      error: result.ok ? '' : extractErrorBody(result.data)
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

  const suite = filterSuite(buildSuite(token, authInfo))
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
    console.log(target)
    return
  }
  console.log(json)
}

main().catch((error) => {
  console.error(error?.stack || String(error))
  process.exit(1)
})

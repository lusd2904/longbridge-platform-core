import fs from 'node:fs/promises'
import path from 'node:path'

const ROOT = path.resolve(new URL('..', import.meta.url).pathname)
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3100'
const USERNAME = process.env.SMOKE_USERNAME || 'admin'
const PASSWORD = process.env.SMOKE_PASSWORD || 'admin123'
const REPORT_PATH = process.env.DOCKER_API_PROBE_REPORT ||
  path.join(ROOT, 'tmp/evidence/docker-api-probe.json')

const requestJson = async (pathName, options = {}) => {
  const response = await fetch(`${BASE_URL}${pathName}`, options)
  const text = await response.text()
  let body = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = { rawText: text.slice(0, 500) }
  }
  return { status: response.status, body }
}

const unwrapObject = (payload) => (
  payload?.data && typeof payload.data === 'object' && !Array.isArray(payload.data)
    ? payload.data
    : payload
)

const unwrapArray = (payload) => {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.data)) return payload.data
  if (Array.isArray(payload?.items)) return payload.items
  if (Array.isArray(payload?.data?.items)) return payload.data.items
  if (Array.isArray(payload?.data?.accounts)) return payload.data.accounts
  if (Array.isArray(payload?.accounts)) return payload.accounts
  return []
}

const getToken = async () => {
  const login = await requestJson('/svc/user/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD })
  })
  const token = login.body?.data?.token ||
    login.body?.data?.access_token ||
    login.body?.token ||
    login.body?.access_token
  return { loginStatus: login.status, token }
}

const authHeaders = (token) => ({
  Authorization: `Bearer ${token}`,
  'Content-Type': 'application/json'
})

const summarizeAccounts = (payload) => unwrapArray(payload).map((account) => ({
  id: account.id ?? account.accountId ?? account.account_id,
  brokerType: account.brokerType ?? account.broker_type ?? account.broker,
  tradingMode: account.tradingMode ?? account.trading_mode ?? account.mode,
  isPaper: Boolean(account.isPaper ?? account.is_paper ?? account.paper)
}))

const createProbePositions = () => Array.from({ length: 14 }, (_, index) => ({
  symbol: `PROBE${index}.US`,
  quantity: 1,
  market_value: 1000 + index,
  cost_basis: 900 + index
}))

const extractJobId = (payload = {}) => {
  const dataPayload = unwrapObject(payload) || {}
  const metaPayload = payload.meta && typeof payload.meta === 'object' ? payload.meta : {}
  return payload.jobId ||
    payload.job_id ||
    dataPayload.jobId ||
    dataPayload.job_id ||
    metaPayload.jobId ||
    metaPayload.job_id ||
    null
}

const buildReport = async () => {
  const report = {
    generatedAt: new Date().toISOString(),
    baseUrl: BASE_URL,
    ok: false
  }

  const { loginStatus, token } = await getToken()
  report.loginStatus = loginStatus
  report.loginSuccess = Boolean(token)

  if (!token) {
    return report
  }

  const headers = authHeaders(token)

  const accountsResponse = await requestJson('/svc/trade/api/v1/trade/accounts', { headers })
  const accounts = summarizeAccounts(accountsResponse.body)
  report.accountStatus = accountsResponse.status
  report.accountCount = accounts.length
  report.accounts = accounts

  const analysisHealth = await requestJson('/svc/analysis/health', { headers })
  const healthPayload = unwrapObject(analysisHealth.body) || {}
  report.analysisHealthStatus = analysisHealth.status
  report.deferredAnalysisJobs = healthPayload.deps?.deferredAnalysisJobs ||
    healthPayload.deferredAnalysisJobs ||
    null

  const analyzePositions = await requestJson('/svc/analysis/api/v1/analysis/analyze-positions', {
    method: 'POST',
    headers,
    body: JSON.stringify({ positions: createProbePositions() })
  })
  const analyzePayload = unwrapObject(analyzePositions.body) || analyzePositions.body || {}
  const analyzeMeta = analyzePositions.body?.meta || {}
  report.analyzePositionsStatus = analyzePositions.status
  report.analyzePositionsResult = {
    jobId: extractJobId(analyzePositions.body || {}),
    jobStatus: analyzePayload.jobStatus || analyzePayload.status || analyzeMeta.jobStatus || null,
    jobTtlSeconds: analyzePayload.jobTtlSeconds || analyzeMeta.jobTtlSeconds || null
  }

  const missingJob = await requestJson('/svc/analysis/api/v1/analysis/analyze-positions/jobs/definitely-missing-job-id', { headers })
  const missingPayload = unwrapObject(missingJob.body) || missingJob.body || {}
  report.missingJobStatus = missingJob.status
  report.missingJobResult = {
    status: missingPayload.status || null,
    retryable: missingPayload.retryable ?? null
  }

  const stoploss = await requestJson('/svc/risk/api/v1/risk/stoploss', { headers })
  const stoplossRows = unwrapArray(stoploss.body)
  report.stoplossStatus = stoploss.status
  report.stoplossCount = stoplossRows.length
  report.stoplossRowsWithStrategyIdProperty = stoplossRows.filter((row) => (
    Object.prototype.hasOwnProperty.call(row, 'strategyId') ||
    Object.prototype.hasOwnProperty.call(row, 'strategy_id')
  )).length

  report.ok = report.loginStatus === 200 &&
    report.loginSuccess &&
    report.accountStatus === 200 &&
    report.accountCount === 1 &&
    report.accounts[0]?.isPaper === true &&
    String(report.accounts[0]?.tradingMode || '').toLowerCase() === 'paper' &&
    report.analysisHealthStatus === 200 &&
    report.deferredAnalysisJobs?.status === 'healthy' &&
    report.deferredAnalysisJobs?.storage === 'memory+redis_snapshot' &&
    report.analyzePositionsStatus === 202 &&
    Boolean(report.analyzePositionsResult.jobId) &&
    report.missingJobStatus === 410 &&
    report.missingJobResult.status === 'expired' &&
    report.missingJobResult.retryable === false &&
    report.stoplossStatus === 200 &&
    report.stoplossRowsWithStrategyIdProperty === report.stoplossCount

  return report
}

const main = async () => {
  await fs.mkdir(path.dirname(REPORT_PATH), { recursive: true })
  let report
  try {
    report = await buildReport()
  } catch (error) {
    report = {
      generatedAt: new Date().toISOString(),
      baseUrl: BASE_URL,
      ok: false,
      error: error?.message || String(error)
    }
  }

  await fs.writeFile(REPORT_PATH, JSON.stringify(report, null, 2))
  console.log(JSON.stringify({ reportPath: REPORT_PATH, ...report }, null, 2))
  if (!report.ok) {
    process.exitCode = 1
  }
}

main()

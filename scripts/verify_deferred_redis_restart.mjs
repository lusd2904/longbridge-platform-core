import fs from 'node:fs/promises'
import path from 'node:path'
import { spawnSync } from 'node:child_process'

const ROOT = path.resolve(new URL('..', import.meta.url).pathname)
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3100'
const USERNAME = process.env.SMOKE_USERNAME || 'admin'
const PASSWORD = process.env.SMOKE_PASSWORD || 'admin123'
const DOCKER_BIN = process.env.DOCKER_BIN || '/Users/lusd/.local/bin/docker'
const REPORT_PATH = process.env.DEFERRED_REDIS_RESTART_REPORT ||
  path.join(ROOT, 'tmp/evidence/deferred-redis-restart-report.json')
const JOB_TIMEOUT_MS = Number(process.env.DEFERRED_REDIS_RESTART_JOB_TIMEOUT_MS || 120000)
const HEALTH_TIMEOUT_MS = Number(process.env.DEFERRED_REDIS_RESTART_HEALTH_TIMEOUT_MS || 120000)

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const runCommand = (args, options = {}) => {
  const result = spawnSync(DOCKER_BIN, args, {
    cwd: ROOT,
    encoding: 'utf-8',
    ...options
  })
  if (result.status !== 0) {
    throw new Error(`${DOCKER_BIN} ${args.join(' ')} failed: ${(result.stderr || result.stdout || '').trim()}`)
  }
  return result.stdout.trim()
}

const waitForHealthy = async (containerName, timeoutMs = HEALTH_TIMEOUT_MS) => {
  const started = Date.now()
  let lastStatus = ''
  while (Date.now() - started < timeoutMs) {
    const result = spawnSync(DOCKER_BIN, ['inspect', '-f', '{{.State.Health.Status}}', containerName], {
      cwd: ROOT,
      encoding: 'utf-8'
    })
    lastStatus = (result.stdout || '').trim()
    if (result.status === 0 && lastStatus === 'healthy') {
      return lastStatus
    }
    await sleep(2000)
  }
  throw new Error(`${containerName} did not become healthy; last status=${lastStatus || 'unknown'}`)
}

const requestJson = async (pathName, options = {}) => {
  const response = await fetch(`${BASE_URL}${pathName}`, options)
  const text = await response.text()
  let body = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  return { status: response.status, body }
}

const getToken = async () => {
  const login = await requestJson('/svc/user/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD })
  })
  const token = login.body?.data?.token || login.body?.data?.access_token || login.body?.token
  if (login.status !== 200 || !token) {
    throw new Error(`login failed: status=${login.status}`)
  }
  return token
}

const authHeaders = (token) => ({
  Authorization: `Bearer ${token}`,
  'Content-Type': 'application/json'
})

const createDeferredJob = async (token) => {
  const positions = Array.from({ length: 14 }, (_, index) => ({
    symbol: `REDIS${index}.US`,
    quantity: 1,
    market_value: 1000 + index,
    cost_basis: 900 + index
  }))
  const response = await requestJson('/svc/analysis/api/v1/analysis/analyze-positions', {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ positions })
  })
  const payload = response.body || {}
  const dataPayload = payload.data && !Array.isArray(payload.data) ? payload.data : {}
  const metaPayload = payload.meta && typeof payload.meta === 'object' ? payload.meta : {}
  const jobId = payload.jobId || payload.job_id || dataPayload.jobId || dataPayload.job_id || metaPayload.jobId || metaPayload.job_id
  if (response.status !== 202 || !jobId) {
    throw new Error(`expected 202 deferred job with jobId; status=${response.status}`)
  }
  return jobId
}

const getJobStatus = async (token, jobId) => {
  const response = await requestJson(`/svc/analysis/api/v1/analysis/analyze-positions/jobs/${encodeURIComponent(jobId)}`, {
    headers: authHeaders(token)
  })
  const payload = response.body?.data || response.body || {}
  return {
    httpStatus: response.status,
    status: String(payload.status || '').toLowerCase(),
    payload
  }
}

const summarizeJobStatus = (job) => {
  const payload = job?.payload || {}
  const result = payload.result && typeof payload.result === 'object' ? payload.result : {}
  const data = Array.isArray(result.data) ? result.data : []
  return {
    httpStatus: job?.httpStatus || 0,
    status: job?.status || '',
    jobId: payload.jobId || payload.job_id || '',
    createdAt: payload.createdAt || null,
    updatedAt: payload.updatedAt || null,
    completedAt: payload.completedAt || null,
    resultDataCount: data.length,
    stats: result.stats || payload.stats || null,
    errorCount: Array.isArray(result.errors) ? result.errors.length : 0
  }
}

const waitForTerminalJob = async (token, jobId) => {
  const started = Date.now()
  let last = null
  while (Date.now() - started < JOB_TIMEOUT_MS) {
    last = await getJobStatus(token, jobId)
    if (last.httpStatus === 200 && ['completed', 'failed', 'cancelled', 'expired'].includes(last.status)) {
      return last
    }
    await sleep(2000)
  }
  throw new Error(`deferred job ${jobId} did not reach terminal status; last=${JSON.stringify(last)}`)
}

const main = async () => {
  await fs.mkdir(path.dirname(REPORT_PATH), { recursive: true })
  const report = {
    generatedAt: new Date().toISOString(),
    baseUrl: BASE_URL,
    dockerBin: DOCKER_BIN,
    ok: false
  }

  try {
    const token = await getToken()
    const jobId = await createDeferredJob(token)
    report.jobId = jobId
    const beforeRestart = await waitForTerminalJob(token, jobId)
    report.beforeRestart = summarizeJobStatus(beforeRestart)

    runCommand(['compose', 'restart', 'redis'])
    await waitForHealthy('refactor-v2-redis')
    runCommand(['compose', 'restart', 'analysis-service'])
    await waitForHealthy('refactor-v2-analysis')

    const tokenAfterRestart = await getToken()
    const afterRestart = await getJobStatus(tokenAfterRestart, jobId)
    report.afterRestart = summarizeJobStatus(afterRestart)
    report.ok = beforeRestart.httpStatus === 200 &&
      afterRestart.httpStatus === 200 &&
      afterRestart.status === beforeRestart.status &&
      report.afterRestart.jobId === jobId
  } catch (error) {
    report.error = error?.message || String(error)
  }

  await fs.writeFile(REPORT_PATH, JSON.stringify(report, null, 2))
  console.log(JSON.stringify({ reportPath: REPORT_PATH, ...report }, null, 2))
  if (!report.ok) {
    process.exitCode = 1
  }
}

main()

const fs = require('node:fs')
const path = require('node:path')

const HELP_TEXT = `Continuous smoke/performance gate

Usage:
  node scripts/continuous_regression_gate.cjs
  node scripts/continuous_regression_gate.cjs --check=web-smoke
  node scripts/continuous_regression_gate.cjs --check=api-benchmark

Environment:
  CONTINUOUS_GATE_CHECK       all | web-smoke | api-benchmark (default: all)
  WEB_SMOKE_REPORT            Path to smoke report JSON
  API_BENCHMARK_REPORT        Path to benchmark report JSON
`

const ROOT_DIR = path.resolve(__dirname, '..')
const DEFAULT_WEB_SMOKE_REPORT = path.join(ROOT_DIR, 'apps/runtime/smoke/web-portal-smoke-report.json')
const DEFAULT_API_BENCHMARK_REPORT = path.join(ROOT_DIR, '.omx/artifacts/benchmarks/admin-benchmark.json')

const WEB_SMOKE_THRESHOLDS = {
  market: { maxReadyMs: 6000, maxTotalMs: 20000 },
  trading: { maxReadyMs: 6000, maxTotalMs: 20000 },
  'scheduler-center': { maxReadyMs: 6000, maxTotalMs: 15000 },
  'history-coverage': { maxReadyMs: 6000, maxTotalMs: 20000 }
}

const API_BENCHMARK_THRESHOLDS = {
  'market-stock-pool': { maxP95Ms: 1000 },
  'market-insights': { maxP95Ms: 1000 },
  'market-history-compare': { maxP95Ms: 2000 },
  'market-history-coverage': { maxP95Ms: 20000 },
  'risk-overview': { maxP95Ms: 1000 },
  'orders-projection': { maxP95Ms: 1000 },
  'positions-projection': { maxP95Ms: 1000 }
}

function parseArgs(argv = process.argv.slice(2)) {
  const options = {}
  for (const arg of argv) {
    if (arg === '--help' || arg === '-h') {
      options.help = true
      continue
    }
    if (arg.startsWith('--check=')) {
      options.check = arg.slice('--check='.length)
    }
  }
  return options
}

function normalizeCheckMode(rawValue) {
  const value = String(rawValue || 'all').trim().toLowerCase()
  if (['all', 'web-smoke', 'api-benchmark'].includes(value)) {
    return value
  }
  throw new Error(`Unsupported check mode: ${rawValue}`)
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'))
}

function formatMetric(value) {
  return Number.isFinite(value) ? `${Number(value.toFixed(2))}ms` : 'n/a'
}

function evaluateWebSmokeReport(report, thresholds = WEB_SMOKE_THRESHOLDS) {
  const pages = Array.isArray(report?.pages) ? report.pages : []
  const errors = Array.isArray(report?.errors) ? report.errors : []
  const failures = []
  const summaries = []

  if (errors.length) {
    failures.push(`web-smoke: report contains ${errors.length} runtime errors`)
  }

  for (const [pageName, threshold] of Object.entries(thresholds)) {
    const page = pages.find((item) => item?.name === pageName)
    if (!page) {
      failures.push(`web-smoke:${pageName}: missing page result`)
      continue
    }
    summaries.push(
      `web-smoke:${pageName} ok=${page.ok !== false} ready=${formatMetric(page.initialReadyDurationMs ?? page.readinessDurationMs)} total=${formatMetric(page.durationMs)}`
    )
    if (page.ok === false) {
      failures.push(`web-smoke:${pageName}: page marked failed`)
    }
    const readyMs = Number(page.initialReadyDurationMs ?? page.readinessDurationMs)
    const totalMs = Number(page.durationMs)
    if (!Number.isFinite(readyMs)) {
      failures.push(`web-smoke:${pageName}: missing ready duration`)
    } else if (readyMs > threshold.maxReadyMs) {
      failures.push(`web-smoke:${pageName}: ready ${formatMetric(readyMs)} > ${formatMetric(threshold.maxReadyMs)}`)
    }
    if (!Number.isFinite(totalMs)) {
      failures.push(`web-smoke:${pageName}: missing total duration`)
    } else if (totalMs > threshold.maxTotalMs) {
      failures.push(`web-smoke:${pageName}: total ${formatMetric(totalMs)} > ${formatMetric(threshold.maxTotalMs)}`)
    }
  }

  return { summaries, failures }
}

function evaluateApiBenchmarkReport(report, thresholds = API_BENCHMARK_THRESHOLDS) {
  const endpoints = Array.isArray(report?.endpoints) ? report.endpoints : []
  const failures = []
  const summaries = []

  for (const [endpointId, threshold] of Object.entries(thresholds)) {
    const endpoint = endpoints.find((item) => item?.id === endpointId)
    if (!endpoint) {
      failures.push(`api-benchmark:${endpointId}: missing endpoint result`)
      continue
    }
    summaries.push(
      `api-benchmark:${endpointId} ok=${endpoint.failCount === 0} p95=${formatMetric(endpoint.p95Ms)} status=${(endpoint.statusCodes || []).join(',') || 'n/a'}`
    )
    if (Number(endpoint.failCount || 0) > 0) {
      failures.push(`api-benchmark:${endpointId}: ${endpoint.failCount} failed samples`)
    }
    if (Number(endpoint.okCount || 0) <= 0) {
      failures.push(`api-benchmark:${endpointId}: no successful samples`)
    }
    const p95Ms = Number(endpoint.p95Ms)
    if (!Number.isFinite(p95Ms)) {
      failures.push(`api-benchmark:${endpointId}: missing p95`)
    } else if (p95Ms > threshold.maxP95Ms) {
      failures.push(`api-benchmark:${endpointId}: p95 ${formatMetric(p95Ms)} > ${formatMetric(threshold.maxP95Ms)}`)
    }
  }

  return { summaries, failures }
}

function runGate(options = {}) {
  const check = normalizeCheckMode(options.check || process.env.CONTINUOUS_GATE_CHECK || 'all')
  const lines = []
  const failures = []

  if (check === 'all' || check === 'web-smoke') {
    const webSmokeReportPath = path.resolve(options.webSmokeReportPath || process.env.WEB_SMOKE_REPORT || DEFAULT_WEB_SMOKE_REPORT)
    if (!fs.existsSync(webSmokeReportPath)) {
      failures.push(`web-smoke: missing report ${webSmokeReportPath}`)
    } else {
      const result = evaluateWebSmokeReport(readJson(webSmokeReportPath))
      lines.push(`[web-smoke] ${webSmokeReportPath}`)
      lines.push(...result.summaries)
      failures.push(...result.failures)
    }
  }

  if (check === 'all' || check === 'api-benchmark') {
    const apiBenchmarkReportPath = path.resolve(options.apiBenchmarkReportPath || process.env.API_BENCHMARK_REPORT || DEFAULT_API_BENCHMARK_REPORT)
    if (!fs.existsSync(apiBenchmarkReportPath)) {
      failures.push(`api-benchmark: missing report ${apiBenchmarkReportPath}`)
    } else {
      const result = evaluateApiBenchmarkReport(readJson(apiBenchmarkReportPath))
      lines.push(`[api-benchmark] ${apiBenchmarkReportPath}`)
      lines.push(...result.summaries)
      failures.push(...result.failures)
    }
  }

  return { check, lines, failures }
}

function printHelp() {
  console.log(HELP_TEXT)
}

function main() {
  const args = parseArgs()
  if (args.help) {
    printHelp()
    return
  }

  const result = runGate({ check: args.check })
  const output = [
    `check=${result.check}`,
    ...result.lines
  ]

  if (result.failures.length) {
    output.push('--- failures ---')
    output.push(...result.failures)
    console.log(output.join('\n'))
    process.exit(1)
  }

  output.push('gate=pass')
  console.log(output.join('\n'))
}

module.exports = {
  API_BENCHMARK_THRESHOLDS,
  DEFAULT_API_BENCHMARK_REPORT,
  DEFAULT_WEB_SMOKE_REPORT,
  WEB_SMOKE_THRESHOLDS,
  evaluateApiBenchmarkReport,
  evaluateWebSmokeReport,
  normalizeCheckMode,
  runGate
}

if (require.main === module) {
  try {
    main()
  } catch (error) {
    console.error(error?.stack || String(error))
    process.exit(1)
  }
}

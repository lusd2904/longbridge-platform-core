import fs from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const require = createRequire(import.meta.url)
const { resolveBaseUrl } = require('../../../../scripts/base_url_helper.cjs')

const projectRoot = path.resolve(__dirname, '..')
const artifactsDir = path.resolve(projectRoot, '../../runtime/smoke')
const baseUrl = resolveBaseUrl('BASE_URL')
const username = process.env.SMOKE_USERNAME || 'admin'
const password = process.env.SMOKE_PASSWORD || 'admin123'
const PAGE_TIMEOUT_MS = Number(process.env.SMOKE_PAGE_TIMEOUT_MS || 30000)
const DEFAULT_CHROME_EXECUTABLE = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const fileExists = async (candidate) => {
  if (!candidate) return false
  try {
    await fs.access(candidate)
    return true
  } catch {
    return false
  }
}

const resolveBrowserLaunchOptions = async () => {
  const requestedExecutable = process.env.SMOKE_BROWSER_EXECUTABLE || ''
  const bundledExecutable = chromium.executablePath()
  const executablePath = requestedExecutable ||
    (await fileExists(bundledExecutable) ? bundledExecutable : '') ||
    (await fileExists(DEFAULT_CHROME_EXECUTABLE) ? DEFAULT_CHROME_EXECUTABLE : '')
  return executablePath
    ? { headless: true, executablePath }
    : { headless: true }
}

const retrySuccessPayload = {
  data: [
    {
      symbol: 'NVDA.US',
      name: 'NVIDIA Corporation',
      finalDecision: '买入',
      finalSignal: 'buy',
      confidence: 88,
      reason: 'E2E retry response',
      scanLayers: [],
      indicators: {},
      marketSummary: {
        regime: 'risk_on',
        summary: 'E2E retry recovered',
        benchmarks: []
      }
    }
  ],
  marketSummary: {
    regime: 'risk_on',
    summary: 'E2E retry recovered',
    benchmarks: []
  },
  modelPlan: {
    final: {
      alias: 'e2e-final'
    }
  }
}

const run = async () => {
  await fs.mkdir(artifactsDir, { recursive: true })
  const reportPath = process.env.SMOKE_AI_RETRY_REPORT ||
    path.join(artifactsDir, 'ai-analysis-410-retry-report.json')

  let browser
  let requestCount = 0
  const consoleErrors = []
  const ignoredConsoleErrors = []
  const report = {
    generatedAt: new Date().toISOString(),
    baseUrl,
    requestCount: 0,
    retryVisible: false,
    secondRequestTriggered: false,
    consoleErrors,
    ignoredConsoleErrors: 0,
    ok: false
  }

  try {
    browser = await chromium.launch(await resolveBrowserLaunchOptions())
    const page = await browser.newPage({ viewport: { width: 1366, height: 900 } })

    page.on('console', (msg) => {
      if (msg.type() !== 'error') return
      const text = msg.text()
      if (/Failed to load resource: the server responded with a status of 410/.test(text)) {
        ignoredConsoleErrors.push(text)
        return
      }
      consoleErrors.push(text)
    })

    await page.goto(`${baseUrl}/login`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS })
    await page.getByPlaceholder('用户名').fill(username)
    await page.getByPlaceholder('密码').fill(password)
    await page.getByRole('button', { name: '登录' }).click()
    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: PAGE_TIMEOUT_MS })

    await page.route('**/svc/analysis/api/v1/analysis/analyze-positions', async (route) => {
      requestCount += 1
      report.requestCount = requestCount

      if (requestCount === 1) {
        await route.fulfill({
          status: 410,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            error: '分析任务已失效或不存在，请重新发起扫描',
            data: {
              jobId: 'e2e-expired-job',
              status: 'expired',
              retryable: false
            }
          })
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(retrySuccessPayload)
      })
    })

    await page.goto(`${baseUrl}/ai-analysis`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS })
    await page.waitForFunction(
      () => Array.from(document.querySelectorAll('button')).some((node) => /扫描/.test(node.textContent || '')),
      undefined,
      { timeout: 15000 }
    )
    await page.getByRole('button', { name: /扫描当前列表/ }).first().click()
    await page.waitForFunction(
      () => document.body.textContent?.includes('重新分析'),
      undefined,
      { timeout: 15000 }
    )
    report.retryVisible = true

    await page.getByRole('button', { name: '重新分析' }).click()
    await page.waitForFunction(
      () => document.body.textContent?.includes('最近一次扫描已完成') || document.body.textContent?.includes('已收录'),
      undefined,
      { timeout: 15000 }
    )
    report.secondRequestTriggered = requestCount >= 2
    report.ignoredConsoleErrors = ignoredConsoleErrors.length
    report.ok = report.retryVisible && report.secondRequestTriggered && consoleErrors.length === 0
  } catch (error) {
    report.error = error?.message || String(error)
    report.ignoredConsoleErrors = ignoredConsoleErrors.length
  } finally {
    if (browser) {
      await browser.close()
    }
  }

  await fs.writeFile(reportPath, JSON.stringify(report, null, 2))
  console.log(JSON.stringify({ reportPath, ...report }, null, 2))
  if (!report.ok) {
    process.exitCode = 1
  }
}

run()

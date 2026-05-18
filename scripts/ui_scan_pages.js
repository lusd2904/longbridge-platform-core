const { chromium } = require('../apps/web-portal/node_modules/playwright')
const { resolveBaseUrl } = require('./base_url_helper.cjs')

const BASE_URL = resolveBaseUrl('UI_SCAN_BASE_URL')
const LOGIN_USERNAME = process.env.UI_SCAN_USERNAME || 'admin'
const LOGIN_PASSWORD = process.env.UI_SCAN_PASSWORD || 'admin123'

const ROUTES = [
  '/dashboard',
  '/trading',
  '/positions',
  '/orders',
  '/stock-pool',
  '/ai-analysis',
  '/strategy',
  '/backtest',
  '/risk',
  '/market',
  '/kline',
  '/recommendations',
  '/finance-news',
  '/profile',
  '/broker-management',
  '/notifications',
  '/settings',
  '/user-management',
  '/scheduler-center',
  '/symbol/AAPL.US'
]

async function captureSnapshot(page) {
  return page.evaluate(() => {
    const text = document.body.innerText || ''
    const tableRows = document.querySelectorAll('.el-table__body-wrapper tbody tr').length
    const statistics = Array.from(document.querySelectorAll('.el-statistic')).map((node) => (
      node.textContent || ''
    ).replace(/\s+/g, ' ').trim()).filter(Boolean)
    const indexCards = Array.from(document.querySelectorAll('.index-card'))
      .map((node) => (node.textContent || '').replace(/\s+/g, ' ').trim())
      .filter(Boolean)
    const paragraphs = Array.from(document.querySelectorAll('p'))
      .slice(0, 12)
      .map((node) => (node.textContent || '').replace(/\s+/g, ' ').trim())
      .filter(Boolean)

    return {
      title: document.title,
      text,
      tableRows,
      statistics,
      indexCards,
      paragraphs,
      loadingMaskCount: document.querySelectorAll('.el-loading-mask').length
    }
  })
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({
    viewport: { width: 1440, height: 980 }
  })

  const issues = []

  page.on('pageerror', (error) => {
    issues.push({
      kind: 'pageerror',
      url: page.url(),
      message: String(error)
    })
  })

  page.on('console', (message) => {
    const type = message.type()
    if (type === 'error' || type === 'warning') {
      issues.push({
        kind: `console:${type}`,
        url: page.url(),
        message: message.text()
      })
    }
  })

  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' })
  await page.getByPlaceholder('用户名').fill(LOGIN_USERNAME)
  await page.getByPlaceholder('密码').fill(LOGIN_PASSWORD)
  await page.getByRole('button', { name: '登录' }).click()
  await page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: 15000 })

  const report = []

  for (const route of ROUTES) {
    await page.goto(`${BASE_URL}${route}`, { waitUntil: 'domcontentloaded' })
    try {
      await page.waitForLoadState('networkidle', { timeout: 8000 })
    } catch {
      // 某些页面有持续轮询，这里允许继续收集当前快照。
    }
    await page.waitForTimeout(2500)

    const snapshot = await captureSnapshot(page)
    report.push({
      route,
      title: snapshot.title,
      tableRows: snapshot.tableRows,
      loadingMaskCount: snapshot.loadingMaskCount,
      statistics: snapshot.statistics.slice(0, 8),
      indexCards: snapshot.indexCards.slice(0, 4),
      paragraphs: snapshot.paragraphs,
      promptArtifact: /we need to produce|let'?s craft|including punctuation|count characters/i.test(snapshot.text),
      zeroMarketBenchmarks: route === '/market'
        ? snapshot.indexCards.some((item) => /标普500.*(?:\$|HK\$|¥)?0\.00|纳指100.*(?:\$|HK\$|¥)?0\.00|道琼斯.*(?:\$|HK\$|¥)?0\.00/.test(item))
        : false
    })
  }

  console.log(JSON.stringify({ report, issues }, null, 2))
  await browser.close()
}

main().catch((error) => {
  console.error(error?.stack || String(error))
  process.exit(1)
})

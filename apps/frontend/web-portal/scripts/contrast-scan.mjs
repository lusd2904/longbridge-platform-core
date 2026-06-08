import fs from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { createProgressReporter, withStepTimeout } from './smoke-helpers.mjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const require = createRequire(import.meta.url)
const { resolveBaseUrl } = require('../../../../scripts/base_url_helper.cjs')
const projectRoot = path.resolve(__dirname, '..')
const artifactsDir = path.resolve(projectRoot, '../../runtime/contrast')

const baseUrl = resolveBaseUrl('BASE_URL')
const username = process.env.SMOKE_USERNAME || 'admin'
const password = process.env.SMOKE_PASSWORD || 'admin123'
const PAGE_TIMEOUT_MS = Number(process.env.SMOKE_PAGE_TIMEOUT_MS || 60000)
const ACTION_TIMEOUT_MS = Number(process.env.SMOKE_ACTION_TIMEOUT_MS || 60000)
const DEFAULT_CHROME_EXECUTABLE = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const progress = createProgressReporter({
  enabled: process.env.CONTRAST_PROGRESS !== '0'
})

const routes = [
  { route: '/', name: 'root-redirect' },
  { route: '/dashboard', name: 'dashboard' },
  { route: '/market', name: 'market' },
  { route: '/stock-pool', name: 'stock-pool' },
  { route: '/watchlist-pool', name: 'watchlist-pool' },
  { route: '/watchlist-ai-trade-runs', name: 'watchlist-ai-trade-runs' },
  { route: '/watchlist-pool/AAPL.US/scan-result', name: 'watchlist-scan-result' },
  { route: '/watchlist-pool/NVDL.US/scan-result', name: 'watchlist-scan-result-alt' },
  { route: '/ai-analysis', name: 'ai-analysis' },
  { route: '/trading', name: 'trading' },
  { route: '/positions', name: 'positions' },
  { route: '/orders', name: 'orders' },
  { route: '/symbol/AAPL.US', name: 'symbol-detail' },
  { route: '/symbol/000001.SZ', name: 'symbol-detail-cn' },
  { route: '/kline', name: 'kline' },
  { route: '/recommendations', name: 'recommendations' },
  { route: '/sentiment-center', name: 'sentiment-center' },
  { route: '/market-sentiment', name: 'market-sentiment-redirect' },
  { route: '/finance-news', name: 'finance-news' },
  { route: '/strategy', name: 'strategy' },
  { route: '/backtest', name: 'backtest' },
  { route: '/risk', name: 'risk' },
  { route: '/profile', name: 'profile' },
  { route: '/broker-management', name: 'broker-management' },
  { route: '/notifications', name: 'notifications' },
  { route: '/settings', name: 'settings' },
  { route: '/user-management', name: 'user-management' },
  { route: '/scheduler-center', name: 'scheduler-center' },
  { route: '/history-coverage', name: 'history-coverage' }
]

const fileExists = async (candidate) => {
  if (!candidate) {
    return false
  }
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

const waitForStable = async (page, ms = 1200) => {
  await page.waitForLoadState('domcontentloaded')
  await page.waitForTimeout(ms)
}

const closeBrowserQuietly = async (browserInstance) => {
  const childProcess = typeof browserInstance.process === 'function' ? browserInstance.process() : null
  let timedOut = false
  const closeTask = browserInstance.close().catch((error) => {
    if (!timedOut) {
      throw error
    }
  })

  try {
    await Promise.race([
      closeTask,
      new Promise((_, reject) => {
        setTimeout(() => {
          timedOut = true
          reject(new Error('contrast:browser:close timed out after 5000ms'))
        }, 5000)
      })
    ])
  } catch (error) {
    progress(`browser close skipped after timeout: ${error.message}`)
    if (childProcess && !childProcess.killed) {
      childProcess.kill('SIGKILL')
    }
  }
}

const login = async (page) => {
  await withStepTimeout(
    page.goto(`${baseUrl}/login`, { waitUntil: 'domcontentloaded' }),
    { label: 'contrast:login:goto', timeoutMs: PAGE_TIMEOUT_MS }
  )
  await withStepTimeout(
    page.getByPlaceholder('用户名').fill(username),
    { label: 'contrast:login:username', timeoutMs: 8000 }
  )
  await withStepTimeout(
    page.getByPlaceholder('密码').fill(password),
    { label: 'contrast:login:password', timeoutMs: 8000 }
  )
  await withStepTimeout(
    page.getByRole('button', { name: '登录' }).click(),
    { label: 'contrast:login:submit', timeoutMs: 10000 }
  )
  await withStepTimeout(
    page.waitForURL(/\/dashboard/, { timeout: 20000 }),
    { label: 'contrast:login:redirect', timeoutMs: 22000 }
  )
  await withStepTimeout(
    waitForStable(page, 2000),
    { label: 'contrast:login:stabilize', timeoutMs: 12000 }
  )
}

const scanVisibleTextContrast = async (page) => {
  return page.evaluate(() => {
    const parseColor = (value) => {
      const normalized = String(value || '').trim()
      if (!normalized || normalized === 'transparent') {
        return null
      }

      const rgbaMatch = normalized.match(/^rgba?\(([^)]+)\)$/i)
      if (rgbaMatch) {
        const parts = rgbaMatch[1].split(',').map((part) => part.trim())
        return {
          r: Number(parts[0]),
          g: Number(parts[1]),
          b: Number(parts[2]),
          a: parts.length > 3 ? Number(parts[3]) : 1
        }
      }

      const hexMatch = normalized.match(/^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i)
      if (!hexMatch) {
        return null
      }
      let hex = hexMatch[1]
      if (hex.length === 3) {
        hex = hex.split('').map((char) => `${char}${char}`).join('')
      }
      return {
        r: Number.parseInt(hex.slice(0, 2), 16),
        g: Number.parseInt(hex.slice(2, 4), 16),
        b: Number.parseInt(hex.slice(4, 6), 16),
        a: hex.length === 8 ? Number.parseInt(hex.slice(6, 8), 16) / 255 : 1
      }
    }

    const blend = (foreground, background) => {
      const alpha = Math.min(Math.max(foreground.a ?? 1, 0), 1)
      return {
        r: Math.round(foreground.r * alpha + background.r * (1 - alpha)),
        g: Math.round(foreground.g * alpha + background.g * (1 - alpha)),
        b: Math.round(foreground.b * alpha + background.b * (1 - alpha)),
        a: 1
      }
    }

    const luminance = (color) => {
      const convert = (channel) => {
        const value = channel / 255
        return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
      }
      return (0.2126 * convert(color.r)) + (0.7152 * convert(color.g)) + (0.0722 * convert(color.b))
    }

    const contrastRatio = (a, b) => {
      const l1 = luminance(a)
      const l2 = luminance(b)
      const lighter = Math.max(l1, l2)
      const darker = Math.min(l1, l2)
      return (lighter + 0.05) / (darker + 0.05)
    }

    const nearestBackground = (element) => {
      let current = element
      let color = { r: 8, g: 16, b: 29, a: 1 }

      while (current && current.nodeType === Node.ELEMENT_NODE) {
        const styles = window.getComputedStyle(current)
        const background = parseColor(styles.backgroundColor)
        if (background && background.a > 0) {
          color = background.a < 1 ? blend(background, color) : background
          if (background.a >= 0.92) {
            return color
          }
        }
        current = current.parentElement
      }

      const bodyBackground = parseColor(window.getComputedStyle(document.body).backgroundColor)
      return bodyBackground && bodyBackground.a > 0 ? bodyBackground : color
    }

    const hasVisibleText = (element) => {
      const text = String(element.innerText || element.textContent || '').replace(/\s+/g, ' ').trim()
      if (!text || text.length < 2) {
        return false
      }
      if (/^[\d\s.,:%+\-/$()]+$/.test(text) && text.length < 4) {
        return false
      }
      return true
    }

    const ignoredSelectors = [
      'script',
      'style',
      'noscript',
      'svg',
      'canvas',
      '.el-overlay',
      '.el-tooltip__popper[aria-hidden="true"]',
      '[aria-hidden="true"]'
    ]

    const isIgnored = (element) => ignoredSelectors.some((selector) => element.matches(selector) || element.closest(selector))
    const selectorFor = (element) => {
      const parts = []
      let current = element
      while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 4) {
        const tag = current.tagName.toLowerCase()
        const id = current.id ? `#${current.id}` : ''
        const classes = Array.from(current.classList || []).slice(0, 3).map((item) => `.${item}`).join('')
        parts.unshift(`${tag}${id}${classes}`)
        current = current.parentElement
      }
      return parts.join(' > ')
    }

    const candidates = Array.from(document.body.querySelectorAll('body *'))
      .filter((element) => {
        if (isIgnored(element) || !hasVisibleText(element)) {
          return false
        }
        const rect = element.getBoundingClientRect()
        if (rect.width < 8 || rect.height < 8 || rect.bottom < 0 || rect.top > window.innerHeight) {
          return false
        }
        const styles = window.getComputedStyle(element)
        if (styles.visibility === 'hidden' || styles.display === 'none' || Number(styles.opacity) < 0.35) {
          return false
        }
        const childText = Array.from(element.children || []).reduce((sum, child) => {
          return sum + String(child.innerText || child.textContent || '').replace(/\s+/g, ' ').trim().length
        }, 0)
        const totalText = String(element.innerText || element.textContent || '').replace(/\s+/g, ' ').trim().length
        return totalText > childText || element.children.length === 0
      })

    const issues = []
    for (const element of candidates) {
      const styles = window.getComputedStyle(element)
      const color = parseColor(styles.color)
      if (!color || color.a < 0.45) {
        continue
      }
      const background = nearestBackground(element)
      const blendedColor = color.a < 1 ? blend(color, background) : color
      const ratio = contrastRatio(blendedColor, background)
      const fontSize = Number.parseFloat(styles.fontSize) || 13
      const fontWeight = Number.parseInt(styles.fontWeight, 10) || 400
      const largeText = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700)
      const threshold = largeText ? 3 : 4.5
      if (ratio < threshold) {
        issues.push({
          text: String(element.innerText || element.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80),
          selector: selectorFor(element),
          ratio: Number(ratio.toFixed(2)),
          threshold,
          color: styles.color,
          background: window.getComputedStyle(element).backgroundColor,
          fontSize,
          fontWeight,
          rect: {
            x: Math.round(element.getBoundingClientRect().x),
            y: Math.round(element.getBoundingClientRect().y),
            width: Math.round(element.getBoundingClientRect().width),
            height: Math.round(element.getBoundingClientRect().height)
          }
        })
      }
    }

    return issues
      .sort((a, b) => a.ratio - b.ratio)
      .slice(0, 60)
  })
}

await fs.mkdir(artifactsDir, { recursive: true })

const browser = await chromium.launch(await resolveBrowserLaunchOptions())
const context = await browser.newContext({ viewport: { width: 1440, height: 960 } })
const page = await context.newPage()
const pageErrors = []
page.on('pageerror', (error) => {
  pageErrors.push({ type: 'pageerror', message: error?.stack || error?.message || String(error), url: page.url() })
})
page.on('response', (response) => {
  if (response.status() >= 400 && response.url().includes('/svc/')) {
    pageErrors.push({ type: 'http', status: response.status(), url: response.url() })
  }
})

const results = []

const scanTarget = async (target) => {
  progress(`scan ${target.name} ${target.route}`)
  await withStepTimeout(
    page.goto(`${baseUrl}${target.route}`, { waitUntil: 'domcontentloaded' }),
    { label: `contrast:${target.name}:goto`, timeoutMs: PAGE_TIMEOUT_MS }
  )
  await withStepTimeout(
    waitForStable(page, 1600),
    { label: `contrast:${target.name}:stable`, timeoutMs: ACTION_TIMEOUT_MS }
  )
  const issues = await withStepTimeout(
    scanVisibleTextContrast(page),
    { label: `contrast:${target.name}:scan`, timeoutMs: ACTION_TIMEOUT_MS }
  )
  results.push({
    ...target,
    url: page.url(),
    issueCount: issues.length,
    issues
  })
  progress(`done ${target.name} issues=${issues.length}`)
}

try {
  await scanTarget({ route: '/login', name: 'login' })
  await login(page)

  for (const target of routes) {
    await scanTarget(target)
  }
} finally {
  await closeBrowserQuietly(browser)
}

const report = {
  generatedAt: new Date().toISOString(),
  baseUrl,
  username,
  pages: results,
  errors: pageErrors
}

const reportFile = path.join(artifactsDir, 'web-portal-contrast-report.json')
await fs.writeFile(reportFile, JSON.stringify(report, null, 2), 'utf8')

const totalIssues = results.reduce((sum, item) => sum + item.issueCount, 0)
const summaryLines = [
  `baseUrl=${baseUrl}`,
  `pages=${results.length}`,
  `contrastIssues=${totalIssues}`,
  `errors=${pageErrors.length}`
]

for (const item of results) {
  summaryLines.push(`${item.issueCount === 0 ? 'OK' : 'FAIL'} ${item.name} ${item.route} issues=${item.issueCount}`)
  for (const issue of item.issues.slice(0, 5)) {
    summaryLines.push(`  ratio=${issue.ratio}/${issue.threshold} ${issue.selector} "${issue.text}"`)
  }
}

if (pageErrors.length) {
  summaryLines.push('--- errors ---')
  for (const error of pageErrors.slice(0, 20)) {
    summaryLines.push(`${error.type} ${error.status || ''} ${error.url || ''} ${error.message || ''}`.trim())
  }
}

console.log(summaryLines.join('\n'))

if (totalIssues > 0 || pageErrors.length > 0) {
  process.exitCode = 1
}

process.exit(process.exitCode || 0)

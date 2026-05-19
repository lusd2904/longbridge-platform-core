import fs from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { createProgressReporter, sanitizeText, waitForPageStable, withStepTimeout } from './smoke-helpers.mjs'
import { collectRenderableSuggestionTexts, hasExpectedSuggestion } from '../src/utils/aiAnalysisSuggestions.js'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const require = createRequire(import.meta.url)
const { resolveBaseUrl } = require('../../../../scripts/base_url_helper.cjs')
const projectRoot = path.resolve(__dirname, '..')
const artifactsDir = path.resolve(projectRoot, '../../runtime/smoke')

const baseUrl = resolveBaseUrl('BASE_URL')
const username = process.env.SMOKE_USERNAME || 'admin'
const password = process.env.SMOKE_PASSWORD || 'admin123'
const PAGE_TIMEOUT_MS = Number(process.env.SMOKE_PAGE_TIMEOUT_MS || 60000)
const ACTION_TIMEOUT_MS = Number(process.env.SMOKE_ACTION_TIMEOUT_MS || 60000)
const OPTIONAL_ACTION_TIMEOUT_MS = Number(process.env.SMOKE_OPTIONAL_ACTION_TIMEOUT_MS || 1200)
const RUN_MOBILE_SMOKE = process.env.SMOKE_INCLUDE_MOBILE === '1'
const AI_ANALYSIS_DEEP_SCAN = process.env.SMOKE_AI_ANALYSIS_DEEP === '1'
const PAGE_FILTERS = String(process.env.SMOKE_PAGE_FILTER || '')
  .split(',')
  .map((item) => item.trim().toLowerCase())
  .filter(Boolean)
const DEFAULT_CHROME_EXECUTABLE = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const progress = createProgressReporter({
  enabled: process.env.SMOKE_PROGRESS !== '0'
})

const errors = []
const results = []
const OPTIONAL_OUTBOX_ENDPOINTS = [
  '/svc/trade/api/v1/trade/outbox/events',
  '/svc/trade/api/v1/trade/outbox/sagas'
]

const pushError = (type, payload) => {
  errors.push({
    type,
    at: new Date().toISOString(),
    ...payload
  })
}

const isOptionalOutbox404 = (url = '', status = 0) => {
  return Number(status) === 404 && OPTIONAL_OUTBOX_ENDPOINTS.some((pattern) => url.includes(pattern))
}

const readSuggestionTexts = async (suggestionsLocator) => {
  const texts = await suggestionsLocator.evaluateAll((nodes) => nodes.map((node) => node.textContent || '')).catch(() => [])
  return collectRenderableSuggestionTexts(texts)
}

const verifyAiAnalysisSuggestions = async (page, search, keyword, expectedSymbols) => {
  await search.fill(keyword)
  const suggestions = page.locator('.ai-target-suggest-popper .el-autocomplete-suggestion li')
  await page.waitForFunction(
    ({ selector, expected }) => {
      const suggestionTexts = Array.from(document.querySelectorAll(selector))
        .map((node) => (node.textContent || '').replace(/\s+/g, ' ').trim().toUpperCase())
        .filter(Boolean)

      return expected.some((candidate) => {
        const normalizedCandidate = String(candidate || '').trim().toUpperCase()
        return normalizedCandidate && suggestionTexts.some((text) => text.includes(normalizedCandidate))
      })
    },
    {
      selector: '.ai-target-suggest-popper .el-autocomplete-suggestion li',
      expected: expectedSymbols
    },
    { timeout: 8000 }
  )
  const suggestionTexts = await readSuggestionTexts(suggestions)
  if (!suggestionTexts.length) {
    throw new Error(`AI analysis symbol autocomplete did not show suggestions for ${keyword}`)
  }
  if (!hasExpectedSuggestion(suggestionTexts, expectedSymbols)) {
    throw new Error(`AI analysis suggestions missing expected targets for ${keyword}: ${suggestionTexts.join(' | ')}`)
  }
  return suggestionTexts
}

const waitForAiAnalysisScanState = async (page, timeoutMs = 8000) => {
  await page.waitForFunction(
    () => {
      const selectors = [
        '.scan-loading-panel',
        '.scan-inline-status',
        '.analysis-scan-status.is-running'
      ]

      return selectors.some((selector) => {
        const node = document.querySelector(selector)
        if (!node) {
          return false
        }

        const style = window.getComputedStyle(node)
        return style.visibility !== 'hidden' && style.display !== 'none'
      })
    },
    undefined,
    { timeout: timeoutMs }
  )
}

const waitForAiAnalysisScanOutcome = async (page, timeoutMs = 45000) => {
  await page.waitForFunction(
    () => {
      const status = document.querySelector('.analysis-scan-status')
      const statusText = (status?.textContent || '').replace(/\s+/g, ' ').trim()
      const hasCompletedStatus = status?.classList.contains('is-complete') || statusText.includes('最近一次扫描已完成')
      const hasFailedStatus = status?.classList.contains('is-error') || statusText.includes('最近一次扫描失败')
      const hasVerdict = Boolean(document.querySelector('.verdict-row-card'))
      const hasScannedTarget = Array.from(document.querySelectorAll('.target-decision'))
        .some((node) => {
          const text = (node.textContent || '').replace(/\s+/g, ' ').trim()
          return text && text !== '未扫描'
        })

      return hasCompletedStatus || hasFailedStatus || hasVerdict || hasScannedTarget
    },
    undefined,
    { timeout: timeoutMs }
  )

  const statusText = sanitizeText(await page.locator('.analysis-scan-status').innerText().catch(() => ''))
  if (statusText.includes('最近一次扫描失败')) {
    throw new Error(`AI analysis scan failed: ${statusText}`)
  }
}

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
  const executablePath = process.env.SMOKE_BROWSER_EXECUTABLE ||
    (await fileExists(DEFAULT_CHROME_EXECUTABLE) ? DEFAULT_CHROME_EXECUTABLE : '')
  return executablePath
    ? { headless: true, executablePath }
    : { headless: true }
}

const safeClick = async (page, target, options = {}) => {
  const timeout = options.timeout ?? OPTIONAL_ACTION_TIMEOUT_MS
  try {
    await target.waitFor({ state: 'visible', timeout })
    await target.click({ timeout })
    return true
  } catch {
    return false
  }
}

const safeClickWhenReady = async (page, target, options = {}) => {
  const timeout = options.timeout ?? OPTIONAL_ACTION_TIMEOUT_MS
  try {
    await target.waitFor({ state: 'visible', timeout })
    await page.waitForFunction(
      (element) => {
        if (!element) {
          return false
        }

        const isDisabled = element.disabled ||
          element.getAttribute('aria-disabled') === 'true' ||
          element.classList.contains('is-disabled')
        const isLoading = element.classList.contains('is-loading') ||
          element.getAttribute('aria-busy') === 'true'

        return !isDisabled && !isLoading
      },
      await target.elementHandle(),
      { timeout }
    )
    await target.click({ timeout })
    return true
  } catch {
    return false
  }
}

const clickByRole = async (page, role, name, options = {}) => {
  return safeClick(page, page.getByRole(role, { name }), options)
}

const clickByText = async (page, text, options = {}) => {
  return safeClick(page, page.getByText(text, { exact: true }), options)
}

const clickFirstButtonByText = async (page, text, options = {}) => {
  return safeClick(page, page.locator('button').filter({ hasText: text }).first(), options)
}

const clickReadyButtonByText = async (page, text, options = {}) => {
  return safeClickWhenReady(page, page.locator('button').filter({ hasText: text }).first(), options)
}

const clickSegmentByText = async (page, text, options = {}) => {
  const label = typeof text === 'string' ? new RegExp(`^\\s*${text}\\s*$`) : text
  const target = page.locator([
    '.el-radio-button',
    '.el-segmented__item',
    '.segment-button',
    'label',
    'button'
  ].join(',')).filter({ hasText: label }).first()
  return safeClick(page, target, options)
}

const clickTabByText = async (page, text, options = {}) => {
  return safeClick(page, page.locator('.el-tabs__item').filter({ hasText: text }).first(), options)
}

const waitForStable = async (page, options = {}) => waitForPageStable(page, options)
const waitForLightTransition = async (page, options = {}) => waitForStable(page, {
  quietWindowMs: options.quietWindowMs ?? 160,
  timeoutMs: options.timeoutMs ?? 1400,
  ...(options.loadState ? { loadState: options.loadState } : {})
})
const waitForRefreshStable = async (page, options = {}) => waitForStable(page, {
  minimumMs: options.minimumMs ?? 260,
  quietWindowMs: options.quietWindowMs ?? 220,
  timeoutMs: options.timeoutMs ?? 2600,
  ...(options.loadState ? { loadState: options.loadState } : {})
})

const waitForRoutePath = async (page, matcher, timeoutMs = 4000) => {
  await page.waitForURL((url) => {
    const pathname = new URL(url).pathname
    return typeof matcher === 'function' ? matcher(pathname) : matcher.test(pathname)
  }, { timeout: timeoutMs })
}

const shouldVisitPage = ({ route, name }) => {
  if (!PAGE_FILTERS.length) {
    return true
  }
  const normalizedRoute = String(route || '').toLowerCase()
  const normalizedName = String(name || '').toLowerCase()
  return PAGE_FILTERS.some((filter) => (
    filter === normalizedName ||
    filter === normalizedRoute ||
    normalizedRoute.includes(filter)
  ))
}

const visitPages = async (page, visits, scenario = 'desktop') => {
  for (const visit of visits) {
    if (!shouldVisitPage(visit)) {
      continue
    }
    await visitPage(page, visit.route, visit.name, visit.action, scenario)
  }
}

const expectVisible = async (locator, label, timeoutMs = 3000) => {
  await locator.first().waitFor({ state: 'visible', timeout: timeoutMs })
  return label
}

const expectOverlay = async (page, title, timeoutMs = 3000) => {
  const overlay = page.locator('.el-dialog, .el-drawer').filter({ hasText: title }).first()
  await overlay.waitFor({ state: 'visible', timeout: timeoutMs })
  return overlay
}

const closeOverlayByEscape = async (page, overlay, timeoutMs = 3000) => {
  await page.keyboard.press('Escape').catch(() => {})
  if (await overlay.waitFor({ state: 'hidden', timeout: timeoutMs }).then(() => true).catch(() => false)) {
    return
  }

  const closeButton = overlay.locator([
    '.el-dialog__headerbtn',
    '.el-drawer__close-btn',
    'button[aria-label="Close"]'
  ].join(',')).first()
  if (!await safeClick(page, closeButton, { timeout: 1000 })) {
    throw new Error('Overlay did not close with Escape and no close button was clickable')
  }
  await overlay.waitFor({ state: 'hidden', timeout: timeoutMs })
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
          reject(new Error('smoke:browser:close timed out after 5000ms'))
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

const collectPageSnapshot = async (page, name, scenario = 'desktop') => {
  const title = await page.title()
  const url = page.url()
  const bodyText = sanitizeText(await page.locator('body').innerText().catch(() => ''))
  return {
    name,
    scenario,
    title,
    url,
    bodyPreview: bodyText.slice(0, 280)
  }
}

const normalizePageAction = (action) => {
  if (!action) {
    return {}
  }
  return typeof action === 'function' ? { blocking: action } : action
}

const visitPage = async (page, route, name, action, scenario = 'desktop') => {
  const startedAt = Date.now()
  const stepPrefix = `${scenario}:${name}`
  progress(`start ${stepPrefix} ${route}`)
  const actionPlan = normalizePageAction(action)

  await withStepTimeout(
    page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded' }),
    { label: `${stepPrefix}:goto`, timeoutMs: PAGE_TIMEOUT_MS }
  )
  await withStepTimeout(
    waitForStable(page),
    { label: `${stepPrefix}:stabilize`, timeoutMs: ACTION_TIMEOUT_MS }
  )
  const initialReadyDurationMs = Date.now() - startedAt

  const result = {
    name,
    route,
    ok: true,
    actions: [],
    readinessDurationMs: initialReadyDurationMs,
    initialReadyDurationMs,
    actionDurationMs: 0,
    snapshotDurationMs: 0,
    verificationDurationMs: 0,
    verificationActions: [],
    durationMs: 0
  }

  try {
    if (actionPlan.blocking) {
      const actionStartedAt = Date.now()
      result.actions = await withStepTimeout(
        actionPlan.blocking(page),
        { label: `${stepPrefix}:actions`, timeoutMs: ACTION_TIMEOUT_MS }
      )
      result.actionDurationMs = Date.now() - actionStartedAt
    }
    const snapshotStartedAt = Date.now()
    Object.assign(result, await withStepTimeout(
      collectPageSnapshot(page, name, scenario),
      { label: `${stepPrefix}:snapshot`, timeoutMs: 8000 }
    ))
    result.snapshotDurationMs = Date.now() - snapshotStartedAt

    if (actionPlan.afterReady) {
      const verificationStartedAt = Date.now()
      result.verificationActions = await withStepTimeout(
        actionPlan.afterReady(page),
        { label: `${stepPrefix}:verify`, timeoutMs: ACTION_TIMEOUT_MS }
      )
      result.verificationDurationMs = Date.now() - verificationStartedAt
    }
  } catch (error) {
    result.ok = false
    result.error = error?.stack || error?.message || String(error)
    pushError('page_action', { route, name, message: result.error })
  } finally {
    result.durationMs = Date.now() - startedAt
    results.push(result)
    progress(`${result.ok ? 'done' : 'fail'} ${stepPrefix} ready=${result.initialReadyDurationMs}ms actions=${result.actionDurationMs}ms snapshot=${result.snapshotDurationMs}ms total=${result.durationMs}ms verify=${result.verificationDurationMs}ms`)
  }
}

const pageActions = {
  dashboard: async (page) => {
    const actions = []
    if (await clickByRole(page, 'button', /刷新|更新/)) {
      actions.push('clicked refresh')
      await waitForRefreshStable(page, { timeoutMs: 2200 })
    }
    const marketSegment = page.locator('.segment-button').filter({ hasText: '市场' }).first()
    if (await safeClick(page, marketSegment)) {
      actions.push('switched dashboard mobile segment market')
      await waitForLightTransition(page)
    }
    return actions
  },
  market: {
    blocking: async (page) => {
      const actions = []
      if (await clickSegmentByText(page, 'A股')) {
        actions.push('switched market CN')
        await waitForStable(page, { minimumMs: 240, quietWindowMs: 220, timeoutMs: 2400 })
      }
      if (await clickSegmentByText(page, '港股')) {
        actions.push('switched market HK')
        await waitForStable(page, { minimumMs: 240, quietWindowMs: 220, timeoutMs: 2400 })
      }
      if (await clickSegmentByText(page, '美股')) {
        actions.push('switched market US')
        await waitForStable(page, { minimumMs: 240, quietWindowMs: 220, timeoutMs: 2400 })
      }
      const listSegment = page.locator('.segment-button').filter({ hasText: '列表' }).first()
      if (await safeClick(page, listSegment)) {
        actions.push('opened market mobile list segment')
        await waitForStable(page, { minimumMs: 180, quietWindowMs: 180, timeoutMs: 1800 })
      }
      return actions
    },
    afterReady: async (page) => {
      const actions = []
      const detailButton = page.locator('button').filter({ hasText: '详情' }).first()
      if (await safeClick(page, detailButton, { timeout: 2500 })) {
        await waitForRoutePath(page, /^\/symbol\/[^/]+$/, 4000)
        actions.push('verified first symbol detail route')
        await page.goBack({ waitUntil: 'domcontentloaded' }).catch(() => {})
        await waitForRoutePath(page, (pathname) => pathname === '/market', 4000)
        await waitForStable(page, { quietWindowMs: 180, timeoutMs: 1600 })
      }
      return actions
    }
  },
  stockPool: async (page) => {
    const actions = []
    const search = page.getByPlaceholder('搜索股票代码或名称')
    if (await search.isVisible().catch(() => false)) {
      await search.fill('AAPL')
      actions.push('searched AAPL')
      await waitForStable(page)
    }
    const detailButton = page.locator('button').filter({ hasText: '详情' }).first()
    if (await safeClick(page, detailButton)) {
      actions.push('opened stock-pool detail')
      await waitForStable(page)
      await page.goBack({ waitUntil: 'domcontentloaded' }).catch(() => {})
      await waitForStable(page)
    }
    const analysisButton = page.locator('button').filter({ hasText: 'AI分析' }).first()
    if (await safeClick(page, analysisButton)) {
      actions.push('opened stock-pool ai-analysis')
      await waitForStable(page)
      await page.goBack({ waitUntil: 'domcontentloaded' }).catch(() => {})
      await waitForStable(page)
    }
    const tradeButton = page.locator('button').filter({ hasText: '交易' }).first()
    if (await safeClick(page, tradeButton)) {
      actions.push('opened stock-pool trading')
      await waitForStable(page)
      await page.goBack({ waitUntil: 'domcontentloaded' }).catch(() => {})
      await waitForStable(page)
    }
    return actions
  },
  aiAnalysis: async (page) => {
    const actions = []
    const search = page.getByPlaceholder('输入代码 / 名称，如 NVDA、NVDL')
    if (await search.isVisible().catch(() => false)) {
      const nvdaSuggestions = await verifyAiAnalysisSuggestions(page, search, 'nvda', ['NVDA.US', 'NVDL.US'])
      actions.push(`verified ${nvdaSuggestions.length} symbol suggestions for nvda`)

      const nvdlSuggestions = await verifyAiAnalysisSuggestions(page, search, 'nvdl', ['NVDL.US'])
      actions.push(`verified ${nvdlSuggestions.length} symbol suggestions for nvdl`)

      await page.keyboard.press('Escape')
      const scanButton = page.locator('button').filter({ hasText: /扫描/ }).first()
      if (await safeClick(page, scanButton, { timeout: 8000 })) {
        actions.push('clicked scan symbols')
        await waitForAiAnalysisScanState(page)
        actions.push('verified scan triggered state')
        if (AI_ANALYSIS_DEEP_SCAN) {
          await waitForAiAnalysisScanOutcome(page)
          actions.push('verified scan completed state')
        } else {
          actions.push('skipped deep scan completion wait')
        }
      }
    }
    if (await clickByRole(page, 'button', '刷新标的')) {
      actions.push('clicked refresh symbols')
      await waitForRefreshStable(page, { timeoutMs: 2600 })
      await expectVisible(page.locator('.target-panel, .control-panel'), 'verified ai analysis targets visible')
      actions.push('verified ai analysis targets visible')
    }
    return actions
  },
  trading: async (page) => {
    const actions = []
    const symbolInput = page.getByPlaceholder(/输入股票代码/)
    if (await symbolInput.isVisible().catch(() => false)) {
      await symbolInput.fill('AAPL.US')
      actions.push('filled AAPL.US')
    }
    if (await clickByRole(page, 'button', '搜索')) {
      actions.push('searched symbol')
      await waitForRefreshStable(page, { timeoutMs: 3200 })
    }
    await expectVisible(page.getByText('盘口与逐笔'), 'verified depth and trades panel', 4000)
    actions.push('verified depth and trades panel')
    await expectVisible(page.getByText('公告 / 资讯 / 讨论'), 'verified content panel', 4000)
    actions.push('verified content panel')
    const positionSegment = page.locator('.segment-button').filter({ hasText: '持仓' }).first()
    if (await safeClick(page, positionSegment)) {
      actions.push('switched trading mobile segment positions')
      await waitForLightTransition(page)
    }
    if (await page.locator('button, label').filter({ hasText: '买入' }).first().isVisible().catch(() => false)) {
      actions.push('verified buy controls visible without submitting')
    }
    if (await page.locator('button, label').filter({ hasText: '卖出' }).first().isVisible().catch(() => false)) {
      actions.push('verified sell controls visible without submitting')
    }
    return actions
  },
  positions: async (page) => {
    const actions = []
    if (await clickByRole(page, 'button', /刷新/)) {
      actions.push('refreshed positions')
      await waitForStable(page)
    }
    const detailButton = page.locator('button').filter({ hasText: '详情' }).first()
    if (await safeClick(page, detailButton)) {
      actions.push('opened position detail')
      await waitForStable(page)
      const dialog = await expectOverlay(page, '持仓详情')
      actions.push('verified position detail dialog')
      await closeOverlayByEscape(page, dialog)
      await waitForLightTransition(page)
    }
    return actions
  },
  orders: async (page) => {
    const actions = []
    if (await clickByRole(page, 'button', /刷新/)) {
      actions.push('refreshed orders')
      await waitForStable(page)
    }
    const detailButton = page.locator('button').filter({ hasText: '详情' }).first()
    if (await safeClick(page, detailButton)) {
      actions.push('opened order detail')
      await waitForStable(page)
      const dialog = await expectOverlay(page, '订单详情')
      actions.push('verified order detail dialog')
      await closeOverlayByEscape(page, dialog)
      await waitForLightTransition(page)
    }
    return actions
  },
  symbolDetail: async (page) => {
    const actions = []
    if (await clickTabByText(page, '资讯')) {
      actions.push('opened symbol news tab')
      await waitForStable(page)
    }
    if (await clickTabByText(page, '讨论')) {
      actions.push('opened symbol topics tab')
      await waitForStable(page)
    }
    if (await clickTabByText(page, '公告')) {
      actions.push('returned symbol announcements tab')
      await waitForStable(page)
    }
    if (await clickByRole(page, 'button', 'AI分析')) {
      actions.push('jumped to AI analysis')
      await waitForStable(page)
      await page.goBack({ waitUntil: 'domcontentloaded' }).catch(() => {})
      await waitForStable(page)
    }
    return actions
  },
  recommendations: async (page) => {
    const actions = []
    if (await clickByRole(page, 'button', '立即刷新')) {
      actions.push('refreshed recommendations')
      await waitForRefreshStable(page, { timeoutMs: 3200 })
      await expectVisible(page.locator('.spotlight-card, .recommendations-table'), 'verified recommendations content visible')
      actions.push('verified recommendations content visible')
    }
    const tradeButton = page.locator('button').filter({ hasText: '去交易' }).first()
    if (await safeClick(page, tradeButton)) {
      actions.push('opened recommendation trade')
      await waitForStable(page)
      await page.goBack({ waitUntil: 'domcontentloaded' }).catch(() => {})
      await waitForStable(page)
    }
    return actions
  },
  kline: async (page) => {
    const actions = []
    if (await clickSegmentByText(page, '周K')) {
      actions.push('switched weekly kline')
      await waitForStable(page, { quietWindowMs: 180, timeoutMs: 1600 })
    }
    if (await clickReadyButtonByText(page, '刷新历史', { timeout: 4000 })) {
      actions.push('refreshed market history')
      await waitForStable(page, { quietWindowMs: 180, timeoutMs: 2600 })
    }
    const focusButton = page.locator('button').filter({ hasText: '聚焦主图' }).first()
    if (await safeClick(page, focusButton)) {
      actions.push('focused primary chart')
      await waitForStable(page, { quietWindowMs: 160, timeoutMs: 1200 })
    }
    return actions
  },
  strategy: async (page) => {
    const actions = []
    const templateSearch = page.getByPlaceholder('搜索模板名称、说明、标签')
    if (await templateSearch.isVisible().catch(() => false)) {
      await templateSearch.fill('趋势')
      actions.push('searched strategy templates')
      await waitForLightTransition(page)
      await expectVisible(page.locator('.template-library-card'), 'verified strategy template library visible')
      actions.push('verified strategy template library visible')
      await templateSearch.clear()
    }
    const strategySearch = page.getByPlaceholder('搜索策略名称、描述或参数')
    if (await strategySearch.isVisible().catch(() => false)) {
      await strategySearch.fill('均线')
      actions.push('searched strategies')
      await waitForLightTransition(page)
      await expectVisible(page.locator('.strategy-table-card'), 'verified strategy table visible')
      actions.push('verified strategy table visible')
      await strategySearch.clear()
    }
    const detailButton = page.locator('button').filter({ hasText: '查看详情' }).first()
    if (await safeClick(page, detailButton)) {
      actions.push('opened strategy template detail')
      const dialog = await expectOverlay(page, '模板详情')
        .catch(() => expectOverlay(page, '策略模板'))
        .catch(() => expectOverlay(page, '详情'))
      actions.push('verified strategy detail dialog')
      await closeOverlayByEscape(page, dialog)
      await waitForLightTransition(page)
    }
    return actions
  },
  backtest: async (page) => {
    const actions = []
    const refreshButton = page.locator('.backtest-list .card-header button').first()
    if (await safeClick(page, refreshButton)) {
      actions.push('refreshed backtest list')
      await waitForRefreshStable(page)
      await expectVisible(page.locator('.backtest-list'), 'verified backtest list visible')
      actions.push('verified backtest list visible')
    }
    if (await clickByRole(page, 'button', '运行回测')) {
      actions.push('opened backtest dialog')
      const dialog = await expectOverlay(page, '运行回测')
      actions.push('verified backtest dialog')
      await closeOverlayByEscape(page, dialog)
      await waitForLightTransition(page)
    }
    return actions
  },
  risk: async (page) => {
    const actions = []
    if (await clickByRole(page, 'button', '实时刷新')) {
      actions.push('refreshed risk overview')
      await waitForRefreshStable(page, { timeoutMs: 3000 })
      await expectVisible(page.locator('.risk-container'), 'verified risk container visible')
      actions.push('verified risk container visible')
    }
    if (await clickSegmentByText(page, '高风险')) {
      actions.push('filtered high risk events')
      await waitForLightTransition(page)
      await expectVisible(page.locator('.risk-events'), 'verified risk events visible')
      actions.push('verified risk events visible')
    }
    if (await clickByRole(page, 'button', '风控设置')) {
      actions.push('opened risk settings dialog')
      const dialog = await expectOverlay(page, '风控设置')
      actions.push('verified risk settings dialog')
      await closeOverlayByEscape(page, dialog)
      await waitForLightTransition(page)
    }
    return actions
  },
  financeNews: async (page) => {
    const actions = []
    if (await clickSegmentByText(page, '美股')) {
      actions.push('selected news US')
      await waitForStable(page, { quietWindowMs: 120, timeoutMs: 1000 })
    }
    if (await clickSegmentByText(page, 'A股')) {
      actions.push('selected news CN')
      await waitForStable(page, { quietWindowMs: 120, timeoutMs: 1000 })
    }
    if (await clickSegmentByText(page, '港股')) {
      actions.push('selected news HK')
      await waitForStable(page, { quietWindowMs: 120, timeoutMs: 1000 })
    }
    return actions
  },
  profile: async (page) => {
    const actions = []
    await waitForStable(page)
    actions.push('loaded profile')
    return actions
  },
  brokers: async (page) => {
    const actions = []
    await waitForStable(page)
    actions.push('loaded brokers')
    return actions
  },
  notifications: async (page) => {
    const actions = []
    if (await clickByRole(page, 'button', /刷新/)) {
      actions.push('refreshed notifications')
      await waitForStable(page, { minimumMs: 220, quietWindowMs: 180, timeoutMs: 1400 })
    }
    if (await clickSegmentByText(page, '交易')) {
      actions.push('filtered trade notifications')
      await waitForStable(page, { quietWindowMs: 120, timeoutMs: 1000 })
    }
    if (await clickSegmentByText(page, '风控')) {
      actions.push('filtered risk notifications')
      await waitForStable(page, { quietWindowMs: 120, timeoutMs: 1000 })
    }
    if (await clickSegmentByText(page, '系统')) {
      actions.push('filtered system notifications')
      await waitForStable(page, { quietWindowMs: 120, timeoutMs: 1000 })
    }
    return actions
  },
  settings: async (page) => {
    const actions = []
    if (await clickByRole(page, 'button', /刷新/)) {
      actions.push('refreshed system logs')
      await waitForRefreshStable(page)
    }
    return actions
  },
  users: async (page) => {
    const actions = []
    await waitForStable(page)
    actions.push('loaded user-management')
    return actions
  },
  scheduler: async (page) => {
    const actions = []
    if (await clickByRole(page, 'button', '刷新任务')) {
      actions.push('refreshed scheduler tasks')
      await waitForRefreshStable(page)
      await expectVisible(page.locator('.task-grid, .scheduler-page'), 'verified scheduler content visible')
      actions.push('verified scheduler content visible')
    }
    return actions
  },
  historyCoverage: async (page) => {
    const actions = []
    await expectVisible(page.getByText('历史补价覆盖'), 'verified history coverage title visible', 4000)
    actions.push('verified history coverage title')
    const keywordInput = page.getByPlaceholder('搜索标的 / 名称 / 市场')
    if (await keywordInput.isVisible().catch(() => false)) {
      await keywordInput.fill('NVDL')
      actions.push('searched NVDL coverage')
      await waitForRefreshStable(page, { timeoutMs: 3600 })
      await expectVisible(page.locator('.table-card'), 'verified history coverage table visible', 4000)
      actions.push('verified history coverage table visible')
      await keywordInput.clear()
    }
    return actions
  }
}

await fs.mkdir(artifactsDir, { recursive: true })

let mobilePage = null
const browser = await chromium.launch(await resolveBrowserLaunchOptions())
const attachListeners = (page) => {
  page.on('pageerror', (error) => {
    pushError('pageerror', { message: error?.stack || error?.message || String(error), url: page.url() })
  })

  page.on('console', (msg) => {
    if (
      msg.type() === 'error' &&
      msg.text() === 'Failed to load resource: the server responded with a status of 404 (Not Found)' &&
      page.url().includes('/settings')
    ) {
      return
    }
    if (msg.type() === 'error') {
      pushError('console', { message: msg.text(), url: page.url() })
    }
  })

  page.on('requestfailed', (request) => {
    const failure = request.failure()?.errorText || 'request failed'
    if (failure.includes('ERR_ABORTED')) {
      return
    }
    pushError('requestfailed', {
      url: request.url(),
      method: request.method(),
      failure
    })
  })

  page.on('response', async (response) => {
    if (response.status() >= 400 && response.url().includes('/svc/')) {
      if (isOptionalOutbox404(response.url(), response.status())) {
        return
      }
      let body = ''
      try {
        body = sanitizeText(await response.text()).slice(0, 280)
      } catch {
        body = ''
      }
      pushError('http', {
        url: response.url(),
        status: response.status(),
        body
      })
    }
  })
}

const desktopVisits = [
  { route: '/dashboard', name: 'dashboard', action: pageActions.dashboard },
  { route: '/market', name: 'market', action: pageActions.market },
  { route: '/stock-pool', name: 'stock-pool', action: pageActions.stockPool },
  { route: '/ai-analysis', name: 'ai-analysis', action: pageActions.aiAnalysis },
  { route: '/trading', name: 'trading', action: pageActions.trading },
  { route: '/positions', name: 'positions', action: pageActions.positions },
  { route: '/orders', name: 'orders', action: pageActions.orders },
  { route: '/symbol/AAPL.US', name: 'symbol-detail', action: pageActions.symbolDetail },
  { route: '/kline', name: 'kline', action: pageActions.kline },
  { route: '/recommendations', name: 'recommendations', action: pageActions.recommendations },
  { route: '/finance-news', name: 'finance-news', action: pageActions.financeNews },
  { route: '/strategy', name: 'strategy', action: pageActions.strategy },
  { route: '/backtest', name: 'backtest', action: pageActions.backtest },
  { route: '/risk', name: 'risk', action: pageActions.risk },
  { route: '/profile', name: 'profile', action: pageActions.profile },
  { route: '/broker-management', name: 'broker-management', action: pageActions.brokers },
  { route: '/notifications', name: 'notifications', action: pageActions.notifications },
  { route: '/settings', name: 'settings', action: pageActions.settings },
  { route: '/user-management', name: 'user-management', action: pageActions.users },
  { route: '/scheduler-center', name: 'scheduler-center', action: pageActions.scheduler },
  { route: '/history-coverage', name: 'history-coverage', action: pageActions.historyCoverage }
]

const mobileVisits = [
  { route: '/dashboard', name: 'dashboard', action: pageActions.dashboard },
  { route: '/market', name: 'market', action: pageActions.market },
  { route: '/trading', name: 'trading', action: pageActions.trading }
]

const login = async (page) => {
  const scenario = page === mobilePage ? 'mobile' : 'desktop'
  progress(`login start ${scenario}`)

  await withStepTimeout(
    page.goto(`${baseUrl}/login`, { waitUntil: 'domcontentloaded' }),
    { label: `${scenario}:login:goto`, timeoutMs: PAGE_TIMEOUT_MS }
  )
  await withStepTimeout(
    page.getByPlaceholder('用户名').fill(username),
    { label: `${scenario}:login:username`, timeoutMs: 8000 }
  )
  await withStepTimeout(
    page.getByPlaceholder('密码').fill(password),
    { label: `${scenario}:login:password`, timeoutMs: 8000 }
  )
  await withStepTimeout(
    clickByRole(page, 'button', '登录', { timeout: 8000 }),
    { label: `${scenario}:login:submit`, timeoutMs: 10000 }
  )
  await withStepTimeout(
    page.waitForURL(/\/dashboard/, { timeout: 20000 }),
    { label: `${scenario}:login:redirect`, timeoutMs: 22000 }
  )
  await withStepTimeout(
    waitForStable(page, 2000),
    { label: `${scenario}:login:stabilize`, timeoutMs: 12000 }
  )

  progress(`login done ${scenario}`)
}

const desktopContext = await browser.newContext({ viewport: { width: 1440, height: 960 } })
const desktopPage = await desktopContext.newPage()
attachListeners(desktopPage)

if (RUN_MOBILE_SMOKE) {
  const mobileContext = await browser.newContext({
    viewport: { width: 430, height: 932 },
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'
  })
  mobilePage = await mobileContext.newPage()
  attachListeners(mobilePage)
}

try {
  await login(desktopPage)
  await visitPages(desktopPage, desktopVisits, 'desktop')

  if (RUN_MOBILE_SMOKE && mobilePage) {
    await login(mobilePage)
    await visitPages(mobilePage, mobileVisits, 'mobile')
  }
} finally {
  await closeBrowserQuietly(browser)
}

const report = {
  generatedAt: new Date().toISOString(),
  baseUrl,
  username,
  mobileIncluded: RUN_MOBILE_SMOKE,
  aiAnalysisDeepScan: AI_ANALYSIS_DEEP_SCAN,
  pageFilters: PAGE_FILTERS,
  pages: results,
  errors
}

const reportFile = path.join(artifactsDir, 'web-portal-smoke-report.json')
await fs.writeFile(reportFile, JSON.stringify(report, null, 2), 'utf8')

const summaryLines = [
  `baseUrl=${baseUrl}`,
  `mobileIncluded=${RUN_MOBILE_SMOKE}`,
  `aiAnalysisDeepScan=${AI_ANALYSIS_DEEP_SCAN}`,
  `pageFilters=${PAGE_FILTERS.join(',') || 'all'}`,
  `pages=${results.length}`,
  `errors=${errors.length}`
]

for (const pageResult of results) {
  summaryLines.push(
    `${pageResult.ok ? 'OK' : 'FAIL'} ${pageResult.name} ${pageResult.route} ready=${pageResult.initialReadyDurationMs ?? pageResult.readinessDurationMs}ms actionMs=${pageResult.actionDurationMs || 0}ms snapshotMs=${pageResult.snapshotDurationMs || 0}ms total=${pageResult.durationMs}ms verify=${pageResult.verificationDurationMs}ms actions=${pageResult.actions.length}+${pageResult.verificationActions.length}`
  )
}

if (errors.length) {
  summaryLines.push('--- errors ---')
  for (const error of errors.slice(0, 50)) {
    summaryLines.push(`${error.type} ${error.status || ''} ${error.url || ''} ${error.message || error.failure || ''}`.trim())
  }
}

console.log(summaryLines.join('\n'))

if (errors.length) {
  process.exitCode = 1
}

process.exit(process.exitCode || 0)

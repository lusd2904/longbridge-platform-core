const normalizeTimeout = (value, fallback) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

export const sanitizeText = (value) => String(value || '').replace(/\s+/g, ' ').trim()

export const OPTIONAL_OUTBOX_ENDPOINTS = [
  '/svc/trade/api/v1/trade/outbox/events',
  '/svc/trade/api/v1/trade/outbox/sagas'
]

export const isOptionalOutbox404 = (url = '', status = 0) => {
  return Number(status) === 404 && OPTIONAL_OUTBOX_ENDPOINTS.some((pattern) => String(url || '').includes(pattern))
}

export const shouldIgnoreSmokeHttpError = ({ url = '', status = 0 } = {}) => {
  return isOptionalOutbox404(url, status)
}

export const shouldIgnoreSmokeConsoleError = ({ type = '', text = '', pageUrl = '' } = {}) => {
  return type === 'error' &&
    text === 'Failed to load resource: the server responded with a status of 404 (Not Found)' &&
    String(pageUrl || '').includes('/settings')
}

export const shouldIgnoreSmokeRequestFailure = (failure = '') => {
  return String(failure || '').includes('ERR_ABORTED')
}

export const normalizePageStabilityOptions = (options = {}) => {
  if (typeof options === 'number') {
    const minimumMs = normalizeTimeout(options, 0)
    return {
      loadState: 'domcontentloaded',
      minimumMs,
      quietWindowMs: 220,
      timeoutMs: Math.max(minimumMs + 1200, 2000)
    }
  }

  const minimumMs = normalizeTimeout(options.minimumMs ?? options.minWaitMs, 0)
  const quietWindowMs = normalizeTimeout(options.quietWindowMs ?? options.idleMs, 220)

  return {
    loadState: options.loadState || 'domcontentloaded',
    minimumMs,
    quietWindowMs,
    timeoutMs: Math.max(
      normalizeTimeout(options.timeoutMs, 2000),
      minimumMs + quietWindowMs + 600
    )
  }
}

export const withStepTimeout = async (task, options = {}) => {
  const label = options.label || 'smoke-step'
  const timeoutMs = normalizeTimeout(options.timeoutMs, 30000)

  let timer = null

  try {
    return await Promise.race([
      Promise.resolve(task),
      new Promise((_, reject) => {
        timer = setTimeout(() => {
          reject(new Error(`${label} timed out after ${timeoutMs}ms`))
        }, timeoutMs)
      })
    ])
  } finally {
    if (timer) {
      clearTimeout(timer)
    }
  }
}

export const waitForPageStable = async (page, options = {}) => {
  const config = normalizePageStabilityOptions(options)

  await page.waitForLoadState(config.loadState)

  if (config.minimumMs > 0) {
    await page.waitForTimeout(config.minimumMs)
  }

  await page.waitForFunction(
    ({ quietWindowMs }) => {
      const isVisible = (node) => {
        if (!node) {
          return false
        }

        const style = window.getComputedStyle(node)
        if (
          style.display === 'none' ||
          style.visibility === 'hidden' ||
          style.opacity === '0' ||
          node.getAttribute('aria-hidden') === 'true'
        ) {
          return false
        }

        const rect = node.getBoundingClientRect()
        return rect.width > 0 && rect.height > 0
      }

      const blockingLoaders = [
        ...document.querySelectorAll('.el-loading-mask'),
        ...document.querySelectorAll('[aria-busy="true"]'),
        ...document.querySelectorAll('.scan-loading-panel')
      ].filter(isVisible).length

      const signature = [
        document.readyState,
        window.location.pathname,
        window.location.search,
        blockingLoaders
      ].join('|')
      const state = window.__smokePageStableState || (window.__smokePageStableState = {})
      const now = Date.now()

      if (state.signature !== signature) {
        state.signature = signature
        state.changedAt = now
        return false
      }

      return now - (state.changedAt || now) >= quietWindowMs
    },
    { quietWindowMs: config.quietWindowMs },
    { timeout: config.timeoutMs }
  )
}

export const createProgressReporter = (options = {}) => {
  const enabled = options.enabled !== false

  return (message) => {
    if (!enabled) {
      return
    }

    const timestamp = new Date().toISOString()
    console.log(`[smoke ${timestamp}] ${message}`)
  }
}

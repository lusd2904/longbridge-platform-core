import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  normalizePageStabilityOptions,
  shouldIgnoreSmokeConsoleError,
  shouldIgnoreSmokeHttpError,
  shouldIgnoreSmokeRequestFailure,
  waitForPageStable,
  withStepTimeout
} from '../../scripts/smoke-helpers.mjs'
import {
  collectRenderableSuggestionTexts,
  filterLocalSuggestionMatches,
  hasExpectedSuggestion,
  mergeSuggestionSources,
  normalizeSuggestionEntry,
  rankSuggestionMatches
} from '../../src/utils/aiAnalysisSuggestions.js'
import { normalizeBaseUrl } from '../../../../../scripts/base_url_helper.cjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const projectRoot = path.resolve(__dirname, '../..')

describe('withStepTimeout', () => {
  it('resolves the original result before the timeout window', async () => {
    const result = await withStepTimeout(
      Promise.resolve('ok'),
      { label: 'dashboard:goto', timeoutMs: 50 }
    )

    expect(result).toBe('ok')
  })

  it('rejects with the step label when execution exceeds the timeout window', async () => {
    await expect(withStepTimeout(
      new Promise(() => {}),
      { label: 'mobile:trading:actions', timeoutMs: 10 }
    )).rejects.toThrow('mobile:trading:actions timed out after 10ms')
  })
})

describe('page stability helpers', () => {
  it('uses a short quiet-window strategy by default and preserves explicit minimum waits', () => {
    expect(normalizePageStabilityOptions()).toEqual({
      loadState: 'domcontentloaded',
      minimumMs: 0,
      quietWindowMs: 220,
      timeoutMs: 2000
    })

    expect(normalizePageStabilityOptions(1200)).toEqual({
      loadState: 'domcontentloaded',
      minimumMs: 1200,
      quietWindowMs: 220,
      timeoutMs: 2400
    })
  })

  it('waits for domcontentloaded, the optional minimum delay, and a quiet DOM window', async () => {
    const calls = []
    const page = {
      waitForLoadState: async (state) => calls.push(['load', state]),
      waitForTimeout: async (ms) => calls.push(['timeout', ms]),
      waitForFunction: async (_fn, args, options) => calls.push(['function', args, options])
    }

    await waitForPageStable(page, { minimumMs: 180, quietWindowMs: 120, timeoutMs: 900 })

    expect(calls).toEqual([
      ['load', 'domcontentloaded'],
      ['timeout', 180],
      ['function', { quietWindowMs: 120 }, { timeout: 900 }]
    ])
  })
})

describe('normalizeBaseUrl', () => {
  it('accepts explicit http and https base URLs', () => {
    expect(normalizeBaseUrl('http://127.0.0.1:3100')).toBe('http://127.0.0.1:3100')
    expect(normalizeBaseUrl('https://example.test/app/')).toBe('https://example.test/app')
  })

  it('rejects protocol typos instead of silently repairing test targets', () => {
    expect(() => normalizeBaseUrl('http//127.0.0.1:3100')).toThrow('must include "://"')
    expect(() => normalizeBaseUrl('http:/127.0.0.1:3100')).toThrow('must include "://"')
    expect(() => normalizeBaseUrl('http:127.0.0.1:3100')).toThrow('must include "://"')
  })
})

describe('smoke page route coverage', () => {
  const expectedAuthenticatedRoutes = () => {
    const routerSource = readFileSync(path.join(projectRoot, 'src/router/index.js'), 'utf8')
    return Array.from(routerSource.matchAll(/path: '([^']+)'/g))
      .map((match) => match[1])
      .filter((routePath) => (
        routePath !== '/' &&
        routePath !== '/login' &&
        routePath !== '/:pathMatch(.*)*'
      ))
      .map((routePath) => routePath.startsWith('/') ? routePath : `/${routePath}`)
      .map((routePath) => routePath
        .replace('/:symbol/scan-result', '/AAPL.US/scan-result')
        .replace('/:symbol', '/AAPL.US')
      )
  }

  it('keeps desktop smoke visits aligned with authenticated router pages', () => {
    const smokeSource = readFileSync(path.join(projectRoot, 'scripts/smoke-pages.mjs'), 'utf8')
    const desktopVisitsMatch = smokeSource.match(/const desktopVisits = \[([\s\S]*?)\n\]/)

    expect(desktopVisitsMatch).toBeTruthy()

    const smokeRoutes = new Set(
      Array.from(desktopVisitsMatch[1].matchAll(/route: '([^']+)'/g)).map((match) => match[1])
    )

    expect(smokeRoutes).toContain('/')
    for (const routePath of expectedAuthenticatedRoutes()) {
      expect(smokeRoutes).toContain(routePath)
    }
  })

  it('keeps mobile smoke visits aligned with the full desktop page matrix', () => {
    const smokeSource = readFileSync(path.join(projectRoot, 'scripts/smoke-pages.mjs'), 'utf8')

    expect(smokeSource).toMatch(/const mobileVisits = desktopVisits\b/)
  })

  it('keeps contrast scan routes aligned with authenticated router pages', () => {
    const contrastSource = readFileSync(path.join(projectRoot, 'scripts/contrast-scan.mjs'), 'utf8')
    const routesMatch = contrastSource.match(/const routes = \[([\s\S]*?)\n\]/)

    expect(routesMatch).toBeTruthy()

    const contrastRoutes = new Set(
      Array.from(routesMatch[1].matchAll(/route: '([^']+)'/g)).map((match) => match[1])
    )

    expect(contrastSource).toContain("scanTarget({ route: '/login', name: 'login' })")
    expect(contrastRoutes).toContain('/')
    for (const routePath of expectedAuthenticatedRoutes()) {
      expect(contrastRoutes).toContain(routePath)
    }
  })
})

describe('smoke failure ignore rules', () => {
  it('ignores only documented optional trade outbox 404 endpoints', () => {
    expect(shouldIgnoreSmokeHttpError({
      url: 'http://127.0.0.1:3100/svc/trade/api/v1/trade/outbox/events',
      status: 404
    })).toBe(true)
    expect(shouldIgnoreSmokeHttpError({
      url: 'http://127.0.0.1:3100/svc/trade/api/v1/trade/outbox/sagas',
      status: 404
    })).toBe(true)
    expect(shouldIgnoreSmokeHttpError({
      url: 'http://127.0.0.1:3100/svc/trade/api/v1/trade/outbox/events',
      status: 500
    })).toBe(false)
    expect(shouldIgnoreSmokeHttpError({
      url: 'http://127.0.0.1:3100/svc/market/api/v1/quotes',
      status: 404
    })).toBe(false)
  })

  it('keeps console and request-failure ignores narrow', () => {
    expect(shouldIgnoreSmokeConsoleError({
      type: 'error',
      text: 'Failed to load resource: the server responded with a status of 404 (Not Found)',
      pageUrl: 'http://127.0.0.1:3100/settings'
    })).toBe(true)
    expect(shouldIgnoreSmokeConsoleError({
      type: 'error',
      text: 'Failed to load resource: the server responded with a status of 500 (Internal Server Error)',
      pageUrl: 'http://127.0.0.1:3100/settings'
    })).toBe(false)
    expect(shouldIgnoreSmokeRequestFailure('net::ERR_ABORTED')).toBe(true)
    expect(shouldIgnoreSmokeRequestFailure('net::ECONNRESET')).toBe(false)
  })
})

describe('aiAnalysisSuggestions', () => {
  it('keeps direct NVDA symbol matches ahead of looser matches and removes duplicates', () => {
    const manual = normalizeSuggestionEntry({ symbol: 'NVDA.US', name: 'NVIDIA Corp', market: 'us' })
    const local = filterLocalSuggestionMatches([
      { symbol: 'NVDL.US', name: 'GraniteShares 2x Long NVDA Daily ETF', market: 'US' },
      { symbol: 'NVDA.US', name: 'NVIDIA Corporation', market: 'US' }
    ], 'nvda')
    const remote = [
      normalizeSuggestionEntry({ symbol: 'NVDA.US', name: 'NVIDIA', market: 'US' }),
      normalizeSuggestionEntry({ symbol: 'NVDS.US', name: 'Tradr 1.5X Short NVDA Daily ETF', market: 'US' })
    ]

    const ranked = rankSuggestionMatches(
      mergeSuggestionSources([manual], local, remote),
      'nvda'
    )

    expect(ranked.map((item) => item.symbol)).toEqual(['NVDA.US', 'NVDL.US', 'NVDS.US'])
  })

  it('keeps exact base-symbol suggestions stable for nvda and nvdl inputs', () => {
    const targets = [
      { symbol: 'NVDA.US', name: 'NVIDIA Corporation', market: 'US' },
      { symbol: 'NVDL.US', name: 'GraniteShares 2x Long NVDA Daily ETF', market: 'US' }
    ]

    const nvdaRanked = rankSuggestionMatches(
      mergeSuggestionSources(
        [normalizeSuggestionEntry({ symbol: 'NVDA.US', name: 'NVDA.US', market: 'US' })],
        filterLocalSuggestionMatches(targets, 'nvda')
      ),
      'nvda'
    )
    const nvdlRanked = rankSuggestionMatches(
      mergeSuggestionSources(
        [normalizeSuggestionEntry({ symbol: 'NVDL.US', name: 'NVDL.US', market: 'US' })],
        filterLocalSuggestionMatches(targets, 'nvdl')
      ),
      'nvdl'
    )

    expect(nvdaRanked.map((item) => item.symbol).slice(0, 2)).toEqual(['NVDA.US', 'NVDL.US'])
    expect(nvdlRanked[0]?.symbol).toBe('NVDL.US')
  })

  it('treats empty rendered suggestion text as absent while still matching expected targets', () => {
    const texts = collectRenderableSuggestionTexts(['', '   ', '\nNVDA.US NVIDIA\n', 'NVDL.US ETF'])

    expect(texts).toEqual(['NVDA.US NVIDIA', 'NVDL.US ETF'])
    expect(hasExpectedSuggestion(texts, ['NVDA.US'])).toBe(true)
    expect(hasExpectedSuggestion(['', ' '], ['NVDA.US', 'NVDL.US'])).toBe(false)
    expect(hasExpectedSuggestion(texts, ['TSLA.US'])).toBe(false)
  })
})

import { describe, expect, it } from 'vitest'
import { normalizePageStabilityOptions, waitForPageStable, withStepTimeout } from '../../scripts/smoke-helpers.mjs'
import {
  collectRenderableSuggestionTexts,
  filterLocalSuggestionMatches,
  hasExpectedSuggestion,
  mergeSuggestionSources,
  normalizeSuggestionEntry,
  rankSuggestionMatches
} from '../../src/utils/aiAnalysisSuggestions.js'
import { normalizeBaseUrl } from '../../../../../scripts/base_url_helper.cjs'

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

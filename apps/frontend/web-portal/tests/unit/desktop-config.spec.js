import { describe, expect, it } from 'vitest'
import {
  buildPreloadContext,
  parseDesktopApiBase
} from '../../desktop/preload-context.cjs'
import {
  DESKTOP_APP_NAME,
  buildServiceTargets,
  buildWindowOptions,
  readConfiguredDesktopApiBase,
  readDesktopApiBase,
  readDesktopPort
} from '../../desktop/config.cjs'

describe('desktop config', () => {
  it('builds secure BrowserWindow options aligned with the web portal runtime', () => {
    const options = buildWindowOptions({
      dirname: '/tmp/refactor-v2/desktop',
      apiBaseUrl: 'http://127.0.0.1:3100',
      icon: '/tmp/icon.png'
    })

    expect(options.minWidth).toBe(1280)
    expect(options.title).toBe(DESKTOP_APP_NAME)
    expect(options.titleBarStyle).toBe('hiddenInset')
    expect(options.webPreferences).toEqual(expect.objectContaining({
      contextIsolation: true,
      nodeIntegration: false,
      preload: '/tmp/refactor-v2/desktop/preload.cjs',
      additionalArguments: ['--refv2-api-base=http://127.0.0.1:3100']
    }))
  })

  it('normalizes desktop ports, api base, and service targets', () => {
    expect(readDesktopPort({ REFV2_DESKTOP_PORT: '4999' })).toBe(4999)
    expect(readDesktopPort({ REFV2_DESKTOP_PORT: 'bad' })).toBe(4168)
    expect(readDesktopApiBase({ REFV2_DESKTOP_API_BASE: '127.0.0.1:4100/' })).toBe('http://127.0.0.1:4100')
    expect(readConfiguredDesktopApiBase({})).toBe('')
    expect(readConfiguredDesktopApiBase({ VITE_DESKTOP_API_BASE_URL: '127.0.0.1:4101/' })).toBe('http://127.0.0.1:4101')

    const targets = buildServiceTargets({
      REF_MARKET_SERVICE_PORT: '8202',
      REF_TRADE_SERVICE_PORT: '8205'
    })
    expect(targets.market).toBe('http://127.0.0.1:8202')
    expect(targets.trade).toBe('http://127.0.0.1:8205')
    expect(targets.gateway).toBe('http://127.0.0.1:5101')
  })

  it('exposes desktop preload context with api base and host OS metadata', () => {
    expect(parseDesktopApiBase(['electron', '--refv2-api-base=http://127.0.0.1:3100'])).toBe('http://127.0.0.1:3100')

    const context = buildPreloadContext(['electron', '--refv2-api-base=http://127.0.0.1:4100'])
    expect(context.__REFV2_DESKTOP__).toBe(true)
    expect(context.__REFV2_DESKTOP_API_BASE__).toBe('http://127.0.0.1:4100')
    expect(context.refactorDesktop).toEqual(expect.objectContaining({
      platform: 'desktop',
      apiBaseUrl: 'http://127.0.0.1:4100'
    }))
  })
})

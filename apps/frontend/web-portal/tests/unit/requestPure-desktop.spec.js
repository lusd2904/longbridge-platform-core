import { beforeEach, describe, expect, it, vi } from 'vitest'

function createStorageMock() {
  const store = new Map()
  return {
    getItem: (key) => store.get(String(key)) ?? null,
    setItem: (key, value) => store.set(String(key), String(value)),
    removeItem: (key) => store.delete(String(key)),
    clear: () => store.clear()
  }
}

vi.mock('@capacitor/core', () => ({
  Capacitor: {
    getPlatform: () => 'web',
    isNativePlatform: () => false,
    isPluginAvailable: () => false
  },
  CapacitorHttp: {
    request: vi.fn()
  }
}))

describe('requestPure desktop base URL resolution', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.unstubAllEnvs()
    const storageMock = createStorageMock()
    Object.defineProperty(window, 'localStorage', {
      value: storageMock,
      configurable: true
    })
    Object.defineProperty(globalThis, 'localStorage', {
      value: storageMock,
      configurable: true
    })
    window.localStorage.clear()
    delete window.__REFV2_DESKTOP__
    delete window.__REFV2_DESKTOP_API_BASE__
  })

  it('uses the preload api base inside the desktop container', async () => {
    window.__REFV2_DESKTOP__ = true
    window.__REFV2_DESKTOP_API_BASE__ = 'http://127.0.0.1:4168'

    const { getApiBaseUrl, isDesktopClient } = await import('../../src/utils/requestPure.js')

    expect(isDesktopClient()).toBe(true)
    expect(getApiBaseUrl()).toBe('http://127.0.0.1:4168')
  })

  it('lets explicit desktop env override the preload base', async () => {
    vi.stubEnv('VITE_DESKTOP_API_BASE_URL', 'http://127.0.0.1:3100')
    window.__REFV2_DESKTOP__ = true
    window.__REFV2_DESKTOP_API_BASE__ = 'http://127.0.0.1:4168'

    const { getApiBaseUrl } = await import('../../src/utils/requestPure.js')

    expect(getApiBaseUrl()).toBe('http://127.0.0.1:3100')
  })

  it('falls back to the browser origin outside native and desktop containers', async () => {
    const { getApiBaseUrl, isDesktopClient } = await import('../../src/utils/requestPure.js')

    expect(isDesktopClient()).toBe(false)
    expect(getApiBaseUrl()).toBe(window.location.origin)
  })
})

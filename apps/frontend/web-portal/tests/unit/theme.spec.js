import { afterEach, describe, expect, it, vi } from 'vitest'

const STORAGE_KEY = 'longbridge-active-theme'

function createStorageMock() {
  const store = new Map()

  return {
    getItem(key) {
      return store.has(String(key)) ? store.get(String(key)) : null
    },
    setItem(key, value) {
      store.set(String(key), String(value))
    },
    removeItem(key) {
      store.delete(String(key))
    },
    clear() {
      store.clear()
    }
  }
}

const installStorageMock = () => {
  const storageMock = createStorageMock()
  Object.defineProperty(window, 'localStorage', {
    value: storageMock,
    configurable: true
  })
  Object.defineProperty(globalThis, 'localStorage', {
    value: storageMock,
    configurable: true
  })
}

const resetThemeModule = async (storedTheme) => {
  vi.resetModules()
  installStorageMock()
  window.localStorage.clear()
  if (storedTheme) {
    window.localStorage.setItem(STORAGE_KEY, storedTheme)
  }
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.style.colorScheme = ''
  return import('../../src/composables/useTheme.js')
}

describe('useTheme', () => {
  afterEach(() => {
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.style.colorScheme = ''
  })

  it('restores a saved skin and applies it to the document', async () => {
    const { useTheme } = await resetThemeModule('emerald-core')
    const { activeTheme, themeMeta } = useTheme()

    expect(activeTheme.value).toBe('emerald-core')
    expect(themeMeta.value.label).toBe('翡翠')
    expect(document.documentElement.dataset.theme).toBe('emerald-core')
  })

  it('switches skins and persists the selected value', async () => {
    const { useTheme } = await resetThemeModule()
    const { activeTheme, themes, setTheme } = useTheme()

    expect(themes.map((theme) => theme.id)).toContain('solar-tide')

    setTheme('solar-tide')

    expect(activeTheme.value).toBe('solar-tide')
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('solar-tide')
    expect(document.documentElement.dataset.theme).toBe('solar-tide')
  })

  it('ignores unknown skin ids', async () => {
    const { useTheme } = await resetThemeModule('neon-grid')
    const { activeTheme, setTheme } = useTheme()

    setTheme('missing-theme')

    expect(activeTheme.value).toBe('neon-grid')
    expect(document.documentElement.dataset.theme).toBe('neon-grid')
  })
})

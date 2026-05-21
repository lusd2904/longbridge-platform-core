import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const getSessionMock = vi.fn()
const getTokenMock = vi.fn()
const setSessionMock = vi.fn()
const getPlatformBootstrapMock = vi.fn()
const replaceMock = vi.fn(() => Promise.resolve())

vi.mock('../../src/composables/useTheme.js', () => ({
  useTheme: () => ({ applyTheme: vi.fn() })
}))

vi.mock('../../src/utils/auth.js', () => ({
  getSession: getSessionMock,
  getToken: getTokenMock,
  setSession: setSessionMock
}))

vi.mock('../../src/api/platform.js', () => ({
  getPlatformBootstrap: getPlatformBootstrapMock
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/dashboard' }),
  useRouter: () => ({
    currentRoute: { value: { path: '/dashboard' } },
    isReady: () => Promise.resolve(),
    replace: replaceMock
  })
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    info: vi.fn(),
    success: vi.fn(),
    warning: vi.fn()
  },
  ElMessageBox: {
    confirm: vi.fn()
  }
}))

describe('App bootstrap refresh', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getTokenMock.mockReturnValue('token')
    getSessionMock.mockReturnValue({
      menus: [{ code: 'market', path: '/market' }],
      navigation: { homePath: '/dashboard' }
    })
    getPlatformBootstrapMock.mockResolvedValue({
      data: {
        menus: [
          { code: 'market', path: '/market' },
          { code: 'sentiment-center', path: '/sentiment-center' }
        ],
        navigation: { homePath: '/dashboard' }
      }
    })
  })

  it('refreshes cached platform bootstrap for existing logged-in sessions', async () => {
    const { default: App } = await import('../../src/App.vue')
    mount(App, {
      global: {
        stubs: {
          RouterView: { template: '<main />' }
        }
      }
    })

    await vi.waitFor(() => {
      expect(getPlatformBootstrapMock).toHaveBeenCalledTimes(1)
      expect(setSessionMock).toHaveBeenCalledWith(expect.objectContaining({
        menus: expect.arrayContaining([
          expect.objectContaining({ code: 'sentiment-center' })
        ])
      }))
    })
  })
})

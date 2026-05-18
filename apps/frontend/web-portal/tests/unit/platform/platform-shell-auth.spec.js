import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  clearAuth,
  getActiveView,
  getMenusByView,
  getViews,
  setActiveView,
  setSession
} from '@/utils/auth.js'

const sessionPayload = {
  user: {
    roleCode: 'trader'
  },
  menus: [
    {
      routeName: 'Dashboard',
      path: '/dashboard',
      title: '仪表盘',
      subsystemCode: 'workspace'
    },
    {
      routeName: 'Trading',
      path: '/trading',
      title: '交易台',
      subsystemCode: 'trading'
    },
    {
      routeName: 'AIAnalysis',
      path: '/ai-analysis',
      title: 'AI研判',
      subsystemCode: 'analysis'
    }
  ]
}

function createStorageMock() {
  const store = new Map()

  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null
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

describe('auth platform shell helpers', () => {
  beforeEach(() => {
    const storageMock = createStorageMock()
    Object.defineProperty(window, 'localStorage', {
      value: storageMock,
      configurable: true
    })
    Object.defineProperty(globalThis, 'localStorage', {
      value: storageMock,
      configurable: true
    })
    localStorage.clear()
  })

  afterEach(() => {
    clearAuth()
  })

  it('返回视角列表并持久化当前视角', () => {
    setSession(sessionPayload)

    expect(getViews().map((item) => item.code)).toEqual(['trading', 'composite'])
    expect(getActiveView()).toBe('trading')

    setActiveView('composite')

    expect(getActiveView()).toBe('composite')
  })

  it('按视角过滤菜单', () => {
    setSession(sessionPayload)

    expect(getMenusByView('trading').map((item) => item.routeName)).toEqual([
      'Dashboard',
      'Trading'
    ])
    expect(getMenusByView('composite').map((item) => item.routeName)).toEqual([
      'Dashboard',
      'Trading',
      'AIAnalysis'
    ])
  })
})

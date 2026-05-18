import { describe, expect, it } from 'vitest'
import { VIEW_REGISTRY } from '@/platform/shell/viewRegistry.js'
import {
  buildPlatformShellModel,
  isFeatureEnabled,
  normalizeFeatureFlags
} from '@/platform/shell/platformShellModel.js'

const sessionPayload = {
  user: {
    roleCode: 'trader'
  },
  menus: [
    {
      routeName: 'Dashboard',
      path: '/dashboard',
      title: '仪表盘',
      subsystemCode: 'workspace',
      icon: 'Odometer'
    },
    {
      routeName: 'Trading',
      path: '/trading',
      title: '交易台',
      subsystemCode: 'trading',
      icon: 'Wallet'
    },
    {
      routeName: 'Orders',
      path: '/orders',
      title: '订单管理',
      subsystemCode: 'trading',
      icon: 'List'
    },
    {
      routeName: 'AIAnalysis',
      path: '/ai-analysis',
      title: 'AI研判',
      subsystemCode: 'analysis',
      icon: 'Cpu'
    },
    {
      routeName: 'Settings',
      path: '/settings',
      title: '系统设置',
      subsystemCode: 'platform',
      icon: 'Setting'
    }
  ],
  featureFlags: [
    {
      code: 'view.management',
      enabled: false
    }
  ]
}

describe('platformShellModel', () => {
  it('暴露稳定的视角注册表', () => {
    expect(Object.keys(VIEW_REGISTRY)).toEqual([
      'trading',
      'research',
      'management',
      'composite'
    ])
    expect(VIEW_REGISTRY.trading.allowedSubsystems).toContain('trading')
    expect(VIEW_REGISTRY.research.allowedSubsystems).toContain('analysis')
  })

  it('根据角色、开关和终端生成可用视角与可见菜单', () => {
    const model = buildPlatformShellModel({
      session: sessionPayload,
      activeViewCode: 'trading',
      terminal: 'web'
    })

    expect(model.activeView.code).toBe('trading')
    expect(model.availableViews.map((item) => item.code)).toEqual([
      'trading',
      'composite'
    ])
    expect(model.visibleMenus.map((item) => item.routeName)).toEqual([
      'Dashboard',
      'Trading',
      'Orders'
    ])
  })

  it('在存储视角失效时回退到第一个可用视角', () => {
    const model = buildPlatformShellModel({
      session: sessionPayload,
      activeViewCode: 'management',
      terminal: 'web'
    })

    expect(model.activeView.code).toBe('trading')
  })

  it('在多角色场景下允许次级角色解锁对应视角', () => {
    const model = buildPlatformShellModel({
      session: {
        ...sessionPayload,
        access: {
          roles: ['analyst']
        },
        featureFlags: [
          {
            code: 'view.research',
            enabled: true,
            roles: ['analyst']
          }
        ]
      },
      activeViewCode: 'research',
      terminal: 'web'
    })

    expect(model.availableViews.map((item) => item.code)).toEqual([
      'trading',
      'composite',
      'research'
    ])
    expect(model.activeView.code).toBe('research')
    expect(model.visibleMenus.map((item) => item.routeName)).toEqual([
      'Dashboard',
      'AIAnalysis'
    ])
  })

  it('按角色与终端判断开关是否开启', () => {
    const flags = normalizeFeatureFlags([
      {
        code: 'view.research',
        enabled: true,
        roles: ['analyst', 'trader'],
        terminals: ['web', 'desktop']
      }
    ])

    expect(isFeatureEnabled(flags, 'view.research', { roleCode: 'trader', terminal: 'web' })).toBe(true)
    expect(isFeatureEnabled(flags, 'view.research', { roleCode: 'viewer', terminal: 'web' })).toBe(false)
    expect(isFeatureEnabled(flags, 'view.research', { roleCode: 'trader', terminal: 'mobile' })).toBe(false)
  })
})

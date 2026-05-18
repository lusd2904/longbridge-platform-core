import { describe, expect, it } from 'vitest'
import { resolveViewBySubsystem } from '@/platform/shell/viewRouting.js'

describe('resolveViewBySubsystem', () => {
  it('把 analysis 路由归到研究视角', () => {
    expect(resolveViewBySubsystem('analysis', 'trading')).toBe('research')
  })

  it('把 platform 路由归到管理视角', () => {
    expect(resolveViewBySubsystem('platform', 'trading')).toBe('management')
  })

  it('为 workspace 保留当前视角', () => {
    expect(resolveViewBySubsystem('workspace', 'composite')).toBe('composite')
  })
})

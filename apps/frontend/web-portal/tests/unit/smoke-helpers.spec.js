import { describe, expect, it } from 'vitest'
import { withStepTimeout } from '../../scripts/smoke-helpers.mjs'

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

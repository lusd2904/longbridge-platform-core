import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DeferredBlock from '@/components/common/DeferredBlock.vue'

describe('DeferredBlock', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders fallback content before activation', () => {
    const wrapper = mount(DeferredBlock, {
      props: {
        active: false,
        delay: 0
      },
      slots: {
        fallback: '<div class="loading-state">loading</div>',
        default: '<div class="loaded-state">loaded</div>'
      }
    })

    expect(wrapper.find('.loading-state').exists()).toBe(true)
    expect(wrapper.find('.loaded-state').exists()).toBe(false)
  })

  it('renders default slot after delay once activated', async () => {
    vi.useFakeTimers()
    const wrapper = mount(DeferredBlock, {
      props: {
        active: true,
        delay: 120
      },
      slots: {
        fallback: '<div class="loading-state">loading</div>',
        default: '<div class="loaded-state">loaded</div>'
      }
    })

    expect(wrapper.find('.loading-state').exists()).toBe(true)

    vi.advanceTimersByTime(121)
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.loaded-state').exists()).toBe(true)
    expect(wrapper.find('.loading-state').exists()).toBe(false)
  })
})

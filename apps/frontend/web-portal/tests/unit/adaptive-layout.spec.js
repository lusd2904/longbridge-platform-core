import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import { useAdaptiveLayout } from '../../src/composables/useAdaptiveLayout.js'

const Probe = {
  template: '<div />',
  setup() {
    return useAdaptiveLayout()
  }
}

function setViewportWidth(width) {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: width
  })
  window.dispatchEvent(new Event('resize'))
}

describe('useAdaptiveLayout', () => {
  it('switches compact and phone layout from viewport width', async () => {
    setViewportWidth(1440)
    const wrapper = mount(Probe)

    expect(wrapper.vm.isCompactLayout).toBe(false)
    expect(wrapper.vm.isPhoneLayout).toBe(false)

    setViewportWidth(390)
    await nextTick()

    expect(wrapper.vm.isCompactLayout).toBe(true)
    expect(wrapper.vm.isPhoneLayout).toBe(true)

    setViewportWidth(900)
    await nextTick()

    expect(wrapper.vm.isCompactLayout).toBe(true)
    expect(wrapper.vm.isPhoneLayout).toBe(false)
  })
})

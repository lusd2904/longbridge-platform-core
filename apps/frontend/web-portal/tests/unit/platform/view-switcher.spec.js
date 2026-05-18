import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ViewSwitcher from '@/components/layout/ViewSwitcher.vue'

describe('ViewSwitcher', () => {
  it('渲染全部可用视角并高亮当前视角', () => {
    const wrapper = mount(ViewSwitcher, {
      props: {
        modelValue: 'trading',
        views: [
          { code: 'trading', title: '交易视角', description: '执行链路' },
          { code: 'research', title: '研究视角', description: '研究链路' }
        ]
      }
    })

    expect(wrapper.text()).toContain('交易视角')
    expect(wrapper.text()).toContain('研究视角')
    expect(wrapper.find('[data-view-code="trading"]').classes()).toContain('active')
  })

  it('点击非当前视角时抛出变更事件', async () => {
    const wrapper = mount(ViewSwitcher, {
      props: {
        modelValue: 'trading',
        views: [
          { code: 'trading', title: '交易视角', description: '执行链路' },
          { code: 'research', title: '研究视角', description: '研究链路' }
        ]
      }
    })

    await wrapper.find('[data-view-code="research"]').trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([['research']])
    expect(wrapper.emitted('change')[0][0]).toMatchObject({ code: 'research' })
  })
})

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PageHero from '@/components/common/PageHero.vue'
import MetricStrip from '@/components/common/MetricStrip.vue'
import SectionCardHeader from '@/components/common/SectionCardHeader.vue'

describe('page shell components', () => {
  it('renders the page hero title, chips, metrics, and actions slot', () => {
    const wrapper = mount(PageHero, {
      props: {
        kicker: 'Trade cockpit',
        title: '交易台',
        description: '把委托、行情和执行结果收在同一工作区。',
        chips: [
          { text: '实时覆盖' },
          { text: '移动优先', tone: 'success' }
        ],
        metrics: [
          { label: '账户', value: 'Alpha' },
          { label: '状态', value: '已连接', tone: 'healthy' }
        ]
      },
      slots: {
        actions: '<button class="hero-action">刷新</button>',
        aside: '<div class="hero-aside">执行上下文</div>'
      }
    })

    expect(wrapper.text()).toContain('交易台')
    expect(wrapper.text()).not.toContain('Trade cockpit')
    expect(wrapper.text()).toContain('实时覆盖')
    expect(wrapper.text()).toContain('账户')
    expect(wrapper.find('.page-hero__actions .hero-action').exists()).toBe(true)
    expect(wrapper.find('.page-hero__aside .hero-aside').exists()).toBe(true)
  })

  it('applies success and info semantic tones for hero chips and metrics', () => {
    const wrapper = mount(PageHero, {
      props: {
        title: '市场快照',
        chips: [
          { text: '已连接', tone: 'success' },
          { text: '数据库读库', tone: 'info' }
        ],
        metrics: [
          { label: '链路', value: '在线', tone: 'success' },
          { label: '模式', value: '快照', tone: 'info' }
        ]
      }
    })

    expect(wrapper.find('.page-hero__chip.success').exists()).toBe(true)
    expect(wrapper.find('.page-hero__chip.info').exists()).toBe(true)
    expect(wrapper.find('.page-hero__metric-value.success').exists()).toBe(true)
    expect(wrapper.find('.page-hero__metric-value.info').exists()).toBe(true)
  })

  it('hides metric strip notes unless requested', () => {
    const wrapper = mount(MetricStrip, {
      props: {
        items: [
          { label: '可用资金', value: '$128,000', note: '账户净值稳定' },
          { label: '市场状态', value: '风险偏好回暖', tone: 'healthy' }
        ]
      }
    })

    expect(wrapper.findAll('.metric-strip__item')).toHaveLength(2)
    expect(wrapper.text()).toContain('可用资金')
    expect(wrapper.text()).not.toContain('账户净值稳定')
    expect(wrapper.find('.metric-strip__note').exists()).toBe(false)
    expect(wrapper.find('.metric-strip__value.healthy').exists()).toBe(true)
  })

  it('renders metric strip notes when explicitly enabled', () => {
    const wrapper = mount(MetricStrip, {
      props: {
        showNotes: true,
        items: [
          { label: '可用资金', value: '$128,000', note: '账户净值稳定' }
        ]
      }
    })

    expect(wrapper.text()).toContain('账户净值稳定')
    expect(wrapper.find('.metric-strip__note').exists()).toBe(true)
  })

  it('applies success and info semantic tones for metric strip items', () => {
    const wrapper = mount(MetricStrip, {
      props: {
        items: [
          { label: '同步模式', value: '实时覆盖', tone: 'success' },
          { label: '数据源', value: '读库底座', tone: 'info' }
        ]
      }
    })

    expect(wrapper.find('.metric-strip__value.success').exists()).toBe(true)
    expect(wrapper.find('.metric-strip__value.info').exists()).toBe(true)
  })

  it('normalizes trend aliases to shared metric strip tones', () => {
    const wrapper = mount(MetricStrip, {
      props: {
        items: [
          { label: '连接状态', value: '在线', tone: 'up' },
          { label: '浮盈浮亏', value: '-2.4%', tone: 'negative' },
          { label: '信号来源', value: '快照模式', tone: 'neutral' }
        ]
      }
    })

    const values = wrapper.findAll('.metric-strip__value')
    expect(values[0].classes()).toContain('healthy')
    expect(values[0].classes()).not.toContain('up')
    expect(values[1].classes()).toContain('error')
    expect(values[1].classes()).not.toContain('negative')
    expect(values[2].classes()).toContain('info')
    expect(values[2].classes()).not.toContain('neutral')
  })

  it('renders section card header copy and secondary actions', () => {
    const wrapper = mount(SectionCardHeader, {
      props: {
        title: '市场快照',
        description: '最新分析和报价会在这里汇总。',
        badge: '数据库回看',
        showDescription: true
      },
      slots: {
        actions: '<button class="section-action">刷新分析</button>'
      }
    })

    expect(wrapper.text()).toContain('市场快照')
    expect(wrapper.text()).toContain('最新分析和报价会在这里汇总。')
    expect(wrapper.text()).toContain('数据库回看')
    expect(wrapper.find('.section-action').exists()).toBe(true)
  })
})

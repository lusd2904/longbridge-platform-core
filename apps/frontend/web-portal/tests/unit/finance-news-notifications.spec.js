import { flushPromises, shallowMount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const getFinanceBriefingsMock = vi.fn()
const getNotificationsMock = vi.fn()
const getNotificationsBootstrapMock = vi.fn()
const markNotificationReadMock = vi.fn()
const pushMock = vi.fn()

vi.mock('../../src/api/analysis.js', () => ({
  getFinanceBriefings: getFinanceBriefingsMock
}))

vi.mock('../../src/api/risk.js', () => ({
  clearNotifications: vi.fn(),
  deleteNotificationItem: vi.fn(),
  getNotifications: getNotificationsMock,
  getNotificationsBootstrap: getNotificationsBootstrapMock,
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: markNotificationReadMock
}))

vi.mock('../../src/composables/useAdaptiveLayout.js', () => ({
  useAdaptiveLayout: () => ({ isPhoneLayout: ref(false) })
}))

vi.mock('../../src/utils/auth.js', () => ({
  getSession: vi.fn(() => null),
  setActiveSubsystem: vi.fn(),
  setSession: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock })
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: {
      ...(actual.ElMessage || {}),
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn(),
      info: vi.fn()
    }
  }
})

vi.mock('@element-plus/icons-vue', () => ({
  Check: {},
  Delete: {},
  Wallet: {},
  Warning: {},
  Bell: {},
  Refresh: {}
}))

const mountOptions = {
  global: {
    stubs: {
      'el-button': { template: '<button><slot /></button>' },
      'el-card': { template: '<section><slot name="header" /><slot /></section>' },
      'el-empty': true,
      'el-icon': true,
      'el-input': { template: '<input />' },
      'el-radio-button': { template: '<button><slot /></button>' },
      'el-radio-group': { template: '<div><slot /></div>' },
      'el-tag': {
        props: ['type'],
        template: '<span :data-tag-type="type"><slot /></span>'
      }
    }
  }
}

describe('FinanceNews and Notifications fetch behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    getFinanceBriefingsMock.mockResolvedValue({
      data: [
        {
          id: 'briefing-us',
          market: 'US',
          headline: '美股简报',
          summary: '科技股延续强势。',
          briefingType: 'market-insight',
          generatedAt: '2026-05-19T08:00:00Z',
          payload: { symbol: 'AAPL.US' }
        },
        {
          id: 'briefing-cn',
          market: 'CN',
          headline: 'A股简报',
          summary: '成长板块轮动。',
          briefingType: 'market-news',
          generatedAt: '2026-05-19T07:30:00Z',
          payload: { symbol: '300750.SZ' }
        }
      ],
      meta: {
        snapshotAt: '2026-05-19T08:00:00Z',
        dataSource: 'finance_briefings'
      }
    })

    getNotificationsMock.mockResolvedValue({
      data: [
        {
          id: 'notification-trade',
          type: 'trade',
          title: '交易提醒',
          message: '委托已成交',
          time: '2026-05-19T08:10:00Z',
          read: false
        },
        {
          id: 'notification-risk',
          type: 'risk',
          title: '风控提醒',
          message: '波动率提升',
          time: '2026-05-19T08:00:00Z',
          read: true
        }
      ]
    })
    getNotificationsBootstrapMock.mockImplementation(async (params = {}) => {
      const allItems = [
        {
          id: 'notification-trade',
          type: 'trade',
          title: '交易提醒',
          message: '委托已成交',
          time: '2026-05-19T08:10:00Z',
          read: false
        },
        {
          id: 'notification-risk',
          type: 'risk',
          title: '风控提醒',
          message: '波动率提升',
          time: '2026-05-19T08:00:00Z',
          read: true
        }
      ]
      const items = params.type
        ? allItems.filter((item) => item.type === params.type)
        : allItems
      return {
        data: {
          items,
          summary: {
            unreadCount: allItems.filter((item) => !item.read).length
          }
        }
      }
    })
    markNotificationReadMock.mockResolvedValue({ data: { ok: true } })
  })

  it('reloads finance news by market so fixed limits cannot hide target markets', async () => {
    const { default: FinanceNews } = await import('../../src/views/FinanceNews.vue')
    const wrapper = shallowMount(FinanceNews, mountOptions)

    await flushPromises()

    expect(getFinanceBriefingsMock).toHaveBeenCalledTimes(1)
    expect(getFinanceBriefingsMock).toHaveBeenLastCalledWith({ limit: 60 })
    expect(wrapper.vm.filteredItems).toHaveLength(2)

    wrapper.vm.selectedMarket = 'US'
    wrapper.vm.handleMarketChange()
    await flushPromises()

    expect(wrapper.vm.filteredItems).toHaveLength(1)
    expect(wrapper.vm.filteredItems[0].market).toBe('US')
    expect(getFinanceBriefingsMock).toHaveBeenCalledTimes(2)
    expect(getFinanceBriefingsMock).toHaveBeenLastCalledWith({ limit: 60, market: 'US' })

    await wrapper.vm.loadData()
    await flushPromises()

    expect(getFinanceBriefingsMock).toHaveBeenCalledTimes(3)
    expect(getFinanceBriefingsMock).toHaveBeenLastCalledWith({ limit: 60, market: 'US' })
  })

  it('reloads notifications by type so fixed limits cannot hide active tabs', async () => {
    const { default: Notifications } = await import('../../src/views/Notifications.vue')
    const wrapper = shallowMount(Notifications, mountOptions)

    await flushPromises()

    expect(getNotificationsBootstrapMock).toHaveBeenCalledTimes(1)
    expect(wrapper.vm.filteredNotifications).toHaveLength(2)
    expect(getNotificationsBootstrapMock).toHaveBeenLastCalledWith({ limit: 60 })

    wrapper.vm.activeType = 'trade'
    await flushPromises()

    expect(wrapper.vm.filteredNotifications).toHaveLength(1)
    expect(wrapper.vm.filteredNotifications[0].type).toBe('trade')
    expect(getNotificationsBootstrapMock).toHaveBeenCalledTimes(2)
    expect(getNotificationsBootstrapMock).toHaveBeenLastCalledWith({ limit: 60, type: 'trade' })

    await wrapper.vm.loadNotifications()
    await flushPromises()

    expect(getNotificationsBootstrapMock).toHaveBeenCalledTimes(3)
    expect(getNotificationsBootstrapMock).toHaveBeenLastCalledWith({ limit: 60, type: 'trade' })
    expect(getNotificationsMock).not.toHaveBeenCalled()
  })

  it('keeps agent run context when opening a notification', async () => {
    getNotificationsBootstrapMock.mockResolvedValueOnce({
      data: {
        items: [
          {
            notificationKey: 'agent:run-20260520-001',
            type: 'agent',
            title: '自选股盘前复核 已完成',
            message: '盘前复核完成',
            time: '2026-05-20T08:35:00Z',
            read: false,
            route: '/scheduler-center?agentRunId=run-20260520-001&scene=watchlist_pre_open_review',
            runId: 'run-20260520-001',
            scene: 'watchlist_pre_open_review'
          }
        ],
        summary: { unreadCount: 1 }
      }
    })
    const { default: Notifications } = await import('../../src/views/Notifications.vue')
    const wrapper = shallowMount(Notifications, mountOptions)

    await flushPromises()
    await wrapper.vm.handleNotification(wrapper.vm.filteredNotifications[0])

    expect(markNotificationReadMock).toHaveBeenCalledWith({ notification_key: 'agent:run-20260520-001' })
    expect(pushMock).toHaveBeenCalledWith('/scheduler-center?agentRunId=run-20260520-001&scene=watchlist_pre_open_review')
  })

  it('labels agent risk notifications distinctly', async () => {
    getNotificationsBootstrapMock.mockResolvedValueOnce({
      data: {
        items: [
          {
            notificationKey: 'agent:run-20260520-003',
            type: 'agent-risk',
            title: '自选股盘前复核 已完成',
            message: '发现 1 条风险',
            time: '2026-05-20T08:35:00Z',
            read: true,
            route: '/scheduler-center?agentRunId=run-20260520-003&scene=watchlist_pre_open_review',
            runId: 'run-20260520-003',
            scene: 'watchlist_pre_open_review',
            reviewStatus: 'needs_review',
            reviewAction: 'needs_review',
            reviewDeadlineAt: '2026-05-20 10:35:00',
            reviewOverdue: true,
            reviewedAt: '2026-05-20T09:20:00Z',
            reviewedBy: 'analyst',
            reviewSlaHours: 2
          }
        ],
        summary: { unreadCount: 0 }
      }
    })
    const { default: Notifications } = await import('../../src/views/Notifications.vue')
    const wrapper = shallowMount(Notifications, mountOptions)

    await flushPromises()

    expect(wrapper.vm.filteredNotifications[0].type).toBe('agent-risk')
    expect(wrapper.vm.filteredNotifications[0].reviewStatus).toBe('needs_review')
    expect(wrapper.vm.filteredNotifications[0].reviewAction).toBe('needs_review')
    expect(wrapper.vm.filteredNotifications[0].reviewDeadlineAt).toBe('2026-05-20 10:35:00')
    expect(wrapper.vm.filteredNotifications[0].reviewOverdue).toBe(true)
    expect(wrapper.vm.filteredNotifications[0].reviewedAt).toBe('2026-05-20T09:20:00Z')
    expect(wrapper.vm.filteredNotifications[0].reviewedBy).toBe('analyst')
    expect(wrapper.vm.filteredNotifications[0].reviewSlaHours).toBe(2)
    expect(wrapper.vm.getReviewStatusLabel('needs_review')).toBe('需复核')
    expect(wrapper.vm.getReviewActionLabel('needs_review')).toBe('动作: 继续复核')
    expect(wrapper.vm.getReviewStatusLabel('reviewed')).toBe('已确认')
    expect(wrapper.vm.getReviewActionLabel('acknowledged')).toBe('动作: 已确认')
    expect(wrapper.vm.getReviewTagType(wrapper.vm.filteredNotifications[0])).toBe('danger')
    expect(wrapper.vm.getReviewActionTagType('needs_review')).toBe('warning')
    expect(wrapper.vm.getTypeLabel('agent-risk')).toBe('Agent 风险')
    expect(wrapper.vm.getTypeTagType('agent-risk')).toBe('warning')
    expect(wrapper.text()).toContain('需复核')
    expect(wrapper.text()).toContain('动作: 继续复核')
    expect(wrapper.text()).toContain('截止')
    expect(wrapper.text()).toContain('SLA 2h')
    expect(wrapper.text()).toContain('复核于')
    expect(wrapper.text()).toContain('复核 analyst')
    expect(wrapper.text()).toContain('已超期')
    expect(wrapper.findAll('[data-tag-type=\"danger\"]').length).toBeGreaterThan(0)
    expect(wrapper.findAll('[data-tag-type=\"warning\"]').length).toBeGreaterThan(0)
  })

  it('supports separate route query payloads for agent notifications', async () => {
    getNotificationsBootstrapMock.mockResolvedValueOnce({
      data: {
        items: [
          {
            notificationKey: 'agent:run-20260520-002',
            type: 'agent',
            title: '自选股盘后复核 已完成',
            message: '盘后复核完成',
            time: '2026-05-20T18:35:00Z',
            read: true,
            route: '/scheduler-center',
            query: {
              agentRunId: 'run-20260520-002',
              scene: 'watchlist_post_close_review'
            }
          }
        ],
        summary: { unreadCount: 0 }
      }
    })
    const { default: Notifications } = await import('../../src/views/Notifications.vue')
    const wrapper = shallowMount(Notifications, mountOptions)

    await flushPromises()
    await wrapper.vm.handleNotification(wrapper.vm.filteredNotifications[0])

    expect(markNotificationReadMock).not.toHaveBeenCalled()
    expect(pushMock).toHaveBeenCalledWith({
      path: '/scheduler-center',
      query: {
        agentRunId: 'run-20260520-002',
        scene: 'watchlist_post_close_review'
      }
    })
  })
})

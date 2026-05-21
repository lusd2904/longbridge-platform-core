import { flushPromises, shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const getAgentRunMock = vi.fn()
const getAgentRunsMock = vi.fn()
const reviewAgentRunMock = vi.fn()
const getPlatformTasksMock = vi.fn()
const runPlatformTaskMock = vi.fn()
const updatePlatformTaskMock = vi.fn()
const routeState = {
  query: {
    agentRunId: 'run-20260520-001',
    scene: 'watchlist_pre_open_review'
  }
}

vi.mock('../../src/api/analysis.js', () => ({
  getAgentRun: getAgentRunMock,
  getAgentRuns: getAgentRunsMock,
  reviewAgentRun: reviewAgentRunMock
}))

vi.mock('../../src/api/platform.js', () => ({
  getPlatformTasks: getPlatformTasksMock,
  runPlatformTask: runPlatformTaskMock,
  updatePlatformTask: updatePlatformTaskMock
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => routeState
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: {
      ...(actual.ElMessage || {}),
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn()
    }
  }
})

const mountOptions = {
  global: {
    stubs: {
      'el-button': { template: '<button><slot /></button>' },
      'el-card': { template: '<section><slot name="header" /><slot /></section>' },
      'el-drawer': { template: '<div><slot /></div>' },
      'el-form': { template: '<form><slot /></form>' },
      'el-form-item': { template: '<div><slot /></div>' },
      'el-input': {
        props: ['modelValue'],
        emits: ['update:modelValue'],
        template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />'
      },
      'el-input-number': true,
      'el-option': true,
      'el-select': {
        props: ['modelValue'],
        emits: ['update:modelValue'],
        template: '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>'
      },
      'el-switch': true,
      'el-tag': { template: '<span><slot /></span>' }
    }
  }
}

describe('SchedulerCenter agent run routing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeState.query = {
      agentRunId: 'run-20260520-001',
      scene: 'watchlist_pre_open_review'
    }
    getPlatformTasksMock.mockResolvedValue({
      data: [
        {
          taskKey: 'watchlist_pre_open_review',
          taskName: '自选股盘前复核',
          category: 'analysis',
          scheduleType: 'daily',
          enabled: true,
          settings: {
            autoBuyEnabled: false,
            autoBuyMaxSymbols: 2,
            autoBuyMaxAmount: 2000,
            autoBuyMaxPositionRatio: 0.08,
            autoBuyMinConfidence: 72
          },
          status: { state: 'success', lastRunAt: '2026-05-20 08:30:00' }
        }
      ]
    })
    getAgentRunsMock.mockResolvedValue({
      data: {
        runs: [
          {
            runId: 'run-latest',
            scene: 'watchlist_pre_open_review',
            status: 'succeeded',
            resultSummary: { summary: '最近复核' }
          }
        ]
      }
    })
    getAgentRunMock.mockResolvedValue({
      data: {
        runId: 'run-20260520-001',
        scene: 'watchlist_pre_open_review',
        status: 'succeeded',
        resultSummary: {
          summary: '通知指定的复核详情',
          confidence: 0.91,
          reviewAdvice: [{ title: '关注 NVDL', advice: '等待回踩' }]
        },
        overrides: []
      }
    })
    reviewAgentRunMock.mockResolvedValue({ data: { ok: true } })
    runPlatformTaskMock.mockResolvedValue({ data: { ok: true } })
    updatePlatformTaskMock.mockResolvedValue({ data: { ok: true } })
  })

  it('opens the agent run drawer from route query', async () => {
    const { default: SchedulerCenter } = await import('../../src/views/system/SchedulerCenter.vue')
    const wrapper = shallowMount(SchedulerCenter, mountOptions)

    await flushPromises()

    expect(getPlatformTasksMock).toHaveBeenCalledTimes(1)
    expect(getAgentRunMock).toHaveBeenCalledWith('run-20260520-001')
    expect(wrapper.vm.agentRunDrawerVisible).toBe(true)
    expect(wrapper.vm.activeAgentRun.id).toBe('run-20260520-001')
    expect(wrapper.vm.activeAgentRun.summary).toBe('通知指定的复核详情')
    expect(wrapper.vm.activeAgentTaskLabel).toBe('自选股盘前复核')
  })

  it('submits non-acknowledged human review actions with notes', async () => {
    const { default: SchedulerCenter } = await import('../../src/views/system/SchedulerCenter.vue')
    const wrapper = shallowMount(SchedulerCenter, mountOptions)

    await flushPromises()

    getAgentRunMock.mockResolvedValueOnce({
      data: {
        runId: 'run-20260520-001',
        scene: 'watchlist_pre_open_review',
        status: 'succeeded',
        resultSummary: {
          summary: '复核后仍需人工确认',
          confidence: 0.72
        },
        overrides: [
          {
            action: 'needs_review',
            reason: '需继续复核',
            reviewNote: '等待盘前行情确认',
            createdAt: '2026-05-20T09:00:00Z'
          }
        ]
      }
    })
    wrapper.vm.reviewActionForm.action = 'needs_review'
    wrapper.vm.reviewActionForm.newStatus = 'failed'
    wrapper.vm.reviewActionForm.reason = '信号不足'
    wrapper.vm.reviewActionForm.reviewNote = '等待盘前行情确认'

    await wrapper.vm.submitAgentRunReviewAction(
      'run-20260520-001',
      'watchlist_pre_open_review'
    )
    await flushPromises()

    expect(reviewAgentRunMock).toHaveBeenCalledWith('run-20260520-001', {
      action: 'needs_review',
      reason: '信号不足',
      newStatus: 'failed',
      reviewNote: '等待盘前行情确认'
    })
    expect(wrapper.vm.activeAgentRun.reviewAction).toBe('needs_review')
    expect(wrapper.vm.activeAgentRun.acknowledged).toBe(false)
    expect(wrapper.vm.agentRunReviewStateLabel(wrapper.vm.activeAgentRun)).toBe('需继续复核')
    expect(wrapper.vm.reviewActionForm).toEqual({
      action: 'acknowledged',
      newStatus: '',
      reason: '',
      reviewNote: ''
    })
  })

  it('does not change run status for default acknowledged review', async () => {
    const { default: SchedulerCenter } = await import('../../src/views/system/SchedulerCenter.vue')
    const wrapper = shallowMount(SchedulerCenter, mountOptions)

    await flushPromises()

    await wrapper.vm.submitAgentRunReviewAction(
      'run-20260520-001',
      'watchlist_pre_open_review'
    )
    await flushPromises()

    expect(reviewAgentRunMock).toHaveBeenCalledWith('run-20260520-001', {
      action: 'acknowledged',
      reason: '已复核'
    })
  })

  it('renders skipped scheduler and agent states without unknown labels', async () => {
    routeState.query = {}
    getPlatformTasksMock.mockResolvedValueOnce({
      data: [
        {
          taskKey: 'watchlist_pre_open_review',
          taskName: '自选股盘前复核',
          category: 'analysis',
          scheduleType: 'daily',
          enabled: true,
          status: {
            state: 'skipped',
            lastRunAt: '2026-05-20 08:45:00',
            message: '自选股 pre_open 复核已跳过：没有开启本时段扫描的自选标的'
          }
        }
      ]
    })
    getAgentRunsMock.mockResolvedValueOnce({
      data: {
        runs: [
          {
            runId: 'run-skipped',
            scene: 'watchlist_pre_open_review',
            status: 'skipped',
            resultSummary: {
              summary: '自选股 Agent 复核已跳过：当前时段没有开启扫描的自选标的。'
            }
          }
        ]
      }
    })

    const { default: SchedulerCenter } = await import('../../src/views/system/SchedulerCenter.vue')
    const wrapper = shallowMount(SchedulerCenter, mountOptions)

    await flushPromises()

    expect(wrapper.vm.taskStateLabel('skipped')).toBe('已跳过')
    expect(wrapper.vm.agentRunStatusLabel('skipped')).toBe('已跳过')
    expect(wrapper.vm.agentRunStatusTone('skipped')).toBe('muted')
    expect(wrapper.text()).toContain('状态: 已跳过')
  })

  it('saves watchlist auto-buy settings with position controls', async () => {
    routeState.query = {}
    const { default: SchedulerCenter } = await import('../../src/views/system/SchedulerCenter.vue')
    const wrapper = shallowMount(SchedulerCenter, mountOptions)

    await flushPromises()

    const task = wrapper.vm.tasks[0]
    expect(wrapper.text()).toContain('机会股自动买入')
    expect(task.settings).toMatchObject({
      autoBuyEnabled: false,
      autoBuyMaxSymbols: 2,
      autoBuyMaxAmount: 2000,
      autoBuyMaxPositionRatio: 0.08,
      autoBuyMinConfidence: 72
    })

    task.settings.autoBuyEnabled = true
    task.settings.autoBuyMaxSymbols = 3
    task.settings.autoBuyMaxAmount = 5000
    task.settings.autoBuyMaxPositionRatio = 0.12
    task.settings.autoBuyMinConfidence = 80

    await wrapper.vm.saveTask(task)

    expect(updatePlatformTaskMock).toHaveBeenCalledWith('watchlist_pre_open_review', expect.objectContaining({
      settings: expect.objectContaining({
        autoBuyEnabled: true,
        autoBuyMaxSymbols: 3,
        autoBuyMaxAmount: 5000,
        autoBuyMaxPositionRatio: 0.12,
        autoBuyMinConfidence: 80
      })
    }))
  })

  it('normalizes zero position ratio consistently with backend contract', async () => {
    routeState.query = {}
    const { default: SchedulerCenter } = await import('../../src/views/system/SchedulerCenter.vue')
    const wrapper = shallowMount(SchedulerCenter, mountOptions)

    await flushPromises()

    const task = wrapper.vm.tasks[0]
    task.settings.autoBuyMaxPositionRatio = 0

    await wrapper.vm.saveTask(task)

    expect(updatePlatformTaskMock).toHaveBeenCalledWith('watchlist_pre_open_review', expect.objectContaining({
      settings: expect.objectContaining({
        autoBuyMaxPositionRatio: 0
      })
    }))
    expect(wrapper.vm.tasks[0].settings.autoBuyMaxPositionRatio).toBe(0)
  })

  it('hides auto-buy controls for non-agent tasks', async () => {
    routeState.query = {}
    getPlatformTasksMock.mockResolvedValueOnce({
      data: [
        {
          taskKey: 'quote_snapshot_refresh',
          taskName: '行情快照刷新',
          category: 'readmodel',
          scheduleType: 'interval',
          enabled: true,
          settings: {
            autoBuyEnabled: true
          },
          status: { state: 'success' }
        }
      ]
    })

    const { default: SchedulerCenter } = await import('../../src/views/system/SchedulerCenter.vue')
    const wrapper = shallowMount(SchedulerCenter, mountOptions)

    await flushPromises()

    expect(wrapper.text()).not.toContain('机会股自动买入')
    expect(wrapper.vm.tasks[0].settings).toEqual({ autoBuyEnabled: true })
  })
})

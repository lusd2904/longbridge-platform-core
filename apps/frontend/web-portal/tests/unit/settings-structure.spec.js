import { ref } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAIModels: vi.fn(),
  testAIConnection: vi.fn(),
  getSystemLogs: vi.fn(),
  getSystemSettings: vi.fn(),
  updateSystemSettings: vi.fn(),
  getTradeOutboxEvents: vi.fn(),
  getTradeOutboxHealth: vi.fn(),
  getTradeOutboxSagas: vi.fn(),
  purgeTradeDeadLetters: vi.fn(),
  purgeTradeDeadLettersBySaga: vi.fn(),
  repairTradeOutbox: vi.fn(),
  requeueTradeOutboxEvents: vi.fn(),
  requeueTradeOutboxSagas: vi.fn(),
  getConfig: vi.fn(),
  updateConfig: vi.fn(),
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
    info: vi.fn()
  },
  ElMessageBox: {
    confirm: vi.fn()
  }
}))

vi.mock('../../src/api/analysis.js', () => ({
  getAIModels: mocks.getAIModels,
  testAIConnection: mocks.testAIConnection
}))

vi.mock('../../src/api/platform.js', () => ({
  getSystemLogs: mocks.getSystemLogs,
  getSystemSettings: mocks.getSystemSettings,
  updateSystemSettings: mocks.updateSystemSettings
}))

vi.mock('../../src/api/trade.js', () => ({
  getTradeOutboxEvents: mocks.getTradeOutboxEvents,
  getTradeOutboxHealth: mocks.getTradeOutboxHealth,
  getTradeOutboxSagas: mocks.getTradeOutboxSagas,
  purgeTradeDeadLetters: mocks.purgeTradeDeadLetters,
  purgeTradeDeadLettersBySaga: mocks.purgeTradeDeadLettersBySaga,
  repairTradeOutbox: mocks.repairTradeOutbox,
  requeueTradeOutboxEvents: mocks.requeueTradeOutboxEvents,
  requeueTradeOutboxSagas: mocks.requeueTradeOutboxSagas
}))

vi.mock('../../src/api/user.js', () => ({
  getConfig: mocks.getConfig,
  updateConfig: mocks.updateConfig
}))

vi.mock('../../src/composables/useAdaptiveLayout.js', () => ({
  useAdaptiveLayout: () => ({
    isPhoneLayout: ref(false)
  })
}))

vi.mock('../../src/utils/auth.js', () => ({
  getAccess: () => ({}),
  isAdmin: () => false
}))

vi.mock('../../src/utils/api.js', () => ({
  getStoredSystemName: () => 'Refactor V2'
}))

vi.mock('../../src/utils/tradeOutboxAdmin.js', () => ({
  supportsTradeOutboxAdminDetails: () => false,
  resolveTradeOutboxAdminPayload: () => ({
    mode: 'health-only',
    availability: { health: true, events: false, sagas: false },
    message: '当前环境未开放事件明细接口',
    summary: { status: 'healthy', eventStream: {}, outbox: {}, kafka: {} },
    events: [],
    sagas: []
  })
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: mocks.ElMessage,
    ElMessageBox: mocks.ElMessageBox
  }
})

import Settings from '../../src/views/Settings.vue'

const defaultMountOptions = {
  global: {
    stubs: {
      'el-alert': {
        props: ['title', 'description'],
        template: '<div class="el-alert"><span class="alert-title">{{ title }}</span><span class="alert-description">{{ description }}</span><slot /></div>'
      },
      'el-button': {
        props: ['disabled', 'loading', 'type'],
        emits: ['click'],
        template: '<button :data-type="type" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>'
      },
      'el-checkbox': { template: '<label><slot /></label>' },
      'el-checkbox-group': { template: '<div><slot /></div>' },
      'el-form': { template: '<form><slot /></form>' },
      'el-form-item': { template: '<div><slot /></div>' },
      'el-icon': { template: '<i><slot /></i>' },
      'el-input': { template: '<input />' },
      'el-input-number': { template: '<input type="number" />' },
      'el-option': true,
      'el-radio-button': { template: '<button><slot /></button>' },
      'el-radio-group': { template: '<div><slot /></div>' },
      'el-select': { template: '<div><slot /></div>' },
      'el-slider': true,
      'el-switch': true,
      'el-table': { template: '<div><slot /></div>' },
      'el-table-column': true,
      'el-tab-pane': {
        props: ['label'],
        template: '<section><span class="tab-label">{{ label }}</span><slot /></section>'
      },
      'el-tabs': { template: '<div><slot /></div>' },
      'el-tag': { template: '<span><slot /></span>' },
      'el-upload': { template: '<div><slot /></div>' },
      MetricStrip: { template: '<div class="metric-strip" />' },
      MobileSegmentControl: { template: '<div class="mobile-segment" />' },
      PageHero: { template: '<section class="page-hero"><slot name="actions" /></section>' },
      SectionCardHeader: {
        props: ['title'],
        template: '<header class="section-card-header">{{ title }}<slot name="actions" /></header>'
      }
    }
  }
}

describe('Settings structure', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    mocks.getAIModels.mockResolvedValue({
      data: [
        { id: 'gpt-5.5', alias: 'GPT-5.5', provider: 'sub2api', latency: 'medium', best_for: ['终审'], available: true },
        { id: 'gpt-5.4', alias: 'GPT-5.4', provider: 'sub2api', latency: 'fast', best_for: ['扫描'], available: true }
      ],
      provider: 'nvidia',
      providerPlan: {}
    })
    mocks.getSystemLogs.mockResolvedValue({ data: [{ id: 'log-1', level: 'info', module: 'system', time: '10:00:00', message: 'boot ok' }] })
    mocks.getSystemSettings.mockResolvedValue({ data: {} })
    mocks.getTradeOutboxHealth.mockResolvedValue({ status: 'healthy' })
    mocks.getConfig.mockResolvedValue({ data: {} })
    mocks.ElMessageBox.confirm.mockResolvedValue()
  })

  it('renders the three settings domains and current sub2api runtime display', async () => {
    const wrapper = shallowMount(Settings, defaultMountOptions)
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('基础设置')
    expect(text).toContain('通知偏好')
    expect(text).toContain('AI 设置')
    expect(text).toContain('日志/数据管理')
    expect(text).toContain('系统日志')
    expect(text).toContain('数据管理')
    expect(text).toContain('https://lucen.cc/v1')
    expect(text).toContain('gpt-5.5')
    expect(text).toContain('gpt-5.4')
  })
})

import { flushPromises, shallowMount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const deleteBrokerAccountMock = vi.fn()
const testBrokerAccountConnectionMock = vi.fn()
const getBrokerAccountDetailMock = vi.fn()
const getBrokerAccountsMock = vi.fn()
const setDefaultBrokerAccountMock = vi.fn()
const saveLongbridgeBrokerConfigMock = vi.fn()
const saveTigerBrokerConfigMock = vi.fn()
const getPlatformBootstrapMock = vi.fn()
const confirmMock = vi.fn()
const errorMock = vi.fn()
const successMock = vi.fn()

vi.mock('../../src/composables/useAdaptiveLayout.js', () => ({
  useAdaptiveLayout: () => ({ isPhoneLayout: ref(false) })
}))

vi.mock('../../src/utils/auth.js', () => ({
  setSession: vi.fn()
}))

vi.mock('../../src/api/platform.js', () => ({
  getPlatformBootstrap: getPlatformBootstrapMock
}))

vi.mock('../../src/api/trade.js', () => ({
  deleteBrokerAccount: deleteBrokerAccountMock,
  getBrokerAccountDetail: getBrokerAccountDetailMock,
  getBrokerAccounts: getBrokerAccountsMock,
  saveLongbridgeBrokerConfig: saveLongbridgeBrokerConfigMock,
  saveTigerBrokerConfig: saveTigerBrokerConfigMock,
  setDefaultBrokerAccount: setDefaultBrokerAccountMock,
  testBrokerAccountConnection: testBrokerAccountConnectionMock
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: {
      ...(actual.ElMessage || {}),
      error: errorMock,
      success: successMock,
      warning: vi.fn(),
      info: vi.fn()
    },
    ElMessageBox: {
      ...(actual.ElMessageBox || {}),
      confirm: confirmMock
    }
  }
})

vi.mock('@element-plus/icons-vue', () => ({
  Plus: {},
  OfficeBuilding: {},
  Money: {},
  Connection: {},
  Edit: {},
  Star: {},
  Delete: {}
}))

describe('BrokerManagement delete flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getBrokerAccountsMock.mockResolvedValue({
      success: true,
      data: [
        { id: 42, broker_name: '长桥证券', account_id: 'ACC-001', broker_type: 'longbridge', is_default: false }
      ]
    })
    getBrokerAccountDetailMock.mockResolvedValue({ success: true, data: { id: 42, broker_type: 'longbridge', config: {} } })
    getPlatformBootstrapMock.mockResolvedValue({ data: {} })
    deleteBrokerAccountMock.mockResolvedValue({ success: true })
    testBrokerAccountConnectionMock.mockResolvedValue({ success: true, data: {} })
    setDefaultBrokerAccountMock.mockResolvedValue({ success: true })
    saveLongbridgeBrokerConfigMock.mockResolvedValue({ success: true })
    saveTigerBrokerConfigMock.mockResolvedValue({ success: true })
    confirmMock.mockResolvedValue(undefined)
  })

  const mountPage = async () => {
    const { default: BrokerManagement } = await import('../../src/views/BrokerManagement.vue')
    const wrapper = shallowMount(BrokerManagement, {
      global: {
        stubs: {
          'el-card': { template: '<div><slot name="header" /><slot /></div>' },
          'el-table': { template: '<div><slot /></div>' },
          'el-table-column': true,
          'el-statistic': {
            props: ['title', 'value'],
            template: '<div class="el-statistic"><span>{{ title }}</span><strong>{{ value }}</strong><slot /></div>'
          },
          'el-button': { template: '<button><slot /></button>' },
          'el-button-group': { template: '<div><slot /></div>' },
          'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>' },
          'el-input': true,
          'el-input-number': true,
          'el-radio-group': true,
          'el-radio-button': true,
          'el-switch': true,
          'el-divider': true,
          'el-alert': true,
          'el-empty': true,
          'el-tag': true,
          'el-result': true,
          'el-descriptions': true,
          'el-descriptions-item': true,
          'el-icon': true
        }
      }
    })

    await flushPromises()
    await nextTick()
    return wrapper
  }

  it('deletes by resolved id and refreshes after confirmation', async () => {
    const wrapper = await mountPage()

    const row = wrapper.vm.accounts[0]
    await wrapper.vm.deleteAccount(row)

    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(deleteBrokerAccountMock).toHaveBeenCalledWith(42)
    expect(successMock).toHaveBeenCalledWith('删除成功')
  })

  it('does not call delete when confirmation is cancelled', async () => {
    confirmMock.mockRejectedValueOnce('cancel')
    const wrapper = await mountPage()

    await wrapper.vm.deleteAccount(wrapper.vm.accounts[0])

    expect(deleteBrokerAccountMock).not.toHaveBeenCalled()
    expect(errorMock).not.toHaveBeenCalled()
  })

  it('shows a readable error and skips request when account id is missing', async () => {
    const wrapper = await mountPage()

    await wrapper.vm.deleteAccount({ broker_name: '模拟券商', account_id: 'SIM-001' })

    expect(deleteBrokerAccountMock).not.toHaveBeenCalled()
    expect(errorMock).toHaveBeenCalledWith('当前券商账户缺少可用 ID，无法执行删除')
  })
})

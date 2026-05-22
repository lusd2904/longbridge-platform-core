import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const getWatchlistUsOpenAiTradeRunsMock = vi.fn()

vi.mock('../../src/api/analysis.js', () => ({
  getWatchlistUsOpenAiTradeRuns: getWatchlistUsOpenAiTradeRunsMock
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: {
      ...(actual.ElMessage || {}),
      error: vi.fn()
    }
  }
})

const mountOptions = {
  global: {
    stubs: {
      'el-alert': { template: '<div class="el-alert">{{ title }}</div>', props: ['title'] },
      'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
      'el-select': { template: '<select><slot /></select>' },
      'el-option': { template: '<option>{{ label }}</option>', props: ['label'] },
      'el-table': { template: '<section><slot /></section>' },
      'el-table-column': { template: '<div><slot :row="row" /><slot name="default" :row="row" /></div>', props: ['label', 'prop'], data: () => ({ row: sampleRun }) },
      'el-tag': { template: '<span><slot /></span>' }
    }
  }
}

const sampleRun = {
  cycleId: 'qt-202605220930',
  source: 'scheduler',
  status: 'completed',
  reason: 'executed',
  message: '美股开盘 AI 自动交易已完成',
  targetCount: 6,
  evaluatedCount: 6,
  opportunityCount: 2,
  submittedCount: 1,
  settings: { autoTradeEnabled: true, maxSymbols: 5, minConfidence: 72, targetPortfolioRatio: 0.7 },
  autoTrade: { enabled: true, submittedCount: 1, accountId: 7 },
  positionControl: { maxSymbols: 5, minConfidence: 72, targetPortfolioRatio: 0.7 },
  candidates: [{ symbol: 'MSFT.US', confidence: 90, riskLevel: 'low', reason: '强势机会' }],
  opportunities: [{ symbol: 'MSFT.US', side: 'BUY', confidence: 90, reason: '强势机会' }],
  skipped: [{ symbol: 'AAPL.US', reason: '已有持仓' }],
  startedAt: '2026-05-22 21:30:00',
  finishedAt: '2026-05-22 21:30:08'
}

describe('WatchlistAiTradeRuns', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getWatchlistUsOpenAiTradeRunsMock.mockResolvedValue({
      data: {
        items: [sampleRun],
        total: 1
      }
    })
  })

  it('loads and renders dedicated AI trade scan run records', async () => {
    const { default: WatchlistAiTradeRuns } = await import('../../src/views/WatchlistAiTradeRuns.vue')
    const wrapper = shallowMount(WatchlistAiTradeRuns, mountOptions)

    await flushPromises()

    expect(getWatchlistUsOpenAiTradeRunsMock).toHaveBeenCalledWith({ limit: 50 })
    expect(wrapper.text()).toContain('AI交易扫描记录')
    expect(wrapper.text()).toContain('自动交易已开启')
    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).toContain('已执行')
    expect(wrapper.text()).toContain('MSFT.US')
    expect(wrapper.text()).toContain('纸账户')
  })
})

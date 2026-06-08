import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import AiAssistantFloat from '@/components/layout/AiAssistantFloat.vue'

const mocks = vi.hoisted(() => ({
  consultAssistant: vi.fn(),
  routeState: {
    fullPath: '/strategy?symbol=AAPL.US&token=secret-token',
    path: '/strategy',
    name: 'Strategy',
    query: { symbol: 'AAPL.US', token: 'secret-token', api_key: 'secret-key' },
    meta: {
      title: '策略管理',
      subsystem: 'analysis'
    }
  }
}))

vi.mock('@/api/analysis.js', () => ({
  consultAssistant: mocks.consultAssistant
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.routeState
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessage: {
      error: vi.fn()
    }
  }
})

const mountOptions = {
  global: {
    stubs: {
      'el-alert': {
        props: ['title'],
        template: '<div class="el-alert">{{ title }}</div>'
      },
      'el-button': {
        props: ['disabled'],
        template: '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
      },
      'el-dialog': {
        props: ['modelValue'],
        emits: ['update:modelValue'],
        template: '<section v-if="modelValue" class="el-dialog"><slot name="header" /><slot /></section>'
      },
      'el-icon': {
        template: '<span class="el-icon"><slot /></span>'
      },
      'el-input': {
        props: ['modelValue', 'disabled'],
        emits: ['update:modelValue'],
        template: '<textarea class="el-textarea" :disabled="disabled" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />'
      }
    }
  }
}

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const projectRoot = path.resolve(__dirname, '../..')

describe('AiAssistantFloat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.consultAssistant.mockResolvedValue({
      data: {
        answer: '当前策略页可先检查风控和回测结果。',
        model: { alias: 'gpt-5.5' }
      }
    })
  })

  it('opens from the floating system button and sends page context to the platform AI service', async () => {
    const wrapper = mount(AiAssistantFloat, mountOptions)

    await wrapper.find('.ai-assistant-float').trigger('click')

    expect(wrapper.text()).toContain('AI 咨询')
    expect(wrapper.text()).toContain('策略管理')

    await wrapper.find('textarea').setValue('这个页面现在应该先看什么？')
    const sendButton = wrapper.findAll('button').find((button) => button.text().includes('发送'))
    await sendButton.trigger('click')
    await flushPromises()

    expect(mocks.consultAssistant).toHaveBeenCalledWith(expect.objectContaining({
      question: '这个页面现在应该先看什么？',
      pageContext: expect.objectContaining({
        path: '/strategy',
        name: 'Strategy',
        title: '策略管理',
        subsystem: 'analysis',
        query: {
          symbol: 'AAPL.US',
          token: '[redacted]',
          api_key: '[redacted]'
        }
      })
    }))
    expect(wrapper.text()).toContain('当前策略页可先检查风控和回测结果。')
    expect(wrapper.text()).toContain('gpt-5.5')
  })

  it('is mounted by the authenticated shell layout', () => {
    const source = readFileSync(
      path.join(projectRoot, 'src/components/layout/MainLayout.vue'),
      'utf8'
    )

    expect(source).toContain("import AiAssistantFloat from './AiAssistantFloat.vue'")
    expect(source).toContain('<AiAssistantFloat />')
  })
})

<template>
  <div class="ai-assistant-root">
    <button
      type="button"
      class="ai-assistant-float"
      aria-label="打开 AI 咨询"
      title="AI 咨询"
      @click="openAssistant"
    >
      <el-icon :size="24"><ChatDotRound /></el-icon>
      <span v-if="hasUnread" class="ai-assistant-pulse" aria-hidden="true"></span>
    </button>

    <el-dialog
      v-model="visible"
      class="ai-assistant-dialog"
      width="min(720px, calc(100vw - 28px))"
      :append-to-body="true"
      :close-on-click-modal="false"
      :destroy-on-close="false"
      :show-close="false"
    >
      <template #header>
        <div class="assistant-dialog-header">
          <div>
            <strong>AI 咨询</strong>
            <span>{{ modelBadge }}</span>
          </div>
          <button type="button" class="assistant-icon-button" aria-label="关闭" @click="visible = false">
            <el-icon><Close /></el-icon>
          </button>
        </div>
      </template>

      <section class="assistant-context-strip">
        <span>当前页面</span>
        <strong>{{ pageTitle }}</strong>
      </section>

      <div ref="messageListRef" class="assistant-messages" role="log" aria-live="polite">
        <article
          v-for="item in messages"
          :key="item.id"
          class="assistant-message"
          :class="item.role"
        >
          <span class="assistant-message-role">{{ item.role === 'user' ? '我' : 'AI' }}</span>
          <p>{{ item.content }}</p>
        </article>

        <article v-if="sending" class="assistant-message assistant">
          <span class="assistant-message-role">AI</span>
          <p>正在分析...</p>
        </article>
      </div>

      <el-alert
        v-if="errorMessage"
        class="assistant-error"
        type="warning"
        :title="errorMessage"
        :closable="false"
        show-icon
      />

      <div class="assistant-quick-actions" aria-label="快捷咨询">
        <button
          v-for="item in quickPrompts"
          :key="item"
          type="button"
          :disabled="sending"
          @click="sendQuickPrompt(item)"
        >
          {{ item }}
        </button>
      </div>

      <div class="assistant-composer">
        <el-input
          v-model="draft"
          type="textarea"
          :rows="3"
          resize="none"
          maxlength="2400"
          show-word-limit
          placeholder="输入你的问题"
          :disabled="sending"
        />
        <div class="assistant-composer-actions">
          <el-button
            :icon="Delete"
            :disabled="sending || messages.length <= 1"
            @click="clearConversation"
          >
            清空
          </el-button>
          <el-button
            type="primary"
            :icon="Promotion"
            :loading="sending"
            :disabled="!canSend"
            @click="sendQuestion"
          >
            发送
          </el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Close, Delete, Promotion } from '@element-plus/icons-vue'
import { consultAssistant } from '../../api/analysis.js'

const route = useRoute()
const visible = ref(false)
const draft = ref('')
const sending = ref(false)
const errorMessage = ref('')
const assistantModel = ref('')
const hasUnread = ref(false)
const messageListRef = ref(null)
const messages = ref([
  {
    id: 'welcome',
    role: 'assistant',
    content: '我在，当前页面的问题可以直接问。',
    createdAt: new Date().toISOString()
  }
])

const quickPrompts = [
  '解释当前页面',
  '检查潜在风险',
  '给出下一步'
]

const SENSITIVE_QUERY_KEY_PATTERN = /(token|secret|password|passwd|auth|session|cookie|jwt|credential|signature|api_?key|key)/i

const pageTitle = computed(() => String(route.meta?.title || route.name || route.path || '当前页面'))
const modelBadge = computed(() => assistantModel.value || '平台 AI')
const canSend = computed(() => Boolean(draft.value.trim()) && !sending.value)

const clipContextValue = (value, limit = 160) => {
  const text = String(value ?? '').trim()
  return text.length > limit ? `${text.slice(0, limit).trimEnd()}...` : text
}

const sanitizeRoutePath = () => {
  const text = String(route.path || route.fullPath || '').trim()
  return text.split(/[?#]/, 1)[0]
}

const sanitizeRouteQuery = () => {
  const entries = Object.entries(route.query || {}).slice(0, 20)
  return entries.reduce((next, [key, value]) => {
    const safeKey = clipContextValue(key, 80)
    if (!safeKey) {
      return next
    }
    if (SENSITIVE_QUERY_KEY_PATTERN.test(safeKey)) {
      next[safeKey] = '[redacted]'
      return next
    }
    if (Array.isArray(value)) {
      next[safeKey] = value.slice(0, 6).map((item) => clipContextValue(item))
      return next
    }
    next[safeKey] = clipContextValue(value)
    return next
  }, {})
}

const buildPageContext = () => ({
  path: sanitizeRoutePath(),
  name: String(route.name || ''),
  title: pageTitle.value,
  subsystem: String(route.meta?.subsystem || ''),
  query: sanitizeRouteQuery()
})

const scrollToBottom = async () => {
  await nextTick()
  const el = messageListRef.value
  if (el) {
    el.scrollTop = el.scrollHeight
  }
}

const openAssistant = () => {
  visible.value = true
  hasUnread.value = false
  scrollToBottom()
}

const clearConversation = () => {
  errorMessage.value = ''
  messages.value = [
    {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '已清空。',
      createdAt: new Date().toISOString()
    }
  ]
}

const appendMessage = (role, content) => {
  messages.value.push({
    id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    createdAt: new Date().toISOString()
  })
}

const sendQuestion = async () => {
  const question = draft.value.trim()
  if (!question || sending.value) {
    return
  }

  const history = messages.value
    .filter((item) => item.role === 'user' || item.role === 'assistant')
    .map((item) => ({ role: item.role, content: item.content }))
    .slice(-6)

  appendMessage('user', question)
  draft.value = ''
  sending.value = true
  errorMessage.value = ''
  await scrollToBottom()

  try {
    const res = await consultAssistant({
      question,
      pageContext: buildPageContext(),
      messages: history
    })
    const payload = res?.data || {}
    const answer = String(payload.answer || '').trim()
    if (!answer) {
      throw new Error('AI 未返回可用内容')
    }

    const model = payload.model || {}
    assistantModel.value = model.alias || model.id || assistantModel.value
    appendMessage('assistant', answer)
    if (!visible.value) {
      hasUnread.value = true
    }
  } catch (error) {
    const message = error?.data?.error || error?.message || 'AI 咨询失败'
    errorMessage.value = message
    ElMessage.error(message)
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

const sendQuickPrompt = (value) => {
  if (sending.value) {
    return
  }
  draft.value = value
  sendQuestion()
}

watch(
  () => route.fullPath,
  () => {
    if (visible.value) {
      errorMessage.value = ''
    }
  }
)
</script>

<style scoped lang="scss">
.ai-assistant-root {
  position: fixed;
  right: max(18px, env(safe-area-inset-right, 0px) + 18px);
  bottom: max(22px, env(safe-area-inset-bottom, 0px) + 22px);
  z-index: 1200;
}

.ai-assistant-float {
  position: relative;
  width: 56px;
  height: 56px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--accent) 38%, var(--border-soft));
  border-radius: 50%;
  background:
    linear-gradient(145deg, color-mix(in srgb, var(--accent) 88%, #ffffff 12%), color-mix(in srgb, var(--accent-strong) 72%, #0b1728 28%));
  color: white;
  box-shadow: 0 16px 38px rgba(0, 0, 0, 0.26), 0 0 0 6px color-mix(in srgb, var(--accent) 12%, transparent);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.ai-assistant-float:hover,
.ai-assistant-float:focus-visible {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--accent) 70%, white 30%);
  box-shadow: 0 20px 44px rgba(0, 0, 0, 0.32), 0 0 0 7px color-mix(in srgb, var(--accent) 16%, transparent);
  outline: none;
}

.ai-assistant-pulse {
  position: absolute;
  top: 9px;
  right: 9px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--success) 22%, transparent);
}

:global(.ai-assistant-dialog) {
  border-radius: 10px;
  overflow: hidden;
  background:
    radial-gradient(circle at top right, color-mix(in srgb, var(--accent) 12%, transparent), transparent 34%),
    color-mix(in srgb, var(--surface-strong) 94%, black 6%);
  border: 1px solid color-mix(in srgb, var(--accent) 14%, var(--border-soft));
  box-shadow: 0 26px 70px rgba(0, 0, 0, 0.36);
}

:global(.ai-assistant-dialog .el-dialog__header) {
  padding: 14px 16px 10px;
  margin: 0;
}

:global(.ai-assistant-dialog .el-dialog__body) {
  padding: 0 16px 16px;
}

.assistant-dialog-header,
.assistant-context-strip,
.assistant-composer-actions,
.assistant-quick-actions {
  display: flex;
  align-items: center;
}

.assistant-dialog-header {
  justify-content: space-between;
  gap: 12px;
}

.assistant-dialog-header > div {
  display: grid;
  gap: 2px;
}

.assistant-dialog-header strong {
  color: var(--text-emphasis);
  font-size: 16px;
  letter-spacing: 0;
}

.assistant-dialog-header span,
.assistant-context-strip span {
  color: var(--text-secondary);
  font-size: 12px;
}

.assistant-icon-button {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface-soft) 86%, transparent);
  color: var(--text-emphasis);
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.assistant-icon-button:hover,
.assistant-icon-button:focus-visible {
  border-color: color-mix(in srgb, var(--accent) 28%, var(--border-soft));
  background: color-mix(in srgb, var(--surface-soft) 96%, transparent);
  outline: none;
}

.assistant-context-strip {
  justify-content: space-between;
  gap: 12px;
  padding: 9px 10px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface-soft) 82%, transparent);
}

.assistant-context-strip strong {
  max-width: 70%;
  overflow: hidden;
  color: var(--text-emphasis);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-messages {
  height: min(48vh, 380px);
  min-height: 220px;
  margin-top: 12px;
  padding: 10px;
  display: grid;
  align-content: start;
  gap: 10px;
  overflow-y: auto;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface-strong) 70%, transparent);
}

.assistant-message {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.assistant-message.user {
  grid-template-columns: minmax(0, 1fr) 30px;
}

.assistant-message.user .assistant-message-role {
  grid-column: 2;
  grid-row: 1;
}

.assistant-message.user p {
  grid-column: 1;
  grid-row: 1;
  justify-self: end;
  background: color-mix(in srgb, var(--accent) 16%, var(--surface-soft));
}

.assistant-message-role {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: color-mix(in srgb, var(--accent) 14%, var(--surface-soft));
  color: var(--text-emphasis);
  font-size: 12px;
  font-weight: 700;
}

.assistant-message p {
  max-width: 100%;
  margin: 0;
  padding: 9px 10px;
  border: 1px solid color-mix(in srgb, var(--border-soft) 82%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface-soft) 84%, transparent);
  color: var(--text-primary);
  line-height: 1.62;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.assistant-error {
  margin-top: 10px;
}

.assistant-quick-actions {
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.assistant-quick-actions button {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface-soft) 82%, transparent);
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease;
}

.assistant-quick-actions button:hover:not(:disabled),
.assistant-quick-actions button:focus-visible:not(:disabled) {
  color: var(--text-emphasis);
  border-color: color-mix(in srgb, var(--accent) 24%, var(--border-soft));
  background: color-mix(in srgb, var(--surface-soft) 96%, transparent);
  outline: none;
}

.assistant-quick-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.assistant-composer {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.assistant-composer :deep(.el-textarea__inner) {
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
  color: var(--text-primary);
  box-shadow: 0 0 0 1px var(--border-soft) inset;
}

.assistant-composer-actions {
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 768px) {
  .ai-assistant-root {
    right: max(12px, env(safe-area-inset-right, 0px) + 12px);
    bottom: max(78px, env(safe-area-inset-bottom, 0px) + 78px);
  }

  .ai-assistant-float {
    width: 52px;
    height: 52px;
  }

  :global(.ai-assistant-dialog) {
    margin: 8px auto;
  }

  :global(.ai-assistant-dialog .el-dialog__body) {
    padding: 0 12px 12px;
  }

  .assistant-messages {
    height: min(52vh, 360px);
    min-height: 210px;
    padding: 8px;
  }

  .assistant-context-strip {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }

  .assistant-context-strip strong {
    max-width: 100%;
  }
}
</style>

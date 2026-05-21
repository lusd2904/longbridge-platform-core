<template>
  <div class="scheduler-page">
    <div class="page-header">
      <div>
        <h2>任务中心</h2>
      </div>
      <el-button type="primary" :loading="loading" @click="loadTasks">刷新任务</el-button>
    </div>

    <div class="overview-grid" v-if="tasks.length">
      <el-card class="overview-card glass-card">
        <span>快照任务</span>
        <strong>{{ readmodelTasks.length }}</strong>
      </el-card>
      <el-card class="overview-card glass-card">
        <span>实时任务</span>
        <strong>{{ realtimeTasks.length }}</strong>
      </el-card>
      <el-card class="overview-card glass-card" v-if="quoteSnapshotTask">
        <span>展示行情快照</span>
        <strong>{{ formatTaskLastRun(quoteSnapshotTask) }}</strong>
      </el-card>
    </div>

    <div class="task-grid">
      <el-card
        v-for="task in displayTasks"
        :key="task.taskKey"
        class="task-card glass-card"
        :class="{ 'is-readmodel': isReadmodelTask(task), 'is-highlight': task.taskKey === 'quote_snapshot_refresh' }"
      >
        <div class="task-top">
          <div>
            <div class="task-tag-row">
              <span class="task-category">{{ categoryLabel(task.category) }}</span>
              <el-tag v-if="isReadmodelTask(task)" size="small" type="info">快照任务</el-tag>
              <el-tag v-if="task.taskKey === 'quote_snapshot_refresh'" size="small" type="success">行情快照</el-tag>
            </div>
            <h3>{{ task.taskName }}</h3>
          </div>
          <el-switch v-model="task.enabled" @change="saveTask(task)" />
        </div>

        <div class="task-body">
          <el-form label-width="96px" size="small">
            <el-form-item label="调度方式">
              <el-tag size="small">{{ scheduleLabel(task.scheduleType) }}</el-tag>
            </el-form-item>
            <el-form-item v-if="task.scheduleType === 'interval'" label="间隔秒数">
              <el-input-number v-model="task.intervalSeconds" :min="60" :step="60" @change="saveTask(task)" />
            </el-form-item>
            <el-form-item v-if="task.scheduleType === 'daily'" label="执行时间">
              <div class="daily-time">
                <el-input-number v-model="task.runHour" :min="0" :max="23" @change="saveTask(task)" />
                <span>:</span>
                <el-input-number v-model="task.runMinute" :min="0" :max="59" @change="saveTask(task)" />
              </div>
            </el-form-item>
            <el-form-item label="每分钟上限">
              <el-input-number v-model="task.maxRequestsPerMinute" :min="0" :step="1" @change="saveTask(task)" />
            </el-form-item>
            <el-form-item label="批次大小">
              <el-input-number v-model="task.batchSize" :min="0" :step="10" @change="saveTask(task)" />
            </el-form-item>
          </el-form>

          <div
            v-if="isAgentReviewTask(task)"
            class="auto-buy-settings"
            :class="{ 'is-enabled': task.settings?.autoBuyEnabled }"
          >
            <div class="auto-buy-head">
              <div>
                <span class="agent-review-label">机会股自动买入</span>
                <strong>{{ task.settings?.autoBuyEnabled ? '已开启' : '默认关闭' }}</strong>
              </div>
              <el-switch v-model="task.settings.autoBuyEnabled" @change="saveTask(task)" />
            </div>
            <p>
              开启后，任务扫描出明确机会股时会尝试自动下单，并按以下参数控制买入数量、预算和单票仓位。
            </p>
            <div class="auto-buy-grid">
              <label>
                <span>最多标的</span>
                <el-input-number
                  v-model="task.settings.autoBuyMaxSymbols"
                  :min="1"
                  :max="10"
                  :step="1"
                  @change="saveTask(task)"
                />
              </label>
              <label>
                <span>单标预算</span>
                <el-input-number
                  v-model="task.settings.autoBuyMaxAmount"
                  :min="0"
                  :step="500"
                  @change="saveTask(task)"
                />
              </label>
              <label>
                <span>单票仓位</span>
                <el-input-number
                  v-model="task.settings.autoBuyMaxPositionRatio"
                  :min="0"
                  :max="1"
                  :step="0.01"
                  :precision="2"
                  @change="saveTask(task)"
                />
              </label>
              <label>
                <span>最低置信</span>
                <el-input-number
                  v-model="task.settings.autoBuyMinConfidence"
                  :min="0"
                  :max="100"
                  :step="1"
                  @change="saveTask(task)"
                />
              </label>
            </div>
          </div>

          <div
            v-if="isUsOpenAiTradeTask(task)"
            class="auto-buy-settings"
            :class="{ 'is-enabled': task.settings?.autoTradeEnabled }"
          >
            <div class="auto-buy-head">
              <div>
                <span class="agent-review-label">AI 自动交易</span>
                <strong>{{ task.settings?.autoTradeEnabled ? '已开启' : '已关闭' }}</strong>
              </div>
              <el-switch v-model="task.settings.autoTradeEnabled" @change="saveTask(task)" />
            </div>
            <p>
              仅在美股常规开盘时段按设定策略执行，并始终受纸账户与交易边界保护，不会绕过真实资金账户限制。
            </p>
            <div class="auto-buy-grid">
              <label>
                <span>最多标的</span>
                <el-input-number
                  v-model="task.settings.maxSymbols"
                  :min="1"
                  :max="20"
                  :step="1"
                  @change="saveTask(task)"
                />
              </label>
              <label>
                <span>组合仓位</span>
                <el-input-number
                  v-model="task.settings.targetPortfolioRatio"
                  :min="0"
                  :max="1"
                  :step="0.01"
                  :precision="2"
                  @change="saveTask(task)"
                />
              </label>
              <label>
                <span>最低置信</span>
                <el-input-number
                  v-model="task.settings.minConfidence"
                  :min="0"
                  :max="100"
                  :step="1"
                  @change="saveTask(task)"
                />
              </label>
              <label>
                <span>策略风格</span>
                <el-select v-model="task.settings.strategyProfile" @change="saveTask(task)">
                  <el-option label="均衡" value="balanced" />
                  <el-option label="动量" value="momentum" />
                  <el-option label="突破" value="breakout" />
                  <el-option label="回归" value="reversion" />
                </el-select>
              </label>
            </div>
            <div class="agent-review-meta">
              <span>市场 {{ task.settings?.market || 'US' }}</span>
              <span>{{ task.settings?.regularSessionOnly ? '仅常规时段' : '允许非常规时段' }}</span>
            </div>
          </div>
        </div>

        <div class="task-status">
          <span>状态: {{ taskStateLabel(task.status?.state) }}</span>
          <span>上次执行: {{ formatTaskLastRun(task) }}</span>
        </div>

        <div v-if="isAgentReviewTask(task)" class="agent-review-summary">
          <div class="agent-review-head">
            <span class="agent-review-label">最近 Agent 复核</span>
            <span
              v-if="getTaskAgentRun(task)?.status"
              class="agent-run-status"
              :class="`is-${agentRunStatusTone(getTaskAgentRun(task)?.status)}`"
            >
              {{ agentRunStatusLabel(getTaskAgentRun(task)?.status) }}
            </span>
          </div>
          <div v-if="isAgentRunSummaryLoading(task)" class="agent-review-empty">
            正在加载复核结果…
          </div>
          <template v-else-if="getTaskAgentRun(task)">
            <div class="agent-review-meta">
              <span>{{ formatAgentRunTimestamp(getTaskAgentRun(task)) }}</span>
              <span v-if="formatAgentRunConfidence(getTaskAgentRun(task))">
                置信度 {{ formatAgentRunConfidence(getTaskAgentRun(task)) }}
              </span>
              <span v-if="getTaskAgentRun(task)?.adviceCount !== null">
                建议 {{ getTaskAgentRun(task)?.adviceCount }}
              </span>
            </div>
            <p class="agent-review-text">
              {{ getTaskAgentRun(task)?.summary || '暂无摘要' }}
            </p>
            <div class="agent-review-actions">
              <el-button
                size="small"
                class="review-button"
                @click="openAgentRunResult(task)"
              >
                查看结果
              </el-button>
              <el-button
                size="small"
                class="ack-button"
                :loading="acknowledgingRunId === getTaskAgentRun(task)?.id"
                :disabled="!getTaskAgentRun(task)?.id || getTaskAgentRun(task)?.acknowledged"
                @click="acknowledgeAgentRun(task)"
              >
                {{ getTaskAgentRun(task)?.acknowledged ? '已复核' : '标记已复核' }}
              </el-button>
            </div>
          </template>
          <div v-else class="agent-review-empty">
            暂无复核结果
          </div>
        </div>

        <div class="task-actions">
          <div class="task-action-buttons">
            <el-button size="small" type="primary" plain :disabled="isTaskRunning(task)" @click="runTask(task)">
              {{ isTaskRunning(task) ? '运行中' : '立即执行' }}
            </el-button>
            <el-button
              v-if="isHistoryCoverageTask(task)"
              size="small"
              class="coverage-button"
              @click="openHistoryCoverage()"
            >
              查看覆盖
            </el-button>
          </div>
          <span class="task-message">{{ taskStatusMessage(task) }}</span>
        </div>
      </el-card>
    </div>

    <el-drawer
      v-model="agentRunDrawerVisible"
      title="Agent 复核结果"
      size="460px"
      class="agent-run-drawer"
    >
      <div v-if="agentRunDetailLoading" class="agent-drawer-empty">
        正在加载复核详情…
      </div>
      <div v-else-if="activeAgentRun" class="agent-run-detail">
        <div class="agent-run-hero">
          <div>
            <div class="agent-review-meta">
              <span>{{ activeAgentRun.scene || activeAgentTaskLabel || '复核任务' }}</span>
              <span>{{ formatAgentRunTimestamp(activeAgentRun) }}</span>
            </div>
            <p class="agent-run-summary">{{ activeAgentRun.summary || '暂无摘要' }}</p>
          </div>
          <span class="agent-run-status" :class="`is-${agentRunStatusTone(activeAgentRun.status)}`">
            {{ agentRunStatusLabel(activeAgentRun.status) }}
          </span>
        </div>

        <div class="agent-run-stats">
          <div class="agent-stat-card">
            <span>置信度</span>
            <strong>{{ formatAgentRunConfidence(activeAgentRun) || '--' }}</strong>
          </div>
          <div class="agent-stat-card">
            <span>建议数</span>
            <strong>{{ activeAgentRun.adviceCount ?? '--' }}</strong>
          </div>
          <div class="agent-stat-card">
            <span>人工处理</span>
            <strong>{{ agentRunReviewStateLabel(activeAgentRun) }}</strong>
          </div>
        </div>

        <div
          v-for="section in agentRunSections"
          :key="section.key"
          class="agent-drawer-section"
        >
          <div class="section-label">{{ section.label }}</div>
          <div v-if="section.type === 'text'" class="section-body">
            {{ section.value }}
          </div>
          <div v-else-if="section.entries.length" class="agent-entry-list">
            <div
              v-for="entry in section.entries"
              :key="entry.key"
              class="agent-entry-card"
            >
              <div v-if="entry.title" class="agent-entry-title">{{ entry.title }}</div>
              <div v-if="entry.text" class="agent-entry-text">{{ entry.text }}</div>
              <div v-if="entry.meta" class="agent-entry-meta">{{ entry.meta }}</div>
            </div>
          </div>
          <div v-else class="agent-drawer-empty">
            暂无数据
          </div>
        </div>

        <div class="agent-review-control">
          <div class="section-label">人工处理</div>
          <div class="review-action-options">
            <button
              v-for="action in AGENT_REVIEW_ACTIONS"
              :key="action.key"
              type="button"
              class="review-action-option"
              :class="[{ active: reviewActionForm.action === action.key }, `is-${action.key}`]"
              @click="reviewActionForm.action = action.key"
            >
              {{ action.label }}
            </button>
          </div>
          <el-select
            v-model="reviewActionForm.newStatus"
            placeholder="同步人工复核状态"
            class="review-status-select"
          >
            <el-option
              v-for="status in activeReviewStatusOptions"
              :key="status.value"
              :label="status.label"
              :value="status.value"
            />
          </el-select>
          <el-input
            v-model="reviewActionForm.reason"
            maxlength="300"
            show-word-limit
            placeholder="处理理由（可选）"
          />
          <el-input
            v-model="reviewActionForm.reviewNote"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="记录本次人工复核意见（可选）"
          />
          <div class="agent-drawer-actions">
            <el-button
              class="review-action-button"
              :class="`is-${reviewActionForm.action}`"
              :loading="isReviewActionLoading(activeAgentRun.id, reviewActionForm.action)"
              :disabled="!activeAgentRun.id || isReviewActionDisabled(activeAgentRun, reviewActionForm.action)"
              @click="submitAgentRunReviewAction(activeAgentRun.id, activeAgentRun.scene)"
            >
              {{ agentReviewSubmitLabel(activeAgentRun) }}
            </el-button>
            <el-button
              class="review-action-button is-reset"
              :disabled="isReviewActionBusy(activeAgentRun.id)"
              @click="resetReviewActionForm()"
            >
              重置
            </el-button>
            <el-button
              class="review-action-button"
              :disabled="isReviewActionBusy(activeAgentRun.id)"
              @click="agentRunDrawerVisible = false"
            >
              关闭
            </el-button>
          </div>
        </div>
      </div>
      <div v-else class="agent-drawer-empty">
        暂无可展示的复核结果
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { getAgentRun, getAgentRuns, reviewAgentRun } from '../../api/analysis.js'
import { getPlatformTasks, runPlatformTask, updatePlatformTask } from '../../api/platform.js'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const tasks = ref([])
const runningTaskKeys = ref(new Set())
const agentRunSummaryMap = ref({})
const agentRunSummaryLoadingKeys = ref(new Set())
const agentRunDrawerVisible = ref(false)
const agentRunDetailLoading = ref(false)
const activeAgentRun = ref(null)
const activeAgentTaskLabel = ref('')
const acknowledgingRunId = ref('')
const acknowledgingAction = ref('')
const routeQueryHydrated = ref(false)
const createReviewActionForm = () => ({
  action: 'acknowledged',
  newStatus: '',
  reason: '',
  reviewNote: ''
})
const reviewActionForm = ref(createReviewActionForm())

const AGENT_REVIEW_TASK_SCENES = {
  watchlist_pre_open_review: 'watchlist_pre_open_review',
  watchlist_post_close_review: 'watchlist_post_close_review'
}
const US_OPEN_AI_TRADE_TASK_KEY = 'watchlist_us_open_ai_trade'
const AGENT_REVIEW_SCENE_LABELS = {
  watchlist_pre_open_review: '自选股盘前复核',
  watchlist_post_close_review: '自选股盘后复核'
}
const AGENT_REVIEW_ACTIONS = [
  { key: 'acknowledged', label: '已复核', doneLabel: '已复核', message: '已记录人工复核' },
  { key: 'needs_review', label: '需继续复核', doneLabel: '需继续复核', message: '已标记为需继续复核' },
  { key: 'dismissed', label: '忽略', doneLabel: '已忽略', message: '已忽略该复核结果' }
]
const REVIEW_STATUS_UNCHANGED_OPTION = { value: '', label: '不改运行状态' }
const AGENT_REVIEW_STATUS_OPTIONS = {
  acknowledged: [REVIEW_STATUS_UNCHANGED_OPTION, { value: 'succeeded', label: '运行成功' }],
  needs_review: [REVIEW_STATUS_UNCHANGED_OPTION, { value: 'failed', label: '运行失败' }],
  dismissed: [REVIEW_STATUS_UNCHANGED_OPTION, { value: 'cancelled', label: '已取消' }]
}
const AGENT_REVIEW_TASK_KEYS = new Set(Object.keys(AGENT_REVIEW_TASK_SCENES))

const scheduleLabel = (type) => ({ interval: '循环', daily: '每日', manual: '手动' }[type] || '未设置')
const categoryLabel = (category) => ({ readmodel: '快照', market: '市场', analysis: '分析', trade: '交易', system: '系统', history: '历史' }[category] || '其他')
const isReadmodelTask = (task) => String(task?.category || '') === 'readmodel'
const resolveAgentReviewScene = (task) => AGENT_REVIEW_TASK_SCENES[String(task?.taskKey || '').trim()] || ''
const resolveAgentReviewTaskLabel = (scene) => {
  const matchedTask = tasks.value.find((task) => resolveAgentReviewScene(task) === scene)
  return matchedTask?.taskName || AGENT_REVIEW_SCENE_LABELS[scene] || 'Agent 复核'
}
const isAgentReviewTask = (task) => AGENT_REVIEW_TASK_KEYS.has(String(task?.taskKey || '').trim())
const isUsOpenAiTradeTask = (task) => String(task?.taskKey || '').trim() === US_OPEN_AI_TRADE_TASK_KEY
const AUTO_BUY_DEFAULT_SETTINGS = {
  autoBuyEnabled: false,
  autoBuyMaxSymbols: 2,
  autoBuyMaxAmount: 2000,
  autoBuyMaxPositionRatio: 0.08,
  autoBuyMinConfidence: 72
}
const AUTO_TRADE_DEFAULT_SETTINGS = {
  autoTradeEnabled: true,
  maxSymbols: 5,
  targetPortfolioRatio: 0.70,
  minConfidence: 72,
  strategyProfile: 'balanced',
  market: 'US',
  regularSessionOnly: true
}
const AUTO_TRADE_STRATEGY_PROFILES = new Set(['balanced', 'momentum', 'breakout', 'reversion'])
const normalizeAutoBuyBool = (value, fallback = false) => {
  if (value === null || value === undefined || value === '') return fallback
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value > 0
  const normalized = String(value).trim().toLowerCase()
  if (['1', 'true', 'yes', 'on', 'enabled'].includes(normalized)) return true
  if (['0', 'false', 'no', 'off', 'disabled'].includes(normalized)) return false
  return fallback
}
const normalizeAutoBuyNumber = (value, fallback, min, max) => {
  const number = Number(value)
  const safeNumber = Number.isFinite(number) ? number : fallback
  return Math.min(Math.max(safeNumber, min), max)
}
const normalizeAutoBuySettings = (settings = {}) => ({
  ...settings,
  autoBuyEnabled: normalizeAutoBuyBool(settings.autoBuyEnabled, AUTO_BUY_DEFAULT_SETTINGS.autoBuyEnabled),
  autoBuyMaxSymbols: Math.round(normalizeAutoBuyNumber(settings.autoBuyMaxSymbols, AUTO_BUY_DEFAULT_SETTINGS.autoBuyMaxSymbols, 1, 10)),
  autoBuyMaxAmount: normalizeAutoBuyNumber(settings.autoBuyMaxAmount, AUTO_BUY_DEFAULT_SETTINGS.autoBuyMaxAmount, 0, 100000000),
  autoBuyMaxPositionRatio: normalizeAutoBuyNumber(settings.autoBuyMaxPositionRatio, AUTO_BUY_DEFAULT_SETTINGS.autoBuyMaxPositionRatio, 0, 1),
  autoBuyMinConfidence: Math.round(normalizeAutoBuyNumber(settings.autoBuyMinConfidence, AUTO_BUY_DEFAULT_SETTINGS.autoBuyMinConfidence, 0, 100))
})
const normalizeAutoTradeSettings = (settings = {}) => {
  const strategyProfile = String(settings.strategyProfile || AUTO_TRADE_DEFAULT_SETTINGS.strategyProfile).trim().toLowerCase()
  return {
    ...settings,
    autoTradeEnabled: normalizeAutoBuyBool(settings.autoTradeEnabled, AUTO_TRADE_DEFAULT_SETTINGS.autoTradeEnabled),
    maxSymbols: Math.round(normalizeAutoBuyNumber(settings.maxSymbols, AUTO_TRADE_DEFAULT_SETTINGS.maxSymbols, 1, 20)),
    targetPortfolioRatio: normalizeAutoBuyNumber(
      settings.targetPortfolioRatio,
      AUTO_TRADE_DEFAULT_SETTINGS.targetPortfolioRatio,
      0,
      1
    ),
    minConfidence: Math.round(normalizeAutoBuyNumber(settings.minConfidence, AUTO_TRADE_DEFAULT_SETTINGS.minConfidence, 0, 100)),
    strategyProfile: AUTO_TRADE_STRATEGY_PROFILES.has(strategyProfile)
      ? strategyProfile
      : AUTO_TRADE_DEFAULT_SETTINGS.strategyProfile,
    market: String(settings.market || AUTO_TRADE_DEFAULT_SETTINGS.market).trim().toUpperCase() || AUTO_TRADE_DEFAULT_SETTINGS.market,
    regularSessionOnly: normalizeAutoBuyBool(settings.regularSessionOnly, AUTO_TRADE_DEFAULT_SETTINGS.regularSessionOnly)
  }
}
const normalizeTaskPolicy = (task = {}) => ({
  ...task,
  settings: isAgentReviewTask(task)
    ? normalizeAutoBuySettings(task.settings && typeof task.settings === 'object' ? task.settings : {})
    : isUsOpenAiTradeTask(task)
      ? normalizeAutoTradeSettings(task.settings && typeof task.settings === 'object' ? task.settings : {})
    : (task.settings && typeof task.settings === 'object' ? task.settings : {})
})
const taskStateLabel = (state) => ({
  idle: '空闲',
  running: '运行中',
  success: '正常',
  skipped: '已跳过',
  failed: '失败',
  paused: '已暂停'
}[String(state || 'idle').toLowerCase()] || '未知')
const isTaskRunning = (task) => runningTaskKeys.value.has(task.taskKey) || String(task?.status?.state || '').toLowerCase() === 'running'
const stripTechnicalNoise = (message) => {
  const text = String(message || '').trim()
  if (!text) return ''
  return text
    .replace(/[,，]?\s*(nextCursor|cursor)\s*[:=]\s*[^,，；;]+/gi, '')
    .replace(/\s{2,}/g, ' ')
    .replace(/[，,\s]+$/, '')
}
const taskStatusMessage = (task) => {
  if (String(task?.status?.state || '').toLowerCase() === 'running') {
    return '任务正在执行，请稍后刷新状态'
  }
  return stripTechnicalNoise(task?.status?.message) || '等待执行'
}
const sanitizeTaskResultMessage = (value) => {
  if (!value || typeof value !== 'object') return ''
  const directMessage = value.message || value.summary || value.result || ''
  if (typeof directMessage === 'string' && directMessage.trim()) {
    return directMessage.trim()
  }
  return Object.entries(value)
    .filter(([key, entry]) => {
      if (['cursor', 'nextCursor', 'settings', 'metadata', 'items', 'list', 'data'].includes(key)) return false
      if (entry === null || entry === undefined || entry === '') return false
      if (typeof entry === 'object') return false
      return true
    })
    .map(([key, entry]) => `${key}: ${entry}`)
    .join('，')
}
const taskPriority = (task) => {
  if (task?.taskKey === 'quote_snapshot_refresh') return -20
  if (isReadmodelTask(task)) return -10
  return 0
}
const isHistoryCoverageTask = (task) => {
  const taskKey = String(task?.taskKey || '').trim().toLowerCase()
  const taskName = String(task?.taskName || '').trim()
  return ['bootstrap_market_history_2024', 'market_history_universe_backfill'].includes(taskKey)
    || /全量历史数据补充|全量历史回补|历史回补/.test(taskName)
}
const displayTasks = computed(() => {
  return [...tasks.value].sort((a, b) => {
    const diff = taskPriority(a) - taskPriority(b)
    if (diff !== 0) return diff
    return String(a.taskName || a.taskKey || '').localeCompare(String(b.taskName || b.taskKey || ''), 'zh-CN')
  })
})
const readmodelTasks = computed(() => tasks.value.filter((task) => isReadmodelTask(task)))
const realtimeTasks = computed(() => tasks.value.filter((task) => !isReadmodelTask(task)))
const quoteSnapshotTask = computed(() => tasks.value.find((task) => task.taskKey === 'quote_snapshot_refresh') || null)
const formatTaskLastRun = (task) => task?.status?.lastRunAt || '--'
const firstDefinedValue = (...values) => {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== '') {
      return value
    }
  }
  return null
}
const extractListPayload = (value) => {
  if (Array.isArray(value)) return value
  if (!value || typeof value !== 'object') return []
  if (Array.isArray(value.items)) return value.items
  if (Array.isArray(value.list)) return value.list
  if (Array.isArray(value.runs)) return value.runs
  if (Array.isArray(value.data)) return value.data
  return []
}
const normalizeScalarText = (value) => {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}
const formatFieldLabel = (value) => String(value || '')
  .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
  .replace(/[_-]+/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()
const formatDateTime = (value) => {
  if (!value) return '--'
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}
const toFiniteNumber = (value) => {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}
const toArray = (value) => {
  if (Array.isArray(value)) {
    return value.filter((item) => item !== null && item !== undefined && item !== '')
  }
  if (value && typeof value === 'object') {
    return [value]
  }
  if (value === null || value === undefined || value === '') {
    return []
  }
  return [value]
}
const normalizeOverrideAction = (value) => String(value || '').trim().toLowerCase().replace(/[-\s]+/g, '_')
const latestAgentOverrideAction = (overrides = []) => {
  const normalized = toArray(overrides)
    .map((item) => ({
      ...item,
      action: normalizeOverrideAction(item?.action || item?.type),
      createdAt: firstDefinedValue(item?.createdAt, item?.created_at, '')
    }))
    .filter((item) => item.action)

  return normalized[normalized.length - 1]?.action || ''
}
const normalizeAgentRun = (run = {}) => {
  const resultPayload = firstDefinedValue(run.resultSummary, run.result_summary, run.result, run.outputSummary, run.output_summary, {})
  const reviewAdvice = toArray(firstDefinedValue(resultPayload?.reviewAdvice, resultPayload?.review_advice, run.reviewAdvice, run.review_advice))
  const overrides = toArray(firstDefinedValue(run.overrides, run.overrideHistory, run.override_history, run.result?.overrides))
  const confidence = toFiniteNumber(firstDefinedValue(resultPayload?.confidence, run.confidence, run.reviewConfidence, run.review_confidence, run.score))
  const adviceCountValue = firstDefinedValue(run.adviceCount, run.advice_count, run.reviewAdviceCount, run.review_advice_count)
  const adviceCount = adviceCountValue !== null ? Number(adviceCountValue) : reviewAdvice.length
  const displayAt = firstDefinedValue(run.completedAt, run.completed_at, run.updatedAt, run.updated_at, run.createdAt, run.created_at)
  const reviewAction = latestAgentOverrideAction(overrides)

  return {
    ...run,
    id: firstDefinedValue(run.runId, run.run_id, run.id),
    scene: normalizeScalarText(firstDefinedValue(run.scene, run.sceneKey, run.scene_key, run.taskKey, run.task_key)),
    status: normalizeScalarText(firstDefinedValue(run.status, run.state, run.reviewStatus, run.review_status)) || 'unknown',
    summary: normalizeScalarText(firstDefinedValue(resultPayload?.summary, run.summary, run.payload?.summary, run.output?.summary)),
    confidence,
    adviceCount: Number.isFinite(adviceCount) ? adviceCount : null,
    signals: toArray(firstDefinedValue(resultPayload?.signals, run.signals)),
    riskFlags: toArray(firstDefinedValue(resultPayload?.riskFlags, resultPayload?.risk_flags, run.riskFlags, run.risk_flags)),
    reviewAdvice,
    evidence: toArray(firstDefinedValue(resultPayload?.evidence, run.evidence)),
    steps: toArray(firstDefinedValue(run.steps, run.timeline, run.result?.steps)),
    overrides,
    createdAt: firstDefinedValue(run.createdAt, run.created_at),
    updatedAt: firstDefinedValue(run.updatedAt, run.updated_at),
    completedAt: firstDefinedValue(run.completedAt, run.completed_at),
    displayAt,
    reviewAction,
    acknowledged: reviewAction === 'acknowledged'
  }
}
const agentReviewActionLabel = (action) => ({
  acknowledged: '已复核',
  needs_review: '需继续复核',
  dismissed: '已忽略'
}[normalizeOverrideAction(action)] || '未处理')
const agentRunReviewStateLabel = (run) => agentReviewActionLabel(run?.reviewAction)
const agentReviewActionButtonLabel = (run, action) => (
  normalizeOverrideAction(run?.reviewAction) === action.key ? action.doneLabel : action.label
)
const activeReviewStatusOptions = computed(() => {
  const action = normalizeOverrideAction(reviewActionForm.value.action) || 'acknowledged'
  return AGENT_REVIEW_STATUS_OPTIONS[action] || AGENT_REVIEW_STATUS_OPTIONS.acknowledged
})
const agentReviewSubmitLabel = (run) => (
  agentReviewActionButtonLabel(
    run,
    AGENT_REVIEW_ACTIONS.find((item) => item.key === reviewActionForm.value.action) || AGENT_REVIEW_ACTIONS[0]
  )
)
const isReviewActionLoading = (runId, action = '') => Boolean(
  runId &&
  acknowledgingRunId.value === runId &&
  (!action || acknowledgingAction.value === action)
)
const isReviewActionBusy = (runId) => Boolean(runId && acknowledgingRunId.value === runId)
const isReviewActionDisabled = (run, action) => {
  if (!run?.id || isReviewActionBusy(run.id)) return true
  return normalizeOverrideAction(run.reviewAction) === action
}
const resetReviewActionForm = () => {
  reviewActionForm.value = createReviewActionForm()
}
watch(
  () => reviewActionForm.value.action,
  (action) => {
    const normalizedAction = normalizeOverrideAction(action) || 'acknowledged'
    const options = AGENT_REVIEW_STATUS_OPTIONS[normalizedAction] || AGENT_REVIEW_STATUS_OPTIONS.acknowledged
    const fallbackStatus = options[0]?.value || ''
    if (!options.some((item) => item.value === reviewActionForm.value.newStatus)) {
      reviewActionForm.value.newStatus = fallbackStatus
    }
  },
  { immediate: true }
)
const agentRunStatusLabel = (status) => ({
  success: '成功',
  succeeded: '成功',
  completed: '成功',
  skipped: '已跳过',
  failed: '失败',
  error: '失败',
  degraded: '降级',
  running: '运行中',
  pending: '等待中',
  queued: '等待中',
  acknowledged: '已复核'
}[String(status || '').toLowerCase()] || '未知')
const agentRunStatusTone = (status) => {
  const normalized = String(status || '').toLowerCase()
  if (['success', 'succeeded', 'completed', 'acknowledged'].includes(normalized)) return 'success'
  if (['failed', 'error'].includes(normalized)) return 'danger'
  if (['running'].includes(normalized)) return 'accent'
  if (['skipped'].includes(normalized)) return 'muted'
  return 'muted'
}
const formatAgentRunTimestamp = (run) => formatDateTime(run?.displayAt || run?.completedAt || run?.updatedAt || run?.createdAt)
const formatAgentRunConfidence = (run) => {
  const number = toFiniteNumber(run?.confidence)
  if (number === null) return ''
  return `${(number <= 1 ? number * 100 : number).toFixed(number <= 1 ? 0 : 1)}%`
}
const summarizeObjectScalars = (value = {}) => {
  return Object.entries(value)
    .filter(([, entry]) => ['string', 'number', 'boolean'].includes(typeof entry) && entry !== '')
    .slice(0, 6)
    .map(([key, entry]) => `${formatFieldLabel(key)}: ${entry}`)
    .join(' · ')
}
const normalizeAgentRunEntries = (value, sectionKey) => {
  return toArray(value).map((item, index) => {
    if (typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean') {
      return {
        key: `${sectionKey}-${index}`,
        title: '',
        text: String(item),
        meta: ''
      }
    }

    if (!item || typeof item !== 'object') {
      return null
    }

    const title = normalizeScalarText(firstDefinedValue(item.title, item.name, item.label, item.signal, item.flag, item.action, item.step))
    const text = normalizeScalarText(firstDefinedValue(item.summary, item.description, item.message, item.advice, item.reason, item.content, item.value, item.result))
    const metaSource = { ...item }

    delete metaSource.title
    delete metaSource.name
    delete metaSource.label
    delete metaSource.signal
    delete metaSource.flag
    delete metaSource.action
    delete metaSource.step
    delete metaSource.summary
    delete metaSource.description
    delete metaSource.message
    delete metaSource.advice
    delete metaSource.reason
    delete metaSource.content
    delete metaSource.value
    delete metaSource.result

    return {
      key: `${sectionKey}-${index}`,
      title,
      text: text || summarizeObjectScalars(item),
      meta: summarizeObjectScalars(metaSource)
    }
  }).filter(Boolean)
}
const getTaskAgentRun = (task) => agentRunSummaryMap.value[resolveAgentReviewScene(task)] || null
const isAgentRunSummaryLoading = (task) => agentRunSummaryLoadingKeys.value.has(resolveAgentReviewScene(task))
const agentRunSections = computed(() => {
  const run = activeAgentRun.value
  if (!run) return []

  return [
    { key: 'signals', label: '信号', type: 'list', entries: normalizeAgentRunEntries(run.signals, 'signals') },
    { key: 'riskFlags', label: '风险', type: 'list', entries: normalizeAgentRunEntries(run.riskFlags, 'riskFlags') },
    { key: 'reviewAdvice', label: '复核建议', type: 'list', entries: normalizeAgentRunEntries(run.reviewAdvice, 'reviewAdvice') },
    { key: 'evidence', label: '依据', type: 'list', entries: normalizeAgentRunEntries(run.evidence, 'evidence') },
    { key: 'steps', label: '步骤', type: 'list', entries: normalizeAgentRunEntries(run.steps, 'steps') },
    { key: 'overrides', label: '人工记录', type: 'list', entries: normalizeAgentRunEntries(run.overrides, 'overrides') }
  ]
})
const openHistoryCoverage = () => {
  router.push({ name: 'HistoryCoverage' })
}
const loadAgentRunSummaryForScene = async (scene) => {
  if (!scene) return null

  agentRunSummaryLoadingKeys.value = new Set([...agentRunSummaryLoadingKeys.value, scene])
  try {
    const res = await getAgentRuns({ scene, limit: 1 })
    const latestRun = normalizeAgentRun(extractListPayload(res?.data)[0] || {})
    agentRunSummaryMap.value = {
      ...agentRunSummaryMap.value,
      [scene]: latestRun.id ? latestRun : null
    }
    return latestRun.id ? latestRun : null
  } catch (error) {
    console.error(`加载 Agent 复核摘要失败: ${scene}`, error)
    return null
  } finally {
    const next = new Set(agentRunSummaryLoadingKeys.value)
    next.delete(scene)
    agentRunSummaryLoadingKeys.value = next
  }
}
const loadAgentRunSummaries = async (taskList = tasks.value) => {
  const scenes = [...new Set(taskList.map((task) => resolveAgentReviewScene(task)).filter(Boolean))]
  if (!scenes.length) return
  await Promise.allSettled(scenes.map((scene) => loadAgentRunSummaryForScene(scene)))
}
const loadTasks = async () => {
  loading.value = true
  try {
    const res = await getPlatformTasks()
    tasks.value = (Array.isArray(res?.data) ? res.data : []).map(normalizeTaskPolicy)
    await loadAgentRunSummaries(tasks.value)
  } catch (error) {
    console.error('加载任务失败:', error)
    ElMessage.error('加载任务失败')
  } finally {
    loading.value = false
  }
}

const saveTask = async (task) => {
  try {
    const normalizedTask = normalizeTaskPolicy(task)
    if (isAgentReviewTask(task) || isUsOpenAiTradeTask(task)) {
      task.settings = normalizedTask.settings
    }
    await updatePlatformTask(task.taskKey, {
      enabled: task.enabled,
      intervalSeconds: task.intervalSeconds,
      runHour: task.runHour,
      runMinute: task.runMinute,
      maxRequestsPerMinute: task.maxRequestsPerMinute,
      batchSize: task.batchSize,
      description: task.description,
      settings: normalizedTask.settings || {}
    })
    const index = tasks.value.findIndex((item) => item.taskKey === task.taskKey)
    if (index >= 0) {
      tasks.value[index] = {
        ...tasks.value[index],
        ...normalizedTask,
        settings: normalizedTask.settings || {}
      }
    }
    ElMessage.success(`${task.taskName} 已更新`)
  } catch (error) {
    console.error('更新任务失败:', error)
    ElMessage.error('更新任务失败')
  }
}

const runTask = async (task) => {
  if (isTaskRunning(task)) return
  runningTaskKeys.value = new Set([...runningTaskKeys.value, task.taskKey])
  try {
    const res = await runPlatformTask(task.taskKey)
    const resultMessage = sanitizeTaskResultMessage(res?.data)
    ElMessage.success(resultMessage ? `${task.taskName} 已触发：${resultMessage}` : `${task.taskName} 已触发`)
    await loadTasks()
  } catch (error) {
    console.error('执行任务失败:', error)
    ElMessage.error(error?.message || '执行任务失败')
  } finally {
    const next = new Set(runningTaskKeys.value)
    next.delete(task.taskKey)
    runningTaskKeys.value = next
  }
}
const openAgentRunResult = async (task) => {
  const scene = resolveAgentReviewScene(task)
  const summaryRun = getTaskAgentRun(task) || await loadAgentRunSummaryForScene(scene)

  if (!summaryRun?.id) {
    ElMessage.warning('暂无可查看的复核结果')
    return
  }

  activeAgentTaskLabel.value = task.taskName || task.taskKey || ''
  agentRunDrawerVisible.value = true
  agentRunDetailLoading.value = true

  try {
    const res = await getAgentRun(summaryRun.id)
    activeAgentRun.value = normalizeAgentRun(res?.data || {})
    resetReviewActionForm()
  } catch (error) {
    console.error('加载 Agent 复核详情失败:', error)
    activeAgentRun.value = summaryRun
    ElMessage.error(error?.message || '加载复核详情失败')
  } finally {
    agentRunDetailLoading.value = false
  }
}
const openAgentRunResultById = async (runId, scene = '') => {
  const normalizedRunId = normalizeScalarText(runId)
  const normalizedScene = normalizeScalarText(scene)
  if (!normalizedRunId) return

  activeAgentTaskLabel.value = resolveAgentReviewTaskLabel(normalizedScene)
  agentRunDrawerVisible.value = true
  agentRunDetailLoading.value = true

  try {
    const res = await getAgentRun(normalizedRunId)
    const run = normalizeAgentRun(res?.data || {})
    activeAgentRun.value = run.id ? run : { ...run, id: normalizedRunId, scene: normalizedScene }
    resetReviewActionForm()
    const summaryScene = activeAgentRun.value.scene || normalizedScene
    if (summaryScene) {
      agentRunSummaryMap.value = {
        ...agentRunSummaryMap.value,
        [summaryScene]: activeAgentRun.value
      }
      activeAgentTaskLabel.value = resolveAgentReviewTaskLabel(summaryScene)
    }
  } catch (error) {
    console.error('加载 Agent 复核详情失败:', error)
    activeAgentRun.value = { id: normalizedRunId, scene: normalizedScene, status: 'unknown', summary: '' }
    ElMessage.error(error?.message || '加载复核详情失败')
  } finally {
    agentRunDetailLoading.value = false
  }
}
const submitAgentRunReviewAction = async (runId, scene = '', action = reviewActionForm.value.action) => {
  if (!runId || acknowledgingRunId.value === runId) return

  const normalizedAction = normalizeOverrideAction(action)
  const actionConfig = AGENT_REVIEW_ACTIONS.find((item) => item.key === normalizedAction) || AGENT_REVIEW_ACTIONS[0]
  const reason = normalizeScalarText(reviewActionForm.value.reason)
  const reviewNote = normalizeScalarText(reviewActionForm.value.reviewNote)
  const newStatus = normalizeScalarText(reviewActionForm.value.newStatus)
  acknowledgingRunId.value = runId
  acknowledgingAction.value = normalizedAction
  try {
    await reviewAgentRun(runId, {
      action: normalizedAction,
      reason: reason || actionConfig.label,
      ...(newStatus ? { newStatus } : {}),
      ...(reviewNote ? { reviewNote } : {})
    })
    ElMessage.success(actionConfig.message)
    resetReviewActionForm()
    if (scene) {
      await loadAgentRunSummaryForScene(scene)
    }
    if (activeAgentRun.value?.id === runId) {
      const res = await getAgentRun(runId)
      activeAgentRun.value = normalizeAgentRun(res?.data || activeAgentRun.value)
      const summaryScene = activeAgentRun.value.scene || scene
      if (summaryScene) {
        agentRunSummaryMap.value = {
          ...agentRunSummaryMap.value,
          [summaryScene]: activeAgentRun.value
        }
      }
    }
  } catch (error) {
    console.error('记录人工复核失败:', error)
    ElMessage.error(error?.message || '记录人工复核失败')
  } finally {
    acknowledgingRunId.value = ''
    acknowledgingAction.value = ''
  }
}
const acknowledgeAgentRunById = async (runId, scene = '') => {
  await submitAgentRunReviewAction(runId, scene, 'acknowledged')
}
const acknowledgeAgentRun = async (task) => {
  const scene = resolveAgentReviewScene(task)
  const summaryRun = getTaskAgentRun(task) || await loadAgentRunSummaryForScene(scene)
  if (!summaryRun?.id) {
    ElMessage.warning('暂无可复核的运行结果')
    return
  }
  await acknowledgeAgentRunById(summaryRun.id, scene)
}

onMounted(async () => {
  await loadTasks()
  await openAgentRunResultById(route.query?.agentRunId, route.query?.scene)
  routeQueryHydrated.value = true
})

watch(
  () => route.query?.agentRunId,
  async (runId, previousRunId) => {
    if (!routeQueryHydrated.value || !runId || runId === previousRunId) return
    await openAgentRunResultById(runId, route.query?.scene)
  }
)
</script>

<style scoped lang="scss">
.scheduler-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.page-header,
.task-top,
.task-status,
.task-actions,
.daily-time {
  display: flex;
  align-items: center;
}

.page-header {
  justify-content: space-between;
  gap: 16px;

  h2 {
    margin: 0;
    color: var(--text-primary);
  }

  p {
    margin: 6px 0 0;
    color: var(--text-secondary);
  }
}

.task-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.glass-card {
  border: 1px solid var(--border-soft);
  background: var(--surface-strong);
  box-shadow: var(--shadow-strong);
}

.overview-card {
  :deep(.el-card__body) {
    display: grid;
    gap: 8px;
  }

  span,
  small {
    color: var(--text-muted);
  }

  strong {
    color: var(--text-primary);
    font-size: 22px;
  }
}

.task-card {
  :deep(.el-card__body) {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  &.is-readmodel {
    border-color: color-mix(in srgb, var(--accent) 28%, var(--border-soft));
  }

  &.is-highlight {
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--success) 22%, transparent), var(--shadow-strong);
  }
}

.task-top {
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;

  h3 {
    margin: 4px 0 0;
    color: var(--text-primary);
    font-size: 16px;
  }
}

.task-tag-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.task-category,
.task-status,
.task-message {
  color: var(--text-muted);
  font-size: 12px;
}

.task-scene {
  margin: 8px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.task-desc {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.daily-time {
  gap: 10px;
}

.task-status,
.task-actions {
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.agent-review-summary {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
}

.agent-review-head,
.agent-review-meta,
.agent-review-actions,
.agent-run-hero,
.agent-run-stats {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-review-head,
.agent-run-hero {
  justify-content: space-between;
  align-items: flex-start;
}

.agent-review-label,
.agent-review-meta,
.agent-review-empty,
.agent-entry-meta {
  color: var(--text-muted);
  font-size: 12px;
}

.agent-review-text,
.agent-run-summary {
  margin: 0;
  color: var(--text-primary);
  line-height: 1.6;
}

.agent-run-status {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid var(--border-soft);
  background: var(--surface-strong);
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.agent-run-status.is-success {
  border-color: color-mix(in srgb, var(--success) 28%, var(--border-soft));
  background: color-mix(in srgb, var(--success) 12%, var(--surface-strong));
  color: var(--success);
}

.agent-run-status.is-danger {
  border-color: color-mix(in srgb, var(--danger) 28%, var(--border-soft));
  background: color-mix(in srgb, var(--danger) 12%, var(--surface-strong));
  color: var(--danger);
}

.agent-run-status.is-accent {
  border-color: color-mix(in srgb, var(--accent) 28%, var(--border-soft));
  background: color-mix(in srgb, var(--accent) 12%, var(--surface-strong));
  color: var(--accent);
}

.review-button,
.ack-button {
  border-color: color-mix(in srgb, var(--accent) 24%, var(--border-soft));
  background: var(--surface-strong);
  color: var(--text-primary);
}

.review-button:hover,
.review-button:focus-visible,
.ack-button:hover,
.ack-button:focus-visible {
  border-color: color-mix(in srgb, var(--accent) 38%, var(--border-soft));
  background: color-mix(in srgb, var(--accent) 14%, var(--surface-strong));
}

.ack-button:disabled {
  background: var(--surface-strong);
  color: var(--text-muted);
  border-color: var(--border-soft);
}

.task-action-buttons {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.coverage-button {
  border-color: color-mix(in srgb, var(--accent) 28%, transparent);
  background: color-mix(in srgb, var(--accent) 14%, var(--surface-soft));
  color: var(--text-emphasis);
}

.coverage-button:hover,
.coverage-button:focus-visible {
  border-color: color-mix(in srgb, var(--accent) 36%, transparent);
  background: color-mix(in srgb, var(--accent) 20%, var(--surface-soft));
  color: var(--text-emphasis);
}

.task-body :deep(.el-form) {
  --el-component-size: 28px;
}

.task-body :deep(.el-form-item) {
  margin-bottom: 8px;
}

.auto-buy-settings {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--warning) 28%, var(--border-soft));
  background: color-mix(in srgb, var(--warning) 8%, var(--surface-soft));
}

.auto-buy-settings.is-enabled {
  border-color: color-mix(in srgb, var(--success) 32%, var(--border-soft));
  background: color-mix(in srgb, var(--success) 9%, var(--surface-soft));
}

.auto-buy-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;

  > div {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  strong {
    color: var(--text-primary);
    font-size: 14px;
  }
}

.auto-buy-settings p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.auto-buy-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;

  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }

  span {
    color: var(--text-muted);
    font-size: 12px;
  }

  :deep(.el-input-number) {
    width: 100%;
  }
}

.agent-run-drawer :deep(.el-drawer) {
  background: var(--surface-strong);
}

.agent-run-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-soft);
}

.agent-run-drawer :deep(.el-drawer__title) {
  color: var(--text-primary);
}

.agent-run-drawer :deep(.el-drawer__body) {
  padding-top: 18px;
  background: var(--surface-strong);
}

.agent-run-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.agent-run-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.agent-stat-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);

  span {
    color: var(--text-muted);
    font-size: 12px;
  }

  strong {
    color: var(--text-primary);
    font-size: 16px;
  }
}

.agent-drawer-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-entry-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-entry-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
}

.agent-entry-title {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.agent-entry-text {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.agent-drawer-empty {
  color: var(--text-muted);
  font-size: 13px;
}

.agent-review-control {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
}

.review-action-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.review-action-option {
  min-height: 34px;
  padding: 0 10px;
  border-radius: 10px;
  border: 1px solid var(--border-soft);
  background: var(--surface-strong);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.review-action-option.active {
  color: var(--text-primary);
  border-color: color-mix(in srgb, var(--accent) 42%, var(--border-soft));
  background: color-mix(in srgb, var(--accent) 15%, var(--surface-strong));
}

.review-action-option.is-acknowledged.active {
  border-color: color-mix(in srgb, var(--success) 46%, var(--border-soft));
  background: color-mix(in srgb, var(--success) 15%, var(--surface-strong));
}

.review-action-option.is-needs_review.active {
  border-color: color-mix(in srgb, var(--warning) 50%, var(--border-soft));
  background: color-mix(in srgb, var(--warning) 16%, var(--surface-strong));
}

.review-action-option.is-dismissed.active {
  border-color: color-mix(in srgb, var(--text-muted) 42%, var(--border-soft));
  background: color-mix(in srgb, var(--text-muted) 12%, var(--surface-strong));
}

.review-status-select {
  width: 100%;
}

.agent-review-control :deep(.el-input__wrapper),
.agent-review-control :deep(.el-select__wrapper) {
  background: var(--surface-strong);
  border: 1px solid var(--border-soft);
  box-shadow: none;
}

.agent-review-control :deep(.el-input__inner),
.agent-review-control :deep(.el-select__placeholder),
.agent-review-control :deep(.el-select__selected-item) {
  color: var(--text-primary);
}

.agent-review-control :deep(.el-textarea__inner) {
  min-height: 82px;
  background: var(--surface-strong);
  color: var(--text-primary);
  border-color: var(--border-soft);
  box-shadow: none;
}

.agent-review-control :deep(.el-textarea__inner::placeholder) {
  color: var(--text-muted);
}

.agent-review-control :deep(.el-input__count) {
  color: var(--text-muted);
  background: transparent;
}

.agent-drawer-actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.review-action-button {
  min-width: 0;
  border-color: var(--border-soft);
  color: var(--text-primary);
  background: var(--surface-strong);
}

.review-action-button:hover,
.review-action-button:focus-visible {
  color: var(--text-primary);
  border-color: color-mix(in srgb, var(--accent) 34%, transparent);
  background: color-mix(in srgb, var(--accent) 14%, var(--surface-strong));
}

.review-action-button.is-acknowledged {
  border-color: color-mix(in srgb, var(--success) 34%, transparent);
  background: color-mix(in srgb, var(--success) 14%, var(--surface-strong));
}

.review-action-button.is-needs_review {
  border-color: color-mix(in srgb, var(--warning) 38%, transparent);
  background: color-mix(in srgb, var(--warning) 16%, var(--surface-strong));
}

.review-action-button.is-dismissed {
  border-color: color-mix(in srgb, var(--text-muted) 32%, transparent);
  background: color-mix(in srgb, var(--text-muted) 12%, var(--surface-strong));
}

.review-action-button.is-reset {
  border-color: var(--border-soft);
  background: var(--surface-strong);
}

.review-action-button.is-disabled,
.review-action-button:disabled {
  color: var(--text-muted);
  border-color: var(--border-soft);
  background: var(--surface-strong);
}

@media (max-width: 1100px) {
  .overview-grid,
  .task-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .auto-buy-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<template>
  <div class="profile-page">
    <PageHero
      title="个人中心"
      :chips="profileHeroChips"
      :metrics="profileHeroMetrics"
    >
      <template #actions>
        <div class="hero-actions">
          <el-select v-model="selectedAccount" placeholder="选择账户" class="profile-account-select">
            <el-option
              v-for="account in accounts"
              :key="account.id"
              :label="account.name"
              :value="account.id"
            />
          </el-select>
          <el-button type="primary" :loading="accountLoading" @click="refreshAccountPanel">
            实时刷新
          </el-button>
        </div>
      </template>
    </PageHero>

    <MetricStrip class="profile-overview-strip" :items="profileOverviewItems" />

    <MobileSegmentControl
      v-if="isPhoneLayout"
      v-model="activeProfileSection"
      class="mobile-profile-rail"
      label="个人中心分段"
      :items="profileMobileSections"
    />

    <div class="profile-container">
      <div class="profile-main-column">
        <el-card v-if="!isPhoneLayout || activeProfileSection === 'overview'" class="glass-card">
          <template #header>
            <SectionCardHeader
              title="实时账户"
              :badge="realtimeBadge.text"
              :badge-type="realtimeBadge.type"
            >
              <template #actions>
                <div class="card-actions">
                  <el-tag size="small" :type="simulationTag.type">{{ simulationTag.text }}</el-tag>
                  <el-tag size="small" type="info">{{ summaryLabel }}</el-tag>
                </div>
              </template>
            </SectionCardHeader>
          </template>

          <ReadModelSourceStrip
            label="账户状态"
            :status-text="accountReadiness.statusText"
            :status-type="accountReadiness.statusType"
            :updated-at="formattedUpdatedAt"
            :updated-prefix="accountReadiness.updatedPrefix"
            :tags="accountReadiness.tags"
            compact
          />

          <div class="stats-grid account-stats-grid">
            <div class="stat-item emphasis">
              <div class="stat-icon blue">
                <el-icon size="24"><Wallet /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-label">账户总资产</div>
                <div class="stat-value">{{ formatCurrency(accountStats.totalAssets) }}</div>
                <div class="stat-note">可用资金 {{ formatCurrency(accountStats.cash) }}</div>
              </div>
            </div>
            <div class="stat-item">
              <div class="stat-icon green">
                <el-icon size="24"><TrendCharts /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-label">今日盈亏</div>
                <div class="stat-value" :class="accountStats.todayPnl >= 0 ? 'up' : 'down'">
                  {{ formatSignedCurrency(accountStats.todayPnl) }}
                </div>
                <div class="stat-note" :class="accountStats.todayPnlPercent >= 0 ? 'up' : 'down'">
                  {{ formatPercent(accountStats.todayPnlPercent) }}
                </div>
              </div>
            </div>
            <div class="stat-item">
              <div class="stat-icon amber">
                <el-icon size="24"><Document /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-label">订单数</div>
                <div class="stat-value">{{ accountStats.orderCount }}</div>
                <div class="stat-note">今日/最近活跃订单统计</div>
              </div>
            </div>
            <div class="stat-item">
              <div class="stat-icon rose">
                <el-icon size="24"><Star /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-label">启用规则</div>
                <div class="stat-value">{{ accountStats.strategyCount }}</div>
                <div class="stat-note">当前 active 策略数量</div>
              </div>
            </div>
          </div>

          <div class="status-panel">
            <article v-for="item in accountStatusCards" :key="item.label" class="status-card">
              <span class="status-label">{{ item.label }}</span>
              <strong :class="item.tone">{{ item.value }}</strong>
              <p v-if="item.note">{{ item.note }}</p>
            </article>
          </div>

          <el-alert
            v-if="accountError"
            class="profile-alert"
            type="warning"
            :closable="false"
            show-icon
            :title="accountError"
          />
        </el-card>

        <el-card v-if="!isPhoneLayout || activeProfileSection === 'overview'" class="glass-card compact-card">
          <template #header>
            <SectionCardHeader title="最近活动" />
          </template>
          <el-timeline>
            <el-timeline-item
              v-for="activity in activities"
              :key="activity.id"
              :timestamp="formatDate(activity.time)"
              :type="activity.type"
            >
              {{ activity.content }}
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </div>

      <div class="profile-side-column">
        <el-card v-if="!isPhoneLayout || activeProfileSection === 'broker'" class="glass-card compact-card">
          <template #header>
            <SectionCardHeader
              title="券商连接"
              :badge="accounts.length ? `已绑定 ${accounts.length} 个账户` : '未绑定'"
              :badge-type="accounts.length ? 'success' : 'info'"
            />
          </template>

          <div class="broker-summary-grid">
            <div class="status-item slim">
              <span class="label">默认账户</span>
              <strong>{{ defaultBrokerName }}</strong>
            </div>
            <div class="status-item slim">
              <span class="label">量化交易 API</span>
              <strong>{{ access?.quantApiEnabled ? '已开通' : '未开通' }}</strong>
            </div>
          </div>

          <div class="broker-account-list" v-if="accounts.length">
            <div class="broker-account-item" v-for="account in accounts" :key="account.id">
              <div>
                <div class="broker-account-name">{{ account.name }}</div>
                <div class="broker-account-meta">{{ account.brokerName }} · {{ account.accountId || '未回填账户号' }}</div>
              </div>
              <div class="broker-account-tags">
                <el-tag v-if="account.isDefault" size="small" type="warning">默认</el-tag>
                <el-tag size="small" :type="account.isActive ? 'success' : 'info'">{{ account.isActive ? '可用' : '停用' }}</el-tag>
              </div>
            </div>
          </div>

          <el-empty v-else description="当前用户还没有绑定券商连接，可先添加长桥或老虎账户" :image-size="92" />

          <div class="broker-actions">
            <el-button type="primary" @click="openBrokerManagement">管理券商连接</el-button>
          </div>
        </el-card>

        <el-card v-if="!isPhoneLayout || activeProfileSection === 'quant'" class="glass-card compact-card">
          <template #header>
            <SectionCardHeader
              title="AI 量化交易"
              :badge="quantStatus.enabled ? '已启用' : '未启用'"
              :badge-type="quantStatus.enabled ? 'success' : 'info'"
            />
          </template>

          <el-alert
            v-if="!hasBoundAccount"
            type="warning"
            :closable="false"
            show-icon
            class="quant-alert"
            title="当前用户还没有绑定券商账户，量化交易与自动执行将保持关闭。"
          />

          <el-alert
            v-else-if="!canUseQuantTrading"
            type="info"
            :closable="false"
            show-icon
            class="quant-alert"
            title="当前用户尚未开通量化交易 API 或角色未授权量化能力，可继续查看分析结果。"
          />

          <el-form :model="quantForm" label-width="118px" class="quant-form">
            <el-form-item label="启用 AI 量化">
              <el-switch v-model="quantForm.ai_quant_trading_enabled" :disabled="!canUseQuantTrading" />
            </el-form-item>
            <el-form-item label="允许自动执行">
              <el-switch v-model="quantForm.ai_quant_auto_execute" :disabled="!canUseQuantTrading" />
            </el-form-item>
            <el-form-item label="监控间隔(秒)">
              <el-input-number v-model="quantForm.position_monitor_interval" :min="120" :step="60" :disabled="!canUseQuantTrading" />
            </el-form-item>
            <el-form-item label="量化间隔(秒)">
              <el-input-number v-model="quantForm.ai_quant_interval" :min="300" :step="300" :disabled="!canUseQuantTrading" />
            </el-form-item>
            <el-form-item label="置信度阈值">
              <el-input-number v-model="quantForm.ai_quant_confidence_threshold" :min="1" :max="100" :disabled="!canUseQuantTrading" />
            </el-form-item>
            <el-form-item label="单次买入预算">
              <el-input-number v-model="quantForm.ai_quant_max_buy_amount" :min="100" :step="100" :disabled="!canUseQuantTrading" />
            </el-form-item>
            <el-form-item>
              <div class="quant-actions">
                <el-button type="primary" @click="saveQuantConfig" :disabled="!canUseQuantTrading">保存量化配置</el-button>
                <el-button @click="runQuantNow" :loading="runningQuant" :disabled="!canUseQuantTrading">立即分析一次</el-button>
              </div>
            </el-form-item>
          </el-form>

          <div class="status-grid compact-status-grid">
            <div class="status-item slim">
              <span class="label">调度状态</span>
              <strong>{{ quantSchedulerStatusLabel }}</strong>
            </div>
            <div class="status-item slim">
              <span class="label">最近运行</span>
              <strong>{{ formatDate(quantStatus.lastRunAt) }}</strong>
            </div>
            <div class="status-item slim">
              <span class="label">周期</span>
              <strong>{{ quantStatus.interval || 0 }} 秒</strong>
            </div>
            <div class="status-item slim">
              <span class="label">最新信号数</span>
              <strong>{{ latestSignals.length }}</strong>
            </div>
          </div>
        </el-card>

        <el-card v-if="!isPhoneLayout || activeProfileSection === 'quant'" class="glass-card compact-card">
          <template #header>
            <SectionCardHeader
              title="最近量化建议"
              :badge="latestSignals.length ? `${latestSignals.length} 条` : '暂无'"
              :badge-type="latestSignals.length ? 'success' : 'info'"
            />
          </template>

          <div v-if="latestSignals.length" class="mobile-signal-list desktop-signal-list">
            <article v-for="row in latestSignals" :key="`${row.symbol}-${row.createdAt}`" class="mobile-signal-card">
              <div class="mobile-signal-head">
                <strong>{{ row.symbol }}</strong>
                <el-tag size="small" :type="row.side === 'BUY' ? 'success' : row.side === 'SELL' ? 'danger' : 'info'">
                  {{ signalSideLabel(row.side) }}
                </el-tag>
              </div>
              <p v-if="row.reason">{{ row.reason }}</p>
              <span>{{ formatDate(row.createdAt) }} · {{ signalStatusLabel(row.status) }} · 置信度 {{ formatPercent(row.confidence, false) }}</span>
            </article>
          </div>
          <el-empty v-else description="暂无量化建议" />
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Document, Star, TrendCharts, Wallet } from '@element-plus/icons-vue'
import { getQuantStatus, getStrategies, runQuantCycle } from '../api/analysis.js'
import { getBrokerAccountDetail, getBrokerAccounts, getTradeAccountState } from '../api/trade.js'
import { getConfig, getUserInfo, updateConfig } from '../api/user.js'
import { useOrderStream } from '../composables/useWebSocket.js'
import { useAdaptiveLayout } from '../composables/useAdaptiveLayout.js'
import MetricStrip from '../components/common/MetricStrip.vue'
import MobileSegmentControl from '../components/common/MobileSegmentControl.vue'
import PageHero from '../components/common/PageHero.vue'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'
import { formatCurrency as formatCurrencyValue, formatPercent as formatPercentValue } from '../utils/formatters.js'
import { formatReadModelSourceLabel } from '../utils/readModelSource.js'

const router = useRouter()
const { isPhoneLayout } = useAdaptiveLayout()
const activeProfileSection = ref('overview')

const userInfo = ref({})
const access = ref({})
const accounts = ref([])
const selectedAccount = ref(null)
const accountDetail = ref(null)
const accountState = ref(null)
const accountLoading = ref(false)
const accountError = ref('')
const strategies = ref([])
const activities = ref([])
const runningQuant = ref(false)
const pollTimer = ref(null)
const accountMeta = ref({
  dataSource: 'realtime',
  snapshotAt: '',
  sources: {},
  realtimeOverlay: [],
  defaultMode: 'realtime'
})

const quantStatus = ref({
  enabled: false,
  autoExecute: false,
  interval: 0,
  schedulerStatus: 'idle',
  signals: [],
  lastRunAt: ''
})

const quantForm = ref({
  ai_quant_trading_enabled: false,
  ai_quant_auto_execute: false,
  position_monitor_interval: 300,
  ai_quant_interval: 900,
  ai_quant_confidence_threshold: 72,
  ai_quant_max_buy_amount: 2000
})

const orderStreamStatus = ref('')
const {
  orders: streamedOrders,
  isConnected: orderStreamConnected,
  lastReceivedAt: orderStreamLastReceivedAt
} = useOrderStream(selectedAccount, orderStreamStatus, { limit: 20 })

const latestSignals = computed(() => {
  const signals = Array.isArray(quantStatus.value?.signals) ? quantStatus.value.signals : []
  return signals.slice(0, 5)
})

const latestOrders = computed(() => {
  const rows = Array.isArray(streamedOrders.value) && streamedOrders.value.length
    ? streamedOrders.value
    : Array.isArray(accountState.value?.orders)
      ? accountState.value.orders
      : []
  return rows.slice(0, 6)
})

const selectedAccountRecord = computed(() => accounts.value.find((item) => item.id === selectedAccount.value) || null)
const selectedAccountName = computed(() => selectedAccountRecord.value?.name || '未选择账户')
const summaryLabel = computed(() => selectedAccountName.value)
const defaultBrokerName = computed(() => {
  const target = accounts.value.find((item) => item.isDefault || item.is_default) || accounts.value[0]
  return target?.name || '未设置'
})
const roleLabel = computed(() => ({
  admin: '系统管理员',
  user: '普通用户',
  trader: '交易用户',
  analyst: '普通用户',
  viewer: '普通用户'
}[userInfo.value.roleCode || userInfo.value.role] || '平台用户'))
const quantSchedulerStatusLabel = computed(() => ({
  idle: '空闲',
  running: '运行中',
  success: '正常',
  failed: '失败',
  paused: '已暂停'
}[String(quantStatus.value?.schedulerStatus || 'idle').toLowerCase()] || '未知'))
const hasBoundAccount = computed(() => Boolean(quantStatus.value?.hasBoundAccount ?? accounts.value.length))
const canUseQuantTrading = computed(() => Boolean(quantStatus.value?.canUseQuantTrading))

const accountInfo = computed(() => accountState.value?.accountInfo || {})
const accountPositionRows = computed(() => Array.isArray(accountState.value?.positions) ? accountState.value.positions : [])
const accountOrderCount = computed(() => {
  if (Array.isArray(streamedOrders.value) && streamedOrders.value.length) {
    return streamedOrders.value.length
  }
  return Number(accountState.value?.orderCount || latestOrders.value.length || 0)
})

const accountPnlStats = computed(() => {
  const rows = accountPositionRows.value
  const totalPnl = rows.reduce((sum, item) => sum + Number(item.pnl ?? item.unrealized_pnl ?? 0), 0)
  const totalCost = rows.reduce((sum, item) => {
    const quantity = Number(item.quantity || 0)
    const avgPrice = Number(item.avgPrice ?? item.avg_price ?? item.average_cost ?? 0)
    return sum + quantity * avgPrice
  }, 0)
  return {
    totalPnl,
    totalPnlPercent: totalCost > 0 ? (totalPnl / totalCost) * 100 : 0
  }
})

const accountStats = computed(() => ({
  totalAssets: Number(accountInfo.value.total_equity ?? accountInfo.value.totalAssets ?? 0),
  cash: Number(accountInfo.value.cash || 0),
  marketValue: Number(accountInfo.value.market_value ?? accountInfo.value.marketValue ?? 0),
  buyingPower: Number(accountInfo.value.buying_power ?? accountInfo.value.buyingPower ?? accountInfo.value.cash ?? 0),
  todayPnl: Number(accountInfo.value.today_pnl ?? accountInfo.value.daily_pnl ?? accountPnlStats.value.totalPnl ?? 0),
  todayPnlPercent: Number(accountInfo.value.today_pnl_percent ?? accountInfo.value.pnl_ratio ?? accountPnlStats.value.totalPnlPercent ?? 0),
  orderCount: accountOrderCount.value,
  strategyCount: strategies.value.filter((item) => item.status === 'active').length
}))

const accountDataSourceLabel = computed(() => {
  const source = accountMeta.value?.sources?.account || 'broker'
  return formatReadModelSourceLabel(source)
})

const formattedUpdatedAt = computed(() => {
  const source = accountMeta.value.snapshotAt || orderStreamLastReceivedAt.value || ''
  return source ? formatDate(source) : ''
})

const isSimulationAccount = computed(() => {
  const fields = accountDetail.value?.credential_status?.fields || accountDetail.value?.config || {}
  if ((selectedAccountRecord.value?.brokerType || selectedAccountRecord.value?.broker_type) !== 'longbridge') {
    return false
  }
  return Boolean(fields.has_cli_auth)
})

const realtimeBadge = computed(() => {
  if (!selectedAccount.value) {
    return { text: '等待账户', type: 'warning' }
  }
  if (accountLoading.value && !accountState.value) {
    return { text: '连接中', type: 'info' }
  }
  if (accountError.value) {
    return { text: '读取失败', type: 'danger' }
  }
  return { text: orderStreamConnected.value ? '实时账户' : '实时账户 / 轮询更新', type: 'success' }
})

const simulationTag = computed(() => (
  isSimulationAccount.value
    ? { text: '模拟账户', type: 'success' }
    : { text: '未确认模拟账户', type: 'warning' }
))

const accountReadiness = computed(() => {
  if (!selectedAccount.value) {
    return {
      statusText: '等待账户接入',
      statusType: 'warning',
      updatedPrefix: '更新时间',
      tags: [{ type: 'warning', text: '未选择账户' }]
    }
  }

  const tags = [
    { type: 'info', text: `来源 ${accountDataSourceLabel.value}` },
    { type: 'info', text: orderStreamConnected.value ? '订单推送在线' : '订单轮询兜底' },
    { type: isSimulationAccount.value ? 'success' : 'warning', text: isSimulationAccount.value ? '长桥 CLI 模拟账户' : '模拟账户状态待确认' }
  ]

  if (accountError.value) {
    tags.push({ type: 'warning', text: '最近一次读取失败' })
  }

  return {
    statusText: accountError.value ? '实时账户异常' : '实时账户可用',
    statusType: accountError.value ? 'warning' : 'success',
    updatedPrefix: '更新时间',
    tags
  }
})

const accountStatusCards = computed(() => {
  const fields = accountDetail.value?.credential_status?.fields || accountDetail.value?.config || {}
  const rows = [
    {
      label: '数据来源',
      value: accountDataSourceLabel.value,
      note: orderStreamConnected.value ? '账户资产来自实时接口，订单数叠加订单流更新。' : '账户资产来自实时接口，当前未接到账户资产推送，使用轮询。',
      tone: ''
    },
    {
      label: '账户',
      value: selectedAccountName.value,
      note: accountDetail.value?.accountId ? `账户号 ${accountDetail.value.accountId}` : '未返回账户号',
      tone: ''
    },
    {
      label: '连接状态',
      value: accountError.value ? '读取失败' : accountLoading.value && !accountState.value ? '连接中' : '已连接',
      note: orderStreamConnected.value ? '订单长连接已建立。' : '未发现账户资产推送，保留订单流与轮询。',
      tone: accountError.value ? 'down' : 'up'
    },
    {
      label: '更新时间',
      value: formattedUpdatedAt.value || '等待首帧',
      note: accountMeta.value.snapshotAt ? '以后端返回时间为准。' : '等待 trade-service 返回首帧。',
      tone: ''
    },
    {
      label: '模拟账户',
      value: isSimulationAccount.value ? '是' : '未确认',
      note: isSimulationAccount.value
        ? `认证模式 ${fields.auth_mode || 'cli'}${fields.cli_account_channel ? ` · ${fields.cli_account_channel}` : ''}`
        : '当前只识别长桥 CLI 模拟账户标记。',
      tone: isSimulationAccount.value ? 'up' : ''
    },
    {
      label: '失败原因',
      value: accountError.value || '无',
      note: accountError.value ? '页面会继续轮询重试，不会触发真实交易。' : '最近一次刷新成功。',
      tone: accountError.value ? 'down' : ''
    }
  ]

  return rows
})

const profileHeroChips = computed(() => ([
  { text: roleLabel.value, tone: userInfo.value.roleCode === 'admin' ? 'warning' : 'info' },
  { text: realtimeBadge.value.text, tone: realtimeBadge.value.type },
  { text: simulationTag.value.text, tone: simulationTag.value.type },
  { text: orderStreamConnected.value ? '订单推送在线' : '轮询更新中', tone: orderStreamConnected.value ? 'success' : 'warning' }
]))

const profileHeroMetrics = computed(() => ([
  {
    label: '当前账户',
    value: summaryLabel.value,
    note: accounts.value.length ? `${accounts.value.length} 个账户已接入` : '尚未绑定券商账户'
  },
  {
    label: '账户状态',
    value: accountError.value ? '异常' : '在线',
    note: formattedUpdatedAt.value || '等待实时账户数据'
  },
  {
    label: '数据方式',
    value: orderStreamConnected.value ? '实时接口 + 订单流' : '实时接口 + 轮询',
    note: isSimulationAccount.value ? '已识别为模拟账户' : '模拟账户状态待确认'
  }
]))

const profileOverviewItems = computed(() => ([
  { label: '总资产', value: formatCurrency(accountStats.value.totalAssets), note: summaryLabel.value },
  {
    label: '今日盈亏',
    value: formatSignedCurrency(accountStats.value.todayPnl),
    note: formatPercent(accountStats.value.todayPnlPercent),
    tone: accountStats.value.todayPnl >= 0 ? 'healthy' : 'error'
  },
  { label: '订单数', value: String(accountStats.value.orderCount), note: orderStreamConnected.value ? '订单流已接入' : '实时接口 / 轮询' },
  { label: '启用规则', value: String(accountStats.value.strategyCount), note: '当前处于 active 的策略数量' }
]))

const profileMobileSections = computed(() => ([
  { value: 'overview', label: '概览', note: realtimeBadge.value.text },
  { value: 'broker', label: '券商', note: `${accounts.value.length} 个` },
  { value: 'quant', label: '量化', note: quantStatus.value.enabled ? '已启用' : '未启用' }
]))

const coerceBoolean = (value) => value === true || value === 'true' || value === 1 || value === '1'
const coerceNumber = (value, fallback = 0) => {
  const amount = Number(value)
  return Number.isFinite(amount) ? amount : fallback
}

const loadUserInfo = async () => {
  try {
    const res = await getUserInfo()
    const payload = res?.data || {}
    userInfo.value = payload.user || payload || {}
    access.value = payload.access || {}
  } catch (error) {
    console.error('加载用户信息失败:', error)
  }
}

const loadAccounts = async () => {
  try {
    const res = await getBrokerAccounts()
    accounts.value = res.data || []
    if (accounts.value.length > 0 && !selectedAccount.value) {
      const longbridgeDefault = accounts.value.find((account) => (account.brokerType || account.broker_type) === 'longbridge' && (account.isDefault || account.is_default))
      const longbridgeAccount = accounts.value.find((account) => (account.brokerType || account.broker_type) === 'longbridge')
      const defaultAccount = accounts.value.find((account) => account.isDefault || account.is_default)
      selectedAccount.value = longbridgeDefault?.id || longbridgeAccount?.id || defaultAccount?.id || accounts.value[0].id
    }
  } catch (error) {
    console.error('加载账户失败:', error)
    accounts.value = []
  }
}

const buildActivities = () => {
  const orderActivities = latestOrders.value.map((order, index) => ({
    id: `order-${index}-${order.orderId || order.symbol || index}`,
    time: order.updateTime || order.createTime || accountMeta.value.snapshotAt,
    type: order.action === 'buy' ? 'success' : order.action === 'sell' ? 'warning' : 'info',
    content: `${signalSideLabel(order.action || '').replace('观望', '订单')} ${order.symbol || '未知标的'} ${order.quantity || 0} 股，状态 ${order.status || '未知'}`
  }))

  const quantActivities = latestSignals.value.map((signal, index) => ({
    id: `signal-${index}-${signal.symbol}-${signal.createdAt}`,
    time: signal.createdAt,
    type: signal.side === 'BUY' ? 'success' : signal.side === 'SELL' ? 'danger' : 'info',
    content: `量化建议 ${signalSideLabel(signal.side)} ${signal.symbol}，置信度 ${signal.confidence || 0}%`
  }))

  const accountActivity = accountMeta.value.snapshotAt
    ? [{
        id: `account-${selectedAccount.value}-${accountMeta.value.snapshotAt}`,
        time: accountMeta.value.snapshotAt,
        type: accountError.value ? 'warning' : 'success',
        content: `${accountError.value ? '账户刷新异常后重试' : '实时账户已更新'}，总资产 ${formatCurrency(accountStats.value.totalAssets)}`
      }]
    : []

  activities.value = [...accountActivity, ...quantActivities, ...orderActivities]
    .filter((item) => item.time)
    .sort((a, b) => new Date(b.time || 0).getTime() - new Date(a.time || 0).getTime())
    .slice(0, 8)
}

const loadAccountDetail = async () => {
  if (!selectedAccount.value) {
    accountDetail.value = null
    return
  }
  try {
    const res = await getBrokerAccountDetail(selectedAccount.value)
    accountDetail.value = res?.data || null
  } catch (error) {
    console.error('加载账户详情失败:', error)
    accountDetail.value = null
  }
}

const loadAccountState = async ({ silent = false } = {}) => {
  if (!selectedAccount.value) {
    accountState.value = null
    accountMeta.value = { dataSource: 'realtime', snapshotAt: '', sources: {}, realtimeOverlay: [], defaultMode: 'realtime' }
    accountError.value = ''
    activities.value = []
    return
  }

  if (!silent) {
    accountLoading.value = true
  }

  try {
    const res = await getTradeAccountState(selectedAccount.value, { limit: 20 })
    accountState.value = res?.data || null
    const meta = res?.data?.meta && typeof res.data.meta === 'object' ? res.data.meta : {}
    accountMeta.value = {
      dataSource: meta.dataSource || res?.data?.dataSource || 'live',
      snapshotAt: res?.data?.snapshotAt || meta.snapshotAt || '',
      sources: meta.sources || {},
      realtimeOverlay: Array.isArray(meta.realtimeOverlay) ? meta.realtimeOverlay : ['broker'],
      defaultMode: meta.defaultMode || 'realtime'
    }
    accountError.value = ''
  } catch (error) {
    console.error('加载实时账户失败:', error)
    accountError.value = error?.response?.data?.detail || error?.data?.error || error?.message || '实时账户读取失败'
  } finally {
    accountLoading.value = false
    buildActivities()
  }
}

const loadQuantConfig = async () => {
  try {
    const [configRes, statusRes, strategiesRes] = await Promise.all([getConfig(), getQuantStatus(), getStrategies()])
    const config = configRes?.data || {}
    quantStatus.value = statusRes?.data || quantStatus.value
    strategies.value = Array.isArray(strategiesRes?.data) ? strategiesRes.data : []
    quantForm.value = {
      ai_quant_trading_enabled: coerceBoolean(config.ai_quant_trading_enabled ?? quantStatus.value.enabled),
      ai_quant_auto_execute: coerceBoolean(config.ai_quant_auto_execute ?? quantStatus.value.autoExecute),
      position_monitor_interval: coerceNumber(config.position_monitor_interval, 300),
      ai_quant_interval: coerceNumber(config.ai_quant_interval ?? quantStatus.value.interval, 900),
      ai_quant_confidence_threshold: coerceNumber(config.ai_quant_confidence_threshold, 72),
      ai_quant_max_buy_amount: coerceNumber(config.ai_quant_max_buy_amount, 2000)
    }
  } catch (error) {
    console.error('加载量化配置失败:', error)
  }
}

const startPolling = () => {
  stopPolling()
  pollTimer.value = window.setInterval(() => {
    loadAccountState({ silent: true })
  }, 15000)
}

const stopPolling = () => {
  if (pollTimer.value) {
    window.clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

const refreshAccountPanel = async () => {
  await Promise.all([
    loadAccountDetail(),
    loadAccountState()
  ])
}

const saveQuantConfig = async () => {
  if (!canUseQuantTrading.value) {
    ElMessage.warning('当前用户未开通量化交易 API，或尚未绑定可用券商账户')
    return
  }
  try {
    await updateConfig({
      configs: {
        ai_quant_trading_enabled: quantForm.value.ai_quant_trading_enabled,
        ai_quant_auto_execute: quantForm.value.ai_quant_auto_execute,
        position_monitor_interval: quantForm.value.position_monitor_interval,
        ai_quant_interval: quantForm.value.ai_quant_interval,
        ai_quant_confidence_threshold: quantForm.value.ai_quant_confidence_threshold,
        ai_quant_max_buy_amount: quantForm.value.ai_quant_max_buy_amount
      }
    })
    ElMessage.success('量化配置已保存')
    await loadQuantConfig()
  } catch (error) {
    ElMessage.error('保存量化配置失败: ' + (error.message || '未知错误'))
  }
}

const runQuantNow = async () => {
  if (!canUseQuantTrading.value) {
    ElMessage.warning('当前用户未开通量化交易 API，或尚未绑定可用券商账户')
    return
  }
  runningQuant.value = true
  try {
    const res = await runQuantCycle({
      account_id: selectedAccount.value,
      execute: quantForm.value.ai_quant_auto_execute
    })
    const signalCount = Array.isArray(res?.data?.signals) ? res.data.signals.length : 0
    ElMessage.success(signalCount > 0 ? `本轮生成 ${signalCount} 条量化建议` : '本轮未生成新建议')
    await Promise.all([loadQuantConfig(), loadAccountState({ silent: true })])
  } catch (error) {
    ElMessage.error('量化分析失败: ' + (error.message || '未知错误'))
  } finally {
    runningQuant.value = false
  }
}

const openBrokerManagement = () => {
  router.push({ name: 'BrokerManagement' })
}

const formatCurrency = (value) => formatCurrencyValue(value, { currency: '$' })
const formatSignedCurrency = (value) => {
  const amount = Number(value) || 0
  return `${amount >= 0 ? '+' : '-'}${formatCurrencyValue(Math.abs(amount), { currency: '$' })}`
}
const formatPercent = (value, signed = true) => formatPercentValue(value, { signed })
const signalSideLabel = (side) => ({
  BUY: '买入',
  SELL: '卖出',
  HOLD: '观望',
  buy: '买入',
  sell: '卖出'
}[String(side || 'HOLD')] || ({ BUY: '买入', SELL: '卖出', HOLD: '观望' }[String(side || 'HOLD').toUpperCase()] || '观望'))
const signalStatusLabel = (status) => ({
  pending: '待处理',
  queued: '排队中',
  executed: '已执行',
  skipped: '已跳过',
  failed: '失败',
  success: '成功'
}[String(status || '').toLowerCase()] || '待处理')

const formatDate = (date) => {
  if (!date) {
    return '-'
  }
  const target = new Date(date)
  if (Number.isNaN(target.getTime())) {
    return String(date)
  }
  return target.toLocaleString('zh-CN')
}

watch(selectedAccount, async (value, oldValue) => {
  if (!value || value === oldValue) {
    return
  }
  await refreshAccountPanel()
})

watch([latestSignals, latestOrders, orderStreamConnected], () => {
  buildActivities()
})

onMounted(async () => {
  await Promise.all([loadUserInfo(), loadAccounts(), loadQuantConfig()])
  await refreshAccountPanel()
  startPolling()
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped lang="scss">
.profile-page {
  display: grid;
  gap: 16px;
  padding: 18px;
}

.hero-actions,
.card-actions,
.quant-actions,
.broker-account-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.profile-account-select {
  width: 240px;
  max-width: 100%;
}

.profile-container {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.9fr);
  gap: 16px;
  align-items: start;
}

.profile-main-column,
.profile-side-column {
  display: grid;
  gap: 16px;
}

.mobile-profile-rail {
  display: none;
}

.glass-card {
  background: var(--panel-surface);
  border: 1px solid var(--border-soft);
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.compact-card {
  :deep(.el-card__body) {
    padding-top: 16px;
  }
}

.account-stats-grid {
  margin-top: 16px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.stat-item,
.status-item,
.status-card {
  min-width: 0;
  border-radius: 18px;
  border: 1px solid var(--border-soft);
  background: color-mix(in srgb, var(--surface-soft) 90%, transparent);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
}

.stat-item.emphasis {
  background: linear-gradient(135deg, color-mix(in srgb, var(--surface-soft) 80%, #4f8cff 20%), color-mix(in srgb, var(--panel-surface) 92%, transparent));
}

.stat-icon {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex: 0 0 auto;
}

.stat-icon.blue {
  background: linear-gradient(135deg, #58b0ff, #2b67ff);
}

.stat-icon.green {
  background: linear-gradient(135deg, #39d79d, #10996f);
}

.stat-icon.amber {
  background: linear-gradient(135deg, #f7c25d, #ee8e22);
}

.stat-icon.rose {
  background: linear-gradient(135deg, #ff8989, #d54780);
}

.stat-info {
  min-width: 0;
}

.stat-label,
.status-label,
.status-item .label {
  color: var(--text-muted);
  font-size: 12px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  word-break: break-word;
}

.stat-note {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 12px;
}

.status-panel {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.status-card {
  padding: 14px 16px;
}

.status-card strong,
.status-item strong {
  display: block;
  margin-top: 8px;
  color: var(--text-primary);
  font-size: 17px;
  line-height: 1.4;
  word-break: break-word;
}

.status-card p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.status-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 14px 16px;
}

.status-item.slim strong {
  font-size: 16px;
}

.profile-alert {
  margin-top: 16px;
}

.broker-summary-grid,
.broker-account-list,
.mobile-signal-list {
  display: grid;
  gap: 12px;
}

.broker-summary-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.broker-account-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: var(--surface-soft);
  border: 1px solid var(--border-soft);
  border-radius: 18px;
}

.broker-account-name,
.mobile-signal-card strong {
  color: var(--text-primary);
  font-weight: 600;
}

.broker-account-meta,
.mobile-signal-card p,
.mobile-signal-card span {
  color: var(--text-secondary);
  font-size: 12px;
}

.broker-account-meta {
  margin-top: 4px;
}

.broker-actions {
  margin-top: 16px;
}

.quant-alert {
  margin-bottom: 16px;
}

.mobile-signal-card {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
}

.mobile-signal-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.mobile-signal-card p {
  margin: 0;
  line-height: 1.6;
}

.mobile-signal-card span {
  display: block;
  margin-top: 8px;
}

.profile-page :deep(.el-timeline) {
  padding-left: 18px;
}

.profile-page :deep(.el-timeline-item) {
  padding-bottom: 12px;
}

.profile-page :deep(.el-timeline-item__content) {
  color: var(--text-primary) !important;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.55;
}

.profile-page :deep(.el-timeline-item__timestamp) {
  color: var(--text-secondary) !important;
  font-size: 12px;
}

.profile-page :deep(.el-timeline-item__tail) {
  border-left-color: color-mix(in srgb, var(--text-secondary) 50%, transparent) !important;
}

.up {
  color: var(--success);
}

.down {
  color: var(--danger);
}

@media (max-width: 1180px) {
  .profile-container {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .profile-page {
    padding: 10px;
  }

  .mobile-profile-rail {
    display: block;
  }

  .hero-actions,
  .profile-account-select,
  .stats-grid,
  .status-panel,
  .status-grid,
  .broker-summary-grid {
    width: 100%;
  }

  .stats-grid,
  .status-panel,
  .status-grid,
  .broker-summary-grid {
    grid-template-columns: 1fr;
  }

  .broker-account-item {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>

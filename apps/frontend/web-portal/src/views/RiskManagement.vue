<template>
  <div class="risk-page">
    <PageHero
      class="risk-hero"
      title="风控管理"
      :chips="riskHeroChips"
      :metrics="riskHeroMetrics"
    >
      <template #actions>
        <div class="page-actions">
          <el-button :loading="overviewRefreshing" @click="refreshOverview">
            实时刷新
          </el-button>
          <el-button type="primary" :icon="Setting" @click="showConfigDialog">
            风控设置
          </el-button>
        </div>
      </template>
    </PageHero>

    <ReadModelSourceStrip
      class="risk-source-strip"
      label="风控状态"
      :status-text="riskReadModelStatus"
      :status-type="riskReadModelStatusType"
      :updated-at="riskReadModelUpdatedAt"
      :updated-prefix="riskReadModelUpdatedPrefix"
      :tags="riskReadModelTags"
    />

    <MetricStrip class="risk-overview-strip" :items="riskOverviewItems" />

    <div class="risk-container">
      <!-- 左侧：风险事件 -->
      <div class="risk-events">
        <el-card>
          <template #header>
            <SectionCardHeader
              title="风险事件"
              :badge="`${filteredEvents.length} 条`"
              badge-type="warning"
            >
              <template #actions>
                <el-radio-group v-model="eventFilter" size="small">
                  <el-radio-button value="">全部</el-radio-button>
                  <el-radio-button value="high">高风险</el-radio-button>
                  <el-radio-button value="medium">中风险</el-radio-button>
                </el-radio-group>
              </template>
            </SectionCardHeader>
          </template>
          <el-timeline>
            <el-timeline-item
              v-for="event in filteredEvents"
              :key="event.id"
              :type="getEventType(event.level)"
              :timestamp="formatDate(event.timestamp)"
            >
              <div class="event-item">
                <div class="event-header">
                  <el-tag :type="getEventType(event.level)" size="small">
                    {{ event.level }}
                  </el-tag>
                  <span class="event-type">{{ event.type }}</span>
                </div>
                <div class="event-message">{{ event.message }}</div>
                <div class="event-symbol" v-if="event.symbol">{{ event.symbol }}</div>
              </div>
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </div>

      <!-- 右侧：止损止盈订单 -->
      <div class="risk-orders">
        <el-card>
          <template #header>
            <SectionCardHeader
              title="止损止盈"
              :badge="`${displayStopLossOrders.length + displayTakeProfitOrders.length} 条`"
            >
              <template #actions>
                <el-button type="primary" link @click="showAddOrderDialog">
                  <el-icon><Plus /></el-icon> 添加
                </el-button>
              </template>
            </SectionCardHeader>
          </template>
          
          <!-- 止损订单 -->
          <div class="order-section">
            <h4>止损订单</h4>
            <el-table :data="displayStopLossOrders" style="width: 100%">
              <el-table-column prop="symbol" label="股票" width="100" />
              <el-table-column prop="stopPrice" label="止损价" width="100">
                <template #default="{ row }">
                  {{ formatCurrency(row.stopPrice) }}
                </template>
              </el-table-column>
              <el-table-column prop="currentPrice" label="当前价" width="100">
                <template #default="{ row }">
                  {{ formatCurrency(row.currentPrice) }}
                </template>
              </el-table-column>
              <el-table-column prop="distance" label="距离" width="100">
                <template #default="{ row }">
                  <span :class="getDistanceClass(row.distance)">
                    {{ formatPercent(row.distance) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-button type="danger" link size="small" @click="cancelStopLoss(row)">
                    取消
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 止盈订单 -->
          <div class="order-section" style="margin-top: 20px">
            <h4>止盈订单</h4>
            <el-table :data="displayTakeProfitOrders" style="width: 100%">
              <el-table-column prop="symbol" label="股票" width="100" />
              <el-table-column prop="profitPrice" label="止盈价" width="100">
                <template #default="{ row }">
                  {{ formatCurrency(row.profitPrice) }}
                </template>
              </el-table-column>
              <el-table-column prop="currentPrice" label="当前价" width="100">
                <template #default="{ row }">
                  {{ formatCurrency(row.currentPrice) }}
                </template>
              </el-table-column>
              <el-table-column prop="distance" label="距离" width="100">
                <template #default="{ row }">
                  <span :class="getDistanceClass(row.distance)">
                    {{ formatPercent(row.distance) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-button type="danger" link size="small" @click="cancelTakeProfit(row)">
                    取消
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </div>
    </div>

    <!-- 风控设置对话框 -->
    <el-dialog v-model="configDialogVisible" title="风控设置" width="500px">
      <el-form :model="riskConfig" label-width="150px">
        <el-form-item label="最大仓位比例">
          <el-slider v-model="riskConfig.maxPositionSize" :max="100" show-input />
        </el-form-item>
        <el-form-item label="最大单笔亏损">
          <el-input-number v-model="riskConfig.maxLossPerTrade" :min="0" :step="100" style="width: 100%" />
        </el-form-item>
        <el-form-item label="日最大亏损">
          <el-input-number v-model="riskConfig.maxDailyLoss" :min="0" :step="1000" style="width: 100%" />
        </el-form-item>
        <el-form-item label="最大回撤">
          <el-slider v-model="riskConfig.maxDrawdown" :max="50" show-input />
        </el-form-item>
        <el-form-item label="波动率限制">
          <el-slider v-model="riskConfig.volatilityLimit" :max="100" show-input />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveConfig">保存</el-button>
      </template>
    </el-dialog>

    <!-- 添加订单对话框 -->
    <el-dialog v-model="addOrderDialogVisible" title="添加止损止盈" width="400px">
      <el-form :model="orderForm" label-width="100px">
        <el-form-item label="股票代码">
          <el-input v-model="orderForm.symbol" placeholder="输入股票代码" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="orderForm.type">
            <el-radio-button value="stop_loss">止损</el-radio-button>
            <el-radio-button value="take_profit">止盈</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="触发价格">
          <el-input-number v-model="orderForm.price" :precision="2" :step="0.01" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addOrderDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAddOrder">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting, Plus } from '@element-plus/icons-vue'
import { useStockQuotes } from '../composables/useWebSocket.js'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import MetricStrip from '../components/common/MetricStrip.vue'
import PageHero from '../components/common/PageHero.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'
import { 
  getRiskOverview, getRiskOverviewSnapshot, getRiskLimits, updateRiskLimits,
  setStopLoss, setTakeProfit, cancelStopLoss as apiCancelStopLoss, cancelTakeProfit as apiCancelTakeProfit 
} from '../api/risk.js'
import { getTradeSnapshotState } from '../api/trade.js'
import { getCurrentUser } from '../utils/auth.js'
import { buildRiskReadModelSummary } from '../utils/readModelSource.js'

const currentUser = getCurrentUser() || {}

const overview = ref({
  score: 0,
  scoreLabel: '--',
  scoreDescription: '',
  maxWeight: 0,
  positionLimit: 0,
  drawdown: 0,
  drawdownLimit: 0,
  protectionCount: 0,
  stopLossCount: 0,
  takeProfitCount: 0
})
const riskEvents = ref([])
const stopLossOrders = ref([])
const takeProfitOrders = ref([])
const positionRows = ref([])
const riskSnapshotAt = ref('')
const riskOverviewSource = ref('snapshot')
const riskMeta = ref({
  dataSource: 'snapshot',
  snapshotAt: '',
  sources: {},
  realtimeOverlay: [],
  positionSnapshotAt: '',
  eventCount: 0,
  stopLossCount: 0,
  takeProfitCount: 0
})
const tradeSnapshotMeta = ref({
  snapshotAt: '',
  dataSource: 'snapshot',
  sources: {},
  realtimeOverlay: []
})
const eventFilter = ref('')
const configDialogVisible = ref(false)
const addOrderDialogVisible = ref(false)
const overviewRefreshing = ref(false)

const riskConfig = ref({
  maxPositionSize: 35,
  maxLossPerTrade: 1000,
  maxDailyLoss: 5000,
  maxDrawdown: 20,
  volatilityLimit: 50
})

const orderForm = ref({
  symbol: '',
  type: 'stop_loss',
  price: 0
})

const streamSymbols = computed(() => {
  const symbols = [
    ...stopLossOrders.value.map((item) => item.symbol),
    ...takeProfitOrders.value.map((item) => item.symbol),
    ...positionRows.value.map((item) => item.symbol)
  ]
  return Array.from(new Set(symbols.map((item) => String(item || '').toUpperCase()).filter(Boolean)))
})

const { quotes: liveQuoteMap, isConnected: quotesConnected } = useStockQuotes(streamSymbols, {
  userId: currentUser?.id || null
})

const effectiveOverview = computed(() => {
  const rows = Array.isArray(positionRows.value) ? positionRows.value : []
  if (!rows.length) {
    return overview.value
  }

  const marketValues = rows.map((item) => {
    const symbol = String(item.symbol || '').toUpperCase()
    const quote = liveQuoteMap.value[symbol] || {}
    const quantity = Number(item.quantity || 0)
    const currentPrice = Number(quote.last_price ?? quote.price ?? item.currentPrice ?? item.current_price ?? 0)
    return currentPrice * quantity
  })
  const totalMarketValue = marketValues.reduce((sum, value) => sum + Number(value || 0), 0)
  if (!totalMarketValue) {
    return overview.value
  }

  const maxWeight = marketValues.reduce((max, value) => Math.max(max, (Number(value || 0) / totalMarketValue) * 100), 0)
  return {
    ...overview.value,
    maxWeight
  }
})

const displayStopLossOrders = computed(() => stopLossOrders.value.map((row) => enrichRiskOrder(row, 'stop_loss')))
const displayTakeProfitOrders = computed(() => takeProfitOrders.value.map((row) => enrichRiskOrder(row, 'take_profit')))
const riskReadModelSummary = computed(() => buildRiskReadModelSummary({
  overviewSource: riskOverviewSource.value,
  riskMeta: riskMeta.value,
  tradeMeta: tradeSnapshotMeta.value,
  quotesConnected: quotesConnected.value,
  streamSymbolCount: streamSymbols.value.length,
  eventCount: Number(riskMeta.value.eventCount || riskEvents.value.length)
}))
const riskReadModelDetail = computed(() => riskReadModelSummary.value.detail)
const riskReadModelStatus = computed(() => riskReadModelSummary.value.statusText)
const riskReadModelStatusType = computed(() => riskReadModelSummary.value.statusType)
const riskReadModelUpdatedAt = computed(() => (
  riskReadModelSummary.value.updatedAt ? formatDate(riskReadModelSummary.value.updatedAt) : ''
))
const riskReadModelUpdatedPrefix = computed(() => riskReadModelSummary.value.updatedPrefix)
const riskReadModelTags = computed(() => riskReadModelSummary.value.tags || [])
const resolveRiskScoreTone = (score) => {
  const amount = Number(score || 0)
  if (amount >= 75) return 'error'
  if (amount >= 50) return 'warning'
  return 'healthy'
}
const resolveRiskLimitTone = (current, limit) => {
  if (Number(current || 0) <= Number(limit || 0)) return 'healthy'
  return 'error'
}
const riskHeroChips = computed(() => ([
  {
    text: riskOverviewSource.value === 'realtime'
      ? '实时总览'
      : riskSnapshotAt.value
        ? `快照 ${formatDate(riskSnapshotAt.value)}`
        : '风控快照',
    tone: riskOverviewSource.value === 'realtime' ? 'healthy' : 'info'
  },
  {
    text: quotesConnected.value ? '行情在线' : '等待行情',
    tone: quotesConnected.value ? 'healthy' : 'info'
  },
  {
    text: riskReadModelStatus.value,
    tone: riskReadModelStatusType.value === 'success' ? 'healthy' : riskReadModelStatusType.value || 'info'
  }
]))
const riskHeroMetrics = computed(() => ([
  {
    label: '风险评分',
    value: Number(effectiveOverview.value.score || 0).toFixed(0),
    note: effectiveOverview.value.scoreLabel || '--',
    tone: resolveRiskScoreTone(effectiveOverview.value.score)
  },
  {
    label: '最大仓位',
    value: formatPercent(effectiveOverview.value.maxWeight, false),
    note: `上限 ${formatPercent(effectiveOverview.value.positionLimit, false)}`,
    tone: resolveRiskLimitTone(effectiveOverview.value.maxWeight, effectiveOverview.value.positionLimit)
  },
  {
    label: '事件数量',
    value: String(filteredEvents.value.length),
    note: '当前筛选结果'
  }
]))
const riskOverviewItems = computed(() => ([
  {
    label: '风险评分',
    value: Number(effectiveOverview.value.score || 0).toFixed(0),
    note: `${effectiveOverview.value.scoreLabel || '--'} · ${effectiveOverview.value.scoreDescription || '暂无描述'}`,
    tone: resolveRiskScoreTone(effectiveOverview.value.score)
  },
  {
    label: '仓位安全',
    value: Number(effectiveOverview.value.maxWeight || 0) <= Number(effectiveOverview.value.positionLimit || 0) ? '安全' : '偏高',
    note: `最大仓位 ${formatPercent(effectiveOverview.value.maxWeight, false)} / 上限 ${formatPercent(effectiveOverview.value.positionLimit, false)}`,
    tone: resolveRiskLimitTone(effectiveOverview.value.maxWeight, effectiveOverview.value.positionLimit)
  },
  {
    label: '回撤控制',
    value: formatPercent(effectiveOverview.value.drawdown, false),
    note: `控制线 ${formatPercent(effectiveOverview.value.drawdownLimit, false)}`,
    tone: resolveRiskLimitTone(effectiveOverview.value.drawdown, effectiveOverview.value.drawdownLimit)
  },
  {
    label: '止损保护',
    value: String(effectiveOverview.value.protectionCount || 0),
    note: `止损 ${effectiveOverview.value.stopLossCount || 0} / 止盈 ${effectiveOverview.value.takeProfitCount || 0}`,
    tone: Number(effectiveOverview.value.protectionCount || 0) > 0 ? 'info' : 'warning'
  }
]))

const filteredEvents = computed(() => {
  if (!eventFilter.value) return riskEvents.value
  return riskEvents.value.filter((e) => e.level === eventFilter.value)
})

const normalizeRiskOrder = (row = {}, type = 'stop_loss') => {
  const triggerField = type === 'take_profit' ? 'profitPrice' : 'stopPrice'
  return {
    ...row,
    symbol: String(row.symbol || '').toUpperCase(),
    [triggerField]: Number(row[triggerField] ?? row[type === 'take_profit' ? 'profit_price' : 'stop_price'] ?? row.price ?? 0),
    currentPrice: Number(row.currentPrice ?? row.current_price ?? 0),
    distance: Number(row.distance ?? 0)
  }
}

const enrichRiskOrder = (row = {}, type = 'stop_loss') => {
  const normalized = normalizeRiskOrder(row, type)
  const quote = liveQuoteMap.value[normalized.symbol] || {}
  const currentPrice = Number(quote.last_price ?? quote.price ?? normalized.currentPrice ?? 0)
  const triggerPrice = type === 'take_profit' ? Number(normalized.profitPrice || 0) : Number(normalized.stopPrice || 0)
  const distance = currentPrice > 0
    ? (type === 'take_profit'
      ? ((triggerPrice - currentPrice) / currentPrice) * 100
      : ((currentPrice - triggerPrice) / currentPrice) * 100)
    : Number(normalized.distance || 0)

  return {
    ...normalized,
    currentPrice,
    distance
  }
}

const loadOverview = async (forceRealtime = false) => {
  overviewRefreshing.value = true
  try {
    const [snapshotRes, limitsRes, tradeSnapshotRes] = await Promise.allSettled([
      forceRealtime ? Promise.resolve({ data: {} }) : getRiskOverviewSnapshot(),
      getRiskLimits(),
      getTradeSnapshotState()
    ])

    let payload = snapshotRes.status === 'fulfilled' ? snapshotRes.value?.data || {} : {}
    const hasSnapshotPayload = Boolean(
      (payload?.overview && Object.keys(payload.overview).length) ||
      (Array.isArray(payload?.events) && payload.events.length) ||
      (Array.isArray(payload?.stopLossOrders) && payload.stopLossOrders.length) ||
      (Array.isArray(payload?.takeProfitOrders) && payload.takeProfitOrders.length) ||
      payload?.snapshotAt
    )

    if (forceRealtime || !hasSnapshotPayload) {
      const liveOverviewRes = await getRiskOverview()
      payload = liveOverviewRes?.data || payload
    }

    overview.value = payload.overview || overview.value
    riskEvents.value = Array.isArray(payload.events) ? payload.events : []
    stopLossOrders.value = Array.isArray(payload.stopLossOrders) ? payload.stopLossOrders.map((item) => normalizeRiskOrder(item, 'stop_loss')) : []
    takeProfitOrders.value = Array.isArray(payload.takeProfitOrders) ? payload.takeProfitOrders.map((item) => normalizeRiskOrder(item, 'take_profit')) : []
    riskSnapshotAt.value = payload.snapshotAt || ''
    riskMeta.value = payload?.meta && typeof payload.meta === 'object'
      ? {
          dataSource: payload.meta.dataSource || payload.dataSource || 'snapshot',
          snapshotAt: payload.meta.snapshotAt || payload.snapshotAt || '',
          sources: payload.meta.sources || {},
          realtimeOverlay: Array.isArray(payload.meta.realtimeOverlay) ? payload.meta.realtimeOverlay : [],
          positionSnapshotAt: payload.meta.positionSnapshotAt || '',
          eventCount: Number(payload.meta.eventCount || riskEvents.value.length),
          stopLossCount: Number(payload.meta.stopLossCount || stopLossOrders.value.length),
          takeProfitCount: Number(payload.meta.takeProfitCount || takeProfitOrders.value.length)
        }
      : {
          dataSource: payload.dataSource || (forceRealtime ? 'live' : 'snapshot'),
          snapshotAt: payload.snapshotAt || '',
          sources: {},
          realtimeOverlay: [],
          positionSnapshotAt: '',
          eventCount: riskEvents.value.length,
          stopLossCount: stopLossOrders.value.length,
          takeProfitCount: takeProfitOrders.value.length
        }
    riskOverviewSource.value = String(riskMeta.value.dataSource || '').includes('live') ? 'realtime' : 'snapshot'
    positionRows.value = tradeSnapshotRes.status === 'fulfilled' && Array.isArray(tradeSnapshotRes.value?.data?.positions)
      ? tradeSnapshotRes.value.data.positions
      : []
    tradeSnapshotMeta.value = tradeSnapshotRes.status === 'fulfilled'
      ? {
          snapshotAt: tradeSnapshotRes.value?.data?.snapshotAt || '',
          dataSource: tradeSnapshotRes.value?.data?.dataSource || 'snapshot',
          ...(tradeSnapshotRes.value?.data?.meta && typeof tradeSnapshotRes.value.data.meta === 'object'
            ? tradeSnapshotRes.value.data.meta
            : {})
        }
      : {
          snapshotAt: '',
          dataSource: 'snapshot',
          sources: {},
          realtimeOverlay: []
        }
    riskConfig.value = {
      ...riskConfig.value,
      ...(limitsRes.status === 'fulfilled' ? limitsRes.value?.data || {} : {}),
      ...(payload.config || {})
    }
  } catch (error) {
    console.error('加载风控总览失败:', error)
    ElMessage.error('加载风控数据失败')
  } finally {
    overviewRefreshing.value = false
  }
}

const refreshOverview = async () => {
  await loadOverview(true)
}

const showConfigDialog = () => {
  configDialogVisible.value = true
}

const saveConfig = async () => {
  try {
    await updateRiskLimits(riskConfig.value)
    ElMessage.success('风控设置已保存')
    configDialogVisible.value = false
    await loadOverview()
  } catch (error) {
    ElMessage.error('保存失败: ' + error.message)
  }
}

const showAddOrderDialog = () => {
  orderForm.value = { symbol: '', type: 'stop_loss', price: 0 }
  addOrderDialogVisible.value = true
}

const confirmAddOrder = async () => {
  try {
    if (orderForm.value.type === 'stop_loss') {
      await setStopLoss(orderForm.value)
    } else {
      await setTakeProfit(orderForm.value)
    }
    ElMessage.success('添加成功')
    addOrderDialogVisible.value = false
    await loadOverview()
  } catch (error) {
    ElMessage.error('添加失败: ' + error.message)
  }
}

const cancelStopLoss = async (row) => {
  try {
    await apiCancelStopLoss(row.id)
    ElMessage.success('已取消')
    await loadOverview()
  } catch (error) {
    ElMessage.error('取消失败: ' + error.message)
  }
}

const cancelTakeProfit = async (row) => {
  try {
    await apiCancelTakeProfit(row.id)
    ElMessage.success('已取消')
    await loadOverview()
  } catch (error) {
    ElMessage.error('取消失败: ' + error.message)
  }
}

const getEventType = (level) => {
  const types = { high: 'danger', medium: 'warning', low: 'info' }
  return types[level] || 'info'
}

const getDistanceClass = (distance) => {
  if (distance > 10) return 'safe'
  if (distance > 5) return 'warning'
  return 'danger'
}

const formatCurrency = (value) => {
  if (!value) return '$0.00'
  return '$' + parseFloat(value).toFixed(2)
}

const formatPercent = (value, signed = true) => {
  if (value === undefined || value === null) return '-'
  const amount = Number(value || 0)
  const prefix = signed && amount >= 0 ? '+' : ''
  return `${prefix}${amount.toFixed(2)}%`
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString('zh-CN')
}

onMounted(loadOverview)
</script>

<style scoped lang="scss">
.risk-page {
  padding: 20px;
}

.risk-hero {
  margin-bottom: 20px;
}

.risk-hero-aside {
  display: grid;
  gap: 6px;
  min-width: min(100%, 280px);
  padding: 16px 18px;
  border-radius: 22px;
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-soft) 84%, transparent);
}

.risk-hero-aside span,
.risk-hero-aside small {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.risk-hero-aside strong {
  color: var(--text-emphasis);
  font-size: 18px;
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.risk-source-strip {
  margin-bottom: 20px;
}

.risk-overview-strip {
  margin-bottom: 20px;
}

.risk-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.event-item {
  .event-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    
    .event-type {
      font-weight: 600;
      color: var(--text-primary);
    }
  }
  
  .event-message {
    color: var(--text-secondary);
    font-size: 14px;
    margin-bottom: 4px;
  }
  
  .event-symbol {
    font-size: 12px;
    color: var(--text-secondary);
  }
}

.order-section {
  h4 {
    margin: 0 0 12px 0;
    font-size: 14px;
    color: var(--text-primary);
  }
}

.safe {
  color: #67c23a;
}

.warning {
  color: #e6a23c;
}

.danger {
  color: #f56c6c;
}
</style>

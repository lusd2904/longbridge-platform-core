<template>
  <div class="positions-page">
    <PageHero
      title="持仓管理"
      :chips="positionsHeroChips"
      :metrics="positionsHeroMetrics"
    >
      <template #actions>
        <div class="positions-hero-actions">
          <el-select v-model="selectedAccount" placeholder="选择账户" class="account-select">
            <el-option
              v-for="account in accounts"
              :key="account.id"
              :label="account.name"
              :value="account.id"
            />
          </el-select>
          <el-button type="primary" :icon="Refresh" @click="refreshPositions">
            刷新
          </el-button>
        </div>
      </template>
    </PageHero>

    <ReadModelSourceStrip
      label="持仓状态"
      :status-text="positionReadModelStatus"
      :status-type="positionReadModelStatusType"
      :updated-at="positionReadModelUpdatedAt"
      :updated-prefix="positionReadModelUpdatedPrefix"
      :tags="positionReadModelTags"
    />

    <MetricStrip
      v-if="!isPhoneLayout || activeMobileSection === 'overview'"
      class="positions-overview-strip"
      :items="positionMetricItems"
      :compact="isPhoneLayout"
    />

    <MobileSegmentControl
      v-if="isPhoneLayout"
      v-model="activeMobileSection"
      class="mobile-position-rail"
      label="持仓分段"
      :items="positionMobileSections"
    />

    <el-card v-if="!isPhoneLayout || activeMobileSection === 'overview'" class="insight-panel">
      <SectionCardHeader
        title="组合洞察"
      />
      <section class="insight-strip">
        <article v-for="item in positionInsights" :key="item.label" class="insight-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </section>
    </el-card>

    <el-card class="positions-table">
      <template #header>
        <SectionCardHeader
          title="持仓明细"
          :badge="positionReadModelStatus"
          :badge-type="positionReadModelStatusType"
        >
          <template #actions>
            <el-radio-group v-if="!isPhoneLayout" v-model="viewMode" size="small">
              <el-radio-button value="list">列表</el-radio-button>
              <el-radio-button value="chart">图表</el-radio-button>
            </el-radio-group>
          </template>
        </SectionCardHeader>
      </template>

      <el-table
        v-if="!isPhoneLayout && viewMode === 'list'"
        :data="positions"
        :empty-text="loading ? '持仓加载中' : '当前账户暂无持仓'"
        style="width: 100%"
        @row-click="showPositionDetail"
      >
        <el-table-column prop="symbol" label="代码" width="120">
          <template #default="{ row }">
            <button type="button" class="symbol-link" @click.stop="viewSymbolDetail(row)">
              {{ row.symbol }}
            </button>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="quantity" label="持仓数量" width="110" />
        <el-table-column prop="avgPrice" label="成本价" width="130">
          <template #default="{ row }">
            {{ formatCurrency(row.avgPrice) }}
          </template>
        </el-table-column>
        <el-table-column prop="currentPrice" label="现价" width="130">
          <template #default="{ row }">
            {{ formatCurrency(row.currentPrice) }}
          </template>
        </el-table-column>
        <el-table-column prop="marketValue" label="市值" width="150">
          <template #default="{ row }">
            {{ formatCurrency(row.marketValue) }}
          </template>
        </el-table-column>
        <el-table-column prop="pnl" label="盈亏" width="150">
          <template #default="{ row }">
            <div class="pnl-cell">
              <span :class="row.pnl >= 0 ? 'up' : 'down'">
                {{ formatSignedCurrency(row.pnl) }}
              </span>
              <span :class="row.pnlPercent >= 0 ? 'up' : 'down'" class="pnl-percent">
                {{ formatPercentValue(row.pnlPercent) }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="weight" label="仓位占比" width="130">
          <template #default="{ row }">
            <div class="weight-cell">
              <el-progress :percentage="row.weight" :color="getWeightColor" :show-text="false" />
              <span class="weight-text">{{ formatWeight(row.weight) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button type="success" size="small" @click.stop="quickBuy(row)">买入</el-button>
            <el-button type="danger" size="small" @click.stop="quickSell(row)">卖出</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-else-if="!isPhoneLayout" class="chart-view">
        <div class="chart-container">
          <v-chart class="chart" :option="pieChartOption" autoresize />
        </div>
      </div>

      <div v-else-if="activeMobileSection === 'holdings'" class="mobile-position-list">
        <div v-if="loading && !positions.length" class="positions-inline-status">
          持仓加载中
        </div>
        <article
          v-for="row in positions"
          :key="row.symbol"
          class="mobile-position-card"
          @click="showPositionDetail(row)"
        >
          <div class="mobile-position-head">
            <div>
              <button type="button" class="symbol-link" @click.stop="viewSymbolDetail(row)">
                {{ row.symbol }}
              </button>
              <strong>{{ row.name || '未命名标的' }}</strong>
            </div>
            <div class="mobile-position-price">
              <span>{{ formatCurrency(row.marketValue) }}</span>
              <small :class="Number(row.pnl || 0) >= 0 ? 'up' : 'down'">{{ formatPercentValue(row.pnlPercent) }}</small>
            </div>
          </div>

          <div class="mobile-position-meta">
            <span>持仓 {{ row.quantity }} 股</span>
            <span>成本 {{ formatCurrency(row.avgPrice) }}</span>
            <span>现价 {{ formatCurrency(row.currentPrice) }}</span>
            <span :class="Number(row.pnl || 0) >= 0 ? 'up' : 'down'">盈亏 {{ formatSignedCurrency(row.pnl) }}</span>
          </div>

          <div class="mobile-position-bar">
            <div class="mobile-position-bar-fill" :style="{ width: `${Math.min(Number(row.weight || 0), 100)}%` }" />
          </div>
          <div class="mobile-position-foot">
            <span>仓位占比 {{ formatWeight(row.weight) }}</span>
            <div class="mobile-position-actions">
              <el-button type="success" size="small" plain @click.stop="quickBuy(row)">买入</el-button>
              <el-button type="danger" size="small" @click.stop="quickSell(row)">卖出</el-button>
            </div>
          </div>
        </article>
        <el-empty v-if="!positions.length && !loading" description="当前账户暂无持仓" />
      </div>

      <div v-else class="chart-view mobile-chart-view">
        <div class="chart-container">
          <v-chart class="chart" :option="pieChartOption" autoresize />
        </div>
        <div v-if="positions.length" class="mobile-allocation-list">
          <article v-for="row in positions.slice(0, 5)" :key="`allocation-${row.symbol}`" class="mobile-allocation-item">
            <div>
              <strong>{{ row.symbol }}</strong>
              <span>{{ row.name }}</span>
            </div>
            <span>{{ formatWeight(row.weight) }}</span>
          </article>
        </div>
      </div>
    </el-card>

    <el-dialog v-model="detailVisible" title="持仓详情" width="700px">
      <div v-if="selectedPosition" class="position-detail">
        <div class="detail-header">
          <div class="stock-info">
            <button type="button" class="symbol-link detail-link" @click="viewSymbolDetail(selectedPosition)">
              {{ selectedPosition.symbol }}
            </button>
            <span class="name">{{ selectedPosition.name }}</span>
          </div>
          <div class="price-info">
            <span class="current-price" :class="selectedPosition.change >= 0 ? 'up' : 'down'">
              {{ formatCurrency(selectedPosition.currentPrice) }}
            </span>
            <span class="change" :class="selectedPosition.change >= 0 ? 'up' : 'down'">
              {{ formatPercentValue(selectedPosition.changePercent) }}
            </span>
          </div>
        </div>

        <el-divider />

        <div class="detail-stats">
          <div class="stat-row">
            <div class="stat-item">
              <div class="stat-label">持仓数量</div>
              <div class="stat-value">{{ selectedPosition.quantity }}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">成本价</div>
              <div class="stat-value">{{ formatCurrency(selectedPosition.avgPrice) }}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">现价</div>
              <div class="stat-value">{{ formatCurrency(selectedPosition.currentPrice) }}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">市值</div>
              <div class="stat-value">{{ formatCurrency(selectedPosition.marketValue) }}</div>
            </div>
          </div>
          <div class="stat-row">
            <div class="stat-item">
              <div class="stat-label">盈亏金额</div>
              <div class="stat-value" :class="selectedPosition.pnl >= 0 ? 'up' : 'down'">
                {{ formatSignedCurrency(selectedPosition.pnl) }}
              </div>
            </div>
            <div class="stat-item">
              <div class="stat-label">盈亏比例</div>
              <div class="stat-value" :class="selectedPosition.pnlPercent >= 0 ? 'up' : 'down'">
                {{ formatPercentValue(selectedPosition.pnlPercent) }}
              </div>
            </div>
            <div class="stat-item">
              <div class="stat-label">仓位占比</div>
              <div class="stat-value">{{ formatWeight(selectedPosition.weight) }}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">持仓天数</div>
              <div class="stat-value">{{ selectedPosition.holdDays }}天</div>
            </div>
          </div>
        </div>

        <el-divider />

        <div class="detail-actions">
          <el-button type="success" size="large" @click="quickBuy(selectedPosition)">买入</el-button>
          <el-button type="danger" size="large" @click="quickSell(selectedPosition)">卖出</el-button>
          <el-button type="primary" size="large" @click="setStopLoss(selectedPosition)">设置止损</el-button>
          <el-button type="warning" size="large" @click="setTakeProfit(selectedPosition)">设置止盈</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Coin, Money, Refresh, TrendCharts, Wallet } from '@element-plus/icons-vue'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { getAccounts, getPositionsSnapshot } from '../api/trade.js'
import { useStockQuotes } from '../composables/useWebSocket.js'
import { useTheme } from '../composables/useTheme.js'
import MetricStrip from '../components/common/MetricStrip.vue'
import PageHero from '../components/common/PageHero.vue'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import MobileSegmentControl from '../components/common/MobileSegmentControl.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'
import { useAdaptiveLayout } from '../composables/useAdaptiveLayout.js'
import { getCurrentUser } from '../utils/auth.js'
import { formatCurrency as formatCurrencyValue, formatPercent as formatPercentDisplay } from '../utils/formatters.js'
import { buildPositionReadModelSummary, formatReadModelSourceLabel } from '../utils/readModelSource.js'

use([CanvasRenderer, PieChart, TooltipComponent, LegendComponent])

const router = useRouter()
const currentUser = getCurrentUser() || {}
const { isPhoneLayout } = useAdaptiveLayout()
const loading = ref(false)
const viewMode = ref('list')
const activeMobileSection = ref('overview')
const selectedAccount = ref('')
const accounts = ref([])
const positionSnapshots = ref([])
const positionSnapshotMeta = ref({
  snapshotAt: '',
  dataSource: 'snapshot',
  sources: {},
  realtimeOverlay: [],
  positionCount: 0
})
const detailVisible = ref(false)
const selectedPositionSymbol = ref('')
const AUTO_REFRESH_INTERVAL = 10000
let refreshTimer = null
const { activeTheme } = useTheme()

const readThemeValue = (variableName, fallback) => {
  activeTheme.value
  if (typeof window === 'undefined') {
    return fallback
  }

  const value = getComputedStyle(document.documentElement).getPropertyValue(variableName).trim()
  return value || fallback
}

const getChartPalette = () => ({
  text: readThemeValue('--text-primary', '#ffffff'),
  muted: readThemeValue('--chart-axis', 'rgba(210, 225, 248, 0.7)'),
  border: readThemeValue('--surface-emphasis', 'rgba(13, 26, 49, 0.72)'),
  grid: readThemeValue('--chart-grid', 'rgba(255, 255, 255, 0.1)')
})

const selectedAccountName = computed(() => {
  return accounts.value.find((account) => account.id === selectedAccount.value)?.name || ''
})

const streamSymbols = computed(() => positionSnapshots.value.map((item) => item.symbol).filter(Boolean))
const { quotes: liveQuoteMap, isConnected: quotesConnected } = useStockQuotes(streamSymbols, {
  userId: currentUser?.id || null
})

const positions = computed(() => {
  const merged = positionSnapshots.value.map((item) => {
    const symbol = String(item.symbol || '').toUpperCase()
    const quote = liveQuoteMap.value[symbol] || null
    if (!quote) {
      return item
    }

    const quantity = Number(item.quantity || 0)
    const avgPrice = Number(item.avgPrice || 0)
    const currentPrice = Number(quote.last_price ?? quote.price ?? item.currentPrice ?? 0)
    const marketValue = quantity * currentPrice
    const pnl = (currentPrice - avgPrice) * quantity
    const pnlPercent = avgPrice > 0 ? ((currentPrice - avgPrice) / avgPrice) * 100 : Number(item.pnlPercent || 0)

    return {
      ...item,
      currentPrice,
      current_price: currentPrice,
      marketValue,
      market_value: marketValue,
      pnl,
      pnlPercent,
      pnl_ratio: pnlPercent,
      change: Number(quote.change ?? (currentPrice - avgPrice)),
      changePercent: Number(quote.change_percent ?? quote.changePercent ?? pnlPercent),
      updatedAt: quote.timestamp || item.updatedAt || null
    }
  })

  const totalMarketValue = merged.reduce((sum, item) => sum + Number(item.marketValue || 0), 0)
  return merged.map((item) => ({
    ...item,
    weight: totalMarketValue > 0 ? (Number(item.marketValue || 0) / totalMarketValue) * 100 : Number(item.weight || 0)
  }))
})

const selectedPosition = computed(() => {
  return positions.value.find((item) => item.symbol === selectedPositionSymbol.value) || null
})
const positionSnapshotSources = computed(() => (
  positionSnapshotMeta.value?.sources && typeof positionSnapshotMeta.value.sources === 'object'
    ? positionSnapshotMeta.value.sources
    : {}
))
const positionRealtimeOverlayLabel = computed(() => {
  const overlays = new Set(Array.isArray(positionSnapshotMeta.value?.realtimeOverlay) ? positionSnapshotMeta.value.realtimeOverlay : [])
  if (quotesConnected.value && streamSymbols.value.length) {
    overlays.add('quotes')
  }
  return Array.from(overlays).filter(Boolean).join(' / ')
})
const positionReadModelSummary = computed(() => buildPositionReadModelSummary({
  meta: positionSnapshotMeta.value,
  accountLabel: selectedAccountName.value,
  quotesConnected: quotesConnected.value,
  streamSymbolCount: streamSymbols.value.length,
  positionCount: positionSnapshots.value.length
}))
const positionReadModelStatus = computed(() => positionReadModelSummary.value.statusText)
const positionReadModelStatusType = computed(() => positionReadModelSummary.value.statusType)
const positionReadModelUpdatedAt = computed(() => (
  positionReadModelSummary.value.updatedAt ? formatDateTime(positionReadModelSummary.value.updatedAt) : ''
))
const positionReadModelUpdatedPrefix = computed(() => positionReadModelSummary.value.updatedPrefix)
const positionReadModelTags = computed(() => positionReadModelSummary.value.tags || [])
const positionsHeroChips = computed(() => ([
  { text: selectedAccountName.value || '未选择账户', tone: selectedAccount.value ? 'success' : 'warning' },
  { text: loading.value ? '持仓同步中' : `自动刷新 ${AUTO_REFRESH_INTERVAL / 1000} 秒`, tone: loading.value ? 'warning' : 'info' },
  { text: quotesConnected.value ? '行情在线' : '持仓快照', tone: quotesConnected.value ? 'success' : 'info' }
]))
const positionsHeroMetrics = computed(() => ([
  {
    label: '数据状态',
    value: positionReadModelStatus.value,
    note: positionReadModelUpdatedAt.value || '等待快照接入'
  },
  {
    label: '行情标的',
    value: `${streamSymbols.value.length} 个`,
    note: quotesConnected.value ? '最新价在线' : '当前快照'
  },
  {
    label: '账户',
    value: selectedAccountName.value || '未选择',
    note: formatReadModelSourceLabel(positionSnapshotSources.value.positions || 'position_snapshots')
  }
]))

const totalMarketValue = computed(() => positions.value.reduce((sum, item) => sum + Number(item.marketValue || 0), 0))
const totalPnl = computed(() => positions.value.reduce((sum, item) => sum + Number(item.pnl || 0), 0))

const positionStats = computed(() => {
  const pnlBase = totalMarketValue.value - totalPnl.value
  const totalPnlPercent = pnlBase > 0 ? (totalPnl.value / pnlBase) * 100 : 0

  return [
    {
      label: '持仓市值',
      value: formatCurrency(totalMarketValue.value),
      icon: Wallet,
      color: '#409eff',
      class: ''
    },
    {
      label: '总盈亏',
      value: formatSignedCurrency(totalPnl.value),
      icon: TrendCharts,
      color: totalPnl.value >= 0 ? '#67c23a' : '#f56c6c',
      class: totalPnl.value >= 0 ? 'up' : 'down'
    },
    {
      label: '盈亏比例',
      value: formatPercentValue(totalPnlPercent),
      icon: Coin,
      color: totalPnlPercent >= 0 ? '#67c23a' : '#f56c6c',
      class: totalPnlPercent >= 0 ? 'up' : 'down'
    },
    {
      label: '持仓数量',
      value: `${positions.value.length}只`,
      icon: Money,
      color: '#e6a23c',
      class: ''
    }
  ]
})
const positionMetricItems = computed(() => positionStats.value.map((stat) => ({
  label: stat.label,
  value: stat.value,
  note: stat.label === '持仓市值'
    ? '当前账户持仓合计'
    : stat.label === '总盈亏'
      ? '按最新价计算'
      : stat.label === '盈亏比例'
        ? '当前组合收益率'
        : '当前持仓标的数量',
  tone: stat.class === 'up' ? 'healthy' : stat.class === 'down' ? 'error' : ''
})))

const positionMobileSections = computed(() => ([
  { value: 'overview', label: '总览', note: selectedAccountName.value || '账户摘要' },
  { value: 'holdings', label: '持仓', note: `${positions.value.length} 个标的` },
  { value: 'allocation', label: '分布', note: '仓位结构' }
]))

const positionInsights = computed(() => {
  if (!positions.value.length) {
    return [
      { label: '组合状态', value: '暂无持仓', note: '绑定账户后会显示真实持仓分析。' },
      { label: '最大仓位', value: '--', note: '暂无数据' },
      { label: '表现最好', value: '--', note: '暂无数据' },
      { label: '风险关注', value: '--', note: '暂无数据' }
    ]
  }

  const sortedByValue = [...positions.value].sort((a, b) => Number(b.marketValue || 0) - Number(a.marketValue || 0))
  const sortedByGain = [...positions.value].sort((a, b) => Number(b.pnlPercent || 0) - Number(a.pnlPercent || 0))
  const largest = sortedByValue[0]
  const best = sortedByGain[0]
  const weakest = sortedByGain[sortedByGain.length - 1]
  const concentration = totalMarketValue.value > 0 ? (Number(largest?.marketValue || 0) / totalMarketValue.value) * 100 : 0

  return [
    {
      label: '组合状态',
      value: concentration >= 35 ? '偏集中' : '较均衡',
      note: `最大单仓占比 ${formatWeight(concentration)}`
    },
    {
      label: '最大仓位',
      value: largest?.symbol || '--',
      note: largest ? `${formatCurrency(largest.marketValue)} · ${formatWeight(largest.weight)}` : '暂无数据'
    },
    {
      label: '表现最好',
      value: best?.symbol || '--',
      note: best ? `${formatPercentValue(best.pnlPercent)} · ${formatSignedCurrency(best.pnl)}` : '暂无数据'
    },
    {
      label: '风险关注',
      value: weakest?.symbol || '--',
      note: weakest ? `${formatPercentValue(weakest.pnlPercent)} · ${formatSignedCurrency(weakest.pnl)}` : '暂无数据'
    }
  ]
})

const pieChartOption = computed(() => {
  const palette = getChartPalette()
  const data = positions.value.map((item) => ({
    name: item.symbol,
    value: item.marketValue
  }))

  return {
    tooltip: {
      trigger: 'item',
      backgroundColor: readThemeValue('--surface-emphasis', 'rgba(13, 26, 49, 0.92)'),
      borderColor: palette.grid,
      textStyle: { color: palette.text },
      formatter: '{b}: ${c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left',
      textStyle: { color: palette.muted }
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderRadius: 10,
        borderColor: palette.border,
        borderWidth: 2
      },
      label: {
        show: false,
        position: 'center'
      },
      emphasis: {
        label: {
          show: true,
          fontSize: 20,
          fontWeight: 'bold'
        }
      },
      labelLine: {
        show: false
      },
      data
    }]
  }
})

const loadAccounts = async () => {
  try {
    const res = await getAccounts()
    accounts.value = res.data || []
    if (!selectedAccount.value && accounts.value.length > 0) {
      const defaultAccount = accounts.value.find((account) => account.isDefault || account.is_default)
      selectedAccount.value = defaultAccount?.id || accounts.value[0].id
    }
  } catch (error) {
    console.error('加载账户失败:', error)
    accounts.value = []
  }
}

const loadPositions = async () => {
  if (!selectedAccount.value) {
    positionSnapshots.value = []
    positionSnapshotMeta.value = {
      snapshotAt: '',
      dataSource: 'snapshot',
      sources: {},
      realtimeOverlay: [],
      positionCount: 0
    }
    return
  }

  loading.value = true
  try {
    const res = await getPositionsSnapshot(selectedAccount.value)
    positionSnapshots.value = Array.isArray(res.data) ? res.data : []
    positionSnapshotMeta.value = {
      snapshotAt: res.meta?.snapshotAt || '',
      dataSource: res.meta?.dataSource || 'snapshot',
      sources: res.meta?.sources || {},
      realtimeOverlay: Array.isArray(res.meta?.realtimeOverlay) ? res.meta.realtimeOverlay : [],
      positionCount: Number(res.meta?.positionCount || positionSnapshots.value.length)
    }
  } catch (error) {
    console.error('加载持仓失败:', error)
    ElMessage.error('加载持仓失败')
    positionSnapshotMeta.value = {
      snapshotAt: '',
      dataSource: 'snapshot',
      sources: {},
      realtimeOverlay: [],
      positionCount: 0
    }
  } finally {
    loading.value = false
  }
}

const refreshPositions = () => {
  loadPositions()
}

const stopAutoRefresh = () => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  if (!selectedAccount.value) return
  refreshTimer = window.setInterval(() => {
    loadPositions()
  }, AUTO_REFRESH_INTERVAL)
}

const showPositionDetail = (row) => {
  selectedPositionSymbol.value = row.symbol
  detailVisible.value = true
}

const viewSymbolDetail = (row) => {
  router.push({
    name: 'SymbolDetail',
    params: { symbol: row.symbol }
  })
}

const quickBuy = (row) => {
  router.push({
    name: 'Trading',
    query: { symbol: row.symbol, action: 'buy' }
  })
}

const quickSell = (row) => {
  router.push({
    name: 'Trading',
    query: { symbol: row.symbol, action: 'sell' }
  })
}

const setStopLoss = (row) => {
  ElMessage.success(`设置 ${row.symbol} 止损`)
}

const setTakeProfit = (row) => {
  ElMessage.success(`设置 ${row.symbol} 止盈`)
}

const getWeightColor = (percentage) => {
  if (percentage >= 30) return '#f56c6c'
  if (percentage >= 15) return '#e6a23c'
  return '#67c23a'
}

const formatCurrency = (value) => formatCurrencyValue(value, { currency: '$' })
const formatSignedCurrency = (value) => formatCurrencyValue(value, { currency: '$', signed: true, absolute: true })
const formatPercentValue = (value) => formatPercentDisplay(value)
const formatWeight = (value) => formatPercentDisplay(value, { signed: false })
const formatDateTime = (value) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN')
}

onMounted(() => {
  loadAccounts()
})

watch(selectedAccount, (newValue, oldValue) => {
  if (!newValue || newValue === oldValue) return
  loadPositions()
  startAutoRefresh()
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<style scoped lang="scss">
.positions-page {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
}

.hero-panel,
.positions-table {
  border: 1px solid var(--panel-edge);
  background: var(--panel-surface);
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.hero-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  min-height: 0;
}

.hero-kicker,
.table-kicker,
.insight-card span {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.hero-copy h2,
.card-header h3 {
  margin: 10px 0 8px;
  color: var(--text-primary);
}

.hero-copy p,
.card-header p,
.insight-card p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.hero-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.hero-tag {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 6px;
  border: 1px solid var(--control-border);
  background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
  color: var(--text-secondary);
  font-size: 11px;
}

.hero-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.account-select {
  width: 220px;
}

.insight-strip,
.positions-overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.insight-card,
.stat-card {
  border: 1px solid var(--panel-edge);
  background: var(--panel-surface);
  box-shadow: var(--shadow-soft), var(--panel-inset);
}

.insight-card {
  padding: 8px 10px;
  border-radius: 8px;
}

.insight-card strong {
  display: block;
  margin-top: 4px;
  color: var(--text-primary);
  font-size: 14px;
}

.stat-content {
  display: flex;
  align-items: center;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 12px;
}

.stat-label {
  font-size: 14px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.positions-table {
  border-radius: 10px;
}

.positions-inline-status {
  display: flex;
  align-items: center;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid var(--panel-edge);
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
  color: var(--text-secondary);
  font-size: 13px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.symbol-link {
  padding: 0;
  border: none;
  background: transparent;
  color: var(--accent-strong);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.detail-link {
  font-size: 24px;
}

.pnl-cell {
  display: flex;
  flex-direction: column;
}

.pnl-percent,
.weight-text {
  font-size: 12px;
}

.weight-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.weight-text {
  color: var(--text-secondary);
}

.chart-container {
  height: 320px;
}

.chart {
  width: 100%;
  height: 100%;
}

.position-detail .detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.stock-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.name {
  font-size: 16px;
  color: var(--text-muted);
}

.price-info {
  text-align: right;
}

.current-price {
  display: block;
  font-size: 28px;
  font-weight: 700;
}

.detail-stats .stat-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.detail-stats .stat-item {
  text-align: center;
}

.detail-stats .stat-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.detail-stats .stat-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.detail-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  flex-wrap: wrap;
}

.positions-table :deep(.el-table),
.positions-table :deep(.el-table__expanded-cell) {
  background: transparent !important;
}

.positions-table :deep(.el-table th.el-table__cell) {
  background: color-mix(in srgb, var(--surface-muted) 84%, transparent) !important;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--table-divider);
}

.positions-table :deep(.el-table td.el-table__cell) {
  border-bottom: 1px solid var(--table-divider);
}

.positions-table :deep(.el-table__inner-wrapper::before) {
  background-color: transparent;
}

.mobile-position-rail {
  margin-top: -4px;
}

.mobile-position-list,
.mobile-allocation-list {
  display: grid;
  gap: 12px;
}

.mobile-position-card,
.mobile-allocation-item {
  border: 1px solid var(--panel-edge);
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
  box-shadow: var(--shadow-soft), var(--panel-inset);
}

.mobile-position-card {
  display: grid;
  gap: 12px;
  padding: 16px 18px;
  border-radius: 22px;
}

.mobile-position-head,
.mobile-position-foot,
.mobile-allocation-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.mobile-position-head strong,
.mobile-allocation-item strong {
  display: block;
  color: var(--text-primary);
}

.mobile-position-price {
  text-align: right;

  span {
    display: block;
    color: var(--text-primary);
    font-size: 18px;
    font-weight: 700;
  }

  small {
    font-size: 12px;
  }
}

.mobile-position-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
  color: var(--text-secondary);
  font-size: 13px;
}

.mobile-position-bar {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface-muted) 88%, transparent);
}

.mobile-position-bar-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--accent-strong), var(--accent));
}

.mobile-position-foot {
  align-items: center;

  span {
    color: var(--text-muted);
    font-size: 12px;
  }
}

.mobile-position-actions {
  display: flex;
  gap: 8px;
}

.mobile-chart-view {
  display: grid;
  gap: 12px;
}

.mobile-allocation-item {
  padding: 14px 16px;
  border-radius: 18px;

  span {
    color: var(--text-secondary);
  }
}

.up {
  color: var(--success);
}

.down {
  color: var(--danger);
}

@media (max-width: 1180px) {
  .hero-panel,
  .insight-strip,
  .positions-overview {
    grid-template-columns: 1fr;
  }

  .card-header {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 900px) {
  .positions-page {
    padding: 16px;
  }

  .hero-actions {
    width: 100%;
  }

  .account-select {
    width: 100%;
  }

  .detail-stats .stat-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .mobile-position-meta {
    grid-template-columns: 1fr;
  }

  .mobile-position-foot,
  .mobile-allocation-item {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>

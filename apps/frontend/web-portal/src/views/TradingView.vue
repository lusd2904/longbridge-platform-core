<template>
  <div class="trading-view">
    <div class="min-h-screen bg-black text-gray-200 p-4 font-sans overflow-hidden">
      <div class="max-w-[1800px] mx-auto mb-4 flex flex-wrap justify-between items-center gap-3">
        <div>
          <h1 class="text-3xl font-black italic glow-text text-blue-500 uppercase tracking-widest">交易看板</h1>
        </div>
        <div class="flex items-center gap-3 flex-wrap justify-end">
          <select v-model="selectedAccount" class="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 min-w-[240px]">
            <option :value="''">选择账户</option>
            <option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name }}</option>
          </select>
          <button class="bg-blue-600 hover:bg-blue-500 text-white rounded-lg px-4 py-2 text-sm font-bold" @click="refreshAll">
            刷新
          </button>
          <div class="text-gray-500 text-sm whitespace-nowrap">{{ currentTime }}</div>
        </div>
      </div>

      <div class="max-w-[1800px] mx-auto mb-4 source-strip-shell">
        <ReadModelSourceStrip
          label="账户状态"
          :detail="accountSourceSummary.detail"
          :status-text="accountSourceSummary.statusText"
          :status-type="accountSourceSummary.statusType"
          :updated-at="accountSourceUpdatedAt"
          :updated-prefix="accountSourceSummary.updatedPrefix"
          :tags="accountSourceSummary.tags"
        />
      </div>

      <div class="max-w-[1800px] mx-auto mb-4 source-strip-shell">
        <ReadModelSourceStrip
          label="研判状态"
          :detail="analysisSourceSummary.detail"
          :status-text="analysisSourceSummary.statusText"
          :status-type="analysisSourceSummary.statusType"
          :updated-at="analysisSourceUpdatedAt"
          :updated-prefix="analysisSourceSummary.updatedPrefix"
          :tags="analysisSourceSummary.tags"
          compact
        />
      </div>

      <div class="max-w-[1800px] mx-auto mb-4 grid grid-cols-4 gap-4">
        <div class="bg-gray-900 border border-gray-800 rounded-xl p-4 shadow-2xl">
          <p class="text-gray-500 text-xs uppercase font-bold">总资产 (TOTAL ASSETS)</p>
          <p class="text-3xl font-mono font-bold text-white mt-1 truncate">{{ accountCards.totalAssets }}</p>
        </div>
        <div class="bg-gray-900 border border-gray-800 rounded-xl p-4 shadow-2xl">
          <p class="text-gray-500 text-xs uppercase font-bold">现金 (CASH)</p>
          <p class="text-3xl font-mono font-bold text-white mt-1 truncate">{{ accountCards.cash }}</p>
        </div>
        <div class="bg-gray-900 border border-gray-800 rounded-xl p-4 shadow-2xl">
          <p class="text-gray-500 text-xs uppercase font-bold">持仓市值 (MARKET VALUE)</p>
          <p class="text-3xl font-mono font-bold text-white mt-1 truncate">{{ accountCards.marketValue }}</p>
        </div>
        <div class="bg-gray-900 border border-gray-800 rounded-xl p-4 shadow-2xl">
          <p class="text-gray-500 text-xs uppercase font-bold">账户盈亏 (PNL)</p>
          <p :class="accountPnLClass" class="text-3xl font-mono font-bold mt-1 truncate">{{ accountCards.dailyPnL }}</p>
        </div>
      </div>

      <div class="grid grid-cols-12 gap-4 max-w-[1800px] mx-auto">
        <div class="col-span-4 space-y-4 h-[80vh] flex flex-col">
          <div class="bg-gray-900 border border-gray-800 rounded-xl flex-grow flex flex-col overflow-hidden shadow-2xl">
            <div class="border-b border-gray-800 text-[11px] font-black uppercase py-4 px-4 flex justify-between items-center">
              <span>持仓总览</span>
              <span class="text-gray-500">{{ holdings.length }} 个持仓</span>
            </div>
            <div class="flex-grow custom-scroll overflow-y-auto p-4 font-mono text-[11px]">
              <div class="grid grid-cols-5 text-gray-600 border-b border-gray-800 pb-2 mb-2 text-[10px] font-bold">
                <span class="truncate">代码</span><span class="truncate">现价</span><span class="truncate">成本</span><span class="truncate">盈亏</span><span class="truncate">数量</span>
              </div>
              <div v-for="holding in holdings" :key="holding.symbol" class="grid grid-cols-5 py-3 border-b border-gray-800/40 items-center">
                <span class="text-blue-500 font-black truncate">{{ holding.symbol }}</span>
                <span class="text-gray-300 truncate">{{ holding.priceText }}</span>
                <span class="text-gray-500 truncate">{{ holding.costText }}</span>
                <span :class="holding.pnlValue >= 0 ? 'text-green-500' : 'text-red-500'" class="font-bold truncate">{{ holding.pnlText }}</span>
                <span class="text-gray-300 truncate">{{ holding.qtyText }}</span>
              </div>
              <div v-if="holdings.length === 0" class="flex items-center justify-center h-full text-gray-600 text-sm">
                暂无持仓数据
              </div>
            </div>
          </div>

          <div class="bg-gray-900 border border-gray-800 rounded-xl flex-grow flex flex-col overflow-hidden shadow-2xl">
            <div class="border-b border-gray-800 text-[11px] font-black uppercase py-4 px-4 flex justify-between items-center">
              <span>挂单记录</span>
              <span class="text-gray-500">{{ activeOrders.length }} 条订单</span>
            </div>
            <div class="flex-grow custom-scroll overflow-y-auto p-4 font-mono text-[11px]">
              <div class="grid grid-cols-4 text-gray-600 border-b border-gray-800 pb-2 mb-2 text-[10px] font-bold">
                <span class="truncate">代码</span><span class="truncate">方向</span><span class="truncate">价格</span><span class="truncate">数量</span>
              </div>
              <div v-for="order in activeOrders" :key="order.orderId || `${order.symbol}-${order.createTime}`" class="grid grid-cols-4 py-3 border-b border-gray-800/40 items-center">
                <span class="text-blue-500 font-black truncate">{{ order.symbol }}</span>
                <span :class="order.action === 'buy' ? 'text-green-400' : 'text-red-400'" class="font-bold truncate">{{ order.action === 'buy' ? 'BUY' : 'SELL' }}</span>
                <span class="text-gray-300 truncate">{{ formatOrderPrice(order) }}</span>
                <span class="text-gray-300 truncate">{{ formatNumber(order.quantity, 0) }}</span>
              </div>
              <div v-if="activeOrders.length === 0" class="flex items-center justify-center h-full text-gray-600 text-sm">
                暂无挂单数据
              </div>
            </div>
          </div>
        </div>

        <div class="col-span-5 h-[80vh] bg-gray-900 border border-gray-800 rounded-xl overflow-hidden shadow-2xl">
          <div class="border-b border-gray-800 text-[11px] font-black uppercase py-4 px-4 flex justify-between items-center">
              <span>研判结果</span>
            <span class="text-gray-500">{{ aiRows.length }} 条</span>
          </div>
          <div class="h-[calc(100%-40px)] custom-scroll overflow-y-auto p-4 font-mono text-[11px]">
            <div v-for="ai in aiRows" :key="`${ai.symbol}-${ai.time}`" class="mb-4 p-3 border border-gray-800 rounded-lg">
              <div class="flex justify-between items-center mb-2 gap-3">
                <span class="text-blue-500 font-black truncate">{{ ai.symbol }}</span>
                <span :class="ai.status === 'BUY' ? 'text-green-400' : ai.status === 'SELL' ? 'text-red-400' : 'text-yellow-400'" class="font-bold truncate">{{ ai.status }}</span>
              </div>
              <div class="text-gray-600 text-xs mb-1 whitespace-nowrap">分析时间: {{ ai.time || currentTime }}</div>
              <div class="text-gray-400 text-xs mb-1 whitespace-pre-wrap break-words"><span class="text-gray-600">市场层:</span> {{ ai.gemma }}</div>
              <div class="text-gray-400 text-xs mb-1 whitespace-pre-wrap break-words"><span class="text-gray-600">风险层:</span> {{ ai.llama }}</div>
              <div class="text-gray-400 text-xs whitespace-pre-wrap break-words"><span class="text-gray-600">决策层:</span> {{ ai.deepseek }}</div>
            </div>
            <div v-if="aiRows.length === 0" class="flex items-center justify-center h-full text-gray-600 text-sm">
              暂无研判数据
            </div>
          </div>
        </div>

        <div class="col-span-3 h-[80vh] bg-gray-900 border border-gray-800 rounded-xl overflow-hidden shadow-2xl">
          <div class="border-b border-gray-800 text-[11px] font-black uppercase py-4 px-4 flex justify-between items-center">
            <span>实时扫描瀑布流</span>
            <span class="text-gray-500">{{ scanFeed.length }} 条</span>
          </div>
          <div class="h-[calc(100%-40px)] custom-scroll overflow-y-auto p-4 font-mono text-[11px]">
            <div v-for="(scan, index) in scanFeed" :key="`${scan.time}-${index}`" class="py-1.5 border-b border-gray-800/50 text-gray-400 whitespace-pre-wrap break-words">
              <span class="text-blue-900 font-bold">{{ scan.time }}</span> {{ scan.content }}
            </div>
            <div v-if="scanFeed.length === 0" class="flex items-center justify-center h-full text-gray-600 text-sm">
              暂无扫描流水
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getLatestTrendScans, getQuantStatus } from '../api/analysis.js'
import { getDashboardMarketInsights } from '../api/market.js'
import { getBrokerAccounts, getProjectedOrders, getTradeSnapshotState } from '../api/trade.js'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import { useOrderStream, useStockQuotes } from '../composables/useWebSocket.js'
import { getCurrentUser } from '../utils/auth.js'
import { formatCurrency as formatCurrencyValue, formatOrderPrice, formatPercent as formatPercentDisplay } from '../utils/formatters.js'
import { buildAccountReadModelSummary, buildMarketInsightReadModelSummary, buildTrendScanReadModelSummary, formatReadModelSourceLabel } from '../utils/readModelSource.js'

const currentUser = getCurrentUser() || {}
const accounts = ref([])
const selectedAccount = ref('')
const snapshotState = ref({ accountInfo: {}, positions: [], orders: [], snapshotAt: '', dataSource: 'snapshot', meta: {} })
const projectedOrders = ref([])
const projectionMeta = ref({ snapshotAt: '', dataSource: 'order-projection', meta: {} })
const marketInsights = ref([])
const trendScans = ref([])
const marketInsightMeta = ref({})
const trendScanMeta = ref({})
const quantStatus = ref({ enabled: false, signals: [] })
const currentTime = ref('')
const emptyStatus = ref('')

let clockTimer = null
let refreshTimer = null
const AUTO_REFRESH_INTERVAL = 15000

const selectedAccountName = computed(() => accounts.value.find((item) => item.id === selectedAccount.value)?.name || '未选择账户')
const holdingSymbols = computed(() => snapshotState.value.positions.map((item) => String(item.symbol || '').trim().toUpperCase()).filter(Boolean))
const { quotes: liveQuoteMap, isConnected: quotesConnected } = useStockQuotes(holdingSymbols, {
  userId: currentUser?.id || null
})
const {
  orders: streamedOrders,
  meta: streamedOrderMeta,
  lastReceivedAt,
  subscriptionAccountId,
  subscriptionStatus
} = useOrderStream(selectedAccount, emptyStatus, { limit: 20 })

const hasOrderStreamCoverage = computed(() => {
  if (!lastReceivedAt.value) {
    return false
  }
  const currentAccountId = selectedAccount.value ? Number(selectedAccount.value) : null
  const streamAccountId = subscriptionAccountId.value !== null && subscriptionAccountId.value !== undefined
    ? Number(subscriptionAccountId.value)
    : null
  return currentAccountId === streamAccountId && String(subscriptionStatus.value || '') === ''
})

const holdings = computed(() => {
  return (Array.isArray(snapshotState.value.positions) ? snapshotState.value.positions : []).map((item) => {
    const symbol = String(item.symbol || '').trim().toUpperCase()
    const quote = liveQuoteMap.value[symbol] || {}
    const quantity = Number(item.quantity || 0)
    const avgPrice = Number(item.avgPrice ?? item.avg_price ?? 0)
    const currentPrice = Number(quote.last_price ?? quote.price ?? item.currentPrice ?? item.current_price ?? 0)
    const pnlValue = (currentPrice - avgPrice) * quantity
    return {
      ...item,
      symbol,
      currentPrice,
      pnlValue,
      priceText: formatMoney(currentPrice),
      costText: formatMoney(avgPrice),
      pnlText: `${pnlValue >= 0 ? '+' : '-'}${formatMoney(Math.abs(pnlValue), { signed: false })}`,
      qtyText: formatNumber(quantity, 0)
    }
  })
})

const activeOrders = computed(() => {
  const rows = hasOrderStreamCoverage.value ? streamedOrders.value : projectedOrders.value
  return (Array.isArray(rows) ? rows : []).slice(0, 10)
})
const activeOrderMeta = computed(() => {
  if (hasOrderStreamCoverage.value) {
    return streamedOrderMeta.value && typeof streamedOrderMeta.value === 'object'
      ? streamedOrderMeta.value
      : {}
  }
  return {
    snapshotAt: projectionMeta.value?.snapshotAt || '',
    dataSource: projectionMeta.value?.dataSource || 'order-projection',
    ...(projectionMeta.value?.meta && typeof projectionMeta.value.meta === 'object' ? projectionMeta.value.meta : {})
  }
})
const accountMetaSources = computed(() => (
  snapshotState.value.meta?.sources && typeof snapshotState.value.meta.sources === 'object'
    ? snapshotState.value.meta.sources
    : {}
))
const activeOrderSourceLabel = computed(() => formatReadModelSourceLabel(activeOrderMeta.value?.sources?.orders || 'trade_order_projections'))
const activeOrderOverlayLabel = computed(() => {
  const overlays = Array.isArray(activeOrderMeta.value?.realtimeOverlay) ? activeOrderMeta.value.realtimeOverlay : []
  return overlays.includes('order-stream') ? '订单推送' : ''
})

const accountSummary = computed(() => {
  const info = snapshotState.value.accountInfo || {}
  const cash = Number(info.cash || 0)
  const marketValue = holdings.value.reduce((sum, item) => sum + Number(item.currentPrice || 0) * Number(item.quantity || 0), 0)
  const cost = holdings.value.reduce((sum, item) => sum + Number(item.avgPrice || item.avg_price || 0) * Number(item.quantity || 0), 0)
  const pnl = holdings.value.reduce((sum, item) => sum + Number(item.pnlValue || 0), 0)
  const pnlRatio = cost > 0 ? (pnl / cost) * 100 : 0
  return {
    totalAssets: cash + marketValue,
    cash,
    marketValue,
    pnl,
    pnlRatio
  }
})

const accountCards = computed(() => ({
  totalAssets: formatMoney(accountSummary.value.totalAssets),
  cash: formatMoney(accountSummary.value.cash),
  marketValue: formatMoney(accountSummary.value.marketValue),
  dailyPnL: `${accountSummary.value.pnl >= 0 ? '+' : '-'}${formatMoney(Math.abs(accountSummary.value.pnl), { signed: false })} (${formatPercent(accountSummary.value.pnlRatio, true)})`
}))

const accountPnLClass = computed(() => (accountSummary.value.pnl >= 0 ? 'text-green-400' : 'text-red-400'))

const accountSourceSummary = computed(() => {
  if (!selectedAccount.value) {
    return {
      detail: '先选择账户；未选账户时仍可查看市场研判。',
      statusText: '等待账户接入',
      statusType: 'warning',
      updatedAt: '',
      updatedPrefix: '快照于',
      tags: [
        { type: 'warning', text: '未选择账户' },
        { type: 'info', text: '市场研判可用' }
      ]
    }
  }

  const summary = buildAccountReadModelSummary({
    source: snapshotState.value.dataSource || 'snapshot',
    snapshotAt: snapshotState.value.snapshotAt || snapshotState.value.meta?.snapshotAt || '',
    accountLabel: selectedAccountName.value,
    quotesConnected: quotesConnected.value,
    orderStreamConnected: hasOrderStreamCoverage.value,
    positionCount: holdings.value.length,
    orderCount: activeOrders.value.length
  })

  return {
    ...summary,
    detail: '账户资产、持仓与订单按最近状态展示。',
    tags: [
      ...summary.tags,
      {
        type: activeOrderMeta.value?.snapshotAt ? 'info' : 'warning',
        text: activeOrderMeta.value?.snapshotAt ? `订单 ${activeOrderSourceLabel.value}` : '等待订单'
      },
      {
        type: hasOrderStreamCoverage.value ? 'success' : 'info',
        text: hasOrderStreamCoverage.value
          ? `${activeOrderOverlayLabel.value || '订单推送'}中`
          : '快照'
      }
    ]
  }
})

const accountSourceUpdatedAt = computed(() => (
  accountSourceSummary.value.updatedAt ? formatDateTime(accountSourceSummary.value.updatedAt) : ''
))

const aiRows = computed(() => {
  const rows = (Array.isArray(trendScans.value) ? trendScans.value : []).slice(0, 8)
  if (rows.length) {
    return rows.map((item) => ({
      symbol: item.symbol,
      status: normalizeDecision(item.finalDecision || item.finalSignal),
      time: formatDateTime(item.analysisTime),
      gemma: item.scanLayers?.[0]?.summary || item.marketSummary?.summary || item.reason || '等待分析结果',
      llama: item.scanLayers?.[1]?.summary || item.reason || '等待风险分层结果',
      deepseek: item.scanLayers?.[2]?.summary || item.finalDecision || '等待决策终审结果'
    }))
  }

  return (Array.isArray(quantStatus.value?.signals) ? quantStatus.value.signals : []).slice(0, 8).map((item) => ({
    symbol: item.symbol || '--',
    status: normalizeDecision(item.side || item.signal || 'HOLD'),
    time: formatDateTime(item.createdAt || item.updatedAt),
    gemma: item.reason || '量化信号待补充',
    llama: item.marketSummary || '等待风险说明',
    deepseek: `置信度 ${Number(item.confidence || 0).toFixed(2)}%`
  }))
})

const latestAnalysisAt = computed(() => {
  return (Array.isArray(trendScans.value) ? trendScans.value : [])
    .map((item) => item.analysisTime)
    .filter(Boolean)
    .sort((a, b) => String(b).localeCompare(String(a)))[0] || ''
})

const trendReadModelSummary = computed(() => buildTrendScanReadModelSummary(
  trendScanMeta.value,
  { count: trendScans.value.length }
))
const marketReadModelSummary = computed(() => buildMarketInsightReadModelSummary(
  marketInsightMeta.value,
  { count: marketInsights.value.length, quoteCoverageLabel: marketInsights.value.length ? `${marketInsights.value.length} 条市场快照` : '市场快照待补齐', label: '交易看板分析' }
))
const analysisSourceSummary = computed(() => ({
  detail: aiRows.value.length
    ? `${trendReadModelSummary.value.detail} ${marketReadModelSummary.value.detail}`
    : '当前会先等待趋势扫描和市场快照入库；若还没有结果，就回退展示最近量化信号。',
  statusText: aiRows.value.length ? '分析快照' : '等待扫描结果',
  statusType: aiRows.value.length ? 'info' : 'warning',
  updatedAt: latestAnalysisAt.value || trendReadModelSummary.value.updatedAt || marketReadModelSummary.value.updatedAt || '',
  updatedPrefix: '扫描于',
  tags: [
    ...(trendReadModelSummary.value.tags || []).slice(0, 2),
    { type: quantStatus.value.enabled ? 'success' : 'info', text: quantStatus.value.enabled ? '量化已启用' : '量化未启用' },
    { type: marketInsights.value.length ? 'info' : 'warning', text: marketInsights.value.length ? `${marketInsights.value.length} 条市场快照` : '等待市场快照' }
  ]
}))

const analysisSourceUpdatedAt = computed(() => (
  analysisSourceSummary.value.updatedAt ? formatDateTime(analysisSourceSummary.value.updatedAt) : ''
))

const scanFeed = computed(() => {
  const marketFeed = (Array.isArray(marketInsights.value) ? marketInsights.value : []).slice(0, 4).map((item) => ({
    time: formatDateTime(item.generatedAt),
    sortKey: item.generatedAt || '',
    content: `${item.marketLabel || item.market || '市场'}：${item.summary || '等待市场快照'}`
  }))
  const signalFeed = (Array.isArray(quantStatus.value?.signals) ? quantStatus.value.signals : []).slice(0, 6).map((item) => ({
    time: formatDateTime(item.createdAt || item.updatedAt),
    sortKey: item.createdAt || item.updatedAt || '',
    content: `量化信号 ${item.side || 'HOLD'} ${item.symbol || '--'}，置信度 ${Number(item.confidence || 0).toFixed(2)}%`
  }))
  const orderFeed = activeOrders.value.slice(0, 6).map((item) => ({
    time: formatDateTime(item.updateTime || item.createTime),
    sortKey: item.updateTime || item.createTime || '',
    content: `订单 ${item.action === 'buy' ? 'BUY' : 'SELL'} ${item.symbol} ${formatNumber(item.quantity, 0)} 股，状态 ${item.status || '--'}`
  }))

  return [...marketFeed, ...signalFeed, ...orderFeed]
    .filter((item) => item.content)
    .sort((left, right) => String(right.sortKey || '').localeCompare(String(left.sortKey || '')))
    .slice(0, 20)
    .map((item) => ({ time: item.time || '--', content: item.content }))
})

const updateClock = () => {
  currentTime.value = formatDateTime(new Date().toISOString())
}

const loadAccounts = async () => {
  const res = await getBrokerAccounts()
  accounts.value = Array.isArray(res.data) ? res.data : []
  if (!selectedAccount.value && accounts.value.length) {
    const defaultAccount = accounts.value.find((item) => item.isDefault || item.is_default)
    selectedAccount.value = defaultAccount?.id || accounts.value[0].id
  }
}

const loadTradeSnapshot = async () => {
  if (!selectedAccount.value) {
    snapshotState.value = { accountInfo: {}, positions: [], orders: [], snapshotAt: '', dataSource: 'snapshot', meta: {} }
    return
  }
  const res = await getTradeSnapshotState(selectedAccount.value)
  snapshotState.value = res.data || { accountInfo: {}, positions: [], orders: [], snapshotAt: '', dataSource: 'snapshot', meta: {} }
}

const loadProjectedOrders = async () => {
  if (!selectedAccount.value) {
    projectedOrders.value = []
    projectionMeta.value = { snapshotAt: '', dataSource: 'order-projection', meta: {}, warnings: [] }
    return
  }
  const res = await getProjectedOrders({ account_id: selectedAccount.value, limit: 20 })
  projectedOrders.value = Array.isArray(res.data?.list) ? res.data.list : []
  projectionMeta.value = {
    snapshotAt: res.data?.snapshotAt || '',
    dataSource: res.data?.dataSource || 'order-projection',
    meta: res.data?.meta || {},
    warnings: Array.isArray(res.data?.warnings) ? res.data.warnings : []
  }
}

const loadAnalysisData = async () => {
  const symbols = holdingSymbols.value.slice(0, 8)
  const [marketRes, quantRes, trendRes] = await Promise.allSettled([
    getDashboardMarketInsights(),
    getQuantStatus(),
    getLatestTrendScans(symbols.length ? { symbols, limit: 8 } : { limit: 8 })
  ])

  marketInsights.value = marketRes.status === 'fulfilled' && Array.isArray(marketRes.value?.data) ? marketRes.value.data : []
  marketInsightMeta.value = marketRes.status === 'fulfilled' && marketRes.value?.meta && typeof marketRes.value.meta === 'object'
    ? marketRes.value.meta
    : {}
  quantStatus.value = quantRes.status === 'fulfilled' ? (quantRes.value?.data || { enabled: false, signals: [] }) : { enabled: false, signals: [] }
  trendScans.value = trendRes.status === 'fulfilled' && Array.isArray(trendRes.value?.data) ? trendRes.value.data : []
  trendScanMeta.value = trendRes.status === 'fulfilled' && trendRes.value?.meta && typeof trendRes.value.meta === 'object'
    ? trendRes.value.meta
    : {}
}

const refreshAll = async () => {
  try {
    await loadTradeSnapshot()
    await Promise.allSettled([
      loadProjectedOrders(),
      loadAnalysisData()
    ])
  } catch (error) {
    console.error('TradingView 刷新失败:', error)
  }
}

const startTimers = () => {
  stopTimers()
  updateClock()
  clockTimer = window.setInterval(updateClock, 1000)
  refreshTimer = window.setInterval(() => {
    refreshAll()
  }, AUTO_REFRESH_INTERVAL)
}

const stopTimers = () => {
  if (clockTimer) {
    window.clearInterval(clockTimer)
    clockTimer = null
  }
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const normalizeDecision = (value) => {
  const text = String(value || '').toLowerCase()
  if (text.includes('buy') || text.includes('买') || text.includes('bull')) return 'BUY'
  if (text.includes('sell') || text.includes('卖') || text.includes('bear')) return 'SELL'
  return 'HOLD'
}

const formatMoney = (value, options = {}) => formatCurrencyValue(value, { currency: '$', fallback: '$0.00', ...options })
const formatPercent = (value, keepSign = false) => formatPercentDisplay(value, { signed: keepSign })
const formatNumber = (value, digits = 2) => Number(value || 0).toFixed(digits)
const formatDateTime = (value) => {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

watch(selectedAccount, async (nextValue, previousValue) => {
  if (!nextValue || nextValue === previousValue) {
    return
  }
  await refreshAll()
})

onMounted(async () => {
  startTimers()
  await loadAccounts()
  if (selectedAccount.value) {
    await refreshAll()
  }
})

onUnmounted(() => {
  stopTimers()
})
</script>

<style scoped>
.glow-text {
  text-shadow: 0 0 10px rgba(59, 130, 246, 0.5);
}

.source-strip-shell :deep(.readmodel-source-strip) {
  border-color: rgba(31, 41, 55, 0.95);
  background: rgba(17, 24, 39, 0.92);
}

.source-strip-shell :deep(.source-label),
.source-strip-shell :deep(.source-time) {
  color: #9ca3af;
}

.source-strip-shell :deep(.source-detail) {
  color: #e5e7eb;
}

.custom-scroll::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.custom-scroll::-webkit-scrollbar-track {
  background: rgba(31, 41, 55, 0.5);
  border-radius: 3px;
}

.custom-scroll::-webkit-scrollbar-thumb {
  background: rgba(107, 114, 128, 0.5);
  border-radius: 3px;
}

.custom-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(107, 114, 128, 0.8);
}
</style>

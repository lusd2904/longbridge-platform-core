<template>
  <div class="market-page">
    <PageHero
      title="实时行情"
      :chips="marketHeroChips"
      :metrics="marketHeroMetrics"
      :compact="isPhoneLayout"
    >
      <template #actions>
        <div class="header-actions">
          <el-radio-group v-model="selectedMarket" size="large" @change="changeMarket">
            <el-radio-button value="US">美股</el-radio-button>
            <el-radio-button value="CN">A股</el-radio-button>
            <el-radio-button value="HK">港股</el-radio-button>
          </el-radio-group>
          <el-select
            v-model="selectedInsightTime"
            class="insight-time-select"
            placeholder="选择分析时刻"
            @change="handleInsightTimeChange"
          >
            <el-option
              v-for="item in insightHistory"
              :key="item.generatedAt"
              :label="formatInsightOption(item)"
              :value="item.generatedAt"
            />
          </el-select>
          <el-button
            v-if="access.canManageTasks"
            :loading="insightRefreshing"
            @click="refreshMarketInsightNow"
          >
            刷新分析
          </el-button>
          <el-button v-if="!isPhoneLayout" plain :disabled="!selectedRows.length" @click="openBatchKline">
            多标的K线
          </el-button>
        </div>
      </template>
    </PageHero>

    <ReadModelSourceStrip
      label="行情状态"
      :status-text="marketReadModelStatus"
      :status-type="marketReadModelStatusType"
      :updated-at="marketReadModelUpdatedAt"
      :updated-prefix="marketReadModelUpdatedPrefix"
      :tags="marketReadModelTags"
      :compact="isPhoneLayout"
    />

    <MetricStrip v-if="!isPhoneLayout && marketIndexMetrics.length" class="market-overview-strip" :items="marketIndexMetrics" />

    <!-- 行情表格 -->
    <MobileSegmentControl
      v-if="isPhoneLayout"
      v-model="activeMarketSection"
      class="mobile-market-rail"
      label="行情分段"
      :items="marketMobileSections"
    />

    <div v-if="isPhoneLayout && activeMarketSection !== 'watch'" class="mobile-market-summary">
      <MetricStrip v-if="marketIndexMetrics.length" class="mobile-market-overview" :items="marketIndexMetrics" compact />
    </div>

    <el-card class="market-table" v-if="!isPhoneLayout || activeMarketSection === 'watch'">
      <template #header>
        <SectionCardHeader :title="`${marketName}行情`">
          <template #actions>
            <el-input
              v-model="searchKeyword"
              placeholder="搜索股票代码或名称"
              :prefix-icon="Search"
              clearable
              style="width: 280px"
              @input="handleSearch"
            />
          </template>
        </SectionCardHeader>
      </template>
      <div v-if="quoteSyncActive" class="quote-sync-rail">
        <div class="quote-sync-copy">
          <span class="sync-dot" />
          <strong>{{ quoteSyncTitle }}</strong>
          <span>{{ quoteSyncHint }}</span>
        </div>
        <div class="quote-sync-metrics">
          <span class="metric-pill">实时 {{ realtimeReadyCount }}/{{ pagedQuotes.length }}</span>
          <span class="metric-pill subdued">快照 {{ snapshotFallbackCount }}</span>
          <span v-if="quotePendingCount" class="metric-pill subdued">待补齐 {{ quotePendingCount }}</span>
        </div>
      </div>
      <el-alert
        v-if="loadError"
        class="table-alert"
        type="warning"
        :closable="false"
        show-icon
        :title="loadError"
      />
      <el-table
        v-if="!isPhoneLayout"
        :data="pagedQuotes"
        style="width: 100%"
        v-loading="loading"
        @selection-change="handleSelectionChange"
      >
        <template #empty>
          <div class="table-empty-state">
            <strong>{{ marketTableEmptyTitle }}</strong>
          </div>
        </template>
        <el-table-column type="selection" width="55" />
        <el-table-column prop="symbol" label="代码" width="100">
          <template #default="{ row }">
            <button type="button" class="symbol-button" @click="viewSymbolDetail(row)">
              {{ row.symbol }}
            </button>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="150">
          <template #default="{ row }">
            <button type="button" class="name-button" @click="viewSymbolDetail(row)">
              {{ row.name }}
            </button>
          </template>
        </el-table-column>
        <el-table-column prop="price" label="最新价" width="120">
          <template #default="{ row }">
            <template v-if="shouldShowQuotePlaceholder(row, 'price')">
              <span class="quote-placeholder">{{ quotePlaceholderLabel(row, 'price') }}</span>
            </template>
            <span v-else :class="effectiveChangePercent(row) >= 0 ? 'up' : 'down'">
              {{ formatCurrency(row.price) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="change" label="涨跌额" width="120">
          <template #default="{ row }">
            <template v-if="shouldShowQuotePlaceholder(row, 'change')">
              <span class="quote-placeholder">{{ quotePlaceholderLabel(row, 'change') }}</span>
            </template>
            <span v-else :class="approximateChange(row) >= 0 ? 'up' : 'down'">
              {{ formatSignedCurrency(approximateChange(row)) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="changePercent" label="涨跌幅" width="120">
          <template #default="{ row }">
            <template v-if="shouldShowQuotePlaceholder(row, 'changePercent')">
              <span class="quote-placeholder">{{ quotePlaceholderLabel(row, 'changePercent') }}</span>
            </template>
            <span v-else :class="effectiveChangePercent(row) >= 0 ? 'up' : 'down'">
              {{ formatPercent(effectiveChangePercent(row)) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="volume" label="成交量" width="120">
          <template #default="{ row }">
            <span v-if="shouldShowQuotePlaceholder(row, 'volume')" class="quote-placeholder">{{ quotePlaceholderLabel(row, 'volume') }}</span>
            <template v-else>
              {{ formatVolume(row.volume) }}
            </template>
          </template>
        </el-table-column>
        <el-table-column prop="high" label="最高" width="100">
          <template #default="{ row }">
            <span v-if="shouldShowQuotePlaceholder(row, 'high')" class="quote-placeholder">{{ quotePlaceholderLabel(row, 'high') }}</span>
            <template v-else>
              {{ formatCurrency(row.high) }}
            </template>
          </template>
        </el-table-column>
        <el-table-column prop="low" label="最低" width="100">
          <template #default="{ row }">
            <span v-if="shouldShowQuotePlaceholder(row, 'low')" class="quote-placeholder">{{ quotePlaceholderLabel(row, 'low') }}</span>
            <template v-else>
              {{ formatCurrency(row.low) }}
            </template>
          </template>
        </el-table-column>
        <el-table-column label="数据源" width="124">
          <template #default="{ row }">
            <span class="quote-source-pill" :class="quoteSourceTone(row)">
              {{ quoteSourceLabel(row) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button type="info" size="small" link @click="viewSymbolDetail(row)">
              详情
            </el-button>
            <el-button type="warning" size="small" link @click="openSingleKline(row)">
              K线
            </el-button>
            <el-button type="primary" size="small" link @click="addToPool(row)">
              加入股票池
            </el-button>
            <el-button type="success" size="small" link @click="quickTrade(row)">
              交易
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="mobile-quote-list" v-loading="loading">
        <article v-for="row in pagedQuotes" :key="row.symbol" class="mobile-quote-card">
          <div class="mobile-quote-head">
            <div>
              <button type="button" class="symbol-button" @click="viewSymbolDetail(row)">{{ row.symbol }}</button>
              <strong>{{ row.name }}</strong>
            </div>
            <div class="mobile-quote-price" :class="effectiveChangePercent(row) >= 0 ? 'up' : 'down'">
              <span>{{ shouldShowQuotePlaceholder(row, 'price') ? quotePlaceholderLabel(row, 'price') : formatCurrency(row.price) }}</span>
              <small>{{ shouldShowQuotePlaceholder(row, 'changePercent') ? quotePlaceholderLabel(row, 'changePercent') : formatPercent(effectiveChangePercent(row)) }}</small>
            </div>
          </div>

          <div class="mobile-quote-meta">
            <span class="quote-source-pill" :class="quoteSourceTone(row)">{{ quoteSourceLabel(row) }}</span>
            <span>成交量 {{ shouldShowQuotePlaceholder(row, 'volume') ? quotePlaceholderLabel(row, 'volume') : formatVolume(row.volume) }}</span>
            <span>最高 {{ shouldShowQuotePlaceholder(row, 'high') ? quotePlaceholderLabel(row, 'high') : formatCurrency(row.high) }}</span>
            <span>最低 {{ shouldShowQuotePlaceholder(row, 'low') ? quotePlaceholderLabel(row, 'low') : formatCurrency(row.low) }}</span>
          </div>

          <div class="mobile-quote-actions">
            <el-button type="info" size="small" plain @click="viewSymbolDetail(row)">详情</el-button>
            <el-button type="warning" size="small" plain @click="openSingleKline(row)">K线</el-button>
            <el-button type="primary" size="small" plain @click="addToPool(row)">自选</el-button>
            <el-button type="success" size="small" @click="quickTrade(row)">交易</el-button>
          </div>
        </article>
        <el-empty v-if="!pagedQuotes.length && !loading" :description="marketTableEmptyTitle" />
      </div>

      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="totalQuotes"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadMarketData"
          @size-change="handlePageSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { addStockToPool, getMarketInsightHistory, getMarketInsightsAtTime, getStockPool } from '../api/market.js'
import { runPlatformTask } from '../api/platform.js'
import { useStockQuotes } from '../composables/useWebSocket.js'
import { getAccess, getCurrentUser } from '../utils/auth.js'
import { formatCurrency as formatCurrencyValue, formatPercent as formatPercentDisplay } from '../utils/formatters.js'
import { getQuoteSnapshotAt, summarizeQuoteSnapshotCoverage } from '../utils/quoteSnapshot.js'
import { buildMarketInsightReadModelSummary, buildStockPoolReadModelSummary, formatQuoteCoverageLabel, formatQuoteSnapshotTimeLabel } from '../utils/readModelSource.js'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import { useAdaptiveLayout } from '../composables/useAdaptiveLayout.js'
import MobileSegmentControl from '../components/common/MobileSegmentControl.vue'
import PageHero from '../components/common/PageHero.vue'
import MetricStrip from '../components/common/MetricStrip.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'

const router = useRouter()
const { isPhoneLayout } = useAdaptiveLayout()
const activeMarketSection = ref('pulse')
const currentUser = getCurrentUser() || {}
const access = getAccess() || {}
const loading = ref(false)
const hasLoadedMarketData = ref(false)
const selectedMarket = ref('US')
const searchKeyword = ref('')
const quotes = ref([])
const marketInsights = ref([])
const marketInsightMeta = ref({})
const stockPoolMeta = ref({})
const insightHistory = ref([])
const selectedInsightTime = ref('')
const loadError = ref('')
const insightRefreshing = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)
const totalQuotes = ref(0)
const selectedRows = ref([])
let searchTimer = null
let marketDataRequestId = 0

const marketMobileSections = computed(() => ([
  { value: 'pulse', label: '脉冲', note: currentMarketInsight.value?.generatedAt || '市场节奏' },
  { value: 'watch', label: '列表', note: `${pagedQuotes.value.length} 个标的` }
]))

const marketName = computed(() => {
  const names = { US: '美股', CN: 'A股', HK: '港股' }
  return names[selectedMarket.value] || '美股'
})

const currentMarketInsight = computed(() => {
  return marketInsights.value.find((item) => item.market === selectedMarket.value) || null
})
const streamSymbols = computed(() => {
  const pageSymbols = pagedQuotesBase.value.map((item) => item.symbol).filter(Boolean)
  const benchmarkSymbols = (currentMarketInsight.value?.benchmarks || []).map((item) => item.symbol).filter(Boolean)
  return Array.from(new Set([...pageSymbols, ...benchmarkSymbols]))
})
const { quotes: liveQuoteMap, isConnected: wsConnected } = useStockQuotes(streamSymbols, {
  userId: currentUser?.id || null
})
const hasReliableDelta = (row = {}) => {
  const prevClose = Number(row.prevClose ?? row.prev_close ?? 0)
  const rawChange = Number(row.change ?? 0)
  const rawPercent = Number(row.changePercent ?? row.change_percent ?? 0)
  return Boolean(prevClose || rawChange || rawPercent)
}
const pickFiniteNumber = (...values) => {
  for (const value of values) {
    const numeric = Number(value)
    if (Number.isFinite(numeric)) {
      return numeric
    }
  }
  return null
}
const pickPositiveNumber = (...values) => {
  for (const value of values) {
    const numeric = Number(value)
    if (Number.isFinite(numeric) && numeric > 0) {
      return numeric
    }
  }
  return null
}
const toTimestampMs = (value) => {
  if (!value) return 0
  const parsed = Date.parse(String(value))
  return Number.isFinite(parsed) ? parsed : 0
}
const isQuoteRealtime = (row = {}) => {
  const mode = String(row.quoteMode ?? row.quote_mode ?? '').trim().toLowerCase()
  if (mode) {
    return mode === 'push'
  }
  return Boolean(row.isRealtime)
}
const hasSnapshotFallback = (row = {}) => {
  return Boolean(
    row.quoteReady ||
    row.quote_ready ||
    row.quoteSnapshotAt ||
    row.quote_snapshot_at ||
    row.snapshotAt ||
    row.snapshot_at
  )
}
const quoteSourceLabel = (row = {}) => {
  if (isQuoteRealtime(row)) return '实时'
  if (hasSnapshotFallback(row)) return '快照'
  return '待补齐'
}
const quoteSourceTone = (row = {}) => {
  if (isQuoteRealtime(row)) return 'realtime'
  if (hasSnapshotFallback(row)) return 'snapshot'
  return 'pending'
}
const resolveRealtimePrice = (realtime = {}, fallback = {}) => {
  const price = Number(realtime.last_price ?? realtime.price ?? fallback.price ?? 0)
  return Number.isFinite(price) ? price : Number(fallback.price ?? 0)
}
const resolveRealtimeChangePercent = (realtime = {}, fallback = {}) => {
  const explicit = realtime.change_percent ?? realtime.changePercent ?? realtime.change_rate ?? realtime.changeRate
  if (explicit !== null && explicit !== undefined && explicit !== '') {
    const numeric = Number(explicit)
    if (Number.isFinite(numeric)) {
      return numeric
    }
  }

  const price = resolveRealtimePrice(realtime, fallback)
  const prevClose = Number(realtime.prev_close ?? realtime.prevClose ?? fallback.prevClose ?? fallback.prev_close ?? 0)
  if (prevClose) {
    return ((price - prevClose) / prevClose) * 100
  }

  return Number(fallback.changePercent ?? fallback.change_percent ?? 0)
}
const mergeRealtimeQuote = (row = {}) => {
  const symbol = String(row.symbol || '').toUpperCase()
  const realtime = liveQuoteMap.value[symbol]
  if (!realtime) {
    return row
  }
  const realtimeTimestamp = realtime.timestamp || realtime.pushReceivedAt || realtime.updatedAt || ''
  const fallbackTimestamp = row.updatedAt || row.quoteSnapshotAt || row.snapshotAt || ''
  if (toTimestampMs(realtimeTimestamp) && toTimestampMs(fallbackTimestamp) > toTimestampMs(realtimeTimestamp)) {
    return row
  }

  const price = resolveRealtimePrice(realtime, row)
  const prevClose = Number(realtime.prev_close ?? realtime.prevClose ?? row.prev_close ?? row.prevClose ?? 0)
  const changePercent = resolveRealtimeChangePercent(realtime, row)
  const high = pickPositiveNumber(realtime.high, row.high, price) ?? price
  const low = pickPositiveNumber(realtime.low, row.low, price) ?? price
  const volume = pickFiniteNumber(realtime.volume, row.volume, 0) ?? 0
  const open = pickPositiveNumber(realtime.open, row.open, 0) ?? 0
  const change = pickFiniteNumber(
    realtime.change,
    realtime.change_value,
    row.change,
    prevClose ? price - prevClose : 0
  ) ?? 0
  const quoteMode = String(realtime.quoteMode ?? realtime.quote_mode ?? '').trim() || 'push'
  const timestamp = realtime.timestamp || realtime.pushReceivedAt || row.updatedAt || null

  return {
    ...row,
    price,
    prevClose,
    prev_close: prevClose,
    change,
    volume,
    changePercent,
    change_percent: changePercent,
    open,
    high,
    low,
    updatedAt: timestamp,
    quoteReady: true,
    quoteMode,
    quote_mode: quoteMode,
    quoteSource: realtime.quoteSource || realtime.quote_source || (quoteMode === 'push' ? 'longbridge-push' : 'quote-snapshot'),
    quote_source: realtime.quoteSource || realtime.quote_source || (quoteMode === 'push' ? 'longbridge-push' : 'quote-snapshot'),
    isRealtime: quoteMode === 'push',
    snapshotAt: realtime.snapshotAt || row.snapshotAt || row.quoteSnapshotAt || null,
    quoteSnapshotAt: realtime.snapshotAt || row.quoteSnapshotAt || row.updatedAt || null
  }
}
const pagedQuotesBase = computed(() => quotes.value)
const pagedQuotes = computed(() => pagedQuotesBase.value.map((item) => mergeRealtimeQuote(item)))
const quoteCoverage = computed(() => summarizeQuoteSnapshotCoverage(pagedQuotesBase.value))
const quoteReadyCount = computed(() => quoteCoverage.value.readyCount)
const realtimeReadyCount = computed(() => pagedQuotes.value.filter((item) => isQuoteRealtime(item)).length)
const snapshotFallbackCount = computed(() => pagedQuotes.value.filter((item) => !isQuoteRealtime(item) && hasSnapshotFallback(item)).length)
const quotePendingCount = computed(() => quoteCoverage.value.pendingCount)
const quoteSyncActive = computed(() => wsConnected.value && pagedQuotes.value.length > 0)
const quoteSyncTitle = computed(() => {
  if (realtimeReadyCount.value === pagedQuotes.value.length && pagedQuotes.value.length) {
    return '当前页标的实时推送中'
  }
  if (realtimeReadyCount.value > 0) {
    return '当前页标的部分实时推送，剩余使用快照兜底'
  }
  return '当前页标的已订阅，等待实时推送'
})
const quoteSyncHint = computed(() => {
  if (snapshotFallbackCount.value > 0) {
    return '快照数据仅作兜底，收到 push 后会立即覆盖最新价、涨跌、成交量与高低价。'
  }
  return '页面仅对当前页与当前可见基准标的保持订阅。'
})
const quoteSnapshotUpdatedAt = computed(() => quoteCoverage.value.latestSnapshotAt || '')
const quoteSnapshotTag = computed(() => formatQuoteSnapshotTimeLabel(quoteSnapshotUpdatedAt.value, formatDateTime))
const quoteStatusTag = computed(() => {
  if (realtimeReadyCount.value > 0) {
    return {
      type: 'success',
      text: snapshotFallbackCount.value > 0 ? '实时 + 快照兜底' : '实时推送'
    }
  }
  if (snapshotFallbackCount.value > 0) {
    return {
      type: wsConnected.value ? 'info' : 'warning',
      text: wsConnected.value ? '已订阅，快照兜底' : '报价快照'
    }
  }
  if (wsConnected.value && pagedQuotes.value.length) {
    return { type: 'info', text: '等待实时推送' }
  }
  return { type: 'warning', text: '等待报价快照' }
})
const marketHeroChips = computed(() => ([
  { text: quoteStatusTag.value.text, tone: quoteStatusTag.value.type === 'success' ? 'healthy' : quoteStatusTag.value.type },
  { text: quoteSnapshotTag.value },
  { text: selectedInsightTime.value ? '历史时刻' : '最新时刻', tone: selectedInsightTime.value ? 'warning' : 'healthy' },
  {
    text: totalQuotes.value ? `${totalQuotes.value} 个标的` : (loading.value && !hasLoadedMarketData.value ? '加载中' : '等待标的'),
    tone: totalQuotes.value ? 'healthy' : 'info'
  }
]))
const marketInsightQuoteCoverageLabel = computed(() => (
  formatQuoteCoverageLabel(quoteCoverage.value, {
    prefix: '报价快照',
    emptyLabel: '报价快照待补齐'
  })
))
const marketInsightSummary = computed(() => buildMarketInsightReadModelSummary(
  marketInsightMeta.value,
  {
    count: marketInsights.value.length,
    quoteCoverageLabel: currentMarketInsight.value?.quoteSourceTag || marketInsightQuoteCoverageLabel.value,
    label: `${marketName.value} 行情`
  }
))
const stockPoolSummary = computed(() => buildStockPoolReadModelSummary(
  stockPoolMeta.value,
  {
    count: quotes.value.length,
    total: totalQuotes.value,
    marketLabel: marketName.value,
    quoteCoverageLabel: quoteReadyCount.value
      ? `报价快照 ${quoteReadyCount.value}/${pagedQuotes.value.length || 0}`
      : '报价快照待补齐'
  }
))
const marketReadModelStatus = computed(() => {
  if (wsConnected.value && pagedQuotes.value.length) {
    return realtimeReadyCount.value ? '实时行情在线' : '已订阅实时行情'
  }
  if (quoteReadyCount.value > 0 || marketInsightSummary.value.updatedAt || stockPoolSummary.value.updatedAt || totalQuotes.value > 0) {
    return '行情快照兜底'
  }
  return '等待行情快照'
})
const marketReadModelStatusType = computed(() => (
  realtimeReadyCount.value > 0
    ? 'success'
    : (quoteReadyCount.value > 0 || marketInsightSummary.value.updatedAt || totalQuotes.value > 0 || (wsConnected.value && pagedQuotes.value.length))
        ? 'info'
        : 'warning'
))
const marketReadModelUpdatedAt = computed(() => {
  const timestamp = quoteSnapshotUpdatedAt.value || marketInsightSummary.value.updatedAt || stockPoolSummary.value.updatedAt || ''
  return timestamp ? formatDateTime(timestamp) : ''
})
const marketReadModelUpdatedPrefix = computed(() => (
  '更新于'
))
const marketReadModelTags = computed(() => {
  const tags = [
    ...(stockPoolSummary.value.tags || []).slice(0, 3),
    ...(marketInsightSummary.value.tags || []).slice(0, 2)
  ]
  if (pagedQuotes.value.length) {
    tags.push({
      type: wsConnected.value ? 'success' : 'info',
      text: wsConnected.value ? `实时 ${realtimeReadyCount.value}/${pagedQuotes.value.length}` : `${pagedQuotes.value.length} 个标的`
    })
  }
  if (selectedInsightTime.value) {
    tags.push({ type: 'warning', text: '历史时刻' })
  }
  return tags
})
const marketIndices = computed(() => {
  const benchmarks = currentMarketInsight.value?.benchmarks || []
  return benchmarks.slice(0, 4).map((item) => ({
    ...item,
    price: resolveRealtimePrice(liveQuoteMap.value[item.symbol], item),
    changePercent: resolveRealtimeChangePercent(liveQuoteMap.value[item.symbol], item),
    roleLabel: benchmarkRoleLabel(item.role)
  }))
})
const marketHeroMetrics = computed(() => [
  {
    label: '分析时刻',
    value: currentMarketInsight.value?.generatedAt || '--',
    note: selectedInsightTime.value ? '历史时刻' : '最新快照'
  },
  {
    label: '市场分数',
    value: Number(currentMarketInsight.value?.marketScore || 0).toFixed(2),
    note: currentMarketInsight.value?.headline || `${marketName.value} 大盘脉冲`
  },
  {
    label: '报价进度',
    value: `${realtimeReadyCount.value}/${pagedQuotes.value.length || 0}`,
    note: wsConnected.value ? '实时推送覆盖' : '快照兜底',
    tone: wsConnected.value ? 'healthy' : ''
  }
])
const marketTableEmptyTitle = computed(() => {
  if (loading.value && !pagedQuotes.value.length) return '行情加载中'
  if (!hasLoadedMarketData.value) return '等待行情数据'
  if (searchKeyword.value) return '没有找到匹配的标的'
  return `${marketName.value} 暂无可展示行情`
})
const marketIndexMetrics = computed(() => (
  marketIndices.value.map((item) => ({
    label: item.name,
    value: formatIndexValue(item.price),
    note: `${item.roleLabel} · ${formatPercent(item.changePercent)}`,
    tone: item.changePercent >= 0 ? 'healthy' : 'error'
  }))
))

const inferQuoteReady = (row = {}) => {
  const quoteBase = Boolean(
    row.price ||
    row.prevClose ||
    row.prev_close ||
    row.high ||
    row.low ||
    row.open ||
    row.quoteSnapshotAt ||
    row.quote_snapshot_at
  )
  return row.quoteReady ?? row.quote_ready ?? quoteBase
}

const normalizeQuoteRow = (row = {}) => {
  const price = Number(row.price ?? 0)
  const prevClose = Number(row.prevClose ?? row.prev_close ?? 0)
  const change = Number(row.change ?? (prevClose ? price - prevClose : 0))
  const changePercent = Number(
    row.changePercent ??
    row.change_percent ??
    (prevClose ? (change / prevClose) * 100 : 0)
  )

  return {
    ...row,
    symbol: row.symbol || '',
    name: row.name || row.symbol_name || row.company_name || row.symbol || '',
    market: row.market || selectedMarket.value,
    type: row.type || row.assetType || 'stock',
    price,
    change,
    prevClose,
    prev_close: prevClose,
    changePercent,
    change_percent: changePercent,
    volume: Number(row.volume ?? 0),
    high: Number(row.high ?? 0) > 0 ? Number(row.high) : price,
    low: Number(row.low ?? 0) > 0 ? Number(row.low) : price,
    marketCap: Number(row.marketCap ?? row.market_cap ?? 0),
    market_cap: Number(row.marketCap ?? row.market_cap ?? 0),
    pe: row.pe === null || row.pe === undefined ? null : Number(row.pe),
    quoteReady: inferQuoteReady(row),
    quoteMode: inferQuoteReady(row) ? 'snapshot' : 'pending',
    quote_mode: inferQuoteReady(row) ? 'snapshot' : 'pending',
    quoteSource: row.quoteSource || row.quote_source || '',
    quoteSnapshotAt: getQuoteSnapshotAt(row),
    updatedAt: row.updatedAt || getQuoteSnapshotAt(row) || null
  }
}

const formatInsightOption = (item = {}) => {
  const suffix = item.marketCount ? ` · ${item.marketCount} 个市场` : ''
  return `${item.generatedAt || '--'}${suffix}`
}

const loadMarketInsights = async ({ resetSelection = false } = {}) => {
  const historyRes = await getMarketInsightHistory({
    market: selectedMarket.value,
    limit: 24
  })
  insightHistory.value = Array.isArray(historyRes?.data) ? historyRes.data : []

  if (resetSelection || !insightHistory.value.some((item) => item.generatedAt === selectedInsightTime.value)) {
    selectedInsightTime.value = insightHistory.value[0]?.generatedAt || ''
  }

  const insightRes = await getMarketInsightsAtTime(
    selectedInsightTime.value
      ? { market: selectedMarket.value, generated_at: selectedInsightTime.value }
      : { market: selectedMarket.value }
  )
  marketInsights.value = Array.isArray(insightRes?.data) ? insightRes.data : []
  marketInsightMeta.value = insightRes?.meta && typeof insightRes.meta === 'object' ? insightRes.meta : {}
}

const loadMarketData = async () => {
  const requestId = marketDataRequestId + 1
  marketDataRequestId = requestId
  loading.value = true
  loadError.value = ''
  try {
    const poolRes = await getStockPool({
      market: selectedMarket.value,
      search: searchKeyword.value,
      page: currentPage.value,
      page_size: pageSize.value
    })

    if (requestId !== marketDataRequestId) {
      return
    }

    const baseRows = Array.isArray(poolRes?.data) ? poolRes.data : []
    quotes.value = baseRows.map((row) => normalizeQuoteRow(row))
    totalQuotes.value = Number(poolRes?.total || quotes.value.length || 0)
    stockPoolMeta.value = poolRes?.meta && typeof poolRes.meta === 'object' ? poolRes.meta : {}
    hasLoadedMarketData.value = true

    if (!quotes.value.length && searchKeyword.value) {
      loadError.value = `没有找到与“${searchKeyword.value}”匹配的 ${marketName.value} 标的`
    }
  } catch (error) {
    if (requestId !== marketDataRequestId) {
      return
    }
    console.error('加载行情失败:', error)
    stockPoolMeta.value = {}
    hasLoadedMarketData.value = true
    loadError.value = error?.data?.error || error?.message || '行情数据加载失败，请稍后重试'
    ElMessage.error('加载行情失败')
  } finally {
    if (requestId === marketDataRequestId) {
      loading.value = false
    }
  }
}

const loadMarketInsightsSilently = async (options = {}) => {
  try {
    await loadMarketInsights(options)
  } catch (error) {
    console.error('加载市场分析失败:', error)
    marketInsightMeta.value = {}
  }
}

const changeMarket = () => {
  currentPage.value = 1
  selectedInsightTime.value = ''
  marketInsights.value = []
  insightHistory.value = []
  loadMarketData()
  loadMarketInsightsSilently({ resetSelection: true })
}

const handleInsightTimeChange = async () => {
  loading.value = true
  try {
    await loadMarketInsights()
  } catch (error) {
    console.error('切换分析时刻失败:', error)
    ElMessage.error(error?.data?.error || error?.message || '切换分析时刻失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  currentPage.value = 1
  if (searchTimer) {
    window.clearTimeout(searchTimer)
  }
  searchTimer = window.setTimeout(() => {
    loadMarketData()
  }, 260)
}

const handlePageSizeChange = () => {
  currentPage.value = 1
  loadMarketData()
}

const addToPool = async (row) => {
  try {
    await addStockToPool({
      symbol: row.symbol,
      market: selectedMarket.value,
      name: row.name
    })
    ElMessage.success('已加入股票池')
  } catch (error) {
    ElMessage.error('添加失败: ' + error.message)
  }
}

const handleSelectionChange = (rows = []) => {
  selectedRows.value = Array.isArray(rows) ? rows : []
}

const viewSymbolDetail = (row) => {
  router.push({
    name: 'SymbolDetail',
    params: { symbol: row.symbol }
  })
}

const openSingleKline = (row) => {
  router.push({
    name: 'Kline',
    query: { symbols: row.symbol }
  })
}

const openBatchKline = () => {
  const symbols = selectedRows.value.map((item) => item.symbol).filter(Boolean)
  if (!symbols.length) {
    ElMessage.warning('请先选择至少一个标的')
    return
  }
  router.push({
    name: 'Kline',
    query: { symbols: symbols.join(',') }
  })
}

const refreshMarketInsightNow = async () => {
  insightRefreshing.value = true
  try {
    await runPlatformTask('market_insight_refresh')
    selectedInsightTime.value = ''
    await loadMarketInsights({ resetSelection: true })
    ElMessage.success('市场分析已刷新')
  } catch (error) {
    console.error('刷新市场分析失败:', error)
    ElMessage.error(error?.data?.error || error?.message || '刷新市场分析失败')
  } finally {
    insightRefreshing.value = false
  }
}

const quickTrade = (row) => {
  router.push({
    name: 'Trading',
    query: { symbol: row.symbol }
  })
}

const benchmarkRoleLabel = (role) => {
  const map = {
    index: '宽基大盘',
    growth: '成长风向',
    value: '蓝筹风向',
    volatility: '波动监测',
    defensive: '防御资产',
    china: '中资联动'
  }
  return map[role] || '市场指标'
}

const formatCurrency = (value) => {
  const currency = selectedMarket.value === 'CN' ? '¥' : selectedMarket.value === 'HK' ? 'HK$' : '$'
  return formatCurrencyValue(value, { currency })
}

const formatIndexValue = (value) => {
  const currency = selectedMarket.value === 'CN' ? '' : selectedMarket.value === 'HK' ? 'HK$' : '$'
  return formatCurrencyValue(value, { currency, digits: 2, fallback: '--' })
}

const formatSignedCurrency = (value) => {
  const currency = selectedMarket.value === 'CN' ? '¥' : selectedMarket.value === 'HK' ? 'HK$' : '$'
  return formatCurrencyValue(value, { currency, signed: true, absolute: true })
}

const formatPercent = (value) => formatPercentDisplay(value)
const formatDateTime = (value) => {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN')
}
const shouldShowQuotePlaceholder = (row = {}, field = 'price') => {
  if (field === 'change' || field === 'changePercent') {
    return !hasReliableDelta(row)
  }

  if (field === 'price') {
    return !Number(row.price || 0)
  }

  if (field === 'volume') {
    return !Number(row.volume || 0)
  }

  if (field === 'high') {
    return !Number(row.high || 0)
  }

  if (field === 'low') {
    return !Number(row.low || 0)
  }

  return false
}
const quotePlaceholderLabel = (row = {}, field = 'price') => {
  if (isQuoteRealtime(row)) {
    return '实时中'
  }
  if (hasSnapshotFallback(row)) {
    return field === 'change' || field === 'changePercent' ? '快照缺失' : '快照兜底'
  }
  return '待推送'
}
const approximateChange = (row = {}) => {
  const price = Number(row.price || 0)
  const prevClose = Number(row.prevClose ?? row.prev_close ?? 0)
  const rawChange = Number(row.change ?? 0)

  if (!prevClose) {
    return rawChange
  }

  if (rawChange !== 0 || Math.abs(price - prevClose) < 0.0001) {
    return rawChange
  }

  return price - prevClose
}
const effectiveChangePercent = (row = {}) => {
  const price = Number(row.price || 0)
  const directPrevClose = Number(row.prevClose ?? row.prev_close ?? 0)
  const derivedPrevClose = price - approximateChange(row)
  const prevClose = directPrevClose || derivedPrevClose
  const raw = Number(row.changePercent ?? row.change_percent ?? 0)

  if (!prevClose) {
    return raw
  }

  if (raw !== 0 || Math.abs(price - prevClose) < 0.0001) {
    return raw
  }

  return (approximateChange(row) / prevClose) * 100
}

const formatVolume = (value) => {
  if (!value) return '0'
  if (value >= 1000000) {
    return (value / 1000000).toFixed(2) + 'M'
  }
  if (value >= 1000) {
    return (value / 1000).toFixed(2) + 'K'
  }
  return value.toString()
}

onMounted(() => {
  loadMarketData()
  loadMarketInsightsSilently({ resetSelection: true })
})

onUnmounted(() => {
  if (searchTimer) {
    window.clearTimeout(searchTimer)
    searchTimer = null
  }
})
</script>

<style scoped lang="scss">
.market-page {
  padding: 20px;
}

.insight-time-select {
  width: 240px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.index-card {
  .index-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 18px;

    .index-name {
      font-size: 14px;
      color: var(--text-secondary);
      display: block;
    }

    .index-symbol {
      margin-top: 4px;
      font-size: 12px;
      color: var(--text-muted);
    }
  }

  .index-spot {
    font-size: 14px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .index-ratio {
    font-size: 32px;
    font-weight: 700;
    margin-bottom: 10px;
  }

  .index-change {
    font-size: 14px;
    color: var(--text-secondary);
  }
}

.market-table {
  .quote-sync-rail {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: center;
    margin-bottom: 16px;
    padding: 10px 12px;
    border-radius: 16px;
    border: 1px solid color-mix(in srgb, var(--accent) 18%, var(--border-soft));
    background: color-mix(in srgb, var(--surface-soft) 90%, transparent);
  }

  .quote-sync-copy {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;

    strong {
      color: var(--text-primary);
      font-size: 13px;
      font-weight: 600;
    }

    span {
      color: var(--text-muted);
      font-size: 12px;
      line-height: 1.5;
    }
  }

  .sync-dot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: var(--accent);
    box-shadow: 0 0 0 6px color-mix(in srgb, var(--accent) 14%, transparent);
  }

  .quote-sync-metrics {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;

    .metric-pill {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      background: color-mix(in srgb, var(--surface-strong) 88%, transparent);
      color: var(--text-secondary);
      font-size: 12px;
      white-space: nowrap;

      &.subdued {
        color: var(--text-muted);
        background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
      }
    }
  }

  .table-alert {
    margin-bottom: 16px;
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 14px;
  }

  .card-header-copy {
    display: flex;
    flex-direction: column;
    gap: 4px;

    small {
      color: var(--text-muted);
    }
  }

  .symbol {
    font-weight: 600;
    color: var(--accent-strong);
  }

  :deep(.el-table__empty-block) {
    min-height: 240px;
  }
}

.table-empty-state {
  display: grid;
  gap: 8px;
  justify-items: center;
  padding: 28px 20px;
  text-align: center;

  strong {
    color: var(--text-primary);
    font-size: 16px;
  }

  span {
    max-width: 420px;
    color: var(--text-muted);
    line-height: 1.7;
  }
}

.mobile-quote-list {
  display: grid;
  gap: 12px;
}

.mobile-market-rail {
  margin-bottom: 14px;
}

.mobile-market-summary {
  display: grid;
  gap: 14px;
  margin-bottom: 14px;
}

.mobile-market-panel {
  margin-bottom: 0;
}

.mobile-market-overview {
  margin-bottom: 0;
}

.mobile-quote-card {
  padding: 16px;
  border-radius: 20px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
}

.mobile-quote-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.mobile-quote-head strong {
  display: block;
  margin-top: 4px;
  color: var(--text-primary);
  font-size: 15px;
}

.mobile-quote-price {
  text-align: right;
}

.mobile-quote-price span,
.mobile-quote-price small {
  display: block;
}

.mobile-quote-price span {
  font-size: 18px;
  font-weight: 700;
}

.mobile-quote-price small {
  margin-top: 4px;
}

.mobile-quote-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.mobile-quote-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.quote-placeholder {
  display: inline-flex;
  align-items: center;
  min-width: 56px;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
  color: var(--text-muted);
  font-size: 12px;
  position: relative;
  overflow: hidden;

  &::after {
    content: '';
    position: absolute;
    inset: 0;
    transform: translateX(-100%);
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.16), transparent);
    animation: quote-placeholder-sheen 1.4s ease-in-out infinite;
  }
}

.quote-source-pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  border: 1px solid transparent;

  &.realtime {
    color: var(--success);
    border-color: color-mix(in srgb, var(--success) 30%, transparent);
    background: color-mix(in srgb, var(--success) 14%, transparent);
  }

  &.snapshot {
    color: var(--warning, #d97706);
    border-color: color-mix(in srgb, var(--warning, #d97706) 28%, transparent);
    background: color-mix(in srgb, var(--warning, #d97706) 12%, transparent);
  }

  &.pending {
    color: var(--text-muted);
    border-color: color-mix(in srgb, var(--border-soft) 88%, transparent);
    background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
  }
}

.up {
  color: var(--success);
}

.down {
  color: var(--danger);
}

.symbol-button,
.name-button {
  padding: 0;
  border: 0;
  background: transparent;
  font: inherit;
  cursor: pointer;
  transition: color 0.18s ease, opacity 0.18s ease;
}

@keyframes quote-placeholder-sheen {
  to {
    transform: translateX(100%);
  }
}

@media (max-width: 900px) {
  .market-page {
    padding: 10px;
  }

  .insight-time-select {
    width: 100%;
  }

  .market-table {
    .quote-sync-rail {
      flex-direction: column;
      align-items: flex-start;
    }

    .quote-sync-metrics {
      justify-content: flex-start;
    }
  }

  .pagination {
    justify-content: center;
  }
}

.symbol-button {
  font-weight: 700;
  color: var(--accent-strong);
}

.name-button {
  color: var(--text-primary);
}

.symbol-button:hover,
.name-button:hover {
  color: var(--accent);
}

:deep(.el-radio-group .el-radio-button__inner),
:deep(.el-button.is-plain),
:deep(.el-pagination button),
:deep(.el-pagination .el-pager li) {
  color: var(--text-primary);
}

:deep(.el-input__wrapper),
:deep(.el-select__wrapper) {
  background: color-mix(in srgb, var(--surface) 94%, transparent);
}

:deep(.el-input__inner),
:deep(.el-select__selected-item) {
  color: var(--text-primary);
}
</style>

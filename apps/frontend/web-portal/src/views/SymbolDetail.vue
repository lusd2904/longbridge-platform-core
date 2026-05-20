<template>
  <div class="symbol-detail-page">
    <div class="page-nav">
      <div class="page-nav-actions">
        <el-button
          v-if="isStandaloneDetailPage"
          class="nav-button nav-button--primary"
          @click="goBack"
        >
          返回上一页
        </el-button>
        <el-button class="nav-button nav-button--secondary" @click="goToMarketList">
          返回市场列表
        </el-button>
      </div>
      <span class="page-nav-meta">当前标的 {{ overview.symbol || routeSymbol }}</span>
    </div>

    <PageHero
      :title="overview.symbol || routeSymbol"
      :chips="symbolHeroChips"
      :metrics="symbolHeroMetrics"
    >
      <template #actions>
        <div class="header-actions">
          <el-button class="action-button action-button--primary" :loading="loading" @click="refreshDetail">
            刷新详情
          </el-button>
          <el-button class="action-button action-button--secondary" @click="goToKline">
            历史K线
          </el-button>
          <el-button
            class="action-button action-button--secondary"
            :loading="inlineAnalysisLoading"
            @click="latestAiAnalysis ? goToAnalysis() : runInlineAnalysis()"
          >
            {{ latestAiAnalysis ? 'AI研判' : '立即研判' }}
          </el-button>
        </div>
      </template>
    </PageHero>

    <ReadModelSourceStrip
      label="标的状态"
      :status-text="symbolReadModelStatus"
      :status-type="symbolReadModelStatusType"
      :updated-at="symbolReadModelUpdatedAt"
      :updated-prefix="symbolReadModelUpdatedPrefix"
      :tags="symbolReadModelTags"
    />

    <MetricStrip :items="symbolMetricStripItems" />

    <div class="hero-grid">
      <el-card class="glass-card quote-card">
        <div class="quote-heading">
          <div class="quote-price-block">
            <div class="quote-price">{{ latestCloseDisplay }}</div>
            <div class="quote-source-badge">{{ quoteBaseSourceLabel }}</div>
          </div>
          <div class="quote-session">{{ quoteSnapshotTimeDisplay }}</div>
        </div>
        <div class="quote-change" :class="changeClass(latestChange)">
          <strong>{{ formatSignedCurrency(latestChangeAmount) }}</strong>
          <span>{{ formatPercent(latestChange) }}</span>
        </div>
        <div class="quote-stat-grid">
          <div v-for="item in quoteStats" :key="item.label" class="quote-stat-item">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <div class="quote-meta">
          <span>行业 {{ overview.fundamentals?.sector || '--' }}</span>
          <span>PE {{ numberOrDash(overview.fundamentals?.pe_ratio || overview.fundamentals?.peRatio) }}</span>
          <span>市值 {{ formatMarketCap(overview.fundamentals?.market_cap || overview.fundamentals?.marketCap) }}</span>
        </div>
      </el-card>

      <el-card class="glass-card">
        <template #header>
          <SectionCardHeader
            title="最新技术快照"
            badge="技术快照"
          />
        </template>
        <div class="snapshot-grid">
          <div v-for="item in snapshotCards" :key="item.label" class="snapshot-item">
            <span>{{ item.label }}</span>
            <strong :class="item.className">{{ item.value }}</strong>
          </div>
        </div>
      </el-card>
    </div>

    <div class="market-board-grid">
      <el-card class="glass-card order-book-card">
        <template #header>
          <SectionCardHeader
            title="实时盘口"
            :badge="streamConnected ? '实时推送' : '快照补位'"
            :badge-type="streamConnected ? 'success' : 'info'"
          />
        </template>
        <div class="book-summary">
          <div class="book-summary-item">
            <span>买一</span>
            <strong class="positive">{{ formatCurrency(bestBid.price || 0) }}</strong>
          </div>
          <div class="book-summary-item">
            <span>卖一</span>
            <strong class="negative">{{ formatCurrency(bestAsk.price || 0) }}</strong>
          </div>
          <div class="book-summary-item">
            <span>价差</span>
            <strong>{{ spreadDisplay }}</strong>
          </div>
          <div class="book-summary-item">
            <span>逐笔</span>
            <strong>{{ `${recentTrades.length} 条` }}</strong>
          </div>
        </div>
        <div v-if="depthBids.length || depthAsks.length" class="order-book order-book--compact">
          <div class="book-side">
            <div class="book-title">卖盘</div>
            <div v-for="(item, index) in depthAsks.slice().reverse()" :key="`ask-${index}`" class="book-row">
              <span>{{ depthAsks.length - index }}</span>
              <strong class="negative">{{ formatCurrency(item.price) }}</strong>
              <span>{{ formatVolume(item.volume) }}</span>
            </div>
          </div>
          <div class="book-side">
            <div class="book-title">买盘</div>
            <div v-for="(item, index) in depthBids" :key="`bid-${index}`" class="book-row">
              <span>{{ index + 1 }}</span>
              <strong class="positive">{{ formatCurrency(item.price) }}</strong>
              <span>{{ formatVolume(item.volume) }}</span>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无盘口数据" />
      </el-card>

      <el-card class="glass-card trades-card">
        <template #header>
          <SectionCardHeader
            title="最近成交"
            :badge="streamConnected ? '推送中' : '快照'"
          />
        </template>
        <div v-if="recentTrades.length" class="trade-tape trade-tape--compact">
          <div v-for="trade in compactRecentTrades" :key="trade.id" class="trade-row">
            <div>
              <strong :class="trade.sideClass">{{ formatCurrency(trade.price) }}</strong>
              <span>{{ trade.sideLabel }}</span>
            </div>
            <div>
              <strong>{{ formatVolume(trade.volume) }}</strong>
              <span>{{ formatTimeOnly(trade.timestamp) }}</span>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无逐笔成交" />
      </el-card>
    </div>

    <el-card class="glass-card chart-card">
      <template #header>
        <SectionCardHeader
          title="近120日价格曲线"
          :badge="historySummary.latestDate || '--'"
        />
      </template>
      <v-chart class="line-chart" :option="chartOption" autoresize />
    </el-card>

    <div class="detail-grid">
      <el-card class="glass-card">
        <template #header>
          <SectionCardHeader
            title="最近研判"
            :badge="latestAiAnalysis?.final_decision || '暂无记录'"
            :badge-type="aiDecisionType"
          />
        </template>
        <div v-if="latestAiAnalysis" class="ai-panel">
          <div class="ai-decision">
            <el-tag size="small" :type="aiDecisionType">{{ latestAiAnalysis.final_decision || '--' }}</el-tag>
            <span>置信度 {{ Number(latestAiAnalysis.final_confidence || 0).toFixed(2) }}%</span>
          </div>
          <p>{{ latestAiAnalysis.deepseek_analysis || latestAiAnalysis.gemma_analysis || '暂无分析摘要' }}</p>
          <span class="ai-time">{{ latestAiAnalysis.analysis_time || latestAiAnalysis.created_at || '--' }}</span>
        </div>
        <div v-else class="ai-empty-state">
          <el-empty description="暂无研判记录，可立即发起一次分析" />
          <el-button
            class="action-button action-button--primary"
            :loading="inlineAnalysisLoading"
            @click="runInlineAnalysis"
          >
            立即研判
          </el-button>
        </div>
      </el-card>

      <el-card class="glass-card">
        <template #header>
          <SectionCardHeader
            title="市场联动"
            badge="市场快照"
          />
        </template>
        <div class="market-panel" v-if="marketInsight || marketScan">
          <div class="market-block" v-if="marketInsight">
            <strong>{{ marketInsight.headline }}</strong>
            <p>{{ marketInsight.summary }}</p>
          </div>
          <div class="market-block" v-if="marketScan">
            <strong>{{ marketScan.headline }}</strong>
            <p>{{ marketScan.summary }}</p>
          </div>
        </div>
        <el-empty v-else description="暂无市场联动数据" />
      </el-card>
    </div>

    <el-card class="glass-card content-card">
      <template #header>
        <SectionCardHeader
          title="公告 / 资讯 / 讨论"
          :badge="routeSymbol"
        />
      </template>
      <ReadModelSourceStrip
        label="内容状态"
        :status-text="contentSourceLabel"
        :status-type="contentCacheReady ? 'success' : 'warning'"
        :updated-at="contentMeta?.updatedAt ? contentUpdatedAtDisplay : ''"
        :tags="contentSourceTags"
        compact
      />
      <el-tabs v-model="activeContentTab">
        <el-tab-pane label="公告" name="announcements">
          <div v-if="announcements.length" class="content-list">
            <article v-for="item in announcements" :key="item.id" class="content-item">
              <div class="content-head">
                <strong>{{ item.title }}</strong>
                <span>{{ formatDateTime(item.publishedAt) }}</span>
              </div>
              <p>{{ item.summary }}</p>
              <div class="content-footer">
                <span>{{ item.sourceLabel }}</span>
                <el-button
                  v-if="item.url"
                  class="content-link-button"
                  link
                  @click="openOriginalContent(item)"
                >
                  查看原文
                </el-button>
              </div>
            </article>
          </div>
          <el-empty v-else description="暂无公告" />
        </el-tab-pane>
        <el-tab-pane label="资讯" name="news">
          <div v-if="newsItems.length" class="content-list">
            <article v-for="item in newsItems" :key="item.id" class="content-item">
              <div class="content-head">
                <strong>{{ item.title }}</strong>
                <span>{{ formatDateTime(item.publishedAt) }}</span>
              </div>
              <p>{{ item.summary }}</p>
              <div class="content-footer">
                <span>{{ item.sourceLabel }}</span>
                <el-button
                  v-if="item.url"
                  class="content-link-button"
                  link
                  @click="openOriginalContent(item)"
                >
                  查看原文
                </el-button>
              </div>
            </article>
          </div>
          <el-empty v-else description="暂无资讯" />
        </el-tab-pane>
        <el-tab-pane label="讨论" name="topics">
          <div v-if="topicItems.length" class="content-list">
            <article v-for="item in topicItems" :key="item.id" class="content-item">
              <div class="content-head">
                <strong>{{ item.title }}</strong>
                <span>{{ formatDateTime(item.publishedAt) }}</span>
              </div>
              <p>{{ item.summary }}</p>
              <div class="content-footer">
                <span>{{ item.sourceLabel }}</span>
                <el-button
                  v-if="item.url"
                  class="content-link-button"
                  link
                  @click="openOriginalContent(item)"
                >
                  查看原文
                </el-button>
              </div>
            </article>
          </div>
          <el-empty v-else description="暂无讨论" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-drawer
      v-model="originalContentDrawerVisible"
      :title="activeOriginalContent?.title || '查看原文'"
      direction="rtl"
      size="72%"
      destroy-on-close
      class="original-content-drawer"
    >
      <div v-if="activeOriginalContent?.url" class="original-content-frame-wrap">
        <div class="original-content-meta">
          <span>{{ activeOriginalContent.sourceLabel }}</span>
          <span>{{ formatDateTime(activeOriginalContent.publishedAt) }}</span>
        </div>
        <iframe
          :src="activeOriginalContent.url"
          class="original-content-frame"
          :title="activeOriginalContent.title || '原文内容'"
        />
      </div>
      <el-empty v-else description="原文链接不可用" />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import {
  analyzeStock,
  getLongbridgeAnnouncements,
  getLongbridgeNews,
  getLongbridgeSnapshot,
  getStockQuote,
  getLongbridgeTopics,
  getSymbolOverview
} from '../api/market.js'
import { useLongbridgeMarketStream } from '../composables/useWebSocket.js'
import { getThemeValue } from '../composables/useTheme.js'
import { getCurrentUser } from '../utils/auth.js'
import { sanitizeNarrativeText } from '../utils/contentSanitizer.js'
import { formatCurrency, formatPercent as formatPercentValue } from '../utils/formatters.js'
import { buildContentCacheReadModelSummary, buildSymbolOverviewReadModelSummary } from '../utils/readModelSource.js'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import PageHero from '../components/common/PageHero.vue'
import MetricStrip from '../components/common/MetricStrip.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent])

const props = defineProps({ symbol: { type: String, default: '' } })
const route = useRoute()
const router = useRouter()
const currentUser = getCurrentUser() || {}
const loading = ref(false)
const inlineAnalysisLoading = ref(false)
const overview = ref({ fundamentals: {}, snapshots: {}, history: { items: [], summary: {} } })
const latestAiAnalysis = ref(null)
const marketInsight = ref(null)
const marketScan = ref(null)
const activeContentTab = ref('announcements')
const announcements = ref([])
const newsItems = ref([])
const topicItems = ref([])
const contentMeta = ref({ dataSource: 'content-cache-empty', updatedAt: '', totalCount: 0 })
const depthSnapshotFallback = ref({})
const tradeSnapshotsFallback = ref([])
const quoteApiFallback = ref({})
const originalContentDrawerVisible = ref(false)
const activeOriginalContent = ref(null)
const detailLoadVersion = ref(0)

const routeSymbol = computed(() => String(props.symbol || route.params.symbol || route.query.symbol || 'AAPL.US').toUpperCase())
const isStandaloneDetailPage = computed(() => !props.symbol)
const {
  quotes: liveQuoteMap,
  depth: depthMap,
  trades: tradesMap,
  isConnected: streamConnected
} = useLongbridgeMarketStream(computed(() => [routeSymbol.value]), {
  userId: currentUser?.id || null,
  subTypes: ['quote', 'depth', 'trade'],
  tradeCount: 18
})
const wsConnected = streamConnected
const historyItems = computed(() => overview.value?.history?.items || [])
const historySummary = computed(() => overview.value?.history?.summary || {})
const dailySnapshot = computed(() => overview.value?.snapshots?.daily || {})
const quoteSnapshot = computed(() => overview.value?.quoteSnapshot || {})
const overviewMeta = computed(() => (
  overview.value?.meta && typeof overview.value.meta === 'object'
    ? overview.value.meta
    : {}
))
const overviewSources = computed(() => (
  overviewMeta.value?.sources && typeof overviewMeta.value.sources === 'object'
    ? overviewMeta.value.sources
    : {}
))
const liveQuote = computed(() => liveQuoteMap.value[routeSymbol.value] || null)
const depthSnapshot = computed(() => depthMap.value[routeSymbol.value] || depthSnapshotFallback.value || {})
const liveTradeRows = computed(() => {
  const streamRows = tradesMap.value[routeSymbol.value]
  if (Array.isArray(streamRows) && streamRows.length) {
    return streamRows
  }
  return Array.isArray(tradeSnapshotsFallback.value) ? tradeSnapshotsFallback.value : []
})
const toTimestampMs = (value) => {
  if (!value) return 0
  const parsed = Date.parse(String(value))
  return Number.isFinite(parsed) ? parsed : 0
}
const quoteBase = computed(() => {
  const liveQuoteTimestamp = liveQuote.value?.timestamp || liveQuote.value?.pushReceivedAt || liveQuote.value?.updatedAt || ''
  const pullQuoteTimestamp = quoteApiFallback.value?.timestamp || quoteApiFallback.value?.snapshotAt || quoteApiFallback.value?.updatedAt || ''
  const snapshotQuoteTimestamp = quoteSnapshot.value?.snapshotAt || quoteSnapshot.value?.updatedAt || ''
  const hasLiveQuote = liveQuote.value?.last_price !== undefined && liveQuote.value?.last_price !== null
  const hasPullQuote = quoteApiFallback.value?.price !== undefined && quoteApiFallback.value?.price !== null
  const hasSnapshotQuote = quoteSnapshot.value?.price !== undefined && quoteSnapshot.value?.price !== null

  if (hasLiveQuote && toTimestampMs(liveQuoteTimestamp) >= Math.max(toTimestampMs(pullQuoteTimestamp), toTimestampMs(snapshotQuoteTimestamp))) {
    return { ...liveQuote.value, source: 'realtime-stream' }
  }
  if (hasPullQuote && toTimestampMs(pullQuoteTimestamp) >= toTimestampMs(snapshotQuoteTimestamp)) {
    return { ...quoteApiFallback.value, source: 'longbridge-cli' }
  }
  if (hasSnapshotQuote) {
    return { ...quoteSnapshot.value, source: 'quote-snapshot' }
  }
  return {
    price: dailySnapshot.value?.closePrice ?? 0,
    change_percent: dailySnapshot.value?.changePercent ?? 0,
    prev_close: dailySnapshot.value?.prevClose ?? 0,
    volume: dailySnapshot.value?.volume ?? 0,
    high: dailySnapshot.value?.highPrice ?? 0,
    low: dailySnapshot.value?.lowPrice ?? 0,
    open: dailySnapshot.value?.openPrice ?? 0,
    timestamp: dailySnapshot.value?.snapshotDate || '',
    source: 'daily-history'
  }
})
const latestPrice = computed(() => Number(quoteBase.value?.last_price ?? quoteBase.value?.price ?? 0))
const latestPrevClose = computed(() => Number(quoteBase.value?.prev_close ?? quoteBase.value?.prevClose ?? dailySnapshot.value?.prevClose ?? 0))
const latestChangeAmount = computed(() => {
  const directValue = quoteBase.value?.change
  if (directValue !== undefined && directValue !== null && directValue !== '') {
    return Number(directValue)
  }
  if (latestPrevClose.value) {
    return latestPrice.value - latestPrevClose.value
  }
  return 0
})
const latestChange = computed(() => {
  const directValue = quoteBase.value?.change_percent ?? quoteBase.value?.changePercent
  if (directValue !== undefined && directValue !== null && directValue !== '') {
    return Number(directValue)
  }
  if (latestPrevClose.value) {
    return ((latestPrice.value - latestPrevClose.value) / latestPrevClose.value) * 100
  }
  return 0
})
const latestCloseDisplay = computed(() => formatCurrency(latestPrice.value))
const quoteSnapshotTimeDisplay = computed(() => {
  const timestamp = quoteBase.value?.timestamp
    || quoteBase.value?.snapshotAt
    || quoteBase.value?.snapshot_at
    || quoteSnapshot.value?.snapshotAt
    || quoteSnapshot.value?.snapshot_at
  return timestamp ? formatDateTime(timestamp) : '--'
})
const quoteBaseSourceLabel = computed(() => {
  if (quoteBase.value?.source === 'realtime-stream') return 'Longbridge Push'
  if (quoteBase.value?.source === 'longbridge-cli') return 'Longbridge Quote'
  if (quoteBase.value?.source === 'quote-snapshot') return '行情快照'
  if (quoteBase.value?.source === 'daily-history') return '历史收盘'
  return '行情数据'
})
const symbolRealtimeOverlayLabel = computed(() => {
  const overlays = Array.isArray(overviewMeta.value?.realtimeOverlay) ? overviewMeta.value.realtimeOverlay : []
  return overlays.join(' / ')
})
const symbolReadModelSummary = computed(() => buildSymbolOverviewReadModelSummary(
  overviewMeta.value,
  {
    wsConnected: wsConnected.value,
    overlayLabel: symbolRealtimeOverlayLabel.value || 'quote / depth / trades',
    fallbackUpdatedAt: quoteSnapshot.value?.snapshotAt || dailySnapshot.value?.snapshotDate || historySummary.value?.latestDate || '',
    quoteReady: Boolean(latestPrice.value || quoteSnapshot.value?.snapshotAt || quoteSnapshot.value?.price),
    contentReady: contentCacheReady.value
  }
))
const symbolReadModelStatus = computed(() => symbolReadModelSummary.value.statusText)
const symbolReadModelStatusType = computed(() => symbolReadModelSummary.value.statusType)
const symbolReadModelUpdatedAt = computed(() => (
  symbolReadModelSummary.value.updatedAt ? formatDateTime(symbolReadModelSummary.value.updatedAt) : ''
))
const symbolReadModelUpdatedPrefix = computed(() => symbolReadModelSummary.value.updatedPrefix)
const symbolReadModelTags = computed(() => symbolReadModelSummary.value.tags || [])
const contentCacheReady = computed(() => Number(contentMeta.value?.totalCount || 0) > 0)
const contentReadModelSummary = computed(() => buildContentCacheReadModelSummary(
  contentMeta.value,
  {
    symbol: routeSymbol.value,
    sourceLabel: overviewSources.value.content || 'symbol_content_cache'
  }
))
const contentSourceLabel = computed(() => contentReadModelSummary.value.statusText)
const contentUpdatedAtDisplay = computed(() => contentReadModelSummary.value.updatedAt || '--')
const contentSourceTags = computed(() => contentReadModelSummary.value.tags || [])
const hasRealtimeQuote = computed(() => quoteBase.value?.source === 'realtime-stream')
const historicalBaseTime = computed(() => dailySnapshot.value?.snapshotDate || historySummary.value?.latestDate || '--')
const quoteStats = computed(() => ([
  { label: '今开', value: formatCurrency(quoteBase.value?.open ?? 0) },
  { label: '最高', value: formatCurrency(quoteBase.value?.high ?? 0) },
  { label: '最低', value: formatCurrency(quoteBase.value?.low ?? 0) },
  { label: '成交量', value: formatVolume(quoteBase.value?.volume ?? 0) }
]))
const sourceLayerCards = computed(() => ([
  {
    label: '价格状态',
    value: quoteBaseSourceLabel.value,
    hint: quoteSnapshotTimeDisplay.value === '--' ? '等待报价快照' : `快照 ${quoteSnapshotTimeDisplay.value}`,
    tone: ''
  },
  {
    label: '最新价',
    value: hasRealtimeQuote.value ? '实时行情' : wsConnected.value ? '等待首帧' : '快照',
    hint: liveQuote.value?.timestamp
      ? formatDateTime(liveQuote.value.timestamp)
      : wsConnected.value
        ? '连接已建立，继续等待实时价'
        : '当前显示快照价格',
    tone: hasRealtimeQuote.value ? 'positive' : 'neutral'
  },
  {
    label: '盘口 / 逐笔',
    value: streamConnected.value ? '实时流' : '接口快照',
    hint: `盘口 ${Math.max(depthBids.value.length, depthAsks.value.length)} 档 · 成交 ${recentTrades.value.length} 条`,
    tone: streamConnected.value ? 'positive' : 'neutral'
  },
  {
    label: '历史 / 指标',
    value: historicalBaseTime.value === '--' ? '等待同步' : '历史快照',
    hint: historicalBaseTime.value === '--' ? '日终任务补齐后可回看' : `更新到 ${historicalBaseTime.value}`,
    tone: historicalBaseTime.value === '--' ? 'neutral' : ''
  }
]))
const symbolHeroAside = computed(() => (
  symbolReadModelUpdatedAt.value ? `${symbolReadModelUpdatedPrefix.value}${symbolReadModelUpdatedAt.value}` : '等待最新同步'
))
const symbolHeroChips = computed(() => ([
  {
    text: marketLabel(overview.value?.market),
    tone: marketTone(overview.value?.market)
  },
  {
    text: wsConnected.value ? '实时推送' : '行情快照',
    tone: wsConnected.value ? 'healthy' : 'info'
  },
  {
    text: contentCacheReady.value ? '内容已同步' : '等待内容',
    tone: contentCacheReady.value ? 'healthy' : 'warning'
  }
]))
const symbolHeroMetrics = computed(() => ([
  {
    label: '最新价',
    value: latestCloseDisplay.value,
    note: quoteBaseSourceLabel.value
  },
  {
    label: '涨跌幅',
    value: formatPercent(latestChange.value),
    note: quoteSnapshotTimeDisplay.value,
    tone: changeClass(latestChange.value) === 'positive' ? 'healthy' : changeClass(latestChange.value) === 'negative' ? 'error' : ''
  },
  {
    label: '行业',
    value: overview.value?.fundamentals?.sector || '--',
    note: marketLabel(overview.value?.market)
  },
  {
    label: 'PE',
    value: numberOrDash(overview.value?.fundamentals?.pe_ratio || overview.value?.fundamentals?.peRatio),
    note: `市值 ${formatMarketCap(overview.value?.fundamentals?.market_cap || overview.value?.fundamentals?.marketCap)}`
  }
]))
const symbolMetricStripItems = computed(() => (
  sourceLayerCards.value.map((item) => ({
    label: item.label,
    value: item.value,
    note: item.hint,
    tone: item.tone === 'positive' ? 'healthy' : item.tone === 'neutral' ? 'info' : ''
  }))
))
const aiDecisionType = computed(() => {
  const text = String(latestAiAnalysis.value?.final_decision || '').toLowerCase()
  if (text.includes('买')) return 'success'
  if (text.includes('卖')) return 'danger'
  return 'warning'
})

const marketLabel = (market) => ({ US: '美股', CN: 'A股', HK: '港股' }[market] || market || '--')
const formatPercent = (value) => formatPercentValue(value, { signed: true })
const changeClass = (value) => (Number(value || 0) > 0 ? 'positive' : Number(value || 0) < 0 ? 'negative' : 'neutral')
const numberOrDash = (value) => (value === null || value === undefined || value === '' ? '--' : Number(value).toFixed(2))
const formatSignedCurrency = (value) => {
  const amount = Number(value || 0)
  if (!amount) return formatCurrency(0)
  return `${amount > 0 ? '+' : ''}${formatCurrency(amount)}`
}
const formatVolume = (value) => {
  const amount = Number(value || 0)
  if (!amount) return '0'
  if (amount >= 100000000) return `${(amount / 100000000).toFixed(2)}亿`
  if (amount >= 1000000) return `${(amount / 1000000).toFixed(2)}M`
  if (amount >= 1000) return `${(amount / 1000).toFixed(2)}K`
  return amount.toFixed(0)
}
const formatDateTime = (value) => {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN')
}
const formatTimeOnly = (value) => {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleTimeString('zh-CN', { hour12: false })
}
const formatMarketCap = (value) => {
  const amount = Number(value || 0)
  if (!amount) return '--'
  if (amount >= 1e12) return `${(amount / 1e12).toFixed(2)}T`
  if (amount >= 1e9) return `${(amount / 1e9).toFixed(2)}B`
  if (amount >= 1e6) return `${(amount / 1e6).toFixed(2)}M`
  return amount.toFixed(2)
}

const marketTone = (market) => {
  if (market === 'CN') return 'success'
  if (market === 'HK') return 'warning'
  return 'info'
}

const normalizeDepthSide = (rows = []) => {
  const items = Array.isArray(rows) ? rows : []
  return items.slice(0, 5).map((item, index) => ({
    id: `${index}-${item?.price ?? item?.position ?? index}`,
    price: Number(item?.price ?? item?.price_value ?? item?.last_done ?? item?.value ?? 0),
    volume: Number(item?.volume ?? item?.quantity ?? item?.size ?? item?.total_volume ?? 0)
  }))
}

const depthBids = computed(() => normalizeDepthSide(depthSnapshot.value?.bids || depthSnapshot.value?.bid || []))
const depthAsks = computed(() => normalizeDepthSide(depthSnapshot.value?.asks || depthSnapshot.value?.ask || []))
const bestBid = computed(() => depthBids.value[0] || {})
const bestAsk = computed(() => depthAsks.value[0] || {})
const spreadDisplay = computed(() => {
  if (!bestBid.value?.price || !bestAsk.value?.price) {
    return '--'
  }
  return formatCurrency(bestAsk.value.price - bestBid.value.price)
})

const recentTrades = computed(() => {
  return liveTradeRows.value.slice(0, 10).map((item, index) => {
    const direction = String(item?.trade_direction || item?.direction || '').toLowerCase()
    const isBuy = direction.includes('buy') || direction.includes('up')
    const isSell = direction.includes('sell') || direction.includes('down')
    return {
      id: item?.trade_id || item?.id || `${routeSymbol.value}-${index}`,
      price: Number(item?.price ?? item?.last_done ?? 0),
      volume: Number(item?.volume ?? item?.quantity ?? item?.trade_volume ?? 0),
      timestamp: item?.timestamp || item?.trade_time || item?.time || '',
      sideLabel: isBuy ? '主动买' : isSell ? '主动卖' : '成交',
      sideClass: isBuy ? 'positive' : isSell ? 'negative' : 'neutral'
    }
  })
})
const compactRecentTrades = computed(() => recentTrades.value.slice(0, 6))

const normalizeContentItems = (items = [], type = 'news') => {
  return (Array.isArray(items) ? items : []).map((item, index) => ({
    id: item?.id || `${type}-${index}`,
    title: sanitizeNarrativeText(item?.title || item?.file_name || item?.symbol || routeSymbol.value, routeSymbol.value),
    summary: sanitizeNarrativeText(
      item?.description || item?.content || item?.title,
      `${routeSymbol.value} 已同步最新${type === 'announcements' ? '公告' : type === 'topics' ? '讨论' : '资讯'}。`
    ),
    publishedAt: item?.published_at || item?.publish_time || item?.time || '',
    url: item?.url || item?.file_urls?.[0] || '',
    fetchedAt: item?.cache_fetched_at || item?.fetched_at || '',
    sourceLabel: `${String(item?.data_source || '').includes('content-cache') ? '缓存 · ' : ''}${type === 'announcements' ? '长桥公告' : type === 'topics' ? '长桥讨论' : '长桥资讯'}`
  }))
}

const applyContentBundle = (bundle = {}, fallbackSource = 'content-cache') => {
  const announcementItems = Array.isArray(bundle?.announcements?.items) ? bundle.announcements.items : []
  const newsRows = Array.isArray(bundle?.news?.items) ? bundle.news.items : []
  const topicRows = Array.isArray(bundle?.topics?.items) ? bundle.topics.items : []

  announcements.value = normalizeContentItems(announcementItems, 'announcements')
  newsItems.value = normalizeContentItems(newsRows, 'news')
  topicItems.value = normalizeContentItems(topicRows, 'topics')

  contentMeta.value = {
    dataSource: bundle?.dataSource || fallbackSource,
    updatedAt: bundle?.updatedAt
      || bundle?.announcements?.updatedAt
      || bundle?.news?.updatedAt
      || bundle?.topics?.updatedAt
      || '',
    totalCount: Number(bundle?.totalCount || (announcementItems.length + newsRows.length + topicRows.length))
  }
}

const refreshContentFeeds = async () => {
  const [announcementRes, newsRes, topicRes] = await Promise.allSettled([
    getLongbridgeAnnouncements(routeSymbol.value),
    getLongbridgeNews(routeSymbol.value),
    getLongbridgeTopics(routeSymbol.value)
  ])

  const sourceCandidates = [
    announcementRes.status === 'fulfilled' ? announcementRes.value?.data?.dataSource : '',
    newsRes.status === 'fulfilled' ? newsRes.value?.data?.dataSource : '',
    topicRes.status === 'fulfilled' ? topicRes.value?.data?.dataSource : ''
  ].filter(Boolean)
  const updatedCandidates = [
    ...(announcementRes.status === 'fulfilled' ? (announcementRes.value?.data?.payload || []) : []),
    ...(newsRes.status === 'fulfilled' ? (newsRes.value?.data?.payload || []) : []),
    ...(topicRes.status === 'fulfilled' ? (topicRes.value?.data?.payload || []) : [])
  ].map((item) => item?.cache_fetched_at || item?.fetched_at || '').filter(Boolean).sort()

  announcements.value = announcementRes.status === 'fulfilled'
    ? normalizeContentItems(announcementRes.value?.data?.payload || announcementRes.value?.data || [], 'announcements')
    : []
  newsItems.value = newsRes.status === 'fulfilled'
    ? normalizeContentItems(newsRes.value?.data?.payload || newsRes.value?.data || [], 'news')
    : []
  topicItems.value = topicRes.status === 'fulfilled'
    ? normalizeContentItems(topicRes.value?.data?.payload || topicRes.value?.data || [], 'topics')
    : []

  contentMeta.value = {
    dataSource: sourceCandidates.find((item) => String(item).includes('content-cache'))
      || sourceCandidates[0]
      || 'content-cache-empty',
    updatedAt: updatedCandidates[updatedCandidates.length - 1] || '',
    totalCount: announcements.value.length + newsItems.value.length + topicItems.value.length
  }
}

const snapshotCards = computed(() => {
  const daily = dailySnapshot.value || {}
  return [
    { label: '趋势', value: daily.trendLabel || '--', className: '' },
    { label: 'RSI', value: numberOrDash(daily.rsi), className: changeClass(Number(daily.rsi || 50) - 50) },
    { label: '动量分', value: numberOrDash(daily.momentumScore), className: changeClass(Number(daily.momentumScore || 50) - 50) },
    { label: '支撑', value: formatCurrency(daily.supportPrice || 0), className: '' },
    { label: '阻力', value: formatCurrency(daily.resistancePrice || 0), className: '' },
    { label: 'ATR', value: numberOrDash(daily.atr), className: '' }
  ]
})

const chartOption = computed(() => {
  const items = historyItems.value
  const axisColor = getThemeValue('--chart-axis', 'rgba(99, 115, 141, 0.8)')
  const gridColor = getThemeValue('--chart-grid', 'rgba(125, 154, 191, 0.14)')
  const lineColor = getThemeValue('--accent-strong', '#3b82f6')
  const softColor = getThemeValue('--accent', '#60a5fa')

  return {
    grid: { left: '3%', right: '3%', top: '8%', bottom: '6%', containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: getThemeValue('--surface-strong', 'rgba(255,255,255,0.94)'),
      borderColor: gridColor
    },
    xAxis: {
      type: 'category',
      data: items.map((item) => item.date),
      axisLabel: { color: axisColor },
      axisLine: { lineStyle: { color: gridColor } }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: axisColor },
      splitLine: { lineStyle: { color: gridColor, type: 'dashed' } }
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: items.map((item) => Number(item.close || 0)),
        lineStyle: { color: lineColor, width: 3 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: softColor },
              { offset: 1, color: 'transparent' }
            ]
          },
          opacity: 0.18
        }
      }
    ]
  }
})

const normalizeInlineAnalysis = (result = {}) => ({
  ...result,
  final_decision: result?.final_decision || result?.finalDecision || '观望',
  final_confidence: result?.final_confidence ?? result?.finalConfidence ?? 0,
  deepseek_analysis: sanitizeNarrativeText(
    result?.deepseek_analysis || result?.deepseek || result?.summary || result?.scanLayers?.[0]?.summary,
    '暂无分析摘要'
  ),
  gemma_analysis: sanitizeNarrativeText(
    result?.gemma_analysis || result?.gemma || result?.scanLayers?.[1]?.summary,
    ''
  ),
  analysis_time: result?.analysis_time || result?.analysisTime || new Date().toISOString(),
  created_at: result?.created_at || result?.createdAt || new Date().toISOString()
})

const fetchQuoteFallback = async () => {
  try {
    const res = await getStockQuote(routeSymbol.value)
    quoteApiFallback.value = res?.data || {}
  } catch (error) {
    console.warn('加载实时 quote 回退失败:', error)
    quoteApiFallback.value = {}
  }
}

const normalizeSnapshotQuotePayload = (payload = []) => {
  const symbol = routeSymbol.value
  if (Array.isArray(payload)) {
    return payload.find((item) => String(item?.symbol || '').trim().toUpperCase() === symbol) || payload[0] || {}
  }
  return payload && typeof payload === 'object' ? payload : {}
}

const applyLiveSnapshot = (snapshot = {}) => {
  quoteApiFallback.value = {
    ...normalizeSnapshotQuotePayload(snapshot.quote),
    source: snapshot?.sources?.quote || 'longbridge-cli'
  }
  depthSnapshotFallback.value = snapshot?.depth || {}
  tradeSnapshotsFallback.value = Array.isArray(snapshot?.trades) ? snapshot.trades : []
}

const applyOverviewData = (data = {}, { includeDeferred = true } = {}) => {
  overview.value = {
    ...overview.value,
    ...data,
    history: data.history || overview.value?.history || { items: [], summary: {} },
    snapshots: data.snapshots || overview.value?.snapshots || {},
    fundamentals: data.fundamentals || overview.value?.fundamentals || {}
  }
  if (includeDeferred) {
    latestAiAnalysis.value = data.latestAiAnalysis || null
    marketInsight.value = data.marketInsight || null
    marketScan.value = data.marketScan || null
    applyContentBundle(data.contentCache || {}, 'content-cache')
  }
}

const loadDetail = async ({ refreshContent = false } = {}) => {
  const loadVersion = detailLoadVersion.value + 1
  detailLoadVersion.value = loadVersion
  const requestedSymbol = routeSymbol.value
  loading.value = true
  try {
    const [coreRes, snapshotRes] = await Promise.allSettled([
      getSymbolOverview(requestedSymbol, { include: 'core' }),
      getLongbridgeSnapshot(requestedSymbol, { count: 18 })
    ])

    if (detailLoadVersion.value !== loadVersion || requestedSymbol !== routeSymbol.value) return
    if (coreRes.status !== 'fulfilled') {
      throw coreRes.reason
    }

    applyOverviewData(coreRes.value?.data || {}, { includeDeferred: false })
    if (snapshotRes.status === 'fulfilled') {
      applyLiveSnapshot(snapshotRes.value?.data?.payload || snapshotRes.value?.data || {})
    } else {
      await fetchQuoteFallback()
      depthSnapshotFallback.value = {}
      tradeSnapshotsFallback.value = []
    }

    loading.value = false

    getSymbolOverview(requestedSymbol)
      .then((res) => {
        if (detailLoadVersion.value !== loadVersion || requestedSymbol !== routeSymbol.value) return null
        applyOverviewData(res?.data || {}, { includeDeferred: true })
        if (refreshContent || !contentCacheReady.value) {
          return refreshContentFeeds()
        }
        return null
      })
      .catch((error) => {
        if (detailLoadVersion.value !== loadVersion || requestedSymbol !== routeSymbol.value) return null
        console.warn('加载标的扩展详情失败:', error)
        if (refreshContent || !contentCacheReady.value) {
          return refreshContentFeeds().catch(() => {})
        }
        return null
      })
  } catch (error) {
    console.error('加载标的详情失败:', error)
    ElMessage.error('加载标的详情失败')
  } finally {
    loading.value = false
  }
}

const refreshDetail = () => loadDetail({ refreshContent: true })

const runInlineAnalysis = async () => {
  inlineAnalysisLoading.value = true
  try {
    const res = await analyzeStock(routeSymbol.value, { forceRefresh: true })
    if (res?.data) {
      latestAiAnalysis.value = normalizeInlineAnalysis(res.data)
      ElMessage.success('AI 研判已生成')
      return
    }
    ElMessage.warning('分析接口已返回，但暂无可展示结果')
  } catch (error) {
    const message = error?.businessMessage || error?.data?.detail || error?.message || 'AI 研判失败'
    ElMessage.error(String(message).split('\n')[0].slice(0, 120))
  } finally {
    inlineAnalysisLoading.value = false
  }
}

const goToAnalysis = () => {
  router.push({ name: 'AIAnalysis', query: { symbol: routeSymbol.value, market: overview.value?.market || undefined } })
}

const goBack = () => {
  if (window.history.length > 1) {
    router.back()
    return
  }
  goToMarketList()
}

const goToMarketList = () => {
  router.push({ name: 'MarketData' })
}

const goToKline = () => {
  router.push({ name: 'Kline', query: { symbols: routeSymbol.value } })
}

const openOriginalContent = (item) => {
  activeOriginalContent.value = item
  originalContentDrawerVisible.value = true
}

watch(routeSymbol, () => {
  detailLoadVersion.value += 1
  originalContentDrawerVisible.value = false
  activeOriginalContent.value = null
  quoteApiFallback.value = {}
  loadDetail()
}, { immediate: true })
</script>

<style scoped lang="scss">
.symbol-detail-page {
  --detail-primary-bg: linear-gradient(135deg, color-mix(in srgb, var(--accent-strong) 82%, white 18%), color-mix(in srgb, var(--accent) 76%, var(--surface-strong) 24%));
  --detail-primary-border: color-mix(in srgb, var(--accent-strong) 42%, transparent);
  --detail-secondary-bg: color-mix(in srgb, var(--surface-strong) 92%, black 8%);
  --detail-secondary-hover: color-mix(in srgb, var(--accent-strong) 12%, var(--surface-strong));
  --detail-secondary-border: color-mix(in srgb, var(--border-soft) 84%, transparent);
  --detail-muted-panel: color-mix(in srgb, var(--surface-muted) 82%, transparent);
  --detail-strong-panel: color-mix(in srgb, var(--surface-strong) 92%, black 8%);
  display: flex;
  flex-direction: column;
  gap: 20px;
  color: var(--text-primary);
}

.page-nav,
.page-nav-actions,
.header-actions,
.quote-heading,
.quote-price-block,
.quote-change,
.quote-stat-grid,
.quote-stat-item,
.book-summary,
.book-summary-item,
.quote-meta,
.hero-grid,
.market-board-grid,
.detail-grid,
.snapshot-grid,
.snapshot-item,
.ai-decision {
  display: flex;
  align-items: center;
}

.page-nav {
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.page-nav-actions,
.header-actions,
.quote-meta,
.ai-decision {
  gap: 12px;
}

.page-nav-meta {
  color: var(--text-muted);
  font-size: 13px;
}

.nav-button,
.action-button {
  min-height: 40px;
  border-radius: 999px;
  font-weight: 700;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease, box-shadow 160ms ease;
}

.nav-button--primary,
.action-button--primary {
  color: #fff !important;
  background: var(--detail-primary-bg) !important;
  border-color: var(--detail-primary-border) !important;
  box-shadow: 0 12px 24px color-mix(in srgb, var(--accent-strong) 24%, transparent);
}

.nav-button--secondary,
.action-button--secondary {
  color: var(--text-primary) !important;
  background: var(--detail-secondary-bg) !important;
  border-color: var(--detail-secondary-border) !important;
}

.nav-button--secondary:hover,
.action-button--secondary:hover,
.nav-button--secondary:focus-visible,
.action-button--secondary:focus-visible {
  background: var(--detail-secondary-hover) !important;
  border-color: color-mix(in srgb, var(--accent-strong) 28%, var(--border-soft)) !important;
}

.hero-grid,
.market-board-grid,
.detail-grid {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  gap: 18px;
}

.glass-card {
  border: 1px solid var(--border-soft);
  background: var(--panel-surface);
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.quote-card {
  :deep(.el-card__body) {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
}

.quote-heading {
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.quote-price-block {
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.quote-price {
  font-size: 40px;
  font-weight: 800;
  color: var(--text-primary);
}

.quote-source-badge {
  padding: 6px 12px;
  border-radius: 999px;
  color: var(--accent-strong);
  background: color-mix(in srgb, var(--accent-strong) 14%, var(--surface-soft));
  border: 1px solid color-mix(in srgb, var(--accent-strong) 24%, transparent);
  font-size: 12px;
  font-weight: 700;
}

.quote-session {
  color: var(--text-muted);
  font-size: 13px;
}

.quote-change {
  justify-content: space-between;
  padding: 14px 16px;
  border-radius: 18px;
  background: var(--detail-muted-panel);
  font-size: 18px;
  font-weight: 700;

  strong {
    font-size: 24px;
  }
}

.quote-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.quote-stat-item {
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid color-mix(in srgb, var(--border-soft) 86%, transparent);
  background: var(--detail-strong-panel);

  span {
    color: var(--text-muted);
    font-size: 12px;
  }

  strong {
    color: var(--text-primary);
    font-size: 15px;
  }
}

.quote-meta {
  flex-wrap: wrap;
  color: var(--text-secondary);
}

.source-layer-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.source-layer-item {
  display: grid;
  gap: 4px;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid var(--border-soft);
  background: var(--surface-muted);

  span,
  small {
    color: var(--text-muted);
    font-size: 12px;
  }

  strong {
    color: var(--text-primary);
    font-size: 15px;
  }
}

.snapshot-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.snapshot-item {
  justify-content: space-between;
  padding: 14px 16px;
  border-radius: 18px;
  background: var(--surface-muted);
  color: var(--text-secondary);

  strong {
    color: var(--text-primary);
  }
}

.chart-card :deep(.el-card__body) {
  padding-top: 10px;
}

.content-card :deep(.el-card__body) {
  padding-top: 8px;
}

.line-chart {
  height: 420px;
}

.ai-panel,
.market-panel,
.content-list,
.trade-tape,
.ai-empty-state {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.market-board-grid {
  grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.75fr);
}

.order-book {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.order-book--compact {
  align-items: stretch;
}

.book-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.book-summary-item {
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 16px;
  background: var(--detail-muted-panel);

  span {
    color: var(--text-muted);
    font-size: 12px;
  }

  strong {
    color: var(--text-primary);
    font-size: 15px;
  }
}

.book-side {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  border-radius: 18px;
  background: var(--detail-muted-panel);
}

.book-title {
  color: var(--text-primary);
  font-weight: 700;
}

.book-row,
.trade-row,
.content-head,
.content-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.book-row,
.trade-row {
  color: var(--text-secondary);
  font-size: 13px;
}

.trade-row,
.content-item {
  padding: 16px;
  border-radius: 18px;
  background: var(--detail-muted-panel);
}

.trade-row strong,
.content-head strong {
  color: var(--text-primary);
}

.trade-tape--compact {
  gap: 10px;
}

.trade-tape--compact .trade-row {
  padding: 12px 14px;
}

.trade-row > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.market-block {
  padding: 16px;
  border-radius: 18px;
  background: var(--surface-muted);

  strong {
    color: var(--text-primary);
  }

  p {
    margin: 10px 0 0;
    color: var(--text-secondary);
    line-height: 1.7;
  }
}

.ai-panel p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.content-item p {
  margin: 10px 0 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.content-head span,
.content-footer {
  color: var(--text-muted);
  font-size: 12px;
}

.content-link-button {
  color: var(--accent-strong);
}

.ai-time {
  color: var(--text-muted);
  font-size: 12px;
}

.original-content-frame-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}

.original-content-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-muted);
  font-size: 12px;
}

.original-content-frame {
  width: 100%;
  min-height: 72vh;
  border: 1px solid var(--border-soft);
  border-radius: 18px;
  background: #fff;
}

.original-content-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
}

.original-content-drawer :deep(.el-drawer__body) {
  padding-top: 12px;
}

.positive {
  color: var(--success);
}

.negative {
  color: var(--danger);
}

.neutral {
  color: var(--text-primary);
}

@media (max-width: 1100px) {
  .hero-grid,
  .market-board-grid,
  .detail-grid,
  .snapshot-grid,
  .order-book,
  .quote-stat-grid,
  .book-summary {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .page-nav,
  .quote-heading,
  .quote-change {
    flex-direction: column;
    align-items: stretch;
  }

  .page-nav-actions,
  .header-actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .nav-button,
  .action-button {
    flex: 1 1 160px;
  }

  .quote-price {
    font-size: 32px;
  }

  .line-chart {
    height: 320px;
  }

  .original-content-frame {
    min-height: 60vh;
  }
}
</style>

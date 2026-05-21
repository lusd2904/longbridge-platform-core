<template>
  <div class="recommendations-page">
    <section class="recommendation-control-panel glass-card">
      <div class="recommendation-control-main">
        <div class="recommendation-title">
          <strong>智能化推荐</strong>
          <div class="recommendation-chip-row">
            <span
              v-for="chip in recommendationHeroChips"
              :key="chip.text"
              :class="chip.tone"
            >
              {{ chip.text }}
            </span>
          </div>
        </div>
        <div class="hero-actions">
          <el-radio-group v-model="recommendType" size="large" class="recommend-type-switch">
            <el-radio-button value="growth">成长型</el-radio-button>
            <el-radio-button value="value">价值型</el-radio-button>
            <el-radio-button value="dividend">稳健收益型</el-radio-button>
            <el-radio-button value="momentum">动量型</el-radio-button>
          </el-radio-group>
          <el-button class="primary-action-button" :icon="Refresh" :loading="loading" @click="handleRefresh">
            立即刷新
          </el-button>
        </div>
      </div>
      <div class="recommendation-control-metrics">
        <article v-for="metric in recommendationHeroMetrics" :key="metric.label">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
        </article>
      </div>
    </section>

    <MetricStrip :items="recommendationOverviewMetrics" />

    <ReadModelSourceStrip
      label="推荐状态"
      :status-text="recommendationReadModelStatus"
      :status-type="recommendationReadModelStatusType"
      :updated-at="recommendationReadModelUpdatedAt"
      :updated-prefix="recommendationReadModelUpdatedPrefix"
      :tags="recommendationReadModelTags"
    />

    <div class="stats-row">
      <el-card v-for="stat in statsCards" :key="stat.label" class="stat-card">
        <div class="stat-content">
          <div class="stat-icon" :style="{ background: stat.color }">
            <el-icon size="22" color="white">
              <component :is="stat.icon" />
            </el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">{{ stat.label }}</div>
            <div class="stat-value">{{ stat.value }}</div>
          </div>
        </div>
      </el-card>
    </div>

    <div class="content-grid">
      <el-card class="spotlight-card">
        <template #header>
          <SectionCardHeader
            title="重点标的"
            :badge="`${topPicks.length} 个重点标的`"
            badge-type="danger"
          >
            <template #actions>
              <el-input
                v-model="searchKeyword"
                placeholder="搜索代码 / 名称"
                :prefix-icon="Search"
                clearable
                style="width: 220px"
              />
            </template>
          </SectionCardHeader>
        </template>

        <div class="spotlight-list" v-if="topPicks.length">
          <article v-for="stock in topPicks" :key="stock.symbol" class="spotlight-item">
            <div class="spotlight-main">
              <div class="symbol-row">
                <strong>{{ stock.symbol }}</strong>
                <span>{{ stock.name }}</span>
                <el-tag size="small" type="danger" effect="dark">重点</el-tag>
              </div>
              <div class="thesis-block">
                <p v-for="(paragraph, index) in getReadableParagraphs(stock.thesis)" :key="`${stock.symbol}-${index}`">
                  {{ paragraph }}
                </p>
              </div>
              <div class="reason-row">
                <span v-for="reason in stock.reasons" :key="reason">{{ reason }}</span>
              </div>
            </div>

            <div class="spotlight-side">
              <strong>{{ formatPercent(stock.expectedReturn) }}</strong>
              <span v-if="stock.quoteReady">现价 {{ formatMarketCurrency(stock.price, stock.market) }}</span>
              <span v-if="stock.quoteReady" :class="trendClass(stock.changePercent)">{{ formatPercent(stock.changePercent) }}</span>
              <span>评分 {{ formatDecimal(stock.aiScore) }}</span>
              <span>{{ stock.market }} / {{ stock.assetType === 'etf' ? 'ETF' : '股票' }}</span>
              <div class="spotlight-actions">
                <el-button class="pool-button" size="small" @click="addToPool(stock)">加入股票池</el-button>
                <el-button class="trade-button" size="small" @click="quickTrade(stock)">去交易</el-button>
              </div>
            </div>
          </article>
        </div>
        <el-empty v-else-if="!loading" description="暂无推荐结果" />
      </el-card>

      <div class="side-panels">
        <el-card class="chart-card">
          <template #header>
            <SectionCardHeader
              title="市场分布"
            />
          </template>
          <div class="chart-container">
            <v-chart class="chart" :option="distributionChartOption" autoresize />
          </div>
        </el-card>

        <el-card class="chart-card">
          <template #header>
            <SectionCardHeader
              title="评分与收益"
            />
          </template>
          <div class="chart-container">
            <v-chart class="chart" :option="scoreChartOption" autoresize />
          </div>
        </el-card>
      </div>
    </div>

    <el-card class="recommendations-table">
      <template #header>
        <SectionCardHeader
          title="候选明细"
          :badge="quoteSnapshotCoverage"
        />
      </template>

      <el-table :data="pagedRecommendations" v-loading="loading && !items.length" style="width: 100%">
        <template #empty>
          <div class="table-empty-state">
            <strong>{{ loading ? '推荐加载中' : '暂无候选明细' }}</strong>
          </div>
        </template>
        <el-table-column prop="symbol" label="代码" width="110" />
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column prop="market" label="市场" width="90" />
        <el-table-column prop="assetType" label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.assetType === 'etf' ? 'warning' : 'info'">
              {{ row.assetType === 'etf' ? 'ETF' : '股票' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="price" label="现价" width="120">
          <template #default="{ row }">
            {{ formatMarketCurrency(row.price, row.market) }}
          </template>
        </el-table-column>
        <el-table-column prop="changePercent" label="涨跌幅" width="110">
          <template #default="{ row }">
            <span :class="trendClass(row.changePercent)">{{ formatPercent(row.changePercent) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="expectedReturn" label="预期收益" width="110">
          <template #default="{ row }">
            <span class="up">{{ formatPercent(row.expectedReturn) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aiScore" label="评分" width="100">
          <template #default="{ row }">
            {{ formatDecimal(row.aiScore) }}
          </template>
        </el-table-column>
        <el-table-column prop="confidence" label="置信度" width="100">
          <template #default="{ row }">
            {{ formatPercent(row.confidence, { signed: false }) }}
          </template>
        </el-table-column>
        <el-table-column prop="riskLevel" label="风险" width="120">
          <template #default="{ row }">
            <el-rate v-model="row.riskLevel" disabled :max="5" />
          </template>
        </el-table-column>
        <el-table-column prop="horizon" label="周期" width="90" />
        <el-table-column prop="thesis" label="推荐摘要" min-width="320">
          <template #default="{ row }">
            <div class="table-thesis">
              <p v-for="(paragraph, index) in getReadableParagraphs(row.thesis)" :key="`${row.symbol}-table-${index}`">
                {{ paragraph }}
              </p>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="totalRecommendations"
          layout="total, sizes, prev, pager, next, jumper"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Histogram, Refresh, Search, Star, TrendCharts, Warning } from '@element-plus/icons-vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { getRecommendations, refreshRecommendations } from '../api/analysis.js'
import { addStockToPool, getStockQuotes } from '../api/market.js'
import { formatCurrency, formatDecimal, formatPercent } from '../utils/formatters.js'
import { buildQuoteSnapshotMap, mergeQuoteSnapshots, summarizeQuoteSnapshotCoverage } from '../utils/quoteSnapshot.js'
import { buildRecommendationReadModelSummary, formatQuoteCoverageLabel } from '../utils/readModelSource.js'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import { useRouter } from 'vue-router'
import { useTheme } from '../composables/useTheme.js'
import MetricStrip from '../components/common/MetricStrip.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'

use([CanvasRenderer, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent])

const router = useRouter()
const { activeTheme } = useTheme()
const recommendType = ref('growth')
const searchKeyword = ref('')
const loading = ref(false)
const isAlive = ref(true)
const currentPage = ref(1)
const pageSize = ref(10)
const recommendationData = ref({
  stats: {},
  items: []
})
const recommendationMeta = ref({})

const readThemeValue = (variableName, fallback) => {
  activeTheme.value
  if (typeof window === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(variableName).trim()
  return value || fallback
}

const profileLabelMap = {
  growth: '成长型',
  value: '价值型',
  dividend: '稳健收益型',
  momentum: '动量型'
}

const PROMPT_ARTIFACT_PATTERNS = [
  /we need to produce/i,
  /must be within/i,
  /let'?s craft/i,
  /count characters/i,
  /position sizing/i,
  /market distribution/i,
  /including punctuation/i,
  /growth style/i,
  /use candidates list/i,
  /use (the )?data/i,
  /核心催化\s*\(list/i,
  /主要风险\s*\(list/i,
  /综合评分\s*\(0-?100\)/i,
  /置信度\s*\(0-?100\)/i
]

const profileLabel = computed(() => profileLabelMap[recommendType.value] || '成长型')
const items = computed(() => Array.isArray(recommendationData.value?.items) ? recommendationData.value.items : [])
const summaryParagraphs = computed(() => getReadableParagraphs(
  recommendationData.value.summary || ''
))

const quoteSnapshotCoverage = computed(() => {
  const coverage = summarizeQuoteSnapshotCoverage(recommendationData.value?.items || [])
  return formatQuoteCoverageLabel(coverage, { prefix: '长桥实时', emptyLabel: '等待长桥实时' })
})
const recommendationQuoteCoverage = computed(() => summarizeQuoteSnapshotCoverage(recommendationData.value?.items || []))
const recommendationReadModelSummary = computed(() => buildRecommendationReadModelSummary(
  recommendationMeta.value,
  {
    count: recommendationData.value?.candidate_count || items.value.length,
    profileLabel: recommendationData.value.profile_label || profileLabel.value,
    quoteCoverageLabel: recommendationQuoteCoverage.value.readyCount
      ? `长桥实时 ${recommendationQuoteCoverage.value.readyCount}/${recommendationQuoteCoverage.value.totalCount || 0}`
      : '长桥实时待补齐'
  }
))
const recommendationReadModelStatus = computed(() => recommendationReadModelSummary.value.statusText)
const recommendationReadModelStatusType = computed(() => recommendationReadModelSummary.value.statusType)
const recommendationReadModelUpdatedAt = computed(() => recommendationReadModelSummary.value.updatedAt || recommendationData.value.generated_at || '')
const recommendationReadModelUpdatedPrefix = computed(() => recommendationReadModelSummary.value.updatedPrefix || '生成于')
const recommendationReadModelTags = computed(() => recommendationReadModelSummary.value.tags || [])
const recommendationHeroChips = computed(() => ([
  {
    text: recommendationReadModelStatus.value,
    tone: recommendationReadModelStatusType.value === 'success' ? 'healthy' : recommendationReadModelStatusType.value
  },
  {
    text: recommendationData.value.profile_label || profileLabel.value,
    tone: 'info'
  },
  {
    text: quoteSnapshotCoverage.value,
    tone: recommendationQuoteCoverage.value.readyCount ? 'healthy' : 'warning'
  }
]))
const recommendationHeroMetrics = computed(() => ([
  {
    label: '更新时间',
    value: recommendationData.value.generated_at || '--',
    note: recommendationReadModelUpdatedPrefix.value
  },
  {
    label: '候选数量',
    value: `${recommendationData.value.candidate_count || items.value.length || 0}`,
    note: '当前推荐池'
  },
  {
    label: '下次刷新',
    value: `${recommendationData.value.stats?.next_refresh_minutes || '--'} 分钟`,
    note: '调度节奏'
  }
]))
const recommendationOverviewMetrics = computed(() => ([
  {
    label: '当前风格',
    value: recommendationData.value.profile_label || profileLabel.value,
    note: '当前推荐画像',
    tone: 'info'
  },
  {
    label: '行情快照',
    value: quoteSnapshotCoverage.value,
    note: '最新报价'
  },
  {
    label: '今日推荐',
    value: String(recommendationData.value?.stats?.total || 0),
    note: '已入榜候选数量'
  },
  {
    label: '平均 AI 分',
    value: formatDecimal(recommendationData.value?.stats?.avg_score || 0),
    note: '推荐池平均质量'
  }
]))

const filteredRecommendations = computed(() => {
  if (!searchKeyword.value) return items.value
  const keyword = searchKeyword.value.toLowerCase()
  return items.value.filter((item) =>
    item.symbol?.toLowerCase().includes(keyword) ||
    item.name?.toLowerCase().includes(keyword)
  )
})

const totalRecommendations = computed(() => filteredRecommendations.value.length)

const pagedRecommendations = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredRecommendations.value.slice(start, start + pageSize.value)
})

const topPicks = computed(() => filteredRecommendations.value.filter((item) => item.isTopPick).slice(0, 4))

const statsCards = computed(() => {
  const stats = recommendationData.value?.stats || {}
  return [
    { label: '今日推荐', value: stats.total || 0, icon: Star, color: 'linear-gradient(135deg, #3f89ff, #62c2ff)' },
    { label: '平均预期收益', value: formatPercent(stats.avg_return || 0), icon: TrendCharts, color: 'linear-gradient(135deg, #10b981, #42d392)' },
    { label: '平均评分', value: formatDecimal(stats.avg_score || 0), icon: Check, color: 'linear-gradient(135deg, #f59e0b, #fbbf24)' },
    { label: '风险预警', value: stats.risk_alerts || 0, icon: Warning, color: 'linear-gradient(135deg, #ef4444, #fb7185)' }
  ]
})

const distributionChartOption = computed(() => {
  const markets = recommendationData.value?.stats?.markets || {}
  const data = Object.entries(markets).map(([name, value]) => ({ name, value }))
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { color: readThemeValue('--text-secondary', '#90a3bf') } },
    series: [
      {
        type: 'pie',
        radius: ['50%', '74%'],
        itemStyle: { borderRadius: 14, borderColor: 'transparent', borderWidth: 4 },
        label: { color: readThemeValue('--text-primary', '#ffffff') },
        data
      }
    ]
  }
})

const scoreChartOption = computed(() => {
  const targets = filteredRecommendations.value.slice(0, 6)
  return {
    grid: { left: '4%', right: '4%', bottom: '3%', top: '8%', containLabel: true },
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['评分', '预期收益'],
      bottom: 0,
      textStyle: { color: readThemeValue('--text-secondary', '#90a3bf') }
    },
    xAxis: {
      type: 'category',
      data: targets.map((item) => item.symbol),
      axisLabel: { color: readThemeValue('--text-secondary', '#90a3bf') },
      axisLine: { lineStyle: { color: readThemeValue('--chart-grid', 'rgba(255,255,255,0.12)') } }
    },
    yAxis: [
      {
        type: 'value',
        axisLabel: { color: readThemeValue('--text-secondary', '#90a3bf') },
        splitLine: { lineStyle: { color: readThemeValue('--chart-grid', 'rgba(255,255,255,0.12)') } }
      },
      {
        type: 'value',
        axisLabel: { color: readThemeValue('--text-secondary', '#90a3bf') },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: '评分',
        type: 'bar',
        data: targets.map((item) => item.aiScore),
        itemStyle: { color: '#4f9bff', borderRadius: [12, 12, 0, 0] }
      },
      {
        name: '预期收益',
        type: 'bar',
        yAxisIndex: 1,
        data: targets.map((item) => item.expectedReturn),
        itemStyle: { color: '#22c55e', borderRadius: [12, 12, 0, 0] }
      }
    ]
  }
})

const formatMarketCurrency = (value, market = 'US') => {
  const currency = market === 'CN' ? '¥' : market === 'HK' ? 'HK$' : '$'
  return formatCurrency(value, { currency })
}

const trendClass = (value) => {
  if (Number(value) > 0) return 'up'
  if (Number(value) < 0) return 'down'
  return 'flat'
}

const looksLikePromptArtifact = (text = '') => {
  const source = String(text || '').trim()
  if (!source) {
    return false
  }
  return PROMPT_ARTIFACT_PATTERNS.some((pattern) => pattern.test(source))
}

const buildFallbackRecommendationSummary = (payload = {}) => {
  const rawItems = Array.isArray(payload?.items) ? payload.items : []
  const stats = payload?.stats || {}
  const symbols = rawItems.slice(0, 3).map((item) => item?.symbol).filter(Boolean)
  const marketMix = Object.entries(stats?.markets || {})
    .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
    .slice(0, 2)
    .map(([market, count]) => `${market} ${count}只`)
    .join('、')
  const profile = payload?.profile_label || profileLabelMap[payload?.profile] || profileLabel.value

  return [
    `${profile}当前共 ${stats?.total || rawItems.length || 0} 个候选。`,
    symbols.length ? `优先关注 ${symbols.join('、')}。` : '',
    marketMix ? `分布以 ${marketMix} 为主，建议分批布局并控制单票仓位。` : '建议分批布局，并保持 ETF 与个股的均衡配置。'
  ].join('')
}

const sanitizeRecommendationText = (text = '', fallback = '') => {
  const source = String(text || '').trim()
  if (!source) {
    return String(fallback || '').trim()
  }
  if (looksLikePromptArtifact(source)) {
    return String(fallback || '').trim()
  }

  return source
    .replace(/\*\*/g, '')
    .replace(/`+/g, '')
    .replace(/\r/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

const normalizeRecommendationItem = (item = {}) => {
  const rawReasons = Array.isArray(item?.reasons) ? item.reasons.filter(Boolean) : []
  const reasonText = rawReasons.join(' ')
  const reasons = looksLikePromptArtifact(reasonText) || /核心催化|主要风险|综合评分|置信度|\blist\b/i.test(reasonText)
    ? [
        item?.market ? `${item.market} 市场当前排序靠前` : '',
        Number.isFinite(Number(item?.aiScore ?? item?.score)) ? `量化分数 ${formatDecimal(item?.aiScore ?? item?.score)}` : '',
        Number.isFinite(Number(item?.expectedReturn)) ? `预期收益 ${formatPercent(item.expectedReturn)}` : ''
      ].filter(Boolean)
    : rawReasons.map((entry) => sanitizeRecommendationText(entry)).filter(Boolean)
  const fallbackThesis = [
    reasons.length ? `核心看点：${reasons.slice(0, 3).join('、')}` : '',
    item?.market ? `所属市场：${item.market}` : '',
    Number.isFinite(Number(item?.expectedReturn)) ? `预期收益 ${formatPercent(item.expectedReturn)}` : ''
  ]
    .filter(Boolean)
    .join('。')

  return {
    ...item,
    thesis: sanitizeRecommendationText(item?.thesis, fallbackThesis)
  }
}

const getReadableParagraphs = (text = '') => {
  const source = sanitizeRecommendationText(text)
  if (!source) {
    return []
  }

  const normalized = source
    .replace(/\r/g, '')
    .replace(/([。！？!?])/g, '$1\n')
    .replace(/([；;])/g, '$1\n')
    .replace(/(推荐摘要[:：]?)/g, '\n$1')
    .replace(/(核心催化[:：]?)/g, '\n$1')
    .replace(/(主要风险[:：]?)/g, '\n$1')

  return normalized
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

const loadRecommendations = async (forceRefresh = false) => {
  loading.value = true
  try {
    const res = forceRefresh
      ? await refreshRecommendations({ profile: recommendType.value })
      : await getRecommendations({ profile: recommendType.value })
    const payload = res?.data || { stats: {}, items: [] }
    const normalizedItems = (Array.isArray(payload?.items) ? payload.items : []).map((item) => normalizeRecommendationItem(item))
    recommendationMeta.value = res?.meta && typeof res.meta === 'object' ? res.meta : {}
    recommendationData.value = {
      ...payload,
      generated_at: payload?.generated_at || recommendationMeta.value.generatedAt || recommendationMeta.value.snapshotAt || '',
      summary: sanitizeRecommendationText(payload?.summary, buildFallbackRecommendationSummary(payload)),
      items: normalizedItems
    }
    try {
      const quoteRes = await getStockQuotes(normalizedItems.map((item) => item.symbol))
      const quoteMap = buildQuoteSnapshotMap(quoteRes?.data || [])
      recommendationData.value = {
        ...recommendationData.value,
        items: mergeQuoteSnapshots(normalizedItems, quoteMap)
      }
    } catch (quoteError) {
      console.warn('推荐长桥实时行情加载失败:', quoteError)
    }
  } catch (error) {
    const message = String(error?.message || '')
    if (message.includes('Failed to fetch')) {
      return
    }
    console.error('加载推荐失败:', error)
    recommendationMeta.value = {}
    ElMessage.error('加载推荐失败')
  } finally {
    if (isAlive.value) {
      loading.value = false
    }
  }
}

const handleRefresh = async () => {
  await loadRecommendations(true)
  ElMessage.success('推荐结果已刷新')
}

const addToPool = async (stock) => {
  try {
    await addStockToPool({
      symbol: stock.symbol,
      name: stock.name,
      market: stock.market,
      type: stock.assetType
    })
    ElMessage.success(`${stock.symbol} 已加入股票池`)
  } catch (error) {
    ElMessage.error(error?.message || '添加失败')
  }
}

const quickTrade = (stock) => {
  router.push({
    name: 'Trading',
    query: { symbol: stock.symbol, action: 'buy' }
  })
}

watch(recommendType, () => {
  currentPage.value = 1
  loadRecommendations(false)
})

watch(searchKeyword, () => {
  currentPage.value = 1
})

onMounted(() => {
  isAlive.value = true
  loadRecommendations(false)
})

onUnmounted(() => {
  isAlive.value = false
})
</script>

<style scoped lang="scss">
.recommendations-page {
  padding: 8px;
  display: grid;
  gap: 10px;
}

.glass-card {
  border: 1px solid var(--border-soft);
  background: var(--surface-strong);
  box-shadow: var(--shadow-strong);
}

.recommendation-control-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 0.28fr);
  align-items: center;
  gap: 10px;
  border-radius: 10px;
  padding: 10px;
}

.recommendation-control-main {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.recommendation-title {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.recommendation-title strong {
  color: var(--text-emphasis);
  font-size: 16px;
}

.recommendation-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.recommendation-chip-row span {
  border: 1px solid color-mix(in srgb, var(--border-soft) 76%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
  color: var(--text-muted);
  font-size: 12px;
  padding: 4px 8px;
}

.recommendation-chip-row span.healthy,
.recommendation-chip-row span.success {
  border-color: color-mix(in srgb, var(--success) 36%, var(--border-soft));
  background: color-mix(in srgb, var(--success) 12%, var(--surface-soft));
  color: var(--success);
}

.recommendation-chip-row span.warning {
  border-color: color-mix(in srgb, var(--warning) 36%, var(--border-soft));
  background: color-mix(in srgb, var(--warning) 12%, var(--surface-soft));
  color: var(--warning);
}

.recommendation-chip-row span.info {
  border-color: color-mix(in srgb, var(--accent) 30%, var(--border-soft));
  background: color-mix(in srgb, var(--accent) 10%, var(--surface-soft));
  color: color-mix(in srgb, var(--accent-strong, var(--accent)) 88%, white 12%);
}

.recommendation-control-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.recommendation-control-metrics article {
  min-width: 0;
  border: 1px solid color-mix(in srgb, var(--border-soft) 78%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface-soft) 86%, transparent);
  padding: 7px 8px;
}

.recommendation-control-metrics span {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
}

.recommendation-control-metrics strong {
  display: block;
  margin-top: 4px;
  color: var(--text-emphasis);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-block,
.thesis-block {
  display: grid;
  gap: 8px;
}

.summary-block p,
.thesis-block p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.75;
}

.table-thesis {
  display: grid;
  gap: 6px;
}

.table-thesis p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.6;
}

.hero-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.recommend-type-switch :deep(.el-radio-button__inner) {
  border-color: color-mix(in srgb, var(--border-soft) 84%, transparent);
  background: color-mix(in srgb, var(--surface-soft) 82%, transparent);
  color: var(--text-primary);
  min-height: 34px;
  font-weight: 700;
}

.recommend-type-switch :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  border-color: color-mix(in srgb, var(--accent) 56%, var(--border-soft));
  background: color-mix(in srgb, var(--accent-strong, var(--accent)) 74%, var(--surface-strong));
  color: var(--button-primary-text, #fff);
  box-shadow: none;
}

.primary-action-button,
.pool-button,
.trade-button {
  border-color: color-mix(in srgb, var(--accent) 34%, var(--border-soft)) !important;
  background: color-mix(in srgb, var(--accent-strong, var(--accent)) 72%, var(--surface-strong)) !important;
  color: var(--button-primary-text, #fff) !important;
  font-weight: 700;
}

.primary-action-button:hover,
.pool-button:hover,
.trade-button:hover {
  border-color: color-mix(in srgb, var(--accent) 62%, var(--border-soft)) !important;
  background: color-mix(in srgb, var(--accent-strong, var(--accent)) 84%, var(--surface-strong)) !important;
  color: var(--button-primary-text, #fff) !important;
}

.trade-button {
  background: color-mix(in srgb, var(--surface-soft) 82%, var(--accent) 12%) !important;
  color: var(--text-emphasis) !important;
}

.trade-button:hover {
  background: color-mix(in srgb, var(--accent) 18%, var(--surface-soft)) !important;
  color: var(--text-emphasis) !important;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.stat-card {
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: var(--surface-strong);
  box-shadow: var(--shadow-strong);
}

.stat-content {
  display: flex;
  align-items: center;
  gap: 14px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 16px;
  display: grid;
  place-items: center;
}

.stat-info {
  display: grid;
  gap: 4px;
}

.stat-label {
  font-size: 13px;
  color: var(--text-muted);
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.85fr);
  gap: 10px;
}

.spotlight-card,
.recommendations-table,
.chart-card {
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: var(--surface-strong);
  box-shadow: var(--shadow-strong);
}

.side-panels {
  display: grid;
  gap: 10px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.table-hint {
  color: var(--text-muted);
  font-size: 12px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}

.spotlight-list {
  display: grid;
  gap: 14px;
}

.spotlight-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 180px;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid var(--panel-stroke);
  background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
}

.symbol-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;

  strong {
    color: var(--text-primary);
    font-size: 18px;
  }

  span {
    color: var(--text-secondary);
  }
}

.spotlight-main {
  p {
    margin: 0 0 12px;
    color: var(--text-primary);
    line-height: 1.7;
  }
}

.reason-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;

  span {
    padding: 6px 10px;
    border-radius: 999px;
    background: var(--surface-muted);
    color: var(--text-muted);
    font-size: 12px;
  }
}

.spotlight-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;

  strong {
    color: var(--success);
    font-size: 26px;
  }

  span {
    color: var(--text-secondary);
    font-size: 13px;
  }
}

.spotlight-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  margin-top: 6px;
}

.chart-container {
  height: 300px;
}

.chart {
  height: 100%;
}

.up {
  color: var(--success);
}

.down {
  color: var(--danger);
}

.flat {
  color: var(--text-muted);
}

.table-empty-state {
  display: grid;
  place-items: center;
  min-height: 120px;
  color: var(--text-secondary);

  strong {
    color: var(--text-primary);
    font-size: 14px;
  }
}

@media (max-width: 1180px) {
  .content-grid,
  .stats-row,
  .recommendation-control-panel,
  .recommendation-control-metrics {
    grid-template-columns: 1fr;
  }

  .spotlight-item {
    grid-template-columns: 1fr;
  }

  .spotlight-side {
    align-items: flex-start;
  }
}
</style>

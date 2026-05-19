<template>
  <div class="finance-news-page">
    <PageHero
      title="财经快讯"
      :chips="financeHeroChips"
      :metrics="financeHeroMetrics"
    >
      <template #actions>
        <div class="header-actions">
          <el-radio-group v-model="selectedMarket" @change="handleMarketChange">
            <el-radio-button value="ALL">全部</el-radio-button>
            <el-radio-button value="US">美股</el-radio-button>
            <el-radio-button value="CN">A股</el-radio-button>
            <el-radio-button value="HK">港股</el-radio-button>
          </el-radio-group>
          <el-input
            v-model="focusSymbol"
            placeholder="筛选标的，例如 AAPL.US"
            clearable
            style="width: 220px"
            @keyup.enter="applyLocalFilters"
          />
          <el-button type="primary" :loading="loading" @click="loadData">刷新</el-button>
        </div>
      </template>
    </PageHero>

    <MetricStrip :items="financeOverviewMetrics" />

    <div class="scan-grid">
      <el-card v-for="scan in visibleScans" :key="scan.market" class="scan-card glass-card">
        <div class="scan-top">
          <div>
            <span class="scan-market">{{ marketLabel(scan.market) }}</span>
            <strong>{{ scan.headline }}</strong>
          </div>
          <el-tag size="small">{{ scan.technicalScore?.toFixed?.(2) || '0.00' }}</el-tag>
        </div>
        <p>{{ clampSummary(scan.summary, 150) }}</p>
        <div class="scan-meta">
          <span>广度 {{ formatPercent(scan.breadthRatio) }}</span>
          <span>{{ formatGeneratedAt(scan.generatedAt) }}</span>
        </div>
      </el-card>
    </div>

    <el-card class="glass-card">
      <template #header>
        <SectionCardHeader
          title="资讯列表"
          :badge="`${filteredItems.length} 条`"
        />
      </template>
      <ReadModelSourceStrip
        label="资讯状态"
        :status-text="financeSourceSummary.sourceLabel"
        :status-type="financeSourceSummary.statusType"
        :updated-at="financeSourceSummary.updatedAt ? formatGeneratedAt(financeSourceSummary.updatedAt) : (financeSnapshotAt ? formatGeneratedAt(financeSnapshotAt) : '')"
        :tags="financeSourceTags"
        compact
      />

      <div class="briefing-list">
        <article v-for="item in filteredItems" :key="item.id" class="briefing-item">
          <div class="briefing-head">
            <div class="headline-wrap">
              <el-tag size="small" :type="marketTagType(item.market)">{{ marketLabel(item.market) }}</el-tag>
              <el-tag size="small" effect="plain">{{ typeLabel(item.briefingType) }}</el-tag>
              <h3>{{ item.headline }}</h3>
            </div>
            <span class="briefing-time">{{ formatGeneratedAt(item.generatedAt) }}</span>
          </div>
          <p class="briefing-summary">{{ cleanText(item.summary) }}</p>
          <div class="briefing-footer">
            <span>{{ item.sourceName || 'system' }}</span>
            <span v-if="itemSymbolLabel(item)">关注 {{ itemSymbolLabel(item) }}</span>
            <a v-if="item.sourceLink" :href="item.sourceLink" target="_blank" rel="noreferrer">查看原文</a>
          </div>
        </article>
      </div>

      <el-empty v-if="!filteredItems.length && !loading" description="暂无财经快讯" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getFinanceBriefings } from '../api/analysis.js'
import { formatPercent as formatPercentValue } from '../utils/formatters.js'
import { buildFinanceBriefingReadModelSummary, summarizeBriefingDataset } from '../utils/readModelSource.js'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import PageHero from '../components/common/PageHero.vue'
import MetricStrip from '../components/common/MetricStrip.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'

const loading = ref(false)
const selectedMarket = ref('ALL')
const focusSymbol = ref('')
const items = ref([])
const financeSnapshotAt = ref('')
const financeMeta = ref({})

const financeDatasetSummary = computed(() => summarizeBriefingDataset(items.value))
const financeSourceSummary = computed(() => buildFinanceBriefingReadModelSummary(
  financeMeta.value,
  {
    count: items.value.length,
    filteredCount: filteredItems.value.length,
    marketLabel: selectedMarket.value === 'ALL' ? '全部市场' : marketLabel(selectedMarket.value)
  }
))
const financeSourceTags = computed(() => ([
  ...(financeSourceSummary.value.tags || [])
    .filter((tag) => !/^\d+\s*条$/.test(String(tag?.text || '').trim())),
  ...(loading.value && items.value.length ? [{ text: '后台刷新中', type: 'warning' }] : []),
  { text: `${filteredItems.value.length} 条`, type: 'success' },
  { text: focusSymbol.value ? `关注 ${focusSymbol.value}` : '全部标的', type: 'info' }
]))
const financeHeroChips = computed(() => ([
  {
    text: marketLabel(selectedMarket.value),
    tone: selectedMarket.value === 'ALL'
      ? 'info'
      : selectedMarket.value === 'CN'
        ? 'success'
        : selectedMarket.value === 'HK'
          ? 'warning'
          : 'info'
  },
  {
    text: focusSymbol.value ? `关注 ${focusSymbol.value}` : '全部标的',
    tone: focusSymbol.value ? 'healthy' : 'info'
  },
  {
    text: financeSourceSummary.value.sourceLabel,
    tone: financeSourceSummary.value.statusType === 'success' ? 'healthy' : financeSourceSummary.value.statusType
  }
]))
const financeHeroMetrics = computed(() => ([
  {
    label: '资讯数量',
    value: `${filteredItems.value.length} 条`,
    note: '当前筛选结果'
  },
  {
    label: '市场扫描',
    value: `${visibleScans.value.length} 个`,
    note: '摘要卡片数量'
  },
  {
    label: '最近快照',
    value: formatGeneratedAt(financeSnapshotAt.value),
    note: '聚合时刻'
  }
]))
const financeOverviewMetrics = computed(() => ([
  {
    label: '当前市场',
    value: marketLabel(selectedMarket.value),
    note: '筛选维度',
    tone: selectedMarket.value === 'ALL' ? 'info' : ''
  },
  {
    label: '关注标的',
    value: focusSymbol.value || '全部标的',
    note: '本地筛选关键词'
  },
  {
    label: '数据来源',
    value: financeSourceSummary.value.sourceLabel,
    note: financeSourceSummary.value.detail
  },
  {
    label: '最近快照',
    value: formatGeneratedAt(financeSnapshotAt.value),
    note: '最新聚合批次'
  }
]))

const filteredItems = computed(() => {
  const marketFiltered = selectedMarket.value === 'ALL'
    ? items.value
    : items.value.filter((item) => item.market === selectedMarket.value)
  const symbolKeyword = String(focusSymbol.value || '').trim().toUpperCase()
  if (!symbolKeyword) {
    return marketFiltered
  }
  return marketFiltered.filter((item) => itemSymbolLabel(item).includes(symbolKeyword) || String(item.headline || '').toUpperCase().includes(symbolKeyword))
})

const visibleScans = computed(() => {
  const grouped = new Map()
  filteredItems.value
    .filter((item) => ['market-insight', 'market-ai-scan'].includes(item.briefingType))
    .forEach((item) => {
      const marketKey = item.market || 'ALL'
      const current = grouped.get(marketKey) || {
        market: marketKey,
        headline: '',
        summary: '',
        technicalScore: 0,
        breadthRatio: 0,
        generatedAt: item.generatedAt || '',
        insightHeadline: '',
        insightSummary: ''
      }

      if (item.briefingType === 'market-ai-scan') {
        current.headline = item.headline || current.headline
        current.summary = cleanText(item.summary) || current.summary
        current.technicalScore = Number(item.payload?.technicalScore || 0)
        current.breadthRatio = Number(item.payload?.breadthRatio || 0)
        current.generatedAt = item.generatedAt || current.generatedAt
      } else if (item.briefingType === 'market-insight') {
        current.insightHeadline = item.headline || current.insightHeadline
        current.insightSummary = cleanText(item.summary) || current.insightSummary
        current.generatedAt = item.generatedAt || current.generatedAt
      }

      grouped.set(marketKey, current)
    })

  return Array.from(grouped.values()).map((item) => ({
    ...item,
    headline: item.headline || item.insightHeadline || `${marketLabel(item.market)} 市场简报`,
    summary: item.summary || item.insightSummary || ''
  }))
})

const marketLabel = (market) => ({ US: '美股', CN: 'A股', HK: '港股' }[market] || market || '全部')
const typeLabel = (type) => ({
  'market-insight': '市场动态',
  'market-ai-scan': '技术扫描',
  'market-news': '外部资讯',
  announcements: '公告',
  topics: '讨论',
  recommendation: '推荐关注',
  internal: '系统简报'
}[type] || '简报')
const marketTagType = (market) => ({ US: 'primary', CN: 'success', HK: 'warning' }[market] || 'info')
const formatPercent = (value) => formatPercentValue(value, { signed: true })
const formatGeneratedAt = (value) => {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN')
}
const itemSymbolLabel = (item) => String(item?.payload?.symbol || '').trim()
const cleanText = (text = '') => String(text || '')
  .replace(/&nbsp;/gi, ' ')
  .replace(/&amp;/gi, '&')
  .replace(/&lt;/gi, '<')
  .replace(/&gt;/gi, '>')
  .replace(/&#39;/g, "'")
  .replace(/&quot;/gi, '"')
  .replace(/\s+/g, ' ')
  .trim()

const clampSummary = (text = '', limit = 160) => {
  const source = cleanText(text)
  if (!source || source.length <= limit) {
    return source
  }
  return `${source.slice(0, limit).trim()}...`
}

const dedupeItems = (list = []) => {
  const seen = new Set()
  return list.filter((item) => {
    const key = [
      item.market,
      item.briefingType,
      item.headline,
      item.sourceLink,
      item.generatedAt
    ].join('::')
    if (seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

const applyLocalFilters = () => {
  // 关注标的仍然只做本地筛选；市场维度由后端过滤，避免固定 limit 把目标市场挤掉。
}

const handleMarketChange = () => {
  loadData()
}

const loadData = async () => {
  loading.value = true
  try {
    const params = {
      limit: 60
    }
    if (selectedMarket.value !== 'ALL') {
      params.market = selectedMarket.value
    }
    const res = await getFinanceBriefings(params)
    items.value = dedupeItems(res?.data || [])
      .map((item) => ({
        ...item,
        headline: cleanText(item.headline),
        summary: cleanText(item.summary)
      }))
      .sort((a, b) => String(b.generatedAt || '').localeCompare(String(a.generatedAt || '')))
    financeMeta.value = res?.meta && typeof res.meta === 'object' ? res.meta : {}
    financeSnapshotAt.value = financeMeta.value.snapshotAt || financeDatasetSummary.value.snapshotAt || ''
  } catch (error) {
    console.error('加载财经信息失败:', error)
    ElMessage.error('加载财经信息失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped lang="scss">
.finance-news-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header,
.news-metrics,
.header-actions,
.scan-top,
.scan-meta,
.card-header,
.card-header-tags,
.briefing-head,
.briefing-footer,
.headline-wrap {
  display: flex;
  align-items: center;
}

.page-header {
  justify-content: space-between;
  gap: 18px;

  h2 {
    margin: 0;
    color: var(--text-primary);
  }

  p {
    margin: 6px 0 0;
    color: var(--text-secondary);
  }
}

.header-actions {
  gap: 12px;
  flex-wrap: wrap;
}

.news-metrics {
  gap: 14px;
  flex-wrap: wrap;
}

.metric-card {
  min-width: 160px;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid var(--border-soft);
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
  display: grid;
  gap: 8px;

  span {
    font-size: 12px;
    color: var(--text-muted);
  }

  strong {
    color: var(--text-primary);
    font-size: 16px;
    line-height: 1.35;
  }
}

.scan-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.glass-card {
  border: 1px solid var(--border-soft);
  background: var(--surface-strong);
  box-shadow: var(--shadow-strong);
}

.scan-card {
  :deep(.el-card__body) {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
}

.scan-top {
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;

  strong {
    display: block;
    margin-top: 8px;
    color: var(--text-primary);
  }
}

.scan-market {
  font-size: 12px;
  color: var(--text-muted);
}

.scan-card p,
.briefing-summary {
  color: var(--text-secondary);
  line-height: 1.65;
}

.scan-card p {
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.scan-meta,
.briefing-footer,
.card-header-tags {
  justify-content: space-between;
  color: var(--text-muted);
  font-size: 12px;
  gap: 12px;
  flex-wrap: wrap;
}

.briefing-footer a {
  color: var(--accent-strong);
}

.briefing-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.briefing-item {
  padding: 20px;
  border-radius: 22px;
  border: 1px solid var(--border-soft);
  background: var(--surface-muted);
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    border-color: color-mix(in srgb, var(--accent) 28%, var(--border-soft));
    box-shadow: var(--shadow-soft);
  }
}

.briefing-head {
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.headline-wrap {
  gap: 10px;
  flex-wrap: wrap;
  align-items: flex-start;

  h3 {
    margin: 0;
    color: var(--text-primary);
    font-size: 18px;
    line-height: 1.45;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
}

.briefing-time {
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.briefing-summary {
  margin: 14px 0 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@media (max-width: 1100px) {
  .scan-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 860px) {
  .briefing-head {
    flex-direction: column;
  }

  .briefing-time {
    white-space: normal;
  }
}
</style>

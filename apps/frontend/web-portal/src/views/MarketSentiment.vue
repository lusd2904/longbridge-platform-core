<template>
  <div class="market-sentiment-page">
    <PageHero
      title="市场舆情"
      :chips="heroChips"
      :metrics="heroMetrics"
    >
      <template #actions>
        <div class="header-actions">
          <el-radio-group v-model="selectedMarket" @change="loadOverview">
            <el-radio-button value="ALL">全部</el-radio-button>
            <el-radio-button value="US">美股</el-radio-button>
            <el-radio-button value="CN">A股</el-radio-button>
            <el-radio-button value="HK">港股</el-radio-button>
          </el-radio-group>
          <el-input
            v-model="focusKeyword"
            placeholder="筛选标的 / 风险词"
            clearable
            style="width: 220px"
          />
          <el-button type="primary" :loading="loading" @click="loadOverview">刷新</el-button>
        </div>
      </template>
    </PageHero>

    <MetricStrip :items="overviewMetrics" />

    <el-card class="glass-card">
      <template #header>
        <SectionCardHeader
          title="AI / 配置继承"
          :badge="aiConfigBadge"
        />
      </template>
      <div class="config-grid">
        <div class="config-item">
          <span>Base URL</span>
          <strong>{{ aiConfig.baseUrl || '--' }}</strong>
        </div>
        <div class="config-item">
          <span>Chat Completions</span>
          <strong>{{ aiConfig.chatCompletionsUrl || '--' }}</strong>
        </div>
        <div class="config-item">
          <span>默认模型</span>
          <strong>{{ aiConfig.models?.default || '--' }}</strong>
        </div>
        <div class="config-item">
          <span>扫描 / 总结模型</span>
          <strong>{{ aiConfig.models?.scanPulse || '--' }} / {{ aiConfig.models?.recommendSummary || '--' }}</strong>
        </div>
      </div>
      <p class="config-note">{{ aiConfig.note }}</p>
    </el-card>

    <el-card class="glass-card">
      <template #header>
        <SectionCardHeader
          title="GitHub 选型与量化边界"
          :badge="githubAdoption.decision || 'native-contract-first'"
        />
      </template>
      <div class="adoption-layout">
        <div class="adoption-policy">
          <div class="policy-item">
            <span>推荐栈</span>
            <strong>{{ recommendedStackText }}</strong>
          </div>
          <div class="policy-item">
            <span>AI 复用</span>
            <strong>{{ githubAdoption.aiModelPolicy || 'reuse LONGBRIDGE_AI_* / sub2api' }}</strong>
          </div>
          <div class="policy-item">
            <span>量化边界</span>
            <strong>{{ githubAdoption.quantPolicy || '只读证据，不触发交易执行' }}</strong>
          </div>
        </div>
        <div class="candidate-list">
          <div
            v-for="candidate in githubCandidates"
            :key="candidate.name"
            class="candidate-row"
          >
            <div>
              <strong>{{ candidate.name }}</strong>
              <span>{{ candidate.fit }}</span>
            </div>
            <el-tag size="small" effect="plain">{{ candidate.license }}</el-tag>
            <el-tag size="small" :type="candidate.adoption === 'do-not-vendor' ? 'danger' : 'info'" effect="plain">
              {{ candidate.adoption }}
            </el-tag>
          </div>
        </div>
      </div>
    </el-card>

    <div class="summary-grid">
      <el-card v-for="summary in visibleMarketSummaries" :key="summary.market" class="glass-card summary-card">
        <div class="summary-head">
          <div>
            <span class="summary-market">{{ marketLabel(summary.market) }}</span>
            <strong>{{ sentimentLabel(summary.sentimentLabel) }}</strong>
          </div>
          <el-tag :type="summary.sentimentScore >= 0.2 ? 'success' : summary.sentimentScore <= -0.2 ? 'danger' : 'info'">
            {{ formatSigned(summary.sentimentScore) }}
          </el-tag>
        </div>
        <div class="summary-metrics">
          <span>热度 {{ formatPercent(summary.heat, { signed: false }) }}</span>
          <span>偏多 {{ summary.positiveCount }}</span>
          <span>偏空 {{ summary.negativeCount }}</span>
        </div>
        <div class="summary-risk-row">
          <el-tag
            v-for="risk in summary.topRiskKeywords || []"
            :key="`${summary.market}-${risk}`"
            size="small"
            type="warning"
            effect="plain"
          >
            {{ risk }}
          </el-tag>
        </div>
      </el-card>
    </div>

    <el-card class="glass-card">
      <template #header>
        <SectionCardHeader
          title="风险词热度"
          :badge="`${visibleRiskWords.length} 个关键词`"
        />
      </template>
      <div class="risk-cloud">
        <button
          v-for="risk in visibleRiskWords"
          :key="risk.keyword"
          type="button"
          class="risk-chip"
          @click="focusKeyword = risk.keyword"
        >
          <strong>{{ risk.keyword }}</strong>
          <span>{{ risk.count }}</span>
        </button>
      </div>
    </el-card>

    <el-card class="glass-card">
      <template #header>
        <SectionCardHeader
          title="标的舆情联动"
          :badge="`${filteredSymbols.length} 个标的`"
        />
      </template>

      <el-table :data="filteredSymbols" v-loading="loading" style="width: 100%">
        <template #empty>
          <div class="table-empty-state">
            <strong>{{ loading ? '舆情数据加载中' : '暂无标的舆情' }}</strong>
          </div>
        </template>
        <el-table-column prop="symbol" label="代码" width="120" />
        <el-table-column prop="market" label="市场" width="90">
          <template #default="{ row }">
            {{ marketLabel(row?.market) }}
          </template>
        </el-table-column>
        <el-table-column label="情绪" width="110">
          <template #default="{ row }">
            <el-tag :type="row?.score >= 0.2 ? 'success' : row?.score <= -0.2 ? 'danger' : 'info'">
              {{ formatSigned(row?.score) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="热度" width="110">
          <template #default="{ row }">
            {{ formatPercent(row?.heat, { signed: false }) }}
          </template>
        </el-table-column>
        <el-table-column label="趋势/风控" min-width="180">
          <template #default="{ row }">
            <div class="compact-stack">
              <span>{{ row?.trend_direction || 'sideways' }} / {{ row?.risk_level || 'medium' }}</span>
              <span>技术分 {{ formatNumber(row?.quant_fields?.technical_score) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="风险词" min-width="180">
          <template #default="{ row }">
            <div class="tag-row">
              <el-tag
                v-for="risk in (row?.risk_keywords || []).slice(0, 3)"
                :key="`${row?.symbol || 'symbol'}-${risk}`"
                size="small"
                type="warning"
                effect="plain"
              >
                {{ risk }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="量化契约" min-width="220">
          <template #default="{ row }">
            <div class="compact-stack">
              <span>bias {{ row?.quant_fields?.ai_bias || 'neutral' }}</span>
              <span>expected {{ formatPercent(row?.quant_fields?.expected_return || 0, { signed: true }) }}</span>
              <span>recommended {{ row?.quant_fields?.recommended ? 'yes' : 'no' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="证据摘要" min-width="260">
          <template #default="{ row }">
            <div class="compact-stack">
              <span>{{ (row?.driver_headlines || [])[0] || '--' }}</span>
              <span>{{ row?.latest_analysis_ref?.finalDecision || '无 AI 结论' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="联动入口" width="240" fixed="right">
          <template #default="{ row }">
            <div class="action-row">
              <el-button size="small" @click="goAI(row)">AI研判</el-button>
              <el-button size="small" @click="goRecommendations()">推荐</el-button>
              <el-button size="small" @click="goStrategy()">策略</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getSentimentBootstrap, getSentimentOverview } from '../api/sentiment.js'
import { formatPercent as formatPercentValue } from '../utils/formatters.js'
import MetricStrip from '../components/common/MetricStrip.vue'
import PageHero from '../components/common/PageHero.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'

const router = useRouter()
const loading = ref(false)
const selectedMarket = ref('ALL')
const focusKeyword = ref('')
const overview = ref({
  marketSummaries: [],
  topSymbols: [],
  riskWordCloud: [],
  aiConfig: {},
  githubAdoption: {},
  linkedRoutes: {}
})

const aiConfig = computed(() => overview.value.aiConfig || {})
const githubAdoption = computed(() => overview.value.githubAdoption || {})
const githubCandidates = computed(() => githubAdoption.value.candidates || [])
const recommendedStackText = computed(() => (githubAdoption.value.recommendedStack || []).join(' / ') || 'FinNLP / FinBERT / sub2api')
const visibleMarketSummaries = computed(() => overview.value.marketSummaries || [])
const visibleRiskWords = computed(() => {
  const keyword = String(focusKeyword.value || '').trim()
  const items = overview.value.riskWordCloud || []
  return keyword ? items.filter((item) => String(item.keyword || '').includes(keyword)) : items
})
const filteredSymbols = computed(() => {
  const keyword = String(focusKeyword.value || '').trim().toUpperCase()
  const items = overview.value.topSymbols || []
  if (!keyword) {
    return items
  }
  return items.filter((item) => {
    const haystack = [
      item.symbol,
      ...(item.risk_keywords || []),
      ...(item.driver_headlines || [])
    ].join(' ').toUpperCase()
    return haystack.includes(keyword)
  })
})

const heroChips = computed(() => ([
  { text: selectedMarket.value === 'ALL' ? '全部市场' : marketLabel(selectedMarket.value), tone: 'info' },
  { text: aiConfig.value.provider || 'sub2api', tone: 'healthy' },
  { text: aiConfig.value.models?.default || '--', tone: 'info' },
  { text: githubAdoption.value.decision || 'native-contract-first', tone: 'warning' }
]))
const heroMetrics = computed(() => ([
  { label: '市场摘要', value: `${visibleMarketSummaries.value.length} 个`, note: '跨市场情绪看板' },
  { label: '标的联动', value: `${filteredSymbols.value.length} 个`, note: '可跳 AI/推荐/策略' },
  { label: '风险词', value: `${visibleRiskWords.value.length} 个`, note: '结构化风险提示' }
]))
const overviewMetrics = computed(() => ([
  {
    label: 'Base URL',
    value: aiConfig.value.baseUrl || '--',
    note: '复用现有 LONGBRIDGE_AI_*'
  },
  {
    label: '默认模型',
    value: aiConfig.value.models?.default || '--',
    note: 'OpenAI-compatible'
  },
  {
    label: '扫描模型',
    value: aiConfig.value.models?.scanPulse || '--',
    note: '趋势 / 舆情轻量分析'
  },
  {
    label: '总结模型',
    value: aiConfig.value.models?.recommendSummary || '--',
    note: '推荐 / 摘要复用'
  }
]))
const aiConfigBadge = computed(() => aiConfig.value.source || 'LONGBRIDGE_AI_*')

const marketLabel = (market) => ({ US: '美股', CN: 'A股', HK: '港股' }[market] || market || '全部')
const sentimentLabel = (value) => ({
  positive: '偏多',
  negative: '偏空',
  neutral: '中性'
}[value] || value || '中性')
const formatPercent = (value, options = {}) => formatPercentValue(Number(value || 0), options)
const formatSigned = (value) => {
  const normalized = Number(value || 0)
  return `${normalized > 0 ? '+' : ''}${normalized.toFixed(2)}`
}
const formatNumber = (value) => Number(value || 0).toFixed(1)
const mergeOverview = (payload = {}) => ({
  ...overview.value,
  ...payload,
  aiConfig: {
    ...(overview.value.aiConfig || {}),
    ...(payload.aiConfig || {})
  },
  githubAdoption: {
    ...(overview.value.githubAdoption || {}),
    ...(payload.githubAdoption || {})
  },
  linkedRoutes: {
    ...(overview.value.linkedRoutes || {}),
    ...(payload.linkedRoutes || {})
  }
})

const loadBootstrap = async () => {
  try {
    const res = await getSentimentBootstrap()
    overview.value = mergeOverview(res?.data || {})
  } catch (error) {
    console.warn('加载舆情 bootstrap 失败:', error?.message || error)
  }
}

const loadOverview = async () => {
  loading.value = true
  try {
    const params = selectedMarket.value === 'ALL' ? {} : { market: selectedMarket.value }
    const res = await getSentimentOverview(params)
    overview.value = mergeOverview(res?.data || {})
  } catch (error) {
    console.error('加载舆情概览失败:', error)
    ElMessage.error('加载舆情概览失败')
  } finally {
    loading.value = false
  }
}

const goAI = (row) => {
  router.push({ name: 'AIAnalysis', query: { symbol: row.symbol, market: row.market } })
}
const goRecommendations = () => {
  router.push({ name: 'Recommendations' })
}
const goStrategy = () => {
  router.push({ name: 'Strategy' })
}

onMounted(async () => {
  await loadBootstrap()
  await loadOverview()
})
</script>

<style scoped lang="scss">
.market-sentiment-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.header-actions,
.summary-head,
.summary-metrics,
.action-row,
.tag-row {
  display: flex;
  align-items: center;
}

.header-actions,
.summary-metrics,
.action-row,
.tag-row {
  gap: 12px;
  flex-wrap: wrap;
}

.glass-card {
  border: 1px solid var(--border-soft);
  background: var(--surface-strong);
  box-shadow: var(--shadow-strong);
}

.config-grid,
.summary-grid,
.adoption-layout {
  display: grid;
  gap: 16px;
}

.config-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.config-item {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 18px;
  background: var(--surface-muted);
  border: 1px solid var(--border-soft);

  span {
    color: var(--text-muted);
    font-size: 12px;
  }

  strong {
    color: var(--text-primary);
    word-break: break-all;
  }
}

.config-note {
  margin: 14px 0 0;
  color: var(--text-secondary);
  line-height: 1.6;
}

.adoption-layout {
  grid-template-columns: minmax(280px, 0.9fr) minmax(360px, 1.1fr);
}

.adoption-policy,
.candidate-list {
  display: grid;
  gap: 12px;
}

.policy-item,
.candidate-row {
  border: 1px solid var(--border-soft);
  background: var(--surface-muted);
  border-radius: 8px;
}

.policy-item {
  display: grid;
  gap: 6px;
  padding: 14px 16px;

  span {
    color: var(--text-muted);
    font-size: 12px;
  }

  strong {
    color: var(--text-primary);
    line-height: 1.5;
  }
}

.candidate-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 10px;
  align-items: center;
  padding: 12px 14px;

  div {
    display: grid;
    gap: 4px;
    min-width: 0;
  }

  strong {
    color: var(--text-primary);
  }

  span {
    color: var(--text-secondary);
    line-height: 1.45;
  }
}

.summary-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.summary-card {
  :deep(.el-card__body) {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
}

.summary-head {
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
}

.summary-market {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
}

.summary-head strong {
  display: block;
  margin-top: 8px;
  color: var(--text-primary);
}

.summary-metrics {
  color: var(--text-secondary);
  font-size: 13px;
}

.summary-risk-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.risk-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.risk-chip {
  border: 1px solid color-mix(in srgb, var(--warning) 20%, var(--border-soft));
  background: color-mix(in srgb, var(--warning) 8%, var(--surface-muted));
  color: var(--text-primary);
  border-radius: 999px;
  padding: 10px 14px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.compact-stack {
  display: grid;
  gap: 4px;
  line-height: 1.45;
}

.action-row {
  justify-content: flex-end;
}

.table-empty-state {
  padding: 18px;
}

@media (max-width: 1100px) {
  .summary-grid,
  .config-grid,
  .adoption-layout {
    grid-template-columns: 1fr;
  }

  .candidate-row {
    grid-template-columns: 1fr;
  }
}
</style>

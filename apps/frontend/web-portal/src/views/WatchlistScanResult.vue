<template>
  <div class="watchlist-scan-result-page">
    <section class="result-header">
      <div class="result-title">
        <el-button :icon="ArrowLeft" circle class="back-button" @click="goBack" />
        <div>
          <span class="eyebrow">Watchlist Scan</span>
          <h2>{{ symbol }}</h2>
          <div class="result-tags">
            <el-tag effect="plain">{{ marketLabel }}</el-tag>
            <el-tag effect="plain">{{ sessionLabel }}</el-tag>
            <el-tag effect="plain">{{ latestUpdatedAt ? `更新 ${formatDateTime(latestUpdatedAt)}` : '等待扫描结果' }}</el-tag>
          </div>
        </div>
      </div>

      <div class="result-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadResult">刷新</el-button>
        <el-button type="primary" :icon="Cpu" @click="openAIAnalysis">打开 AI 研判</el-button>
      </div>
    </section>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
    />

    <section class="result-grid">
      <el-card class="panel-card scan-card" v-loading="loading">
        <template #header>
          <div class="panel-head">
            <div>
              <span class="panel-kicker">Daily Symbol Trend</span>
              <h3>最新扫描结果</h3>
            </div>
            <el-tag :type="riskTagType(trendScan.riskLevel)" effect="plain">
              {{ riskLabel(trendScan.riskLevel) }}
            </el-tag>
          </div>
        </template>

        <div v-if="hasTrendScan" class="scan-content">
          <div class="scan-hero">
            <div>
              <span>趋势方向</span>
              <strong>{{ trendDirectionLabel(trendScan.trendDirection) }}</strong>
            </div>
            <div>
              <span>技术评分</span>
              <strong>{{ formatScore(trendScan.technicalScore) }}</strong>
            </div>
            <div>
              <span>置信度</span>
              <strong>{{ formatPercent(trendScan.confidence) }}</strong>
            </div>
          </div>

          <div class="section-block">
            <span class="section-label">扫描摘要</span>
            <p>{{ trendScan.summary || trendScan.headline || '暂无扫描摘要' }}</p>
          </div>

          <div class="indicator-grid">
            <div v-for="item in indicatorItems" :key="item.key" class="indicator-item">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </div>

        <div v-else class="empty-state">
          <strong>暂无扫描结果</strong>
          <span>开启自选股票池扫描任务后，最近一次趋势扫描会在这里形成二级页面台账。</span>
        </div>
      </el-card>

      <el-card class="panel-card ai-card" v-loading="loading">
        <template #header>
          <div class="panel-head">
            <div>
              <span class="panel-kicker">AI Analysis</span>
              <h3>最新 AI 研判</h3>
            </div>
            <el-tag effect="plain">{{ aiDecision || '未研判' }}</el-tag>
          </div>
        </template>

        <div v-if="hasAiAnalysis" class="ai-content">
          <div class="scan-hero">
            <div>
              <span>最终结论</span>
              <strong>{{ aiDecision }}</strong>
            </div>
            <div>
              <span>置信度</span>
              <strong>{{ formatPercent(aiAnalysis.confidence) }}</strong>
            </div>
            <div>
              <span>分析时间</span>
              <strong>{{ formatDateTime(aiAnalysis.analysisTime) }}</strong>
            </div>
          </div>

          <div class="section-block">
            <span class="section-label">结论说明</span>
            <p>{{ aiAnalysis.reason || aiAnalysis.summary || '暂无研判说明' }}</p>
          </div>

          <div class="layer-list">
            <div
              v-for="layer in aiLayers"
              :key="layer.id || layer.name"
              class="layer-item"
            >
              <div>
                <strong>{{ layer.name || layer.id || '研判层' }}</strong>
                <span>{{ layer.decision || layer.signal || '--' }}</span>
              </div>
              <p>{{ layer.summary || layer.fullText || '暂无说明' }}</p>
            </div>
          </div>
        </div>

        <div v-else class="empty-state">
          <strong>暂无 AI 研判</strong>
          <span>可从本页进入 AI 研判触发分析，完成后结果会回写到扫描结果页。</span>
        </div>
      </el-card>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Cpu, Refresh } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { getLatestSymbolAnalysis } from '../api/analysis.js'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const errorMessage = ref('')
const latestPayload = ref({})

const MARKET_LABEL_MAP = {
  US: '美股',
  HK: '港股',
  CN: 'A股',
  SG: '新加坡'
}
const SESSION_LABEL_MAP = {
  pre_market: '开盘前',
  after_market: '收盘后',
  before_open: '开盘前',
  after_close: '收盘后'
}
const TREND_LABEL_MAP = {
  up: '上行',
  bullish: '偏多',
  long: '偏多',
  sideways: '震荡',
  neutral: '中性',
  down: '下行',
  bearish: '偏空'
}
const RISK_LABEL_MAP = {
  low: '低风险',
  medium: '中风险',
  high: '高风险'
}

const symbol = computed(() => String(route.params?.symbol || latestPayload.value?.symbol || '').trim().toUpperCase())
const market = computed(() => String(route.query?.market || '').trim().toUpperCase())
const session = computed(() => String(route.query?.session || '').trim())
const marketLabel = computed(() => MARKET_LABEL_MAP[market.value] || market.value || '未知市场')
const sessionLabel = computed(() => SESSION_LABEL_MAP[session.value] || session.value || '自选扫描')
const trendScan = computed(() => normalizeTrendScan(latestPayload.value?.latestTrendScan || latestPayload.value?.latest_trend_scan || {}))
const aiAnalysis = computed(() => normalizeAiAnalysis(latestPayload.value?.latestAiAnalysis || latestPayload.value?.latest_ai_analysis || {}))
const hasTrendScan = computed(() => Boolean(trendScan.value.symbol || trendScan.value.generatedAt || trendScan.value.summary))
const hasAiAnalysis = computed(() => Boolean(aiAnalysis.value.finalDecision || aiAnalysis.value.analysisTime || aiAnalysis.value.reason))
const aiDecision = computed(() => aiAnalysis.value.finalDecision || aiAnalysis.value.final_signal || '')
const aiLayers = computed(() => Array.isArray(aiAnalysis.value.scanLayers) ? aiAnalysis.value.scanLayers : [])
const latestUpdatedAt = computed(() => trendScan.value.generatedAt || trendScan.value.analysisDate || aiAnalysis.value.analysisTime || '')
const indicatorItems = computed(() => buildIndicatorItems(trendScan.value.indicators))

const firstValue = (...values) => {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== '') {
      return value
    }
  }
  return ''
}

const toFiniteNumber = (value) => {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

const normalizeTrendScan = (scan = {}) => ({
  ...scan,
  symbol: firstValue(scan.symbol, symbol.value),
  trendDirection: String(firstValue(scan.trendDirection, scan.trend_direction, scan.direction, 'neutral')).toLowerCase(),
  riskLevel: String(firstValue(scan.riskLevel, scan.risk_level, 'medium')).toLowerCase(),
  technicalScore: toFiniteNumber(firstValue(scan.technicalScore, scan.technical_score, scan.score)),
  confidence: toFiniteNumber(firstValue(scan.confidence, scan.scanConfidence, scan.scan_confidence)),
  summary: firstValue(scan.summary, scan.headline, scan.reason, scan.description),
  headline: firstValue(scan.headline, scan.title),
  generatedAt: firstValue(scan.generatedAt, scan.generated_at, scan.analysisDate, scan.analysis_date, scan.createdAt, scan.created_at),
  analysisDate: firstValue(scan.analysisDate, scan.analysis_date),
  indicators: scan.indicators && typeof scan.indicators === 'object' ? scan.indicators : {}
})

const normalizeAiAnalysis = (analysis = {}) => ({
  ...analysis,
  finalDecision: firstValue(analysis.finalDecision, analysis.final_decision, analysis.decision),
  confidence: toFiniteNumber(firstValue(analysis.confidence, analysis.score, analysis.finalConfidence, analysis.final_confidence)),
  reason: firstValue(analysis.reason, analysis.summary, analysis.explanation),
  analysisTime: firstValue(analysis.analysisTime, analysis.analysis_time, analysis.timestamp, analysis.createdAt, analysis.created_at),
  scanLayers: Array.isArray(analysis.scanLayers)
    ? analysis.scanLayers
    : Array.isArray(analysis.scan_layers)
      ? analysis.scan_layers
      : []
})

const buildIndicatorItems = (indicators = {}) => {
  const entries = [
    ['price', '价格'],
    ['lastPrice', '最新价'],
    ['momentumScore', '动量'],
    ['volatility', '波动率'],
    ['ma20', 'MA20'],
    ['rsi', 'RSI']
  ]

  return entries
    .map(([key, label]) => ({ key, label, value: formatValue(indicators?.[key]) }))
    .filter((item) => item.value !== '--')
    .slice(0, 6)
}

const formatValue = (value) => {
  const number = toFiniteNumber(value)
  if (number === null) {
    return value === null || value === undefined || value === '' ? '--' : String(value)
  }
  return number.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

const formatScore = (value) => {
  const number = toFiniteNumber(value)
  return number === null ? '--' : `${number.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 分`
}

const formatPercent = (value) => {
  const number = toFiniteNumber(value)
  if (number === null || number <= 0) {
    return '--'
  }
  const percent = number <= 1 ? number * 100 : number
  return `${percent.toLocaleString('zh-CN', { maximumFractionDigits: 1 })}%`
}

const formatDateTime = (value) => {
  if (!value) {
    return '--'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN')
}

const trendDirectionLabel = (value) => TREND_LABEL_MAP[String(value || '').toLowerCase()] || String(value || '--')
const riskLabel = (value) => RISK_LABEL_MAP[String(value || '').toLowerCase()] || String(value || '未知风险')
const riskTagType = (value) => ({
  low: 'success',
  medium: 'warning',
  high: 'danger'
}[String(value || '').toLowerCase()] || 'info')

const loadResult = async () => {
  if (!symbol.value) {
    errorMessage.value = '缺少股票代码'
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await getLatestSymbolAnalysis(symbol.value)
    latestPayload.value = response?.data || {}
  } catch (error) {
    console.error('加载自选扫描结果失败:', error)
    errorMessage.value = error?.data?.error || error?.message || '加载扫描结果失败'
    ElMessage.error(errorMessage.value)
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  router.push({ name: 'WatchlistPool', query: session.value ? { session: session.value } : {} })
}

const openAIAnalysis = () => {
  router.push({
    name: 'AIAnalysis',
    query: {
      symbol: symbol.value,
      ...(market.value ? { market: market.value } : {})
    }
  })
}

watch(
  () => route.params?.symbol,
  () => {
    loadResult()
  }
)

onMounted(loadResult)
</script>

<style scoped>
.watchlist-scan-result-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: var(--text-primary);
}

.result-header,
.panel-card {
  border: 1px solid color-mix(in srgb, var(--accent-strong) 14%, transparent);
  background: linear-gradient(180deg, color-mix(in srgb, var(--surface-strong) 94%, transparent), color-mix(in srgb, var(--surface-emphasis) 96%, transparent));
  box-shadow: var(--shadow-strong);
}

.result-header {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 18px;
  border-radius: 18px;
}

.result-title,
.result-actions,
.result-tags,
.panel-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.result-title {
  align-items: flex-start;
}

.back-button {
  flex: 0 0 auto;
  margin-top: 4px;
  border-color: color-mix(in srgb, var(--accent) 28%, var(--border-soft));
  background: var(--surface-strong);
  color: var(--text-primary);
}

.eyebrow,
.panel-kicker,
.section-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0;
  text-transform: uppercase;
  color: var(--text-muted);
}

.result-title h2,
.panel-head h3 {
  margin: 0;
  color: var(--text-emphasis);
  letter-spacing: 0;
}

.result-title h2 {
  font-size: 24px;
  line-height: 1.15;
}

.panel-head {
  justify-content: space-between;
}

.panel-head h3 {
  font-size: 17px;
}

.result-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  gap: 14px;
}

.scan-content,
.ai-content {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.scan-hero {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.scan-hero > div,
.indicator-item,
.layer-item {
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
}

.scan-hero > div,
.indicator-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 72px;
  padding: 12px;
  border-radius: 12px;
}

.scan-hero span,
.indicator-item span {
  color: var(--text-muted);
  font-size: 12px;
}

.scan-hero strong,
.indicator-item strong {
  color: var(--text-primary);
  font-size: 16px;
}

.section-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-block p,
.layer-item p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.indicator-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.layer-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.layer-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 12px;
}

.layer-item > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.layer-item strong {
  color: var(--text-primary);
  font-size: 13px;
}

.layer-item span {
  color: var(--text-muted);
  font-size: 12px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 160px;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: var(--text-muted);
}

.empty-state strong {
  color: var(--text-primary);
}

@media (max-width: 1100px) {
  .result-header {
    flex-direction: column;
  }

  .result-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .scan-hero,
  .indicator-grid {
    grid-template-columns: 1fr;
  }

  .result-actions {
    width: 100%;
  }

  .result-actions :deep(.el-button) {
    flex: 1 1 140px;
  }
}
</style>

<template>
  <div class="ai-lab-page">
    <section v-if="isPhoneLayout" class="mobile-ai-command glass-panel">
      <div class="mobile-ai-copy">
        <strong>AI 研判</strong>
      </div>

      <div class="mobile-ai-stat-grid">
        <article v-for="item in mobileAnalysisSummaryCards" :key="item.label" class="mobile-ai-stat">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </div>

      <div v-if="benchmarkList.length" class="mobile-benchmark-row">
        <div
          v-for="benchmark in benchmarkList.slice(0, 2)"
          :key="`mobile-${benchmark.symbol}`"
          class="mobile-benchmark-pill"
        >
          <span>{{ benchmark.name }}</span>
          <strong>{{ formatCurrency(benchmark.price) }}</strong>
          <small>{{ formatPercent(benchmark.changePercent) }}</small>
        </div>
      </div>
    </section>

    <section class="control-panel glass-panel" :class="{ mobile: isPhoneLayout }">
      <div v-if="isPhoneLayout" class="mobile-toolbar-intro">
        <span>{{ sourceMode === 'positions' ? '持仓扫描' : '自选股扫描' }}</span>
      </div>

      <div class="toolbar-row">
        <el-select
          v-model="selectedAccountId"
          placeholder="选择账户"
          class="account-select"
          :disabled="sourceMode !== 'positions' || !accounts.length"
        >
          <el-option
            v-for="account in accounts"
            :key="account.id"
            :label="account.name"
            :value="account.id"
          />
        </el-select>

        <el-autocomplete
          ref="targetSearchRef"
          v-model="searchKeyword"
          :fetch-suggestions="queryTargetSuggestions"
          :trigger-on-focus="true"
          :debounce="220"
          :fit-input-width="true"
          highlight-first-item
          value-key="label"
          placeholder="输入代码 / 名称，如 NVDA、NVDL"
          clearable
          class="search-input"
          popper-class="ai-target-suggest-popper"
          @select="handleTargetSuggestionSelect"
          @clear="handleTargetSearchClear"
          @keydown.enter.prevent="handleTargetSearchEnter"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
          <template #default="{ item }">
            <div class="target-suggestion">
              <strong>{{ item.symbol }}</strong>
              <span>{{ item.name }}</span>
              <small>{{ item.market }}</small>
            </div>
          </template>
        </el-autocomplete>

        <div class="toolbar-actions">
          <el-button
            type="primary"
            :icon="MagicStick"
            :loading="analyzing"
            :disabled="analyzing || !scanCandidateTargets.length"
            @click="scanVisibleTargets"
          >
            {{ scanButtonLabel }}
          </el-button>

          <el-button
            class="refresh-targets-button"
            :icon="Refresh"
            :loading="loading"
            :disabled="analyzing"
            @click="loadTargets"
          >
            刷新标的
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="analysisErrorMessage"
        :title="analysisErrorMessage"
        type="warning"
        show-icon
        :closable="false"
        class="analysis-status-alert"
      />

      <div
        v-if="scanStatusVisible"
        class="analysis-scan-status"
        :class="`is-${scanStatusTone}`"
      >
        <span>{{ scanStatusLabel }}</span>
        <strong>{{ scanStatusHeadline }}</strong>
        <small>{{ scanStatusDetail }}</small>
      </div>
    </section>

    <MobileSegmentControl
      v-if="isPhoneLayout"
      v-model="activeMobilePanel"
      class="mobile-analysis-rail"
      label="AI 研判分段"
      :items="mobileAnalysisPanels"
    />

    <section class="content-grid">
      <div v-if="!isPhoneLayout || activeMobilePanel === 'targets'" class="target-panel glass-panel">
        <div class="panel-head">
          <div>
            <h3>扫描标的</h3>
          </div>
          <div class="panel-head-actions">
            <el-radio-group v-model="sourceMode" size="small" class="target-source-switch">
              <el-radio-button value="positions">持仓</el-radio-button>
              <el-radio-button value="watchlist">自选股</el-radio-button>
            </el-radio-group>
            <span class="panel-count">{{ visibleTargets.length }}</span>
          </div>
        </div>

        <div v-if="analyzing" class="scan-inline-status">
          <span class="scan-inline-dot" />
          <strong>扫描中</strong>
          <small>{{ scanProgressText }}</small>
        </div>

        <div class="target-summary-strip">
          <span>已扫描 {{ analyzedCount }}</span>
          <span>信号 {{ actionableCount }}</span>
        </div>

        <div
          class="target-list"
          :class="{ 'single-target-list': visibleTargets.length === 1 }"
          v-if="visibleTargets.length"
        >
          <div
            v-for="target in visibleTargets"
            :key="target.symbol"
            class="target-item"
            :class="{ active: target.symbol === activeSymbol, scanning: isTargetScanning(target.symbol) }"
            @click="selectTarget(target.symbol)"
          >
            <div class="target-item-top">
              <div class="target-main">
                <div class="target-symbol-row">
                  <strong>{{ target.symbol }}</strong>
                  <span>{{ target.name }}</span>
                </div>
                <div class="target-meta-row">
                  <span>{{ target.market }}</span>
                  <span v-if="target.quantity">持仓 {{ target.quantity }}</span>
                  <span v-if="target.marketValue">市值 {{ formatCurrency(target.marketValue) }}</span>
                  <span v-if="target.sector">{{ target.sector }}</span>
                </div>
              </div>

              <div class="target-side">
                <span class="target-price">{{ formatCurrency(target.analysis?.price || target.currentPrice) }}</span>
                <span
                  class="target-decision"
                  :class="target.analysis?.finalSignal || 'neutral'"
                >
                  {{ target.analysis?.finalDecision || '未扫描' }}
                </span>
                <el-button
                  type="primary"
                  text
                  class="target-scan"
                  :loading="isTargetScanning(target.symbol)"
                  :disabled="analyzing"
                  @click.stop="scanSingleTarget(target)"
                >
                  即时扫描
                </el-button>
              </div>
            </div>
          </div>
        </div>

        <div class="target-empty-state" v-else>
          <div class="target-empty-icon">
            <el-icon><Monitor /></el-icon>
          </div>
          <strong>{{ emptyTargetMessage }}</strong>
          <div class="target-empty-actions">
            <el-button
              v-if="manualSearchTarget"
              class="target-action-button target-action-button--primary"
              :icon="MagicStick"
              :loading="analyzing"
              :disabled="analyzing"
              @click="scanVisibleTargets"
            >
              扫描 {{ manualSearchTarget.symbol }}
            </el-button>
            <template v-else>
              <el-button
                v-if="sourceMode === 'positions'"
                class="target-action-button target-action-button--secondary"
                @click="switchToWatchlistTargets"
              >
                自选股
              </el-button>
              <el-button
                class="target-action-button target-action-button--secondary"
                :icon="Refresh"
                :loading="loading"
                :disabled="loading || analyzing"
                @click="loadTargets"
              >
                {{ sourceMode === 'positions' ? '刷新持仓' : '刷新自选股' }}
              </el-button>
              <el-button
                class="target-action-button target-action-button--ghost"
                :disabled="analyzing"
                @click="focusTargetSearch"
              >
                输入代码
              </el-button>
            </template>
          </div>
        </div>
      </div>

      <div v-if="!isPhoneLayout || activeMobilePanel !== 'targets'" class="detail-panel glass-panel">
        <div v-if="analyzing" class="scan-loading-panel">
          <div class="scan-loading-orb">
            <el-icon><MagicStick /></el-icon>
          </div>
          <div class="scan-loading-copy">
            <span>正在扫描</span>
            <strong>{{ scanProgressText }}</strong>
          </div>
          <div class="scan-loading-track">
            <i />
          </div>
        </div>

        <template v-if="activeAnalysis && activeTarget">
          <div v-if="!isPhoneLayout || activeMobilePanel === 'detail'" class="market-panel priority-panel">
            <div class="panel-head compact">
              <div>
                <h3>大盘扫描</h3>
              </div>
              <span class="market-tag">{{ marketSummaryLabel }}</span>
            </div>

            <div v-if="benchmarkList.length" class="market-benchmark-row">
              <span
                v-for="benchmark in benchmarkList"
                :key="`detail-${benchmark.symbol}`"
                class="market-benchmark"
                :class="benchmark.tone"
              >
                <small>{{ benchmark.name }}</small>
                <strong>{{ formatCurrency(benchmark.price) }}</strong>
                <em>{{ formatPercent(benchmark.changePercent) }}</em>
              </span>
            </div>

            <div class="market-grid">
              <div class="market-card">
                <span>市场状态</span>
                <strong>{{ marketSummaryLabel }}</strong>
                <p>{{ marketSummaryText }}</p>
              </div>
              <div class="market-card">
                <span>风险温度</span>
                <strong>{{ resolvedMarketSummary?.riskTemperature || '中性' }}</strong>
                <p>结合指数联动与波动环境综合判断</p>
              </div>
              <div class="market-card">
                <span>评分拆解</span>
                <strong>{{ activeAnalysis.technicalScore || 0 }} / {{ activeAnalysis.marketScore || 0 }}</strong>
                <p>技术面 / 大盘共振评分</p>
              </div>
            </div>
          </div>

          <div v-if="!isPhoneLayout || activeMobilePanel === 'detail'" class="indicator-panel priority-panel">
            <div class="panel-head compact">
              <div>
                <h3>指标数据</h3>
              </div>
              <span class="market-tag">{{ indicatorPanelTag }}</span>
            </div>
            <div v-if="indicatorChips.length" class="indicator-cloud">
              <span v-for="chip in indicatorChips" :key="chip.label" class="indicator-chip">
                <small>{{ chip.label }}</small>
                <strong>{{ chip.value }}</strong>
              </span>
            </div>
            <p v-else class="analysis-note">当前结果还没有可展示的指标快照。</p>
          </div>
        </template>

        <div v-else-if="activeTarget" class="empty-state detail-empty">
          <el-icon><Cpu /></el-icon>
          <p>{{ activeTarget.symbol }} 还没有生成扫描结果</p>
          <el-button type="primary" :icon="DataAnalysis" :loading="analyzing" :disabled="analyzing" @click="scanSingleTarget(activeTarget)">
            立即扫描
          </el-button>
        </div>

        <div v-else class="empty-state detail-empty">
          <el-icon><TrendCharts /></el-icon>
          <p>先选择一个标的。</p>
        </div>
      </div>
    </section>

    <section
      v-if="activeAnalysis && activeTarget && (!isPhoneLayout || activeMobilePanel !== 'targets')"
      class="analysis-wide-panel glass-panel"
    >
      <div v-if="!isPhoneLayout || activeMobilePanel === 'detail'" class="target-context-panel">
        <div class="target-context-head">
          <div class="detail-title-row">
            <span class="detail-symbol">{{ activeAnalysis.symbol }}</span>
            <span class="detail-name">{{ activeTarget.name }}</span>
            <span class="detail-market">{{ activeTarget.market }}</span>
            <span class="detail-source" :class="analysisSourceTone">{{ analysisSourceLabel }}</span>
          </div>
          <span class="detail-pill">{{ analysisLayerCountLabel }}</span>
        </div>
        <p class="detail-reason">{{ activeAnalysis.reason }}</p>
        <div class="mini-stats">
          <div class="mini-card">
            <span>现价</span>
            <strong>{{ formatCurrency(activeAnalysis.price) }}</strong>
          </div>
          <div class="mini-card">
            <span>涨跌幅</span>
            <strong :class="trendClass(activeAnalysis.changePercent)">
              {{ formatPercent(activeAnalysis.changePercent) }}
            </strong>
          </div>
          <div class="mini-card">
            <span>综合评分</span>
            <strong>{{ activeAnalysis.score || 0 }}</strong>
          </div>
          <div class="mini-card">
            <span>扫描时间</span>
            <strong>{{ formatDate(activeAnalysis.analysisTime) }}</strong>
          </div>
        </div>
      </div>

      <div v-if="!isPhoneLayout || activeMobilePanel === 'detail'" class="verdict-row-card" :class="activeAnalysis.finalSignal">
        <div class="verdict-row-main">
          <span>终审结论</span>
          <strong>{{ activeAnalysis.finalDecision }}</strong>
          <small>{{ activeAnalysis.confidence || 0 }}% 置信度 · {{ verdictModelLabel }}</small>
        </div>
        <p>{{ verdictSummary }}</p>
      </div>

      <div v-if="!isPhoneLayout || activeMobilePanel === 'layers'" class="analysis-layers-panel">
        <div class="panel-head compact">
          <div>
            <h3>{{ analysisLayersTitle }}</h3>
          </div>
          <span class="market-tag">{{ analysisLayerCountLabel }}</span>
        </div>
        <div class="layer-grid" :class="{ compact: analysisLayerCount < 3 }">
          <article
            v-for="layer in activeAnalysis.scanLayers"
            :key="layer.id"
            class="layer-card"
            :class="layer.signal"
          >
            <div class="layer-head">
              <div>
                <span class="layer-kicker">{{ layer.id }}</span>
                <h4>{{ layer.name }}</h4>
                <div v-if="layer.modelAlias" class="layer-model">
                  <span>{{ layer.modelAlias }}</span>
                  <small>{{ layer.modelQuality || '最高质量' }}</small>
                </div>
              </div>
              <span class="layer-decision">{{ layer.decision }}</span>
            </div>
            <div class="layer-scroll-body">
              <p class="layer-summary">{{ layer.summary }}</p>
              <div class="layer-highlights">
                <span v-for="highlight in layer.highlights.filter(Boolean)" :key="highlight">
                  {{ highlight }}
                </span>
              </div>
            </div>
          </article>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Cpu,
  DataAnalysis,
  MagicStick,
  Monitor,
  Refresh,
  Search,
  TrendCharts
} from '@element-plus/icons-vue'
import { analyzePositions, getAIModels, getLatestTrendScans } from '../api/analysis.js'
import { getPlatformMarketScans, getStockPool } from '../api/market.js'
import { getBrokerAccounts, getDefaultBrokerAccount, getPositionsSnapshot } from '../api/trade.js'
import { formatCurrency as formatCurrencyValue, formatDecimal, formatPercent as formatPercentValue } from '../utils/formatters.js'
import {
  filterLocalSuggestionMatches,
  mergeSuggestionSources,
  normalizeSuggestionEntry,
  rankSuggestionMatches
} from '../utils/aiAnalysisSuggestions.js'
import { request } from '../utils/requestPure.js'
import MobileSegmentControl from '../components/common/MobileSegmentControl.vue'
import { useAdaptiveLayout } from '../composables/useAdaptiveLayout.js'

const route = useRoute()
const { isPhoneLayout } = useAdaptiveLayout()
const initialSourceMode = 'watchlist'
const MARKET_API_BASE = '/svc/market/api/v1/market'
let marketApiModulePromise = null

const loading = ref(false)
const analyzing = ref(false)
const pageUnmounted = ref(false)
const scanningSymbols = ref([])
const lastSuggestionKeyword = ref('')
const targetSuggestions = ref([])
const targetSearchRef = ref(null)
const activeMobilePanel = ref('targets')
const accounts = ref([])
const selectedAccountId = ref(null)
const sourceMode = ref(initialSourceMode)
const searchKeyword = ref('')
const targets = ref([])
const analysisMap = ref({})
const activeSymbol = ref('')
const lastMarketSummary = ref(null)
const lastScanAt = ref(null)
const modelPlan = ref({})
const marketScanMap = ref({})
const trendScanMeta = ref({})
const analysisErrorMessage = ref('')
const positionSourceMeta = ref({
  dataSource: 'snapshot',
  snapshotAt: '',
  sources: {},
  realtimeOverlay: [],
  positionCount: 0
})
const fallbackGetWatchlist = (params = {}) => request.get(`${MARKET_API_BASE}/watchlist`, params)
const loadMarketApiModule = async () => {
  if (!marketApiModulePromise) {
    marketApiModulePromise = import('../api/market.js')
  }
  return marketApiModulePromise
}

const resolveMarketApiMethod = async (methodName, fallback) => {
  try {
    const marketApi = await loadMarketApiModule()
    return typeof marketApi?.[methodName] === 'function' ? marketApi[methodName] : fallback
  } catch {
    return fallback
  }
}

const extractList = (payload, preferredKeys = []) => {
  if (Array.isArray(payload)) return payload
  for (const key of preferredKeys) {
    if (Array.isArray(payload?.[key])) {
      return payload[key]
    }
  }
  if (Array.isArray(payload?.data)) return payload.data
  if (Array.isArray(payload?.items)) return payload.items
  if (Array.isArray(payload?.targets)) return payload.targets
  return []
}

const detectMarket = (symbol = '') => {
  const normalized = String(symbol || '').toUpperCase()
  if (normalized.endsWith('.HK')) return 'HK'
  if (normalized.endsWith('.SH') || normalized.endsWith('.SZ')) return 'CN'
  return 'US'
}

const normalizeSymbolInput = (value = '') => {
  const raw = String(value || '').trim().toUpperCase()
  if (!raw) return ''
  const cleaned = raw.replace(/[^A-Z0-9.]/g, '')
  if (!cleaned) return ''
  if (cleaned.includes('.')) return cleaned
  return `${cleaned}.US`
}

const SYMBOL_INPUT_PATTERN = /^[A-Z0-9]{1,12}(?:\.[A-Z]{1,6})?$/

const normalizeTarget = (item = {}, source = 'positions') => ({
  symbol: item.symbol || '',
  name: item.name || item.symbol || '',
  market: String(item.market || detectMarket(item.symbol || '')).toUpperCase(),
  sector: item.sector || '',
  source,
  quantity: Number(item.quantity || 0),
  currentPrice: Number(item.currentPrice ?? item.current_price ?? item.latestPrice ?? item.latest_price ?? item.price ?? 0),
  marketValue: Number(item.marketValue ?? item.market_value ?? 0),
  analysis: null
})

const buildManualTarget = (keyword = '') => {
  const symbol = normalizeSymbolInput(keyword)
  if (!symbol || !SYMBOL_INPUT_PATTERN.test(symbol)) {
    return null
  }
  return normalizeTarget({
    symbol,
    name: symbol,
    market: detectMarket(symbol)
  }, 'manual')
}

const selectTarget = (symbol = '') => {
  activeSymbol.value = symbol
  if (isPhoneLayout.value) {
    activeMobilePanel.value = 'detail'
    document.querySelector('.content')?.scrollTo({
      top: 0,
      behavior: 'smooth'
    })
  }
}

const displayTargets = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()

  return targets.value
    .map((target) => ({
      ...target,
      analysis: analysisMap.value[target.symbol] || null
    }))
    .filter((target) => {
      if (!keyword) return true
      return (
        target.symbol.toLowerCase().includes(keyword) ||
        target.name.toLowerCase().includes(keyword)
      )
    })
    .sort((a, b) => {
      if (a.analysis && !b.analysis) return -1
      if (!a.analysis && b.analysis) return 1
      return a.symbol.localeCompare(b.symbol)
    })
})

const visibleTargets = computed(() => displayTargets.value)
const manualSearchTarget = computed(() => {
  const keyword = searchKeyword.value.trim()
  if (!keyword) return null
  const symbol = normalizeSymbolInput(keyword)
  if (!symbol || targets.value.some((item) => item.symbol === symbol)) {
    return null
  }
  return buildManualTarget(keyword)
})
const scanCandidateTargets = computed(() => {
  if (visibleTargets.value.length) return visibleTargets.value
  return manualSearchTarget.value ? [manualSearchTarget.value] : []
})
const scanButtonLabel = computed(() => {
  if (analyzing.value) return '扫描中'
  if (manualSearchTarget.value && !visibleTargets.value.length) return `扫描 ${manualSearchTarget.value.symbol}`
  return visibleTargets.value.length ? `扫描当前列表 (${visibleTargets.value.length})` : '扫描当前列表'
})
const scanProgressText = computed(() => {
  if (!scanningSymbols.value.length) return '正在准备扫描任务'
  const preview = scanningSymbols.value.slice(0, 4).join('、')
  const suffix = scanningSymbols.value.length > 4 ? ` 等 ${scanningSymbols.value.length} 个标的` : ''
  return `${preview}${suffix}`
})
const scanStatusVisible = computed(() => analyzing.value || Boolean(analysisErrorMessage.value) || Boolean(lastScanAt.value))
const scanStatusTone = computed(() => {
  if (analyzing.value) return 'running'
  if (analysisErrorMessage.value) return 'error'
  return 'complete'
})
const scanStatusLabel = computed(() => {
  if (analyzing.value) return '状态'
  if (analysisErrorMessage.value) return '结果'
  return '最近完成'
})
const scanStatusHeadline = computed(() => {
  if (analyzing.value) return '扫描进行中'
  if (analysisErrorMessage.value) return '最近一次扫描失败'
  return '最近一次扫描已完成'
})
const scanStatusDetail = computed(() => {
  if (analyzing.value) return scanProgressText.value
  if (analysisErrorMessage.value) return analysisErrorMessage.value

  const finishedAt = formatDate(lastScanAt.value)
  const summary = analyzedCount.value
    ? `已收录 ${analyzedCount.value} 个扫描结果`
    : '已返回最新扫描结果'
  return finishedAt ? `${finishedAt} · ${summary}` : summary
})
const emptyTargetMessage = computed(() => {
  if (loading.value) return '正在加载标的'
  if (manualSearchTarget.value) return `未在当前列表命中，可直接扫描 ${manualSearchTarget.value.symbol}`
  if (searchKeyword.value.trim()) return `没有找到与“${searchKeyword.value.trim()}”匹配的标的`
  return sourceMode.value === 'positions' ? '当前账户暂无可扫描持仓' : '自选股暂无标的'
})
const activeTarget = computed(() => visibleTargets.value.find((item) => item.symbol === activeSymbol.value) || displayTargets.value.find((item) => item.symbol === activeSymbol.value) || null)
const activeAnalysis = computed(() => activeTarget.value?.analysis || null)
const isTargetScanning = (symbol = '') => scanningSymbols.value.includes(symbol)
const activeMarket = computed(() => {
  const routeMarket = String(route.query.market || '').trim().toUpperCase()
  return activeTarget.value?.market || routeMarket || visibleTargets.value[0]?.market || 'US'
})
const resolvedMarketSummary = computed(() => activeAnalysis.value?.marketSummary || marketScanMap.value[activeMarket.value] || lastMarketSummary.value)

const benchmarkList = computed(() => {
  const summary = resolvedMarketSummary.value
  return Array.isArray(summary?.benchmarks) ? summary.benchmarks : []
})

const mobileAnalysisPanels = computed(() => ([
  { value: 'targets', label: '标的', note: `${visibleTargets.value.length} 个` },
  { value: 'detail', label: '结论', note: activeAnalysis.value?.finalDecision || '等待选择' },
  { value: 'layers', label: '三层', note: analysisLayerCount.value ? `${analysisLayerCount.value} 层` : '暂无' }
]))
const mobileAnalysisSummaryCards = computed(() => ([
  {
    label: '已扫描',
    value: String(analyzedCount.value),
    note: `${visibleTargets.value.length} 个标的`
  },
  {
    label: '可执行信号',
    value: String(actionableCount.value),
    note: activeAnalysis.value?.finalDecision || '等待生成'
  },
  {
    label: '大盘状态',
    value: marketSummaryLabel.value,
    note: marketSummaryText.value
  }
]))

const analyzedCount = computed(() => Object.keys(analysisMap.value).length)
const actionableCount = computed(() => Object.values(analysisMap.value).filter((item) => ['买入', '卖出', 'BUY', 'SELL', '偏多', '偏空'].includes(item.finalDecision)).length)

const marketSummaryLabel = computed(() => {
  const regime = resolvedMarketSummary.value?.regime
  if (regime === 'risk_on') return 'Risk On'
  if (regime === 'risk_off') return 'Risk Off'
  return 'Balanced'
})

const marketSummaryText = computed(() => resolvedMarketSummary.value?.summary || '等待大盘扫描')
const effectiveModelPlan = computed(() => activeAnalysis.value?.modelPlan || modelPlan.value || {})
const analysisLayerCount = computed(() => activeAnalysis.value?.scanLayers?.length || 0)
const isScheduledTrendResult = computed(() => {
  if (!activeAnalysis.value) return false
  return activeAnalysis.value?.source === 'trend_scan' || activeAnalysis.value?.analysisMode === 'scheduled_trend' || analysisLayerCount.value <= 1
})
const analysisSourceLabel = computed(() => isScheduledTrendResult.value ? '定时趋势' : '手动研判')
const analysisSourceTone = computed(() => isScheduledTrendResult.value ? 'warning' : 'success')
const analysisLayerCountLabel = computed(() => analysisLayerCount.value ? `${analysisLayerCount.value} 个视角` : '未生成')
const analysisLayersTitle = computed(() => isScheduledTrendResult.value ? '趋势过程' : '研判过程')
const indicatorPanelTag = computed(() => isScheduledTrendResult.value ? '定时指标快照' : '实时指标快照')
const preferredRouteSymbol = computed(() => String(route.query.symbol || '').trim().toUpperCase())
const verdictLayer = computed(() => {
  const layers = activeAnalysis.value?.scanLayers || []
  return layers.find((item) => item.id === 'final') || layers[layers.length - 1] || null
})
const verdictModelLabel = computed(() => {
  const alias = verdictLayer.value?.modelAlias || effectiveModelPlan.value?.final?.alias || effectiveModelPlan.value?.trendBatch?.alias || '未配置'
  return isScheduledTrendResult.value ? `历史趋势模型 ${alias}` : `终审模型 ${alias}`
})
const verdictSummary = computed(() => verdictLayer.value?.summary || activeAnalysis.value?.reason || '等待扫描结果')

const indicatorChips = computed(() => {
  const indicators = activeAnalysis.value?.indicators || {}
  const hasKey = (...keys) => keys.some((key) => Object.prototype.hasOwnProperty.call(indicators, key) && indicators[key] !== null && indicators[key] !== undefined && indicators[key] !== '')

  if (isScheduledTrendResult.value || hasKey('rsi14', 'ma20', 'trendHint')) {
    return [
      hasKey('trendHint', 'trendLabel') ? { label: '趋势提示', value: indicators.trendHint || indicators.trendLabel || '-' } : null,
      hasKey('ma20') ? { label: 'MA20', value: formatCurrency(indicators.ma20 || 0) } : null,
      hasKey('ma60') ? { label: 'MA60', value: formatCurrency(indicators.ma60 || 0) } : null,
      hasKey('return20') ? { label: '20日收益', value: formatPercentValue(indicators.return20 || 0) } : null,
      hasKey('return60') ? { label: '60日收益', value: formatPercentValue(indicators.return60 || 0) } : null,
      hasKey('rsi14', 'rsi') ? { label: 'RSI', value: formatDecimal(indicators.rsi14 ?? indicators.rsi ?? 0) } : null,
      hasKey('volatility20') ? { label: '波动20', value: formatPercentValue(indicators.volatility20 || 0) } : null,
      hasKey('volumeRatio20') ? { label: '量比20', value: formatDecimal(indicators.volumeRatio20 || 0) } : null,
      hasKey('distanceHigh20') ? { label: '距20日高点', value: formatPercentValue(indicators.distanceHigh20 || 0) } : null,
      hasKey('distanceLow20') ? { label: '距20日低点', value: formatPercentValue(indicators.distanceLow20 || 0) } : null
    ].filter(Boolean)
  }

  return [
    hasKey('trendLabel', 'trend_label') ? { label: '趋势标签', value: indicators.trendLabel || indicators.trend_label || '-' } : null,
    hasKey('momentumScore', 'momentum_score') ? { label: '动量分', value: formatDecimal(indicators.momentumScore ?? indicators.momentum_score ?? 0) } : null,
    hasKey('rsi') ? { label: 'RSI', value: formatDecimal(indicators.rsi || 0) } : null,
    hasKey('macd') ? { label: 'MACD', value: formatDecimal(indicators.macd || 0) } : null,
    hasKey('kdj') ? { label: 'KDJ', value: formatDecimal(indicators.kdj || 0) } : null,
    hasKey('atr') ? { label: 'ATR', value: formatDecimal(indicators.atr || 0) } : null,
    hasKey('roc') ? { label: 'ROC', value: formatPercentValue(indicators.roc || 0) } : null,
    hasKey('cci') ? { label: 'CCI', value: formatDecimal(indicators.cci || 0) } : null,
    hasKey('support') ? { label: '支撑位', value: formatCurrency(indicators.support || 0) } : null,
    hasKey('resistance') ? { label: '阻力位', value: formatCurrency(indicators.resistance || 0) } : null
  ].filter(Boolean)
})

const syncActiveSymbol = () => {
  const preferredSymbol = (route.query.symbol || '').toString().trim()
  const allTargets = displayTargets.value

  if (preferredSymbol && allTargets.some((item) => item.symbol === preferredSymbol)) {
    activeSymbol.value = preferredSymbol
    return
  }

  if (activeSymbol.value && allTargets.some((item) => item.symbol === activeSymbol.value)) {
    return
  }

  activeSymbol.value = allTargets[0]?.symbol || ''
}

const loadAccounts = async () => {
  const [accountRes, defaultAccount] = await Promise.all([
    getBrokerAccounts(),
    getDefaultBrokerAccount()
  ])

  accounts.value = Array.isArray(accountRes?.data) ? accountRes.data : []
  if (!selectedAccountId.value) {
    selectedAccountId.value = defaultAccount?.id || accounts.value[0]?.id || null
  }
}

const loadModelPlan = async () => {
  try {
    const res = await getAIModels()
    modelPlan.value = res?.defaultPlan || res?.data?.defaultPlan || modelPlan.value
  } catch (error) {
    console.error('加载模型计划失败:', error)
  }
}

const mergePersistedScans = (results = []) => {
  if (!results.length) return

  const nextMap = { ...analysisMap.value }
  results.forEach((item) => {
    const existing = nextMap[item.symbol]
    if (existing && existing.source && existing.source !== 'trend_scan') {
      return
    }
    nextMap[item.symbol] = {
      ...item,
      source: item.source || 'trend_scan'
    }
  })

  analysisMap.value = nextMap
  const latestSavedAt = results
    .map((item) => item.analysisTime)
    .filter(Boolean)
    .sort()
    .at(-1)
  if (latestSavedAt && !lastScanAt.value) {
    lastScanAt.value = latestSavedAt
  }
  syncActiveSymbol()
}

const loadSavedScans = async (targetList = targets.value) => {
  const symbols = targetList
    .map((item) => item.symbol)
    .filter(Boolean)
    .slice(0, 60)

  if (!symbols.length) return

  try {
    const res = await getLatestTrendScans({ symbols, limit: symbols.length })
    trendScanMeta.value = res?.meta && typeof res.meta === 'object' ? res.meta : {}
    mergePersistedScans(res?.data || [])
  } catch (error) {
    console.error('加载历史趋势扫描失败:', error)
  }
}

const loadMarketScans = async () => {
  try {
    const res = await getPlatformMarketScans()
    const nextMap = {}
    ;(res?.data || []).forEach((item) => {
      if (item?.market) {
        nextMap[item.market] = item
      }
    })
    marketScanMap.value = nextMap
  } catch (error) {
    console.error('加载大盘扫描失败:', error)
  }
}

const normalizeSuggestion = (item = {}) => {
  const target = normalizeTarget(item, item.source || 'pool')
  return normalizeSuggestionEntry(target)
}

const getLocalTargetSuggestions = (keyword = '') => {
  const trimmed = keyword.trim()
  const localMatches = filterLocalSuggestionMatches(targets.value, trimmed)
  const manualTarget = buildManualTarget(trimmed)
  const manualMatches = manualTarget ? [normalizeSuggestion(manualTarget)] : []
  return rankSuggestionMatches(
    mergeSuggestionSources(manualMatches, localMatches),
    trimmed
  ).slice(0, 8)
}

const fetchTargetSuggestions = async (keyword = '') => {
  const trimmed = keyword.trim()
  const localSuggestions = getLocalTargetSuggestions(trimmed)

  if (!trimmed) {
    return localSuggestions
  }

  if (localSuggestions.length && trimmed.length < 2) {
    return localSuggestions
  }

  try {
    const res = await getStockPool({
      page: 1,
      page_size: 8,
      market: 'all',
      search: trimmed
    })
    const remoteMatches = (res?.data || []).map((item) => normalizeSuggestion({ ...item, source: 'pool' }))
    return rankSuggestionMatches(
      mergeSuggestionSources(localSuggestions, remoteMatches),
      trimmed
    ).slice(0, 8)
  } catch (error) {
    console.error('加载标的快捷搜索失败:', error)
    return localSuggestions
  }
}

const queryTargetSuggestions = async (query, callback) => {
  const keyword = String(query || '').trim()
  lastSuggestionKeyword.value = keyword
  const immediateSuggestions = getLocalTargetSuggestions(keyword)
  targetSuggestions.value = immediateSuggestions
  callback(immediateSuggestions)

  const suggestions = await fetchTargetSuggestions(keyword)
  if (lastSuggestionKeyword.value !== keyword || pageUnmounted.value) {
    return
  }
  targetSuggestions.value = suggestions
  callback(suggestions)
}

const upsertTargets = (items = []) => {
  const nextMap = new Map(targets.value.map((item) => [item.symbol, item]))
  items.forEach((item) => {
    if (!item?.symbol) return
    nextMap.set(item.symbol, {
      ...nextMap.get(item.symbol),
      ...normalizeTarget(item, item.source || 'manual')
    })
  })
  targets.value = Array.from(nextMap.values())
}

const handleTargetSuggestionSelect = (item) => {
  if (!item?.symbol) return
  const target = normalizeTarget(item, item.source || 'pool')
  upsertTargets([target])
  searchKeyword.value = target.symbol
  activeSymbol.value = target.symbol
}

const handleTargetSearchClear = () => {
  targetSuggestions.value = []
  syncActiveSymbol()
}

const focusTargetSearch = () => {
  targetSearchRef.value?.focus?.()
}

const switchToWatchlistTargets = () => {
  if (sourceMode.value === 'watchlist') {
    loadTargets()
    return
  }
  sourceMode.value = 'watchlist'
}

const handleTargetSearchEnter = async () => {
  const keyword = searchKeyword.value.trim()
  if (!keyword) return
  if (visibleTargets.value.length) {
    selectTarget(visibleTargets.value[0].symbol)
    return
  }
  const suggestions = targetSuggestions.value.length ? targetSuggestions.value : await fetchTargetSuggestions(keyword)
  if (suggestions.length) {
    handleTargetSuggestionSelect(suggestions[0])
    return
  }
  const manualTarget = buildManualTarget(keyword)
  if (manualTarget) {
    upsertTargets([manualTarget])
    searchKeyword.value = manualTarget.symbol
    activeSymbol.value = manualTarget.symbol
  }
}

const loadTargets = async () => {
  loading.value = true

  try {
    if (sourceMode.value === 'positions') {
      if (!selectedAccountId.value) {
        targets.value = []
        positionSourceMeta.value = {
          dataSource: 'snapshot',
          snapshotAt: '',
          sources: {},
          realtimeOverlay: [],
          positionCount: 0
        }
        syncActiveSymbol()
        await loadMarketScans()
        return
      }

      const res = await getPositionsSnapshot(selectedAccountId.value)
      const positionTargets = (res?.data || []).map((item) => normalizeTarget(item, 'positions'))
      positionSourceMeta.value = {
        dataSource: res?.meta?.dataSource || 'snapshot',
        snapshotAt: res?.meta?.snapshotAt || '',
        sources: res?.meta?.sources || {},
        realtimeOverlay: Array.isArray(res?.meta?.realtimeOverlay) ? res.meta.realtimeOverlay : [],
        positionCount: Number(res?.meta?.positionCount || positionTargets.length)
      }

      if (preferredRouteSymbol.value && !positionTargets.some((item) => item.symbol === preferredRouteSymbol.value)) {
        sourceMode.value = 'watchlist'
        return
      }

      targets.value = positionTargets
    } else {
      positionSourceMeta.value = {
        dataSource: 'snapshot',
        snapshotAt: '',
        sources: {},
        realtimeOverlay: [],
        positionCount: 0
      }
      const getWatchlist = await resolveMarketApiMethod('getWatchlist', fallbackGetWatchlist)
      const res = await getWatchlist()
      const watchlistTargets = extractList(res, ['watchlist', 'targets'])
        .map((item) => normalizeTarget(item, 'watchlist'))
        .filter((item) => item.symbol)

      if (preferredRouteSymbol.value && !watchlistTargets.some((item) => item.symbol === preferredRouteSymbol.value)) {
        watchlistTargets.unshift(normalizeTarget({
          symbol: preferredRouteSymbol.value,
          name: preferredRouteSymbol.value,
          market: route.query.market || detectMarket(preferredRouteSymbol.value)
        }, 'watchlist'))
      }

      targets.value = watchlistTargets
    }

    syncActiveSymbol()
    await Promise.all([loadSavedScans(targets.value), loadMarketScans()])
  } catch (error) {
    console.error('加载扫描标的失败:', error)
    ElMessage.error('加载扫描标的失败')
  } finally {
    loading.value = false
  }
}

const mergeAnalysisResults = (results = [], marketSummary = null, nextModelPlan = null) => {
  const nextMap = { ...analysisMap.value }
  results.forEach((item) => {
    nextMap[item.symbol] = {
      ...item,
      source: item.source || 'manual_scan'
    }
  })

  analysisMap.value = nextMap
  lastMarketSummary.value = marketSummary || results.find((item) => item.marketSummary)?.marketSummary || lastMarketSummary.value
  modelPlan.value = nextModelPlan || results.find((item) => item.modelPlan)?.modelPlan || modelPlan.value
  lastScanAt.value = Date.now()
  syncActiveSymbol()
}

const scanTargets = async (targetList) => {
  let targetsToScan = Array.isArray(targetList) ? targetList.filter(Boolean) : []
  if (!targetsToScan.length && manualSearchTarget.value) {
    targetsToScan = [manualSearchTarget.value]
  }

  if (!targetsToScan.length) {
    ElMessage.warning('当前列表没有可扫描标的')
    return
  }

  const missingTargets = targetsToScan.filter((target) => target?.symbol && !targets.value.some((item) => item.symbol === target.symbol))
  if (missingTargets.length) {
    upsertTargets(missingTargets)
  }

  if (targetsToScan[0]?.symbol) {
    activeSymbol.value = targetsToScan[0].symbol
    if (manualSearchTarget.value?.symbol === targetsToScan[0].symbol) {
      searchKeyword.value = targetsToScan[0].symbol
    }
  }

  analyzing.value = true
  analysisErrorMessage.value = ''
  scanningSymbols.value = targetsToScan.map((target) => target.symbol).filter(Boolean)

  try {
    const payload = targetsToScan.map((target) => ({
      symbol: target.symbol,
      name: target.name,
      quantity: target.quantity,
      current_price: target.currentPrice
    }))

    const res = await analyzePositions({
      positions: payload,
      accountId: sourceMode.value === 'positions' ? selectedAccountId.value : null
    })

    mergeAnalysisResults(res?.data || [], res?.marketSummary || null, res?.modelPlan || null)

    if ((res?.data || []).length) {
      activeSymbol.value = (route.query.symbol || '').toString() || res.data[0].symbol
    }

    const failedCount = (res?.data || []).filter((item) => item?.error && !item?.degraded).length
    const degradedCount = (res?.data || []).filter((item) => item?.degraded).length
    const successCount = Math.max(payload.length - failedCount, 0)

    if (failedCount === payload.length) {
      ElMessage.error(`扫描失败：${failedCount} 个标的未返回结果`)
    } else if (failedCount > 0 || degradedCount > 0) {
      const degradedSuffix = degradedCount ? `，${degradedCount} 个已自动降级` : ''
      ElMessage.warning(`完成 ${successCount} 个标的扫描，${failedCount} 个失败${degradedSuffix}`)
    } else {
      ElMessage.success(`完成 ${payload.length} 个标的扫描`)
    }
  } catch (error) {
    const message = error?.businessMessage || error?.data?.error || error.message || 'AI 研判失败'
    const recoverableNetworkFailure = /abort|cancel|failed to fetch/i.test(message)
    if (pageUnmounted.value && recoverableNetworkFailure) {
      return
    }
    if (recoverableNetworkFailure) {
      console.warn('AI 研判请求未完成:', message)
    } else {
      console.error('AI 研判失败:', error)
    }
    analysisErrorMessage.value = message
    ElMessage.error(message)
  } finally {
    analyzing.value = false
    scanningSymbols.value = []
  }
}

const scanVisibleTargets = () => scanTargets(scanCandidateTargets.value)
const scanSingleTarget = (target) => scanTargets([target])

const formatCurrency = (value) => {
  return formatCurrencyValue(value, { currency: '$' })
}

const formatPercent = (value) => {
  return formatPercentValue(value)
}

const formatDate = (value) => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const trendClass = (value) => {
  const number = Number(value || 0)
  if (number > 0) return 'positive'
  if (number < 0) return 'negative'
  return 'neutral'
}

watch(sourceMode, async () => {
  await loadTargets()
})

watch(selectedAccountId, async () => {
  if (sourceMode.value === 'positions') {
    await loadTargets()
  }
})

onMounted(async () => {
  try {
    await Promise.all([loadAccounts(), loadModelPlan()])
    await loadTargets()
  } catch (error) {
    console.error('初始化 AI 研判页失败:', error)
    ElMessage.error('初始化 AI 研判页失败')
  }
})

onBeforeUnmount(() => {
  pageUnmounted.value = true
})
</script>

<style scoped lang="scss">
.ai-lab-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  color: var(--text-primary);
  --ai-border: var(--panel-edge);
  --ai-border-strong: var(--control-border-hover);
  --ai-surface: color-mix(in srgb, var(--surface-soft) 88%, transparent);
  --ai-surface-muted: color-mix(in srgb, var(--surface-muted) 86%, transparent);
  --ai-panel: var(--panel-surface);
  --ai-text: var(--text-primary);
  --ai-text-secondary: var(--text-secondary);
  --ai-text-muted: var(--text-muted);
}

.glass-panel {
  position: relative;
  overflow: hidden;
  border-radius: 32px;
  border: 1px solid var(--ai-border);
  background: var(--ai-panel);
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.mobile-ai-command {
  display: grid;
  gap: 14px;
  padding: 20px;
}

.mobile-ai-copy {
  display: grid;
  gap: 8px;
}

.mobile-ai-copy strong {
  color: var(--text-emphasis);
  font-size: 28px;
  line-height: 1.08;
}

.mobile-ai-copy p,
.mobile-ai-stat small {
  margin: 0;
  color: var(--ai-text-secondary);
  line-height: 1.6;
}

.mobile-ai-stat-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.mobile-ai-stat,
.mobile-benchmark-pill {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 22px;
  border: 1px solid var(--ai-border);
  background: var(--ai-surface);
}

.mobile-ai-stat span,
.mobile-benchmark-pill span {
  color: var(--ai-text-muted);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.mobile-ai-stat strong,
.mobile-benchmark-pill strong {
  color: var(--text-emphasis);
  font-size: 18px;
}

.mobile-benchmark-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.eyebrow,
.panel-kicker,
.layer-kicker {
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ai-text-muted);
}

.detail-reason,
.market-card p,
.empty-state p {
  color: var(--ai-text-secondary);
  line-height: 1.7;
}

.mini-card,
.market-card,
.indicator-chip {
  border-radius: 24px;
  border: 1px solid var(--ai-border);
  background: var(--ai-surface);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--accent-strong) 8%, transparent);
}

.mini-card strong,
.market-card strong {
  font-size: 18px;
  color: var(--text-emphasis);
}

.control-panel {
  padding: 22px;
}

.control-panel.mobile {
  padding: 18px;
}

.mobile-toolbar-intro {
  display: grid;
  gap: 4px;
  margin-bottom: 14px;
}

.mobile-toolbar-intro span {
  color: var(--ai-text-muted);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.toolbar-row {
  display: grid;
  grid-template-columns: minmax(190px, 230px) minmax(260px, 1fr) minmax(250px, max-content);
  gap: 12px;
  align-items: center;
}

.account-select,
.search-input {
  min-width: 210px;
}

.search-input {
  min-width: min(360px, 100%);
  width: 100%;
}

.toolbar-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(116px, 1fr));
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  position: relative;
  z-index: 3;
  min-width: 240px;
}

.toolbar-actions :deep(.el-button) {
  margin-left: 0;
  width: 100%;
  min-width: 0;
}

.toolbar-actions :deep(.refresh-targets-button) {
  --el-button-bg-color: var(--button-secondary-bg);
  --el-button-border-color: var(--button-secondary-border);
  --el-button-hover-bg-color: var(--button-secondary-bg-hover);
  --el-button-hover-border-color: var(--control-border-hover);
  --el-button-active-bg-color: var(--button-secondary-bg-hover);
  --el-button-active-border-color: var(--control-border-hover);
  --el-button-text-color: var(--button-secondary-text);
  --el-button-hover-text-color: var(--text-emphasis);
  --el-button-active-text-color: var(--text-emphasis);
  border-color: var(--button-secondary-border) !important;
  background: var(--button-secondary-bg) !important;
  color: var(--button-secondary-text) !important;
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--accent-strong) 10%, transparent);
}

.toolbar-actions :deep(.refresh-targets-button:not(.is-disabled):hover) {
  border-color: var(--control-border-hover) !important;
  background: var(--button-secondary-bg-hover) !important;
  color: var(--text-emphasis) !important;
}

.toolbar-actions :deep(.refresh-targets-button .el-icon) {
  color: var(--accent);
}

.toolbar-actions :deep(.refresh-targets-button.is-disabled) {
  border-color: color-mix(in srgb, var(--border-soft) 72%, transparent) !important;
  background: color-mix(in srgb, var(--surface-soft) 82%, transparent) !important;
  color: var(--text-muted) !important;
  opacity: 1;
}

.analysis-scan-status {
  display: grid;
  gap: 4px;
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--ai-border);
  background: var(--surface-strong);
  box-shadow: var(--shadow-strong);
}

.analysis-scan-status span {
  color: var(--text-muted);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.analysis-scan-status strong {
  color: var(--text-emphasis);
  font-size: 15px;
}

.analysis-scan-status small {
  color: var(--text-secondary);
  line-height: 1.5;
}

.analysis-scan-status.is-running {
  border-color: color-mix(in srgb, var(--accent) 42%, var(--border-soft));
  background: color-mix(in srgb, var(--accent) 12%, var(--surface-strong));
}

.analysis-scan-status.is-running strong {
  color: var(--text-emphasis);
}

.analysis-scan-status.is-complete {
  border-color: color-mix(in srgb, var(--success) 42%, var(--border-soft));
  background: color-mix(in srgb, var(--success) 12%, var(--surface-strong));
}

.analysis-scan-status.is-complete strong {
  color: var(--success);
}

.analysis-scan-status.is-error {
  border-color: color-mix(in srgb, var(--danger) 42%, var(--border-soft));
  background: color-mix(in srgb, var(--danger) 12%, var(--surface-strong));
}

.analysis-scan-status.is-error strong {
  color: var(--danger);
}

.search-input :deep(.el-input__wrapper) {
  min-height: 38px;
}

.target-suggestion {
  display: grid;
  grid-template-columns: minmax(84px, auto) minmax(120px, 1fr) auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  color: var(--text-primary);
}

.target-suggestion strong {
  color: var(--text-emphasis);
  font-size: 13px;
}

.target-suggestion span {
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.target-suggestion small {
  color: var(--accent);
  font-size: 11px;
}

:global(.ai-target-suggest-popper) {
  border: 1px solid var(--panel-edge) !important;
  background: var(--surface-strong) !important;
  box-shadow: var(--shadow-strong) !important;
}

:global(.ai-target-suggest-popper .el-autocomplete-suggestion__wrap) {
  max-height: 220px;
}

:global(.ai-target-suggest-popper .el-autocomplete-suggestion li) {
  min-height: 38px;
  color: var(--text-primary);
}

:global(.ai-target-suggest-popper .el-autocomplete-suggestion li:hover),
:global(.ai-target-suggest-popper .el-autocomplete-suggestion li.highlighted) {
  background: color-mix(in srgb, var(--accent-strong) 18%, var(--surface-soft)) !important;
}

:global(.ai-target-suggest-popper .target-suggestion) {
  display: grid;
  grid-template-columns: minmax(84px, auto) minmax(120px, 1fr) auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  color: var(--text-primary);
}

:global(.ai-target-suggest-popper .target-suggestion strong) {
  color: var(--text-emphasis);
  font-size: 13px;
}

:global(.ai-target-suggest-popper .target-suggestion span) {
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.ai-target-suggest-popper .target-suggestion small) {
  color: var(--accent);
  font-size: 11px;
}

.mobile-analysis-rail {
  margin-top: 4px;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
  align-items: stretch;
  gap: 20px;
  min-height: 0;
}

.target-panel,
.detail-panel,
.analysis-wide-panel {
  padding: 18px;
}

.target-panel {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.panel-head h3,
.layer-head h4,
.detail-title-row {
  margin: 6px 0 0;
}

.panel-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.target-source-switch :deep(.el-radio-button__inner) {
  min-width: 72px;
  padding-inline: 14px;
}

.layer-model {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--ai-surface-muted);
  color: var(--ai-text-secondary);
  font-size: 12px;
}

.layer-model small {
  color: var(--ai-text-muted);
  text-transform: uppercase;
}

.panel-count,
.market-tag,
.detail-market,
.target-decision {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 0 14px;
  border-radius: 999px;
  background: var(--ai-surface-muted);
  color: var(--ai-text);
  font-size: 13px;
}

.target-list {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  gap: 12px;
  min-height: 0;
  max-height: none;
  overflow-y: auto;
  padding-right: 4px;
}

.target-list.single-target-list {
  max-height: none;
}

.target-summary-strip {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: -6px 0 14px;
}

.target-summary-strip span {
  min-width: 0;
  overflow: hidden;
  padding: 8px 10px;
  border: 1px solid var(--ai-border);
  border-radius: 14px;
  background: color-mix(in srgb, var(--surface-soft) 72%, transparent);
  color: var(--ai-text-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scan-inline-status {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  margin: -6px 0 14px;
  padding: 8px 12px;
  border: 1px solid color-mix(in srgb, var(--accent-strong) 22%, var(--ai-border));
  border-radius: 14px;
  background: color-mix(in srgb, var(--accent-strong) 10%, var(--ai-surface-muted));
  color: var(--text-primary);
}

.scan-inline-status strong {
  color: var(--text-emphasis);
  font-size: 13px;
}

.scan-inline-status small {
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scan-inline-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--accent);
  box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent) 14%, transparent);
  animation: scanPulse 1.2s ease-in-out infinite;
}

.target-item {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 104px;
  border: 1px solid var(--ai-border);
  border-radius: 18px;
  background: var(--ai-surface);
  padding: 14px;
  color: inherit;
  cursor: pointer;
  transition: transform 0.28s ease, border-color 0.28s ease, background 0.28s ease;
}

.target-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
}

.target-item:hover,
.target-item.active {
  transform: translateY(-2px);
  border-color: var(--ai-border-strong);
  background: var(--ai-surface);
  box-shadow: inset 3px 0 0 var(--accent-strong), inset 0 1px 0 color-mix(in srgb, var(--accent-strong) 8%, transparent);
}

.target-item.scanning {
  border-color: color-mix(in srgb, var(--accent-strong) 42%, var(--ai-border));
  background: var(--ai-surface);
  box-shadow: inset 3px 0 0 var(--accent-strong);
}

.target-main {
  min-width: 0;
  text-align: left;
}

.target-symbol-row,
.detail-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.target-symbol-row strong,
.detail-symbol {
  font-size: 18px;
  color: var(--text-emphasis);
}

.target-symbol-row span,
.detail-name {
  color: var(--ai-text-secondary);
}

.target-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 8px;
  color: var(--ai-text-muted);
  font-size: 13px;
}

.target-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.target-price {
  font-size: 16px;
  color: var(--text-emphasis);
}

.target-empty-state {
  min-height: 280px;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 10px;
  padding: 26px;
  border: 1px dashed color-mix(in srgb, var(--accent-strong) 22%, var(--ai-border));
  border-radius: 20px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 78%, transparent), color-mix(in srgb, var(--surface-muted) 76%, transparent));
  text-align: center;
}

.target-empty-icon {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border-radius: 16px;
  background: color-mix(in srgb, var(--accent-strong) 16%, var(--surface-soft));
  color: var(--accent);
}

.target-empty-icon .el-icon {
  font-size: 24px;
}

.target-empty-state strong {
  color: var(--text-emphasis);
  font-size: 15px;
}

.target-empty-state span {
  max-width: 260px;
  color: var(--ai-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.target-empty-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 2px;
}

.target-empty-actions :deep(.el-button) {
  margin-left: 0;
}

.target-empty-actions :deep(.target-action-button) {
  min-width: 104px;
  margin-left: 0;
  border-color: var(--button-secondary-border);
  background: var(--button-secondary-bg);
  color: var(--button-secondary-text);
}

.target-empty-actions :deep(.target-action-button .el-icon) {
  color: inherit;
}

.target-empty-actions :deep(.target-action-button:not(.is-disabled):hover),
.target-empty-actions :deep(.target-action-button:not(.is-disabled):focus-visible) {
  border-color: var(--control-border-hover);
  background: var(--button-secondary-bg-hover);
  color: var(--text-emphasis);
}

.target-empty-actions :deep(.target-action-button.is-disabled) {
  opacity: 0.68;
  border-color: color-mix(in srgb, var(--button-secondary-border) 82%, transparent);
  background: color-mix(in srgb, var(--button-secondary-bg) 86%, transparent);
  color: var(--text-muted);
}

.target-empty-actions :deep(.target-action-button--primary) {
  border-color: color-mix(in srgb, var(--accent-strong) 36%, var(--button-primary-border));
  background: var(--button-primary-bg);
  color: var(--button-primary-text);
}

.target-empty-actions :deep(.target-action-button--primary:not(.is-disabled):hover),
.target-empty-actions :deep(.target-action-button--primary:not(.is-disabled):focus-visible) {
  border-color: color-mix(in srgb, var(--accent-strong) 54%, var(--button-primary-border));
  background: var(--button-primary-bg-hover);
  color: var(--button-primary-text);
}

.target-empty-actions :deep(.target-action-button--ghost) {
  background: color-mix(in srgb, var(--surface-strong) 74%, transparent);
  color: var(--text-primary);
}

.target-decision.success {
  color: var(--success);
}

.target-decision.danger {
  color: var(--danger);
}

.target-decision.warning {
  color: var(--warning);
}

.detail-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

.analysis-wide-panel {
  display: grid;
  gap: 14px;
  min-height: 0;
}

.scan-loading-panel {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 18px;
  padding: 32px;
  text-align: center;
  background:
    radial-gradient(circle at center, color-mix(in srgb, var(--accent) 16%, transparent), transparent 42%),
    color-mix(in srgb, var(--surface-strong) 88%, black 12%);
  backdrop-filter: blur(18px) saturate(135%);
}

.scan-loading-orb {
  display: grid;
  place-items: center;
  width: 68px;
  height: 68px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--accent) 42%, transparent);
  background:
    linear-gradient(145deg, color-mix(in srgb, var(--accent-strong) 26%, transparent), color-mix(in srgb, var(--surface-soft) 72%, transparent));
  color: var(--accent);
  box-shadow: 0 0 34px color-mix(in srgb, var(--accent-strong) 24%, transparent);
  animation: scanPulse 1.5s ease-in-out infinite;
}

.scan-loading-orb .el-icon {
  font-size: 28px;
}

.scan-loading-copy {
  display: grid;
  gap: 8px;
}

.scan-loading-copy span {
  color: var(--text-secondary);
  font-size: 13px;
}

.scan-loading-copy strong {
  color: var(--text-emphasis);
  font-size: 18px;
  font-weight: 700;
}

.scan-loading-track {
  width: min(360px, 100%);
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface-soft) 82%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--border-soft) 80%, transparent);
}

.scan-loading-track i {
  display: block;
  width: 42%;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--accent-strong), var(--accent));
  animation: scanTrack 1.1s ease-in-out infinite;
}

.target-context-panel {
  display: grid;
  gap: 12px;
  border: 1px solid var(--ai-border);
  border-radius: 20px;
  padding: 16px;
  background: color-mix(in srgb, var(--surface-soft) 74%, transparent);
}

.analysis-wide-panel .target-context-panel,
.analysis-wide-panel .analysis-layers-panel {
  background: var(--ai-surface-muted);
}

.target-context-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.detail-pill,
.detail-source {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 0 14px;
  border-radius: 999px;
  background: var(--ai-surface-muted);
  color: var(--ai-text);
  font-size: 13px;
}

.detail-source.success {
  color: var(--success);
}

.detail-source.warning {
  color: var(--warning);
}

.analysis-layers-panel,
.indicator-panel,
.market-panel {
  border-radius: 20px;
  padding: 16px;
  border: 1px solid var(--ai-border);
  background: var(--ai-surface-muted);
}

.priority-panel {
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 82%, transparent), color-mix(in srgb, var(--surface-muted) 80%, transparent));
}

.market-benchmark-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.market-benchmark {
  display: grid;
  gap: 5px;
  min-height: 76px;
  padding: 10px 12px;
  border: 1px solid var(--ai-border);
  border-radius: 16px;
  background: color-mix(in srgb, var(--surface-soft) 70%, transparent);
}

.market-benchmark small {
  overflow: hidden;
  color: var(--ai-text-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.market-benchmark strong {
  color: var(--text-emphasis);
  font-size: 14px;
}

.market-benchmark em {
  color: var(--ai-text-secondary);
  font-size: 12px;
  font-style: normal;
}

.market-benchmark.up em {
  color: var(--success);
}

.market-benchmark.down em {
  color: var(--danger);
}

.analysis-note {
  margin: 14px 0 0;
  color: var(--ai-text-secondary);
  line-height: 1.7;
}

.verdict-row-card {
  display: grid;
  grid-template-columns: minmax(180px, 0.32fr) minmax(0, 1fr);
  gap: 16px;
  align-items: stretch;
  border: 1px solid var(--ai-border);
  border-radius: 20px;
  padding: 14px 16px;
  background: var(--ai-surface-muted);
}

.verdict-row-main {
  display: grid;
  align-content: center;
  gap: 5px;
  min-width: 0;
}

.verdict-row-main span,
.verdict-row-main small {
  color: var(--ai-text-muted);
  font-size: 12px;
}

.verdict-row-main strong {
  color: var(--text-emphasis);
  font-size: 28px;
  line-height: 1.1;
}

.verdict-row-card p {
  margin: 0;
  max-height: 108px;
  overflow-y: auto;
  color: var(--ai-text-secondary);
  line-height: 1.7;
}

.mini-stats,
.market-grid,
.indicator-cloud {
  display: grid;
  gap: 10px;
}

.mini-stats {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.mini-card,
.market-card {
  padding: 12px 14px;
}

.mini-card span,
.market-card span,
.indicator-chip small {
  color: var(--ai-text-muted);
}

.positive {
  color: var(--success);
}

.negative {
  color: var(--danger);
}

.neutral {
  color: var(--ai-text);
}

.layer-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.layer-grid.compact {
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}

.layer-card {
  display: flex;
  flex-direction: column;
  border-radius: 18px;
  padding: 14px;
  border: 1px solid var(--ai-border);
  background: var(--ai-surface-muted);
  height: 340px;
  min-height: 340px;
  overflow: hidden;
}

.layer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex: 0 0 auto;
}

.layer-decision {
  color: var(--warning);
  font-size: 14px;
}

.layer-scroll-body {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  flex-direction: column;
  overflow-y: auto;
}

.layer-summary {
  color: var(--ai-text-secondary);
  line-height: 1.7;
}

.layer-summary {
  flex: 0 0 auto;
  margin-bottom: 0;
}

.layer-highlights {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0;
  flex: 0 0 auto;
}

.layer-highlights span {
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--ai-surface);
  color: var(--ai-text);
  font-size: 12px;
}

.panel-head.compact {
  margin-bottom: 16px;
}

.market-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.indicator-cloud {
  grid-template-columns: repeat(auto-fit, minmax(116px, 1fr));
}

.indicator-chip {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 74px;
  padding: 12px 14px;
}

.indicator-chip strong {
  color: var(--text-emphasis);
  font-size: 16px;
}

.empty-state {
  min-height: 320px;
  display: grid;
  place-items: center;
  text-align: center;
  gap: 12px;
  color: var(--text-secondary);
}

.empty-state .el-icon {
  font-size: 34px;
  color: var(--accent);
}

.detail-empty {
  flex: 1;
}

@keyframes scanPulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.92;
  }
  50% {
    transform: scale(1.06);
    opacity: 1;
  }
}

@keyframes scanTrack {
  0% {
    transform: translateX(-120%);
  }
  100% {
    transform: translateX(260%);
  }
}

@media (max-width: 1100px) {
  .content-grid,
  .layer-grid,
  .market-grid,
  .verdict-row-card,
  .mini-stats {
    grid-template-columns: 1fr;
  }

  .toolbar-actions {
    justify-content: flex-start;
  }

  .toolbar-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .search-input,
  .toolbar-actions {
    grid-column: 1 / -1;
  }
}

@media (max-width: 768px) {
  .control-panel,
  .target-panel,
  .detail-panel,
  .analysis-wide-panel {
    padding: 20px;
    border-radius: 26px;
  }

  .mobile-ai-command,
  .control-panel.mobile {
    padding: 18px;
  }

  .toolbar-row {
    grid-template-columns: 1fr;
  }

  .account-select,
  .search-input {
    min-width: 100%;
  }

  .toolbar-actions {
    grid-column: auto;
  }

  .target-item {
    flex-direction: column;
    align-items: flex-start;
  }

  .target-side {
    width: 100%;
    align-items: flex-start;
  }

  .target-summary-strip {
    grid-template-columns: 1fr;
  }

  .target-context-head {
    flex-direction: column;
  }

  .mobile-ai-stat-grid,
  .mobile-benchmark-row {
    grid-template-columns: 1fr;
  }
}
</style>

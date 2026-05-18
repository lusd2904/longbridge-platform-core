<template>
  <div class="history-coverage-page">
    <PageHero
      title="历史补价覆盖"
      :chips="heroChips"
      :metrics="heroMetrics"
    >
      <template #actions>
        <div class="hero-actions">
          <el-input
            v-model="keyword"
            class="keyword-input"
            clearable
            placeholder="搜索标的 / 名称 / 市场"
          />
          <el-select v-model="statusFilter" class="status-select">
            <el-option label="全部状态" value="all" />
            <el-option
              v-for="item in statusOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
          <el-button class="ghost-button" @click="resetFilters">重置</el-button>
          <el-button type="primary" :loading="loading" @click="loadCoverage(true)">刷新</el-button>
        </div>
      </template>
    </PageHero>

    <MetricStrip :items="summaryMetrics" />

    <el-card class="glass-card table-card">
      <template #header>
        <SectionCardHeader
          title="覆盖明细"
          :badge="`${filteredRows.length} / ${tableRows.length}`"
        />
      </template>

      <el-table
        :data="filteredRows"
        v-loading="loading"
        height="620"
        stripe
        empty-text="暂无覆盖数据"
      >
        <el-table-column prop="symbol" label="标的" min-width="132" fixed="left">
          <template #default="{ row }">
            <div class="symbol-cell">
              <strong>{{ row.symbol }}</strong>
              <span>{{ row.marketLabel }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="marketLabel" label="市场" width="86" />
        <el-table-column label="起止日期" min-width="188">
          <template #default="{ row }">
            <div class="range-cell">
              <span>{{ row.startDate }}</span>
              <span class="range-sep">~</span>
              <span>{{ row.endDate }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="rowCount" label="行数" width="112" align="right">
          <template #default="{ row }">
            {{ formatCount(row.rowCount) }}
          </template>
        </el-table-column>
        <el-table-column prop="missingEstimate" label="缺失估算" width="112" align="right">
          <template #default="{ row }">
            {{ formatCount(row.missingEstimate) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="112">
          <template #default="{ row }">
            <el-tag size="small" :type="row.statusType">{{ row.statusLabel }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="coverageRate" label="覆盖率" width="106" align="right">
          <template #default="{ row }">
            <span :class="['coverage-rate', row.coverageTone]">
              {{ formatPercentValue(row.coverageRate, { digits: 1, fallback: '--', signed: false }) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="updatedAt" label="更新时间" min-width="164" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getMarketHistoryCoverage } from '../../api/market.js'
import { formatDecimal, formatPercent as formatPercentValue } from '../../utils/formatters.js'
import MetricStrip from '../../components/common/MetricStrip.vue'
import PageHero from '../../components/common/PageHero.vue'
import SectionCardHeader from '../../components/common/SectionCardHeader.vue'

const loading = ref(false)
const keyword = ref('')
const statusFilter = ref('all')
const summary = ref({})
const tableRows = ref([])

const MARKET_LABEL_MAP = {
  US: '美股',
  HK: '港股',
  CN: 'A股',
  SH: '沪市',
  SZ: '深市',
  ALL: '全市场'
}

const STATUS_META_MAP = {
  complete: { label: '完整', type: 'success', tone: 'healthy' },
  partial: { label: '部分缺失', type: 'warning', tone: 'warning' },
  missing: { label: '未覆盖', type: 'danger', tone: 'error' },
  running: { label: '回补中', type: 'primary', tone: 'info' },
  failed: { label: '失败', type: 'danger', tone: 'error' },
  idle: { label: '待补齐', type: 'info', tone: 'warning' }
}

const normalizeMarketLabel = (market = '') => MARKET_LABEL_MAP[String(market || '').trim().toUpperCase()] || String(market || '--').trim().toUpperCase() || '--'

const toNumber = (value, fallback = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

const clampCoverage = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return null
  return Math.max(0, Math.min(100, num))
}

const normalizeStatusKey = (item = {}) => {
  const normalized = String(item.status || '').trim().toLowerCase()
  if (normalized) return normalized
  const rowCount = toNumber(item.rowCount ?? item.rangeCount ?? item.totalCount, 0)
  const missingEstimate = toNumber(item.missingEstimate ?? item.missingRows ?? item.missingCount, 0)
  if (rowCount <= 0) return 'missing'
  if (missingEstimate > 0) return 'partial'
  if (item.complete === true) return 'complete'
  return 'complete'
}

const estimateCoverageRate = (item = {}) => {
  const explicit = clampCoverage(item.coverageRate ?? item.coverage ?? item.rate)
  if (explicit !== null) return explicit
  const rowCount = toNumber(item.rowCount ?? item.rangeCount ?? item.totalCount, 0)
  const missingEstimate = toNumber(item.missingEstimate ?? item.missingRows ?? item.missingCount, 0)
  const denominator = rowCount + Math.max(missingEstimate, 0)
  if (!denominator) return 0
  return clampCoverage((rowCount / denominator) * 100) ?? 0
}

const deriveMissingEstimate = (item = {}) => {
  const explicit = item.missingEstimate ?? item.missingRows ?? item.missingCount
  if (explicit !== null && explicit !== undefined && explicit !== '') {
    return Math.max(toNumber(explicit, 0), 0)
  }

  const ranges = Array.isArray(item.missingRanges) ? item.missingRanges : []
  if (ranges.length) {
    return ranges.length
  }

  if (item.complete === false) {
    return 1
  }

  return 0
}

const normalizeSummary = (payload = {}) => {
  const task = payload?.task && typeof payload.task === 'object' ? payload.task : {}
  const items = Array.isArray(payload?.items)
    ? payload.items
    : Array.isArray(payload?.rows)
      ? payload.rows
      : Array.isArray(payload?.list)
        ? payload.list
        : []

  return {
    totalUniverseSymbols: toNumber(payload?.totalUniverseSymbols ?? payload?.summary?.totalUniverseSymbols, 0),
    syncedSymbols: toNumber(payload?.syncedSymbols ?? payload?.summary?.syncedSymbols, 0),
    coverageRate: clampCoverage(payload?.coverageRate ?? payload?.summary?.coverageRate) ?? 0,
    totalRows: toNumber(payload?.totalRows ?? payload?.summary?.totalRows, 0),
    latestTradeDate: payload?.latestTradeDate || payload?.summary?.latestTradeDate || '',
    updatedAt: payload?.updatedAt || task?.lastRunAt || payload?.latestTradeDate || '',
    task,
    items
  }
}

const normalizeRow = (item = {}, index = 0, fallback = {}) => {
  const market = String(item.market || item.exchange || 'ALL').trim().toUpperCase()
  const rowCount = Math.max(toNumber(item.rowCount ?? item.rangeCount ?? item.totalCount, 0), 0)
  const missingEstimate = deriveMissingEstimate(item)
  const coverageRate = estimateCoverageRate(item)
  const statusKey = normalizeStatusKey(item)
  const statusMeta = STATUS_META_MAP[statusKey] || STATUS_META_MAP.partial
  return {
    id: item.id || item.symbol || `${market}-${index}`,
    symbol: String(item.symbol || item.code || '--').trim().toUpperCase() || '--',
    name: String(item.name || item.displayName || item.symbolName || `${normalizeMarketLabel(market)}历史覆盖`).trim() || '--',
    market,
    marketLabel: normalizeMarketLabel(market),
    startDate: item.startDate || item.rangeStartDate || item.earliestDate || fallback.task?.backfillStartDate || '--',
    endDate: item.endDate || item.rangeEndDate || item.latestDate || fallback.latestTradeDate || '--',
    rowCount,
    missingEstimate,
    statusKey,
    statusLabel: statusMeta.label,
    statusType: statusMeta.type,
    coverageRate,
    coverageTone: statusMeta.tone,
    updatedAt: item.updatedAt || item.lastUpdatedAt || item.latestSyncAt || fallback.updatedAt || '--'
  }
}

const buildFallbackRows = (payload = {}) => {
  const coverageMap = payload?.marketCoverage && typeof payload.marketCoverage === 'object' ? payload.marketCoverage : {}
  return Object.entries(coverageMap).map(([market, rowCount], index) => ({
    id: `fallback-${market}-${index}`,
    symbol: market === 'ALL' ? 'ALL' : `${market}.ALL`,
    name: `${normalizeMarketLabel(market)}历史覆盖`,
    market,
    startDate: payload?.task?.backfillStartDate || '--',
    endDate: payload?.latestTradeDate || '--',
    rowCount,
    missingEstimate: 0,
    status: Number(payload?.coverageRate || 0) >= 99 ? 'complete' : 'partial',
    coverageRate: payload?.coverageRate ?? 0,
    updatedAt: payload?.task?.lastRunAt || payload?.latestTradeDate || '--'
  }))
}

const heroChips = computed(() => {
  const taskStatus = String(summary.value.task?.status || '').trim().toLowerCase()
  return [
    { text: `起始 ${summary.value.task?.backfillStartDate || '2024-01-01'}`, tone: 'info' },
    { text: summary.value.latestTradeDate ? `最新交易日 ${summary.value.latestTradeDate}` : '等待最新交易日', tone: 'warning' },
    { text: taskStatus === 'running' ? '任务运行中' : '覆盖快照', tone: taskStatus === 'running' ? 'success' : 'info' }
  ]
})

const heroMetrics = computed(() => [
  {
    label: '总覆盖率',
    value: `${formatDecimal(summary.value.coverageRate, 1, '0.0')}%`,
    tone: Number(summary.value.coverageRate || 0) >= 90 ? 'healthy' : 'warning'
  },
  {
    label: '已同步标的',
    value: formatCount(summary.value.syncedSymbols),
    note: `总数 ${formatCount(summary.value.totalUniverseSymbols)}`
  },
  {
    label: '历史总行数',
    value: formatCount(summary.value.totalRows)
  },
  {
    label: '更新时间',
    value: summary.value.updatedAt || '--'
  }
])

const filteredRows = computed(() => {
  const text = String(keyword.value || '').trim().toLowerCase()
  return tableRows.value.filter((item) => {
    const matchesStatus = statusFilter.value === 'all' || item.statusKey === statusFilter.value
    if (!matchesStatus) return false
    if (!text) return true
    return [item.symbol, item.name, item.marketLabel, item.market]
      .map((entry) => String(entry || '').toLowerCase())
      .some((entry) => entry.includes(text))
  })
})

const summaryMetrics = computed(() => {
  const rows = filteredRows.value
  const completeCount = rows.filter((item) => item.statusKey === 'complete').length
  const partialCount = rows.filter((item) => item.statusKey === 'partial').length
  const missingCount = rows.filter((item) => item.statusKey === 'missing').length
  const missingEstimate = rows.reduce((acc, item) => acc + Math.max(toNumber(item.missingEstimate, 0), 0), 0)
  return [
    { label: '完整标的', value: formatCount(completeCount), tone: 'healthy' },
    { label: '部分缺失', value: formatCount(partialCount), tone: partialCount > 0 ? 'warning' : 'info' },
    { label: '未覆盖', value: formatCount(missingCount), tone: missingCount > 0 ? 'error' : 'info' },
    { label: '缺失估算', value: formatCount(missingEstimate), tone: missingEstimate > 0 ? 'warning' : 'info' }
  ]
})

const statusOptions = computed(() => {
  const set = new Set(tableRows.value.map((item) => item.statusKey).filter(Boolean))
  return Array.from(set).map((key) => ({
    value: key,
    label: STATUS_META_MAP[key]?.label || key
  }))
})

const formatCount = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  return num.toLocaleString('zh-CN')
}

const resetFilters = () => {
  keyword.value = ''
  statusFilter.value = 'all'
}

const loadCoverage = async (manual = false) => {
  loading.value = true
  try {
    const res = await getMarketHistoryCoverage()
    const payload = normalizeSummary(res?.data || {})
    summary.value = payload
    const sourceItems = payload.items.length ? payload.items : buildFallbackRows(res?.data || {})
    tableRows.value = sourceItems.map((item, index) => normalizeRow(item, index, payload))
    if (manual) {
      ElMessage.success('覆盖数据已刷新')
    }
  } catch (error) {
    console.error('加载历史补价覆盖失败:', error)
    ElMessage.error(error?.data?.error || error?.message || '加载历史补价覆盖失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadCoverage(false)
})
</script>

<style scoped lang="scss">
.history-coverage-page {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hero-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.keyword-input {
  width: 220px;
}

.status-select {
  width: 132px;
}

.ghost-button {
  border-color: color-mix(in srgb, var(--accent) 20%, var(--border-soft));
  background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
  color: var(--text-emphasis);
}

.glass-card {
  border: 1px solid var(--border-soft);
  background: var(--surface-strong);
  box-shadow: var(--shadow-strong);
}

.table-card :deep(.el-card__body) {
  padding-top: 10px;
}

.table-card :deep(.el-table) {
  --el-table-header-bg-color: color-mix(in srgb, var(--surface-soft) 92%, transparent);
  --el-table-tr-bg-color: transparent;
  --el-table-row-hover-bg-color: color-mix(in srgb, var(--accent) 8%, transparent);
  --el-table-border-color: color-mix(in srgb, var(--border-soft) 86%, transparent);
}

.table-card :deep(.el-table td),
.table-card :deep(.el-table th) {
  padding: 7px 0;
}

.symbol-cell,
.range-cell {
  display: grid;
  gap: 2px;
}

.symbol-cell strong,
.coverage-rate {
  color: var(--text-emphasis);
  font-variant-numeric: tabular-nums;
}

.symbol-cell span,
.range-sep {
  color: var(--text-muted);
  font-size: 12px;
}

.coverage-rate.healthy {
  color: var(--success);
}

.coverage-rate.warning {
  color: var(--warning);
}

.coverage-rate.error {
  color: var(--danger);
}

.coverage-rate.info {
  color: color-mix(in srgb, var(--accent-strong, var(--accent)) 88%, white 12%);
}

@media (max-width: 960px) {
  .hero-actions {
    justify-content: flex-start;
  }

  .keyword-input,
  .status-select {
    width: 100%;
  }
}
</style>

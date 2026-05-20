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

    <section
      v-if="operationState"
      class="operation-feedback-panel"
      :class="operationState.kind"
    >
      <div class="operation-feedback-head">
        <strong>{{ operationState.title }}</strong>
        <span>{{ operationState.timestamp }}</span>
      </div>
      <p>{{ operationState.message }}</p>
    </section>

    <div class="coverage-focus-grid">
      <el-card class="glass-card focus-card">
        <template #header>
          <SectionCardHeader
            title="待补优先"
            :badge="`${repairableRows.length} 个`"
          />
        </template>
        <div v-if="repairableRows.length" class="gap-list">
          <button
            v-for="row in topGapRows"
            :key="row.id"
            type="button"
            class="gap-item"
            :disabled="isBackfillRunning(row)"
            @click="backfillRow(row)"
          >
            <span class="gap-item-copy">
              <strong>{{ row.symbol }}</strong>
              <small>{{ row.statusLabel }} · 缺 {{ formatCount(row.missingEstimate) }}</small>
              <small>{{ row.gapSummary }}</small>
            </span>
            <em>{{ isBackfillRunning(row) ? '补齐中' : '补齐' }}</em>
          </button>
        </div>
        <div v-else class="compact-empty">当前筛选内无待补标的</div>
      </el-card>

      <el-card class="glass-card focus-card">
        <template #header>
          <SectionCardHeader
            title="市场基准"
            :badge="summaryMarkets.length ? `${summaryMarkets.length} 个市场` : '未生成'"
          />
        </template>
        <div v-if="summaryMarkets.length" class="market-baseline-list">
          <div
            v-for="item in summaryMarkets"
            :key="item.market"
            class="market-baseline-item"
          >
            <span>{{ item.marketLabel }}</span>
            <strong>{{ item.expectedEnd || '--' }}</strong>
            <small>{{ formatCount(item.expectedDays) }} 日</small>
          </div>
        </div>
        <div v-else class="compact-empty">等待覆盖快照</div>
      </el-card>
    </div>

    <el-card class="glass-card table-card">
      <template #header>
        <SectionCardHeader
          title="覆盖明细"
          :badge="`${filteredRows.length} / ${formatCount(totalRows)}`"
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
        <el-table-column prop="missingEstimate" label="缺失估算" min-width="136" align="right">
          <template #default="{ row }">
            <div class="missing-cell">
              <strong>{{ formatCount(row.missingEstimate) }}</strong>
              <span>{{ row.gapSummary }}</span>
            </div>
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
        <el-table-column label="操作" width="118" fixed="right" align="right">
          <template #default="{ row }">
            <el-button
              class="repair-button"
              size="small"
              :loading="isBackfillRunning(row)"
              :disabled="!canBackfill(row)"
              @click="backfillRow(row)"
            >
              {{ row.statusKey === 'complete' ? '已完整' : '补齐' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-row">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next"
          :total="totalRows"
          :current-page="currentPage"
          :page-size="pageSize"
          :page-sizes="pageSizes"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getMarketHistoryCoverage, runMarketHistoryBackfill } from '../../api/market.js'
import { formatDecimal, formatPercent as formatPercentValue } from '../../utils/formatters.js'
import MetricStrip from '../../components/common/MetricStrip.vue'
import PageHero from '../../components/common/PageHero.vue'
import SectionCardHeader from '../../components/common/SectionCardHeader.vue'

const loading = ref(false)
const keyword = ref('')
const statusFilter = ref('all')
const summary = ref({})
const tableRows = ref([])
const totalRows = ref(0)
const currentPage = ref(1)
const pageSize = ref(100)
const pageSizes = [50, 100, 200]
const backfillLoadingSymbols = ref(new Set())
const operationState = ref(null)

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
  const missingEstimate = toNumber(item.missingEstimate ?? item.missingRows ?? item.missingCount ?? item.missingDays, 0)
  if (rowCount <= 0) return 'missing'
  if (missingEstimate > 0) return 'partial'
  if (item.complete === true) return 'complete'
  return 'complete'
}

const estimateCoverageRate = (item = {}) => {
  const explicit = clampCoverage(item.coverageRate ?? item.coverage ?? item.rate)
  if (explicit !== null) return explicit
  const rowCount = toNumber(item.rowCount ?? item.rangeCount ?? item.totalCount, 0)
  const missingEstimate = toNumber(item.missingEstimate ?? item.missingRows ?? item.missingCount ?? item.missingDays, 0)
  const denominator = rowCount + Math.max(missingEstimate, 0)
  if (!denominator) return 0
  return clampCoverage((rowCount / denominator) * 100) ?? 0
}

const deriveMissingEstimate = (item = {}) => {
  const explicit = item.missingEstimate ?? item.missingRows ?? item.missingCount ?? item.missingDays ?? item.missing_days
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
  const backendSummary = payload?.summary && typeof payload.summary === 'object' ? payload.summary : {}
  const counts = backendSummary.counts && typeof backendSummary.counts === 'object' ? backendSummary.counts : {}
  const items = Array.isArray(payload?.items)
    ? payload.items
    : Array.isArray(payload?.rows)
      ? payload.rows
      : Array.isArray(payload?.list)
        ? payload.list
        : []
  const totalUniverseSymbols = toNumber(
    payload?.totalUniverseSymbols ?? backendSummary.totalUniverseSymbols ?? backendSummary.filteredTotal ?? payload?.total,
    0
  )
  const syncedSymbols = toNumber(
    payload?.syncedSymbols ?? backendSummary.syncedSymbols,
    toNumber(counts.complete, 0) + toNumber(counts.partial, 0)
  )
  const coverageRate = clampCoverage(payload?.coverageRate ?? backendSummary.coverageRate)
    ?? (totalUniverseSymbols ? clampCoverage((syncedSymbols / totalUniverseSymbols) * 100) : 0)
    ?? 0

  return {
    totalUniverseSymbols,
    syncedSymbols,
    coverageRate,
    totalRows: toNumber(payload?.totalRows ?? backendSummary.totalRows, 0),
    latestTradeDate: payload?.latestTradeDate || backendSummary.latestTradeDate || backendSummary.expectedEnd || '',
    updatedAt: payload?.updatedAt || backendSummary.lastUpdated || task?.lastRunAt || payload?.latestTradeDate || '',
    task: {
      backfillStartDate: backendSummary.expectedStart || task.backfillStartDate,
      ...task
    },
    markets: Array.isArray(backendSummary.markets) ? backendSummary.markets : [],
    items
  }
}

const normalizeRow = (item = {}, index = 0, fallback = {}) => {
  const market = String(item.market || item.exchange || 'ALL').trim().toUpperCase()
  const symbol = String(item.symbol || item.code || '--').trim().toUpperCase() || '--'
  const rowCount = Math.max(toNumber(item.rowCount ?? item.rangeCount ?? item.totalCount, 0), 0)
  const missingEstimate = deriveMissingEstimate(item)
  const coverageRate = estimateCoverageRate(item)
  const statusKey = normalizeStatusKey(item)
  const statusMeta = STATUS_META_MAP[statusKey] || STATUS_META_MAP.partial
  return {
    id: item.id || item.symbol || `${market}-${index}`,
    symbol,
    name: String(item.name || item.displayName || item.symbolName || `${normalizeMarketLabel(market)}历史覆盖`).trim() || '--',
    market,
    marketLabel: normalizeMarketLabel(market),
    startDate: item.startDate || item.rangeStartDate || item.firstDate || item.earliestDate || fallback.task?.backfillStartDate || '--',
    endDate: item.endDate || item.rangeEndDate || item.latestDate || fallback.latestTradeDate || '--',
    rowCount,
    missingEstimate,
    expectedStart: item.expectedStart || item.expected_start || fallback.task?.backfillStartDate || '--',
    expectedEnd: item.expectedEnd || item.expected_end || fallback.latestTradeDate || '',
    gapSummary: buildGapSummary(item, missingEstimate),
    statusKey,
    statusLabel: statusMeta.label,
    statusType: statusMeta.type,
    coverageRate,
    coverageTone: statusMeta.tone,
    updatedAt: item.updatedAt || item.lastUpdated || item.lastUpdatedAt || item.latestSyncAt || fallback.updatedAt || '--',
    isAggregate: Boolean(item.isAggregate || symbol === 'ALL' || symbol.endsWith('.ALL'))
  }
}

const buildGapSummary = (item = {}, missingEstimate = 0) => {
  const ranges = Array.isArray(item.missingRanges) ? item.missingRanges : []
  if (ranges.length) {
    return ranges
      .slice(0, 2)
      .map((range) => `${range.startDate || range.start || '--'} ~ ${range.endDate || range.end || '--'}`)
      .join(' / ')
  }
  const expectedStart = String(item.expectedStart || item.expected_start || '').trim()
  const expectedEnd = String(item.expectedEnd || item.expected_end || '').trim()
  const actualStart = String(item.startDate || item.rangeStartDate || item.firstDate || item.earliestDate || '').trim()
  const actualEnd = String(item.endDate || item.rangeEndDate || item.latestDate || '').trim()
  const hints = []
  if (expectedStart && actualStart && expectedStart !== actualStart) {
    hints.push(`应从 ${expectedStart}，现从 ${actualStart}`)
  }
  if (expectedEnd && actualEnd && expectedEnd !== actualEnd) {
    hints.push(`应至 ${expectedEnd}，现至 ${actualEnd}`)
  }
  if (hints.length) {
    return hints.slice(0, 2).join(' / ')
  }
  return missingEstimate > 0 ? `缺 ${formatCount(missingEstimate)} 日` : '无缺口'
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
    updatedAt: payload?.task?.lastRunAt || payload?.latestTradeDate || '--',
    isAggregate: true
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

const repairableRows = computed(() => filteredRows.value.filter((item) => canBackfill(item)))

const topGapRows = computed(() => {
  return [...repairableRows.value]
    .sort((left, right) => {
      const leftMissing = toNumber(left.missingEstimate, 0)
      const rightMissing = toNumber(right.missingEstimate, 0)
      if (rightMissing !== leftMissing) return rightMissing - leftMissing
      return String(left.symbol).localeCompare(String(right.symbol))
    })
    .slice(0, 6)
})

const summaryMarkets = computed(() => {
  return (summary.value.markets || []).map((item) => ({
    market: String(item.market || '').trim().toUpperCase() || 'ALL',
    marketLabel: normalizeMarketLabel(item.market),
    expectedEnd: item.expectedEnd || item.expected_end || '',
    expectedDays: toNumber(item.expectedDays ?? item.expected_days, 0)
  }))
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
  return ['complete', 'partial', 'missing'].map((key) => ({
    value: key,
    label: STATUS_META_MAP[key]?.label || key
  }))
})

const formatCount = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  return num.toLocaleString('zh-CN')
}

const formatOperationTimestamp = () => new Date().toLocaleString('zh-CN', { hour12: false })

const setOperationState = (kind, title, message) => {
  operationState.value = {
    kind,
    title,
    message,
    timestamp: formatOperationTimestamp()
  }
}

const resetFilters = () => {
  keyword.value = ''
  statusFilter.value = 'all'
  currentPage.value = 1
}

const canBackfill = (row = {}) => {
  return Boolean(row.symbol && row.symbol !== '--' && row.statusKey !== 'complete' && !row.isAggregate)
}

const isBackfillRunning = (row = {}) => {
  return backfillLoadingSymbols.value.has(row.symbol)
}

const setBackfillLoading = (symbol, value) => {
  const next = new Set(backfillLoadingSymbols.value)
  if (value) {
    next.add(symbol)
  } else {
    next.delete(symbol)
  }
  backfillLoadingSymbols.value = next
}

const validDateOrUndefined = (value) => {
  const text = String(value || '').trim()
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : undefined
}

const backfillRow = async (row = {}) => {
  if (!canBackfill(row) || isBackfillRunning(row)) return
  const startDate = validDateOrUndefined(row.expectedStart || summary.value.task?.backfillStartDate)
  const endDate = validDateOrUndefined(row.expectedEnd || summary.value.latestTradeDate)
  setOperationState(
    'loading',
    `正在补齐 ${row.symbol}`,
    `${startDate || '自动起始'} ~ ${endDate || '最新交易日'}`
  )
  setBackfillLoading(row.symbol, true)
  try {
    const res = await runMarketHistoryBackfill({
      symbol: row.symbol,
      startDate,
      endDate
    })
    const savedCount = toNumber(res?.data?.savedCount, 0)
    setOperationState(
      'success',
      `${row.symbol} 补价完成`,
      savedCount > 0 ? `新增 ${formatCount(savedCount)} 条历史行情` : '已检查，无需补齐'
    )
    ElMessage.success(savedCount > 0 ? `${row.symbol} 已补齐 ${formatCount(savedCount)} 条` : `${row.symbol} 已检查，无需补齐`)
    await loadCoverage(false)
  } catch (error) {
    console.error('历史补价失败:', error)
    setOperationState(
      'error',
      `${row.symbol} 补价失败`,
      error?.data?.error || error?.message || '历史补价失败'
    )
    ElMessage.error(error?.data?.error || error?.message || '历史补价失败')
  } finally {
    setBackfillLoading(row.symbol, false)
  }
}

const loadCoverage = async (manual = false) => {
  if (manual) {
    setOperationState('loading', '正在刷新覆盖快照', '同步最新覆盖统计与缺口摘要')
  }
  loading.value = true
  try {
    const res = await getMarketHistoryCoverage({
      search: keyword.value.trim(),
      status: statusFilter.value === 'all' ? '' : statusFilter.value,
      page: currentPage.value,
      page_size: pageSize.value
    })
    const payload = normalizeSummary(res?.data || {})
    summary.value = payload
    totalRows.value = toNumber(res?.data?.total ?? payload.totalUniverseSymbols ?? payload.items.length, payload.items.length)
    const sourceItems = payload.items.length ? payload.items : buildFallbackRows(res?.data || {})
    tableRows.value = sourceItems.map((item, index) => normalizeRow(item, index, payload))
    if (manual) {
      setOperationState('success', '覆盖快照已刷新', `当前展示 ${formatCount(tableRows.value.length)} 条记录`)
      ElMessage.success('覆盖数据已刷新')
    }
  } catch (error) {
    console.error('加载历史补价覆盖失败:', error)
    setOperationState('error', '覆盖快照加载失败', error?.data?.error || error?.message || '加载历史补价覆盖失败')
    ElMessage.error(error?.data?.error || error?.message || '加载历史补价覆盖失败')
  } finally {
    loading.value = false
  }
}

let filterTimer = null
const scheduleCoverageLoad = () => {
  if (filterTimer) {
    window.clearTimeout(filterTimer)
  }
  filterTimer = window.setTimeout(() => {
    currentPage.value = 1
    loadCoverage(false)
  }, 260)
}

watch([keyword, statusFilter], scheduleCoverageLoad)

const handlePageChange = (page) => {
  currentPage.value = Number(page) || 1
  loadCoverage(false)
}

const handlePageSizeChange = (size) => {
  pageSize.value = Number(size) || 100
  currentPage.value = 1
  loadCoverage(false)
}

onBeforeUnmount(() => {
  if (filterTimer) {
    window.clearTimeout(filterTimer)
  }
})

onMounted(() => {
  loadCoverage(false)
})

defineExpose({
  backfillRow,
  currentPage,
  pageSize,
  operationState,
  tableRows,
  totalRows,
  topGapRows
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

.operation-feedback-panel {
  border: 1px solid color-mix(in srgb, var(--border-soft) 82%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface-soft) 90%, transparent);
  color: var(--text-primary);
  padding: 10px 12px;
}

.operation-feedback-panel.loading {
  border-color: color-mix(in srgb, var(--accent) 34%, var(--border-soft));
  background: color-mix(in srgb, var(--accent) 10%, var(--surface-soft));
}

.operation-feedback-panel.success {
  border-color: color-mix(in srgb, var(--success) 42%, var(--border-soft));
  background: color-mix(in srgb, var(--success) 12%, var(--surface-soft));
}

.operation-feedback-panel.error {
  border-color: color-mix(in srgb, var(--danger) 42%, var(--border-soft));
  background: color-mix(in srgb, var(--danger) 10%, var(--surface-soft));
}

.operation-feedback-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.operation-feedback-head strong {
  color: var(--text-emphasis);
}

.operation-feedback-head span,
.operation-feedback-panel p {
  color: var(--text-muted);
  font-size: 13px;
}

.operation-feedback-panel p {
  margin: 6px 0 0;
}

.table-card :deep(.el-card__body) {
  padding-top: 10px;
}

.coverage-focus-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.6fr);
  gap: 10px;
}

.focus-card :deep(.el-card__body) {
  padding: 10px;
}

.gap-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 8px;
}

.gap-item {
  min-height: 52px;
  border: 1px solid color-mix(in srgb, var(--accent) 26%, var(--border-soft));
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface-soft) 88%, var(--accent) 6%);
  color: var(--text-emphasis);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  cursor: pointer;
  text-align: left;
}

.gap-item:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--accent) 54%, var(--border-soft));
  background: color-mix(in srgb, var(--accent) 13%, var(--surface-soft));
}

.gap-item:disabled {
  cursor: not-allowed;
  opacity: 0.72;
}

.gap-item span {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.gap-item-copy {
  min-width: 0;
}

.gap-item strong {
  color: var(--text-emphasis);
  font-size: 13px;
}

.gap-item small,
.market-baseline-item small {
  color: var(--text-muted);
  font-size: 12px;
}

.gap-item em {
  flex: 0 0 auto;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--accent-strong, var(--accent)) 42%, var(--border-soft));
  background: color-mix(in srgb, var(--accent-strong, var(--accent)) 76%, var(--surface-strong));
  color: var(--button-primary-text, #fff);
  font-style: normal;
  font-size: 12px;
  font-weight: 700;
  padding: 4px 8px;
}

.market-baseline-list {
  display: grid;
  gap: 8px;
}

.market-baseline-item {
  display: grid;
  grid-template-columns: 64px 1fr auto;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  border-bottom: 1px solid color-mix(in srgb, var(--border-soft) 72%, transparent);
  color: var(--text-primary);
}

.market-baseline-item:last-child {
  border-bottom: 0;
}

.market-baseline-item strong {
  color: var(--text-emphasis);
  font-size: 13px;
}

.compact-empty {
  min-height: 52px;
  display: grid;
  place-items: center;
  border: 1px dashed color-mix(in srgb, var(--border-soft) 86%, transparent);
  border-radius: 8px;
  color: var(--text-muted);
  font-size: 13px;
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

.pagination-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}

.pagination-row :deep(.el-pagination) {
  --el-pagination-bg-color: color-mix(in srgb, var(--surface-soft) 86%, transparent);
  --el-pagination-button-color: var(--text-primary);
  --el-pagination-hover-color: var(--accent-strong, var(--accent));
  --el-pagination-button-disabled-bg-color: color-mix(in srgb, var(--surface-muted) 86%, transparent);
}

.symbol-cell,
.range-cell,
.missing-cell {
  display: grid;
  gap: 2px;
}

.symbol-cell strong,
.missing-cell strong,
.coverage-rate {
  color: var(--text-emphasis);
  font-variant-numeric: tabular-nums;
}

.symbol-cell span,
.missing-cell span,
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

.repair-button {
  border-color: color-mix(in srgb, var(--accent) 30%, var(--border-soft));
  background: color-mix(in srgb, var(--accent-strong, var(--accent)) 72%, var(--surface-strong));
  color: var(--button-primary-text, #fff);
  font-weight: 700;
}

.repair-button:hover:not(.is-disabled),
.repair-button:focus:not(.is-disabled) {
  border-color: color-mix(in srgb, var(--accent) 60%, var(--border-soft));
  background: color-mix(in srgb, var(--accent-strong, var(--accent)) 82%, var(--surface-strong));
  color: var(--button-primary-text, #fff);
}

.repair-button.is-disabled {
  border-color: color-mix(in srgb, var(--border-soft) 78%, transparent);
  background: color-mix(in srgb, var(--surface-soft) 78%, transparent);
  color: var(--text-muted);
}

@media (max-width: 960px) {
  .coverage-focus-grid {
    grid-template-columns: 1fr;
  }

  .hero-actions {
    justify-content: flex-start;
  }

  .keyword-input,
  .status-select {
    width: 100%;
  }
}
</style>

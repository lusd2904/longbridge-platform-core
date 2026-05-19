<template>
  <div class="kline-page">
    <PageHero
      title="历史K线中心"
      :chips="klineHeroChips"
      :metrics="klineHeroMetrics"
    >
      <template #actions>
        <div class="header-actions">
          <el-select
            v-model="selectedSymbols"
            multiple
            filterable
            allow-create
            default-first-option
            collapse-tags
            collapse-tags-tooltip
            class="symbol-select"
            placeholder="输入或选择多个标的，最多 6 个"
            @change="handleSymbolsChange"
          >
            <el-option
              v-for="item in symbolOptions"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
          <el-select v-model="lookbackLimit" class="limit-select">
            <el-option label="120 根" :value="120" />
            <el-option label="240 根" :value="240" />
            <el-option label="480 根" :value="480" />
          </el-select>
          <el-radio-group v-model="timeframe">
            <el-radio-button value="daily">日K</el-radio-button>
            <el-radio-button value="weekly">周K</el-radio-button>
            <el-radio-button value="monthly">月K</el-radio-button>
            <el-radio-button value="quarterly">季K</el-radio-button>
            <el-radio-button value="yearly">年K</el-radio-button>
          </el-radio-group>
          <el-button plain @click="focusPrimary(primarySymbol)">聚焦主图</el-button>
          <el-button type="primary" :loading="loading" @click="loadHistory(true)">
            刷新历史
          </el-button>
        </div>
      </template>
    </PageHero>

    <MetricStrip class="kline-overview-strip" :items="klineOverviewItems" />

    <div class="quick-picks">
      <span class="pick-label">快捷查看</span>
      <el-button
        v-for="item in quickSymbols"
        :key="item"
        size="small"
        plain
        @click="applyQuickSymbol(item)"
      >
        {{ item }}
      </el-button>
    </div>

    <ReadModelSourceStrip
      label="历史数据"
      :status-text="historyReadModelStatus"
      :status-type="historyReadModelStatusType"
      :updated-at="historyReadModelUpdatedAt"
      :tags="historyReadModelTags"
    />

    <el-card class="glass-card compare-card">
      <template #header>
        <SectionCardHeader
          title="多标的对比"
          :badge="`${selectedSymbols.length} 个标的`"
        />
      </template>
      <v-chart class="compare-chart" :option="compareOption" autoresize />
    </el-card>

    <div class="chart-grid">
      <el-card class="glass-card chart-card">
        <template #header>
          <SectionCardHeader
            :title="`${primarySymbol || '--'} · ${timeframeLabel}`"
            :badge="`${primarySummary.firstDate || '--'} 至 ${primarySummary.latestDate || '--'}`"
          />
        </template>
        <v-chart class="kline-chart" :option="klineOption" autoresize />
      </el-card>

      <el-card class="glass-card indicator-card">
        <template #header>
          <SectionCardHeader
            title="指标快照"
            :badge="timeframeLabel"
          />
        </template>
        <el-table :data="indicatorRows" style="width: 100%" height="520" empty-text="暂无指标数据">
          <el-table-column prop="symbol" label="标的" min-width="150">
            <template #default="{ row }">
              <button type="button" class="symbol-action" @click="focusPrimary(row.symbol)">
                {{ row.symbol }}
              </button>
              <div class="symbol-name">{{ row.name }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="trendLabel" label="趋势" width="110" />
          <el-table-column prop="closePrice" label="收盘" width="110">
            <template #default="{ row }">
              {{ formatSymbolPrice(row.symbol, row.closePrice) }}
            </template>
          </el-table-column>
          <el-table-column prop="changePercent" label="涨跌幅" width="110">
            <template #default="{ row }">
              <span :class="trendClass(row.changePercent)">
                {{ formatPercent(row.changePercent) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="rsi" label="RSI" width="90">
            <template #default="{ row }">
              {{ formatDecimal(row.rsi) }}
            </template>
          </el-table-column>
          <el-table-column prop="macdHist" label="MACD" width="100">
            <template #default="{ row }">
              {{ formatDecimal(row.macdHist, 4) }}
            </template>
          </el-table-column>
          <el-table-column prop="roc" label="ROC" width="90">
            <template #default="{ row }">
              {{ formatDecimal(row.roc) }}
            </template>
          </el-table-column>
          <el-table-column prop="supportPrice" label="支撑" width="110">
            <template #default="{ row }">
              {{ formatSymbolPrice(row.symbol, row.supportPrice) }}
            </template>
          </el-table-column>
          <el-table-column prop="resistancePrice" label="阻力" width="110">
            <template #default="{ row }">
              {{ formatSymbolPrice(row.symbol, row.resistancePrice) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" size="small" link @click="viewSymbolDetail(row.symbol)">
                详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <el-card class="glass-card table-card">
      <template #header>
        <SectionCardHeader
          title="主图历史数据"
          :badge="`${primaryItems.length} 条`"
        />
      </template>

      <el-table :data="tableRows" style="width: 100%" height="460" v-loading="loading" empty-text="暂无历史数据">
        <el-table-column prop="date" label="日期" width="120" />
        <el-table-column prop="open" label="开盘价" width="120">
          <template #default="{ row }">
            {{ formatSymbolPrice(primarySymbol, row.open) }}
          </template>
        </el-table-column>
        <el-table-column prop="high" label="最高价" width="120">
          <template #default="{ row }">
            {{ formatSymbolPrice(primarySymbol, row.high) }}
          </template>
        </el-table-column>
        <el-table-column prop="low" label="最低价" width="120">
          <template #default="{ row }">
            {{ formatSymbolPrice(primarySymbol, row.low) }}
          </template>
        </el-table-column>
        <el-table-column prop="close" label="收盘价" width="120">
          <template #default="{ row }">
            {{ formatSymbolPrice(primarySymbol, row.close) }}
          </template>
        </el-table-column>
        <el-table-column prop="volume" label="成交量" width="150">
          <template #default="{ row }">
            {{ formatVolume(row.volume) }}
          </template>
        </el-table-column>
        <el-table-column prop="changePercent" label="涨跌幅" width="120">
          <template #default="{ row }">
            <span :class="trendClass(row.changePercent)">
              {{ formatPercent(row.changePercent) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { CandlestickChart, BarChart, LineChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { useTheme, getThemeValue } from '../composables/useTheme.js'
import { getMarketHistoryBackfillStatus, getMarketHistoryCompare } from '../api/market.js'
import { formatCurrency, formatDecimal as formatDecimalValue, formatPercent as formatPercentValue } from '../utils/formatters.js'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import PageHero from '../components/common/PageHero.vue'
import MetricStrip from '../components/common/MetricStrip.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'
import { buildHistoryReadModelSummary } from '../utils/readModelSource.js'

use([CanvasRenderer, CandlestickChart, BarChart, LineChart, GridComponent, TooltipComponent, DataZoomComponent, LegendComponent])

const { activeTheme } = useTheme()
const route = useRoute()
const router = useRouter()

const loading = ref(false)
const selectedSymbols = ref(['AAPL.US'])
const timeframe = ref('daily')
const lookbackLimit = ref(240)
const historySeries = ref([])
const comparisonSeries = ref([])
const snapshotPayload = ref([])
const backfillStatus = ref(null)
const historyMeta = ref({})
const backfillStatusLoading = ref(false)

const quickSymbols = ['AAPL.US', 'NVDA.US', 'TSLA.US', 'SPY.US', 'QQQ.US', '700.HK', '9988.HK', '510300.SH']

const symbolOptions = computed(() => Array.from(new Set([...quickSymbols, ...selectedSymbols.value])))
const primarySymbol = computed(() => selectedSymbols.value[0] || '')
const normalizeSymbolKey = (symbol = '') => String(symbol || '').trim().toUpperCase()
const normalizeBareSymbolKey = (symbol = '') => normalizeSymbolKey(symbol).split('.')[0]
const symbolMatches = (left = '', right = '') => {
  const normalizedLeft = normalizeSymbolKey(left)
  const normalizedRight = normalizeSymbolKey(right)
  if (!normalizedLeft || !normalizedRight) return false
  return normalizedLeft === normalizedRight || normalizeBareSymbolKey(normalizedLeft) === normalizeBareSymbolKey(normalizedRight)
}
const primaryHistory = computed(() => (
  historySeries.value.find((item) => symbolMatches(item.symbol, primarySymbol.value)) ||
  historySeries.value[0] ||
  null
))
const primaryItems = computed(() => primaryHistory.value?.items || [])
const primarySummary = computed(() => primaryHistory.value?.summary || {
  count: 0,
  latestDate: null,
  firstDate: null,
  latestClose: 0,
  periodReturn: 0
})
const timeframeLabel = computed(() => {
  return {
    daily: '日K',
    weekly: '周K',
    monthly: '月K',
    quarterly: '季K',
    yearly: '年K'
  }[timeframe.value] || '日K'
})
const tableRows = computed(() => [...primaryItems.value].reverse())
const indicatorRows = computed(() => snapshotPayload.value.map((item) => ({
  symbol: item.symbol,
  name: item.name,
  market: item.market,
  ...(item.snapshot || {})
})))
const historyReadModelSummary = computed(() => buildHistoryReadModelSummary(
  historyMeta.value,
  {
    symbolCount: selectedSymbols.value.length,
    timeframeLabel: timeframeLabel.value,
    limitLabel: lookbackLimit.value
  }
))
const historyReadModelStatus = computed(() => (
  historyReadModelSummary.value.updatedAt || backfillStatus.value?.coverageRate
    ? '历史快照'
    : historyReadModelSummary.value.statusText
))
const historyReadModelStatusType = computed(() => (
  historyReadModelSummary.value.updatedAt || backfillStatus.value?.coverageRate
    ? 'info'
    : historyReadModelSummary.value.statusType
))
const historyReadModelUpdatedAt = computed(() => historyReadModelSummary.value.updatedAt || primarySummary.value?.latestDate || backfillStatus.value?.latestTradeDate || '')
const historyReadModelTags = computed(() => historyReadModelSummary.value.tags || [])
const toneForSignedValue = (value) => {
  const amount = Number(value || 0)
  if (amount > 0) return 'healthy'
  if (amount < 0) return 'error'
  return 'info'
}
const klineHeroChips = computed(() => ([
  {
    text: timeframeLabel.value,
    tone: 'info'
  },
  {
    text: `${selectedSymbols.value.length} 个标的`,
    tone: selectedSymbols.value.length > 1 ? 'healthy' : 'info'
  },
  {
    text: historyReadModelStatus.value,
    tone: historyReadModelStatusType.value === 'success' ? 'healthy' : historyReadModelStatusType.value || 'info'
  }
]))
const klineHeroMetrics = computed(() => ([
  {
    label: '主图标的',
    value: primarySymbol.value || '--',
    note: '当前聚焦'
  },
  {
    label: '最新收盘',
    value: formatSymbolPrice(primarySymbol.value, primarySummary.value.latestClose),
    note: primarySummary.value.latestDate || '等待快照'
  },
  {
    label: '区间涨跌',
    value: formatPercent(primarySummary.value.periodReturn),
    note: `${primarySummary.value.count || 0} 条数据`,
    tone: toneForSignedValue(primarySummary.value.periodReturn)
  }
]))
const klineOverviewItems = computed(() => {
  const items = []
  if (backfillStatus.value) {
    items.push({
      label: '同步状态',
      value: `${formatDecimal(backfillStatus.value.coverageRate)}%`,
      tone: Number(backfillStatus.value.coverageRate || 0) >= 80 ? 'healthy' : 'warning'
    })
  } else if (backfillStatusLoading.value) {
    items.push({
      label: '同步状态',
      value: '更新中',
      tone: 'info'
    })
  }
  items.push(
    {
      label: '主图标的',
      value: primarySymbol.value || '--',
      note: '当前查询主图'
    },
    {
      label: '最新收盘',
      value: formatSymbolPrice(primarySymbol.value, primarySummary.value.latestClose),
      note: primarySummary.value.latestDate || '等待历史快照'
    },
    {
      label: '区间涨跌',
      value: formatPercent(primarySummary.value.periodReturn),
      note: '当前主图区间回报',
      tone: toneForSignedValue(primarySummary.value.periodReturn)
    },
    {
      label: '查询范围',
      value: `${timeframeLabel.value} · ${primarySummary.value.count || 0} 条`,
      note: `回看 ${lookbackLimit.value} 根`
    }
  )
  return items
})

const normalizeSymbols = (symbols = []) => {
  const next = []
  for (const rawSymbol of symbols) {
    const chunks = String(rawSymbol || '')
      .split(',')
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean)
    for (const normalized of chunks) {
      if (next.includes(normalized)) continue
      next.push(normalized)
      if (next.length >= 6) break
    }
    if (next.length >= 6) break
  }
  return next
}

const resolveCurrency = (symbol = '') => {
  const normalized = String(symbol || '').toUpperCase()
  if (normalized.endsWith('.HK')) return 'HK$'
  if (normalized.endsWith('.SH') || normalized.endsWith('.SZ') || normalized.endsWith('.BJ')) return '¥'
  return '$'
}

const formatSymbolPrice = (symbol, value) => formatCurrency(value, {
  currency: resolveCurrency(symbol),
  fallback: `${resolveCurrency(symbol)}0.00`
})
const formatDecimal = (value, digits = 2) => formatDecimalValue(value, digits)
const formatPercent = (value) => formatPercentValue(value, { signed: true })
const formatVolume = (value) => {
  const amount = Number(value || 0)
  if (amount >= 100000000) return `${(amount / 100000000).toFixed(2)}亿`
  if (amount >= 10000) return `${(amount / 10000).toFixed(2)}万`
  return amount.toLocaleString('zh-CN')
}

const trendClass = (value) => {
  const amount = Number(value || 0)
  if (amount > 0) return 'positive'
  if (amount < 0) return 'negative'
  return 'neutral'
}

const loadHistory = async (refresh = false) => {
  const symbols = normalizeSymbols(selectedSymbols.value)
  selectedSymbols.value = symbols.length ? symbols : ['AAPL.US']

  if (!selectedSymbols.value.length) {
    ElMessage.warning('请至少输入一个标的')
    return
  }

  loading.value = true
  try {
    const res = await getMarketHistoryCompare({
      symbols: selectedSymbols.value,
      timeframe: timeframe.value,
      limit: lookbackLimit.value,
      refresh
    })
    historyMeta.value = res?.meta && typeof res.meta === 'object' ? res.meta : {}
    const payload = res?.data || {}
    historySeries.value = Array.isArray(payload.series) ? payload.series : []
    comparisonSeries.value = Array.isArray(payload.comparison) ? payload.comparison : []
    snapshotPayload.value = Array.isArray(payload.snapshots) ? payload.snapshots : []
    const resolvedSymbols = Array.isArray(payload.symbols) && payload.symbols.length
      ? payload.symbols
      : [payload.primarySymbol, ...historySeries.value.map((item) => item.symbol)].filter(Boolean)
    if (resolvedSymbols.length) {
      selectedSymbols.value = normalizeSymbols(resolvedSymbols)
    }
    if (!primaryItems.value.length) {
      ElMessage.warning('当前标的暂无历史数据')
    }
    syncRoute()
  } catch (error) {
    console.error('加载历史K线失败:', error)
    historyMeta.value = {}
    ElMessage.error(error?.data?.error || error?.message || '加载历史K线失败')
  } finally {
    loading.value = false
  }
}

const loadBackfillStatus = async () => {
  backfillStatusLoading.value = true
  try {
    const res = await getMarketHistoryBackfillStatus()
    backfillStatus.value = res?.data || null
  } catch (error) {
    console.error('加载历史补数状态失败:', error)
  } finally {
    backfillStatusLoading.value = false
  }
}

const syncRoute = () => {
  router.replace({
    name: 'Kline',
    query: {
      symbols: selectedSymbols.value.join(','),
      timeframe: timeframe.value,
      limit: String(lookbackLimit.value)
    }
  }).catch(() => {})
}

const handleSymbolsChange = (values = []) => {
  const normalized = normalizeSymbols(values)
  if (normalized.length < values.length) {
    ElMessage.warning('最多支持同时查询 6 个标的')
  }
  selectedSymbols.value = normalized
  loadHistory(false)
}

const applyQuickSymbol = (symbol) => {
  const merged = normalizeSymbols([symbol, ...selectedSymbols.value])
  if (merged.length === selectedSymbols.value.length && merged[0] !== symbol) {
    focusPrimary(symbol)
    return
  }
  selectedSymbols.value = merged
  loadHistory(false)
}

const focusPrimary = (symbol) => {
  const normalized = String(symbol || '').trim().toUpperCase()
  if (!normalized) return
  const others = selectedSymbols.value.filter((item) => item !== normalized)
  selectedSymbols.value = normalizeSymbols([normalized, ...others])
  syncRoute()
}

const viewSymbolDetail = (symbol) => {
  router.push({
    name: 'SymbolDetail',
    params: { symbol }
  })
}

const calculateMovingAverage = (dayCount) => {
  const result = []
  for (let index = 0; index < primaryItems.value.length; index += 1) {
    if (index < dayCount - 1) {
      result.push('-')
      continue
    }
    let sum = 0
    for (let offset = 0; offset < dayCount; offset += 1) {
      sum += Number(primaryItems.value[index - offset]?.close || 0)
    }
    result.push(Number((sum / dayCount).toFixed(2)))
  }
  return result
}

const klineOption = computed(() => {
  activeTheme.value

  const dates = primaryItems.value.map((item) => item.date)
  const klineData = primaryItems.value.map((item) => [item.open, item.close, item.low, item.high])
  const volumes = primaryItems.value.map((item) => item.volume)

  const axisColor = getThemeValue('--chart-axis', 'rgba(99, 115, 141, 0.8)')
  const gridColor = getThemeValue('--chart-grid', 'rgba(125, 154, 191, 0.14)')
  const textColor = getThemeValue('--text-secondary', '#63738d')
  const upColor = getThemeValue('--success', '#16a34a')
  const downColor = getThemeValue('--danger', '#ef5350')
  const surfaceColor = getThemeValue('--surface-strong', 'rgba(255,255,255,0.94)')
  const accentStrong = getThemeValue('--accent-strong', '#3b82f6')
  const accent = getThemeValue('--accent', '#60a5fa')

  return {
    backgroundColor: 'transparent',
    animation: false,
    grid: [
      { left: '3%', right: '3%', top: '9%', height: '58%' },
      { left: '3%', right: '3%', top: '74%', height: '14%' }
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        scale: true,
        boundaryGap: false,
        axisLine: { lineStyle: { color: axisColor } },
        axisLabel: { color: textColor },
        splitLine: { show: false }
      },
      {
        type: 'category',
        gridIndex: 1,
        data: dates,
        axisLabel: { show: false },
        axisLine: { lineStyle: { color: axisColor } }
      }
    ],
    yAxis: [
      {
        scale: true,
        axisLine: { show: false },
        axisLabel: { color: textColor },
        splitLine: { lineStyle: { color: gridColor, type: 'dashed' } }
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false }
      }
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
      { show: true, xAxisIndex: [0, 1], type: 'slider', top: '91%', start: 0, end: 100 }
    ],
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: surfaceColor,
      borderColor: gridColor,
      borderWidth: 1,
      textStyle: { color: getThemeValue('--text-primary', '#132238') }
    },
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: klineData,
        itemStyle: {
          color: upColor,
          color0: downColor,
          borderColor: upColor,
          borderColor0: downColor
        }
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes,
        itemStyle: {
          color: (params) => klineData[params.dataIndex]?.[1] >= klineData[params.dataIndex]?.[0] ? upColor : downColor
        }
      },
      {
        name: 'MA5',
        type: 'line',
        data: calculateMovingAverage(5),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.8, color: accentStrong }
      },
      {
        name: 'MA10',
        type: 'line',
        data: calculateMovingAverage(10),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.6, color: accent }
      },
      {
        name: 'MA20',
        type: 'line',
        data: calculateMovingAverage(20),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.4, color: getThemeValue('--warning', '#f59e0b') }
      }
    ]
  }
})

const compareOption = computed(() => {
  activeTheme.value

  const axisColor = getThemeValue('--chart-axis', 'rgba(99, 115, 141, 0.8)')
  const gridColor = getThemeValue('--chart-grid', 'rgba(125, 154, 191, 0.14)')
  const textColor = getThemeValue('--text-secondary', '#63738d')
  const palette = [
    getThemeValue('--accent-strong', '#3b82f6'),
    getThemeValue('--accent', '#60a5fa'),
    getThemeValue('--warning', '#f59e0b'),
    getThemeValue('--success', '#16a34a'),
    getThemeValue('--danger', '#ef4444'),
    '#8b5cf6'
  ]

  return {
    color: palette,
    grid: { left: '3%', right: '3%', top: '14%', bottom: '8%', containLabel: true },
    legend: {
      top: 0,
      textStyle: { color: textColor }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line' },
      valueFormatter: (value) => `${Number(value || 0).toFixed(2)}%`
    },
    xAxis: {
      type: 'category',
      data: Array.from(new Set(comparisonSeries.value.flatMap((item) => (item.series || []).map((entry) => entry.date)))).sort(),
      axisLabel: { color: axisColor },
      axisLine: { lineStyle: { color: gridColor } }
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: axisColor,
        formatter: (value) => `${Number(value || 0).toFixed(0)}%`
      },
      splitLine: { lineStyle: { color: gridColor, type: 'dashed' } }
    },
    series: comparisonSeries.value.map((item) => ({
      name: item.symbol,
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: Array.from(new Set(comparisonSeries.value.flatMap((row) => (row.series || []).map((entry) => entry.date))))
        .sort()
        .map((date) => {
          const current = (item.series || []).find((entry) => entry.date === date)
          return current ? current.value : null
        }),
      lineStyle: { width: item.symbol === primarySymbol.value ? 3 : 2 },
      emphasis: { focus: 'series' }
    }))
  }
})

onMounted(() => {
  const initialSymbols = normalizeSymbols(
    String(route.query.symbols || route.query.symbol || 'AAPL.US')
      .split(',')
      .map((item) => item.trim())
  )
  selectedSymbols.value = initialSymbols.length ? initialSymbols : ['AAPL.US']
  timeframe.value = ['daily', 'weekly', 'monthly', 'quarterly', 'yearly'].includes(String(route.query.timeframe || ''))
    ? String(route.query.timeframe)
    : 'daily'
  lookbackLimit.value = [120, 240, 480].includes(Number(route.query.limit)) ? Number(route.query.limit) : 240
  loadBackfillStatus()
  loadHistory(false)
})

watch([timeframe, lookbackLimit], () => {
  loadHistory(false)
})
</script>

<style scoped lang="scss">
.kline-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.header-actions,
.quick-picks {
  display: flex;
  align-items: center;
}

.kline-hero-aside {
  display: grid;
  gap: 6px;
  min-width: min(100%, 280px);
  padding: 16px 18px;
  border-radius: 22px;
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-soft) 84%, transparent);
}

.kline-hero-aside span,
.kline-hero-aside small {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.kline-hero-aside strong {
  color: var(--text-emphasis);
  font-size: 18px;
}

.header-actions {
  gap: 12px;
  flex-wrap: wrap;
}

.symbol-select {
  width: 440px;
}

.limit-select {
  width: 110px;
}

.quick-picks {
  gap: 10px;
  flex-wrap: wrap;
}

.pick-label {
  color: var(--text-muted);
  font-size: 13px;
}

.glass-card {
  border-radius: 28px;
  border: 1px solid var(--border-soft);
  background: var(--panel-surface);
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.chart-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(420px, 0.95fr);
  gap: 18px;
}

.compare-chart {
  width: 100%;
  height: 320px;
}

.chart-card,
.table-card,
.indicator-card,
.compare-card {
  overflow: hidden;
}

.kline-chart {
  width: 100%;
  height: 520px;
}

.symbol-action {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent-strong);
  cursor: pointer;
  font: inherit;
  font-weight: 700;
}

.symbol-name {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.positive {
  color: var(--success);
}

.negative {
  color: var(--danger);
}

.neutral {
  color: var(--text-secondary);
}

@media (max-width: 1080px) {
  .chart-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .symbol-select {
    width: 100%;
  }
}
</style>

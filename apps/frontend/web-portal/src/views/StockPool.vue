<template>
  <div class="stock-pool-page">
    <section class="hero-panel">
      <div class="hero-copy">
        <h2>股票池</h2>
        <div class="hero-tags">
          <span class="hero-tag">{{ activeFilterLabel }}</span>
          <span class="hero-tag">{{ filteredSummary }}</span>
          <span class="hero-tag">{{ quotesConnected ? '长桥推送在线' : '长桥实时拉取' }}</span>
          <span class="hero-tag">{{ realtimeQuoteCoverageTag }}</span>
          <span class="hero-tag">{{ realtimeQuoteTimeTag }}</span>
        </div>
      </div>

      <div class="hero-actions">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索股票代码或名称"
          :prefix-icon="Search"
          clearable
          class="search-input"
          @input="handleSearch"
        />
        <div class="action-group">
          <el-button type="primary" class="hero-primary-button" :icon="Plus" @click="showAddDialog">
            添加股票
          </el-button>
          <el-button class="hero-secondary-button" :icon="Refresh" :loading="loading" :disabled="loading" @click="refreshData">
            刷新
          </el-button>
          <el-button
            v-if="canSync"
            class="hero-secondary-button"
            :icon="DataLine"
            :loading="syncing"
            :disabled="syncing"
            @click="syncUniverse"
          >
            全量同步
          </el-button>
        </div>
      </div>
    </section>

    <section class="insight-strip">
      <article v-for="item in universeInsights" :key="item.label" class="insight-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </section>

    <ReadModelSourceStrip
      label="股票池状态"
      :status-text="stockPoolReadModelStatus"
      :status-type="stockPoolReadModelStatusType"
      :updated-at="stockPoolReadModelUpdatedAt"
      :updated-prefix="stockPoolReadModelUpdatedPrefix"
      :tags="stockPoolReadModelTags"
    />

    <section class="stats-row">
      <el-card v-for="stat in stockStats" :key="stat.label" class="stat-card">
        <div class="stat-content">
          <div class="stat-icon" :style="{ background: stat.color }">
            <el-icon size="24" color="white">
              <component :is="stat.icon" />
            </el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">{{ stat.label }}</div>
            <div class="stat-value">{{ stat.value }}</div>
          </div>
        </div>
      </el-card>
    </section>

    <section class="filter-panel">
      <div class="filter-group">
        <span class="filter-label">市场</span>
        <el-radio-group v-model="filterMarket" @change="handleFilterChange">
          <el-radio-button value="">全部市场</el-radio-button>
          <el-radio-button value="US">美股</el-radio-button>
          <el-radio-button value="CN">A股</el-radio-button>
          <el-radio-button value="HK">港股</el-radio-button>
        </el-radio-group>
      </div>
    
      <div class="filter-group">
        <span class="filter-label">类型</span>
        <el-radio-group v-model="filterType" @change="handleFilterChange">
          <el-radio-button value="">全部类型</el-radio-button>
          <el-radio-button value="stock">股票</el-radio-button>
          <el-radio-button value="etf">ETF</el-radio-button>
        </el-radio-group>
      </div>
    </section>
    
    <div class="market-status-strip" v-if="Object.keys(marketStatus).length">
      <div
        v-for="(status, market) in marketStatus"
        :key="market"
        class="market-status-pill"
        :class="getMarketStatusTone(status)"
      >
        <span>{{ market }}</span>
        <strong>{{ status.status_text }}</strong>
      </div>
    </div>
    
    <el-card class="table-card">
      <template #header>
        <div class="table-head">
          <div>
            <h3>全量标的列表</h3>
            <small class="table-meta">{{ realtimeQuoteMeta }}</small>
          </div>
          <el-tag size="large" effect="plain">{{ formatCount(total) }} 条</el-tag>
        </div>
      </template>

      <el-table
        :data="displayStocks"
        style="width: 100%"
        v-loading="loading"
      >
        <template #empty>
          <div class="table-empty-state">
            <strong>{{ stockPoolEmptyTitle }}</strong>
            <span v-if="stockPoolEmptyDescription">{{ stockPoolEmptyDescription }}</span>
          </div>
        </template>
        <el-table-column type="selection" width="55" />

        <el-table-column prop="symbol" label="代码" width="110">
          <template #default="{ row }">
            <button type="button" class="symbol-link" @click="viewSymbolDetail(row)">
              {{ row.symbol }}
            </button>
          </template>
          <template #header>
            <div class="column-filter">
              <el-input
                v-model="columnFilters.symbol"
                placeholder="代码"
                clearable
                @input="handleColumnFilter"
                style="width: 100px; font-size: 12px"
              >
                <template #prefix>
                  <el-icon>
                    <Search />
                  </el-icon>
                </template>
              </el-input>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="name" label="名称" min-width="170">
          <template #default="{ row }">
            <button type="button" class="name-link" @click="viewSymbolDetail(row)">
              {{ row.name }}
            </button>
          </template>
          <template #header>
            <div class="column-filter">
              <el-input
                v-model="columnFilters.name"
                placeholder="名称"
                clearable
                @input="handleColumnFilter"
                style="width: 120px; font-size: 12px"
              >
                <template #prefix>
                  <el-icon>
                    <Search />
                  </el-icon>
                </template>
              </el-input>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="market" label="市场" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="getMarketType(row.market)">
              {{ row.market }}
            </el-tag>
          </template>
          <template #header>
            <div class="column-filter">
              <el-select
                v-model="columnFilters.market"
                placeholder="市场"
                clearable
                @change="handleColumnFilter"
                style="width: 80px; font-size: 12px"
              >
                <el-option label="全部" value="" />
                <el-option label="美股" value="US" />
                <el-option label="A股" value="CN" />
                <el-option label="港股" value="HK" />
              </el-select>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.type === 'etf' ? 'warning' : 'info'">
              {{ row.type === 'etf' ? 'ETF' : '股票' }}
            </el-tag>
          </template>
          <template #header>
            <div class="column-filter">
              <el-select
                v-model="columnFilters.type"
                placeholder="类型"
                clearable
                @change="handleColumnFilter"
                style="width: 80px; font-size: 12px"
              >
                <el-option label="全部" value="" />
                <el-option label="股票" value="stock" />
                <el-option label="ETF" value="etf" />
              </el-select>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="price" label="当前价" width="130">
          <template #default="{ row }">
            <span v-if="row.price != null" class="price">
              {{ formatPrice(row.price, row.market) }}
            </span>
            <span v-else class="no-data">-</span>
          </template>
          <template #header>
            <div class="column-filter">
              <div style="display: flex; gap: 4px; font-size: 12px">
                <el-input
                  v-model.number="columnFilters.price_min"
                  placeholder="最小"
                  clearable
                  @input="handleColumnFilter"
                  style="width: 50px"
                >
                  <template #prefix>
                    <el-icon>
                      <Search />
                    </el-icon>
                  </template>
                </el-input>
                <span>-</span>
                <el-input
                  v-model.number="columnFilters.price_max"
                  placeholder="最大"
                  clearable
                  @input="handleColumnFilter"
                  style="width: 50px"
                >
                  <template #prefix>
                    <el-icon>
                      <Search />
                    </el-icon>
                  </template>
                </el-input>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="change_percent" label="涨跌幅" width="120">
          <template #default="{ row }">
            <span
              v-if="row.change_percent != null"
              class="change"
              :class="getChangeClass(row.change_percent)"
            >
              {{ formatChange(row.change_percent) }}
            </span>
            <span v-else class="no-data">-</span>
          </template>
          <template #header>
            <div class="column-filter">
              <el-input
                v-model="columnFilters.change_percent"
                placeholder="涨跌幅"
                clearable
                @input="handleColumnFilter"
                style="width: 80px; font-size: 12px"
              >
                <template #prefix>
                  <el-icon>
                    <Search />
                  </el-icon>
                </template>
              </el-input>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="volume" label="成交量" width="130">
          <template #default="{ row }">
            <span v-if="row.volume != null">{{ formatVolume(row.volume) }}</span>
            <span v-else class="no-data">-</span>
          </template>
          <template #header>
            <div class="column-filter">
              <div style="display: flex; gap: 4px; font-size: 12px">
                <el-input
                  v-model.number="columnFilters.volume_min"
                  placeholder="最小"
                  clearable
                  @input="handleColumnFilter"
                  style="width: 50px"
                >
                  <template #prefix>
                    <el-icon>
                      <Search />
                    </el-icon>
                  </template>
                </el-input>
                <span>-</span>
                <el-input
                  v-model.number="columnFilters.volume_max"
                  placeholder="最大"
                  clearable
                  @input="handleColumnFilter"
                  style="width: 50px"
                >
                  <template #prefix>
                    <el-icon>
                      <Search />
                    </el-icon>
                  </template>
                </el-input>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="market_cap" label="市值" width="130">
          <template #default="{ row }">
            <span v-if="row.market_cap != null">{{ formatMarketCap(row.market_cap) }}</span>
            <span v-else class="no-data">-</span>
          </template>
          <template #header>
            <div class="column-filter">
              <div style="display: flex; gap: 4px; font-size: 12px">
                <el-input
                  v-model.number="columnFilters.market_cap_min"
                  placeholder="最小"
                  clearable
                  @input="handleColumnFilter"
                  style="width: 50px"
                >
                  <template #prefix>
                    <el-icon>
                      <Search />
                    </el-icon>
                  </template>
                </el-input>
                <span>-</span>
                <el-input
                  v-model.number="columnFilters.market_cap_max"
                  placeholder="最大"
                  clearable
                  @input="handleColumnFilter"
                  style="width: 50px"
                >
                  <template #prefix>
                    <el-icon>
                      <Search />
                    </el-icon>
                  </template>
                </el-input>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="pe" label="PE" width="90">
          <template #default="{ row }">
            <span v-if="row.pe != null">{{ formatDecimal(row.pe) }}</span>
            <span v-else class="no-data">-</span>
          </template>
          <template #header>
            <div class="column-filter">
              <el-input
                v-model="columnFilters.pe"
                placeholder="PE"
                clearable
                @input="handleColumnFilter"
                style="width: 80px; font-size: 12px"
              >
                <template #prefix>
                  <el-icon>
                    <Search />
                  </el-icon>
                </template>
              </el-input>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="320" fixed="right" class-name="action-column">
          <template #default="{ row }">
            <div class="table-action-group">
              <el-button type="info" size="small" link @click="viewSymbolDetail(row)">
                详情
              </el-button>
              <el-button type="primary" size="small" link @click="analyzeStock(row)">
                AI研判
              </el-button>
              <el-button type="success" size="small" link @click="buyStock(row)">
                买入
              </el-button>
              <el-button
                size="small"
                class="watchlist-button"
                :class="{ 'is-added': isWatchlisted(row), 'is-pending': watchlistSubmittingSymbol === getWatchlistKey(row) }"
                :disabled="isWatchlisted(row) || watchlistSubmittingSymbol === getWatchlistKey(row)"
                @click="addToWatchlist(row)"
              >
                {{ isWatchlisted(row) ? '已自选' : watchlistSubmittingSymbol === getWatchlistKey(row) ? '添加中' : '自选' }}
              </el-button>
              <el-button type="danger" size="small" link @click="removeStock(row)">
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="addDialogVisible" title="添加股票" width="500px">
      <el-form :model="addForm" label-width="100px">
        <el-form-item label="股票代码">
          <el-input v-model="addForm.symbol" placeholder="输入股票代码" />
        </el-form-item>
        <el-form-item label="市场">
          <el-radio-group v-model="addForm.market">
            <el-radio-button value="US">美股</el-radio-button>
            <el-radio-button value="CN">A股</el-radio-button>
            <el-radio-button value="HK">港股</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="addForm.type">
            <el-radio-button value="stock">股票</el-radio-button>
            <el-radio-button value="etf">ETF</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAdd">确定</el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="detailDialogVisible"
      :title="`${currentStock.name || ''} (${currentStock.symbol || ''})`"
      direction="rtl"
      size="78%"
      destroy-on-close
    >
      <SymbolDetail v-if="currentStock.symbol" :symbol="currentStock.symbol" />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Collection,
  DataLine,
  Money,
  OfficeBuilding,
  Plus,
  Refresh,
  Search,
  TrendCharts
} from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { addStockToPool, addWatchlistStock, getMarketStatus, getStockPool, getStockQuotes, removeStockFromPool, syncMarketUniverse } from '../api/market.js'
import { useStockQuotes } from '../composables/useWebSocket.js'
import { getCurrentUser, isAdmin } from '../utils/auth.js'
import { formatCurrency, formatDecimal, formatPercent } from '../utils/formatters.js'
import { summarizeQuoteSnapshotCoverage } from '../utils/quoteSnapshot.js'
import { buildStockPoolReadModelSummary, formatQuoteCoverageLabel, formatQuoteCoverageMeta, formatQuoteSnapshotTimeLabel } from '../utils/readModelSource.js'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import SymbolDetail from './SymbolDetail.vue'

const router = useRouter()
const currentUser = getCurrentUser() || {}
const loading = ref(false)
const hasLoadedStocks = ref(false)
const stocks = ref([])
const stockPoolMeta = ref({})
const stockPoolStats = ref({
  total: 0,
  stocks: 0,
  etfs: 0,
  markets: { US: 0, CN: 0, HK: 0 }
})
const searchKeyword = ref('')
const filterMarket = ref('')
const filterType = ref('')
const currentPage = ref(1)
const pageSize = ref(10)
// Selected symbols for real-time subscription
const marketStatus = ref({})
const total = ref(0)
const STOCK_POOL_SEARCH_DELAY_MS = 260
const MARKET_STATUS_REFRESH_MS = 60000
let stockSearchTimer = null
let latestStockRequestId = 0
const watchlistOverrides = ref({})
const watchlistSubmittingSymbol = ref('')
const pulledQuoteMap = ref({})

const hasValue = (value) => !(value === '' || value === null || value === undefined)
const toNumberOrNull = (value) => {
  if (!hasValue(value)) {
    return null
  }

  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

// Load market status (open/closed) for each market
const loadMarketStatus = async () => {
  try {
    const res = await getMarketStatus()
    marketStatus.value = res?.data || {}
  } catch (error) {
    console.warn('获取市场状态失败:', error)
    marketStatus.value = {}
  }
}

const addDialogVisible = ref(false)
const syncing = ref(false)
const canSync = isAdmin()
const addForm = ref({
  symbol: '',
  market: 'US',
  type: 'stock'
})
const columnFilters = ref({
  symbol: '',
  name: '',
  market: '',
  type: '',
  price_min: '',
  price_max: '',
  change_percent: '',
  volume_min: '',
  volume_max: '',
  market_cap_min: '',
  market_cap_max: '',
  pe: ''
})
const detailDialogVisible = ref(false)
const currentStock = ref({})
const streamSymbols = computed(() => stocks.value.map((item) => String(item.symbol || '').trim().toUpperCase()).filter(Boolean))
const { quotes: liveQuoteMap, isConnected: quotesConnected } = useStockQuotes(streamSymbols, {
  userId: currentUser?.id || null
})

const formatCount = (value) => Number(value || 0).toLocaleString('zh-CN')
const formatDateTime = (value) => {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN')
}

const marketCounts = computed(() => {
  const markets = stockPoolStats.value?.markets || {}
  return {
    US: Number(markets.US || 0),
    CN: Number(markets.CN || 0),
    HK: Number(markets.HK || 0)
  }
})

const totalUniverse = computed(() => Number(stockPoolStats.value?.total || total.value || 0))
const etfUniverse = computed(() => Number(stockPoolStats.value?.etfs || 0))
const stockUniverse = computed(() => Number(stockPoolStats.value?.stocks || Math.max(totalUniverse.value - etfUniverse.value, 0)))
const realtimeQuoteCoverage = computed(() => summarizeQuoteSnapshotCoverage(displayStocks.value))
const effectiveMarketFilter = computed(() => columnFilters.value.market || filterMarket.value || '')
const effectiveTypeFilter = computed(() => columnFilters.value.type || filterType.value || '')

const stockStats = computed(() => [
  { label: '股票总数', value: formatCount(totalUniverse.value), icon: Collection, color: '#409eff' },
  { label: '美股', value: formatCount(marketCounts.value.US), icon: Money, color: '#67c23a' },
  { label: 'A股', value: formatCount(marketCounts.value.CN), icon: TrendCharts, color: '#e6a23c' },
  { label: '港股', value: formatCount(marketCounts.value.HK), icon: OfficeBuilding, color: '#f56c6c' }
])

const hasColumnFilters = computed(() => Object.values(columnFilters.value).some((value) => hasValue(value)))
const queryResultTotal = computed(() => Number(stockPoolStats.value?.filtered_total || total.value || 0))
const realtimeQuoteCoverageTag = computed(() => formatQuoteCoverageLabel(realtimeQuoteCoverage.value, {
  prefix: '长桥实时',
  emptyLabel: '等待长桥实时'
}))
const realtimeQuoteTimeTag = computed(() => formatQuoteSnapshotTimeLabel(realtimeQuoteCoverage.value.latestSnapshotAt, formatDateTime, {
  prefix: '长桥实时',
  emptyLabel: '等待实时行情'
}))
const realtimeQuoteMeta = computed(() => formatQuoteCoverageMeta(realtimeQuoteCoverage.value, formatDateTime, {
  prefix: '长桥实时',
  pendingText: '等待长桥实时行情'
}))
const getWatchlistKey = (row = {}) => [
  String(row.symbol || '').trim().toUpperCase(),
  String(row.market || '').trim().toUpperCase(),
  String(row.type || 'stock').trim().toLowerCase()
].join(':')
const isWatchlisted = (row = {}) => {
  const key = getWatchlistKey(row)
  if (Object.prototype.hasOwnProperty.call(watchlistOverrides.value, key)) {
    return Boolean(watchlistOverrides.value[key])
  }
  return Boolean(row.isWatchlisted ?? row.is_watchlisted)
}

const displayStocks = computed(() => {
  return stocks.value.map((item) => {
    const symbol = String(item.symbol || '').trim().toUpperCase()
    const quote = liveQuoteMap.value[symbol] || pulledQuoteMap.value[symbol] || {}
    const livePrice = Number(quote.last_price ?? quote.price ?? item.price ?? 0)
    const liveChangePercent = quote.change_percent ?? quote.changePercent ?? item.change_percent
    const liveVolume = quote.volume ?? item.volume
    const quoteTimestamp = quote.quoteSnapshotAt || quote.quote_snapshot_at || quote.timestamp || quote.updatedAt || item.quoteSnapshotAt || item.quote_snapshot_at || ''
    const quoteSource = quote.quoteSource || quote.quote_source || item.quoteSource || item.quote_source || ''
    const watchlistKey = getWatchlistKey(item)
    const localWatchlistState = watchlistOverrides.value[watchlistKey]
    const watchlisted = localWatchlistState ?? Boolean(item.isWatchlisted ?? item.is_watchlisted)

    return {
      ...item,
      price: Number.isFinite(livePrice) && livePrice > 0 ? livePrice : item.price,
      change_percent: liveChangePercent === null || liveChangePercent === undefined || liveChangePercent === ''
        ? item.change_percent
        : Number(liveChangePercent),
      volume: liveVolume === null || liveVolume === undefined || liveVolume === '' ? item.volume : Number(liveVolume),
      quoteSource,
      quote_source: quoteSource,
      quoteSnapshotAt: quoteTimestamp || null,
      quote_snapshot_at: quoteTimestamp || null,
      quoteReady: Boolean(livePrice || quoteTimestamp),
      isWatchlisted: watchlisted,
      is_watchlisted: watchlisted
    }
  })
})

const stockPoolReadModelSummary = computed(() => buildStockPoolReadModelSummary(
  stockPoolMeta.value,
  {
    count: displayStocks.value.length,
    total: queryResultTotal.value,
    marketLabel: effectiveMarketFilter.value ? ({
      US: '美股',
      CN: 'A股',
      HK: '港股'
    }[effectiveMarketFilter.value] || effectiveMarketFilter.value) : '全部市场',
    quoteCoverageLabel: realtimeQuoteCoverage.value.readyCount
      ? `长桥实时 ${realtimeQuoteCoverage.value.readyCount}/${realtimeQuoteCoverage.value.totalCount || 0}`
      : '长桥实时待补齐'
  }
))
const stockPoolReadModelStatus = computed(() => {
  if (quotesConnected.value && displayStocks.value.length) {
    return '行情在线'
  }
  return stockPoolReadModelSummary.value.statusText
})
const stockPoolReadModelStatusType = computed(() => (
  quotesConnected.value && displayStocks.value.length ? 'success' : stockPoolReadModelSummary.value.statusType
))
const stockPoolReadModelUpdatedAt = computed(() => (
  (realtimeQuoteCoverage.value.latestSnapshotAt || stockPoolReadModelSummary.value.updatedAt)
    ? formatDateTime(realtimeQuoteCoverage.value.latestSnapshotAt || stockPoolReadModelSummary.value.updatedAt)
    : ''
))
const stockPoolReadModelUpdatedPrefix = computed(() => (
  '更新于'
))
const stockPoolReadModelTags = computed(() => ([
  ...(stockPoolReadModelSummary.value.tags || []),
  {
    text: quotesConnected.value ? `长桥推送 ${streamSymbols.value.length} 个` : '长桥实时拉取',
    type: quotesConnected.value ? 'success' : 'info'
  }
]))

const dominantMarket = computed(() => {
  const entries = [
    { key: 'US', label: '美股', count: marketCounts.value.US },
    { key: 'CN', label: 'A股', count: marketCounts.value.CN },
    { key: 'HK', label: '港股', count: marketCounts.value.HK }
  ]
  return entries.sort((a, b) => b.count - a.count)[0] || { key: 'US', label: '美股', count: 0 }
})

const activeFilterLabel = computed(() => {
  const marketText = effectiveMarketFilter.value ? {
    US: '美股',
    CN: 'A股',
    HK: '港股'
  }[effectiveMarketFilter.value] : '全部市场'
  const typeText = effectiveTypeFilter.value === 'stock' ? '股票' : effectiveTypeFilter.value === 'etf' ? 'ETF' : '全部类型'
  return `${marketText} / ${typeText}`
})

const filteredSummary = computed(() => {
  if (loading.value && !hasLoadedStocks.value) {
    return '股票底库加载中'
  }

  if (!hasLoadedStocks.value) {
    return '等待股票底库'
  }

  if (!queryResultTotal.value && !displayStocks.value.length) {
    return '当前筛选暂无结果'
  }

  if (hasColumnFilters.value) {
    return `当前页 ${formatCount(displayStocks.value.length)} 条，查询结果共 ${formatCount(queryResultTotal.value)} 条`
  }

  const start = Math.max(1, (currentPage.value - 1) * pageSize.value + 1)
  const end = Math.min(queryResultTotal.value, start + stocks.value.length - 1)
  return `当前页 ${start}-${end} / 共 ${formatCount(queryResultTotal.value)} 条`
})

const universeInsights = computed(() => [
  {
    label: '标的总数',
    value: `${formatCount(totalUniverse.value)} 标的`,
    note: `股票 ${formatCount(stockUniverse.value)} / ETF ${formatCount(etfUniverse.value)}`
  },
  {
    label: '当前焦点市场',
    value: dominantMarket.value.label,
    note: `${formatCount(dominantMarket.value.count)} 只`
  },
  {
    label: '筛选结果',
    value: `${formatCount(displayStocks.value.length)} / ${formatCount(total.value)}`,
    note: activeFilterLabel.value
  }
])

const stockPoolEmptyTitle = computed(() => {
  if (loading.value && !stocks.value.length) return '股票底库加载中'
  if (!hasLoadedStocks.value) return '等待股票底库'
  if (searchKeyword.value || filterMarket.value || filterType.value || hasColumnFilters.value) return '当前筛选没有命中标的'
  return '股票底库暂时为空'
})
const stockPoolEmptyDescription = computed(() => {
  if (loading.value && !stocks.value.length) return ''
  if (!hasLoadedStocks.value) return ''
  if (searchKeyword.value || filterMarket.value || filterType.value || hasColumnFilters.value) return '可以调整筛选条件后再试。'
  return canSync ? '可以点击全量同步拉取市场底库。' : '可以稍后刷新，或联系管理员同步市场底库。'
})

const buildStockPoolParams = () => ({
  market: columnFilters.value.market || filterMarket.value || 'all',
  type: columnFilters.value.type || filterType.value || '',
  search: searchKeyword.value,
  page: currentPage.value,
  page_size: pageSize.value,
  columnFilters: {
    symbol: columnFilters.value.symbol,
    name: columnFilters.value.name,
    price_min: toNumberOrNull(columnFilters.value.price_min),
    price_max: toNumberOrNull(columnFilters.value.price_max),
    change_percent: toNumberOrNull(columnFilters.value.change_percent),
    volume_min: toNumberOrNull(columnFilters.value.volume_min),
    volume_max: toNumberOrNull(columnFilters.value.volume_max),
    market_cap_min: toNumberOrNull(columnFilters.value.market_cap_min),
    market_cap_max: toNumberOrNull(columnFilters.value.market_cap_max),
    pe: toNumberOrNull(columnFilters.value.pe)
  }
})

const loadRealtimeQuotes = async (items = [], requestId = latestStockRequestId) => {
  const symbols = Array.from(new Set(
    (Array.isArray(items) ? items : [])
      .map((item) => String(item.symbol || '').trim().toUpperCase())
      .filter(Boolean)
  ))
  if (!symbols.length) {
    pulledQuoteMap.value = {}
    return
  }

  try {
    const quoteRes = await getStockQuotes(symbols)
    if (requestId !== latestStockRequestId) {
      return
    }
    pulledQuoteMap.value = Object.fromEntries(
      (Array.isArray(quoteRes?.data) ? quoteRes.data : [])
        .map((quote) => [String(quote?.symbol || '').trim().toUpperCase(), quote])
        .filter(([symbol]) => Boolean(symbol))
    )
  } catch (error) {
    if (requestId === latestStockRequestId) {
      pulledQuoteMap.value = {}
    }
    console.warn('长桥实时行情拉取失败:', error)
  }
}

const loadStocks = async () => {
  const requestId = ++latestStockRequestId
  loading.value = true
  try {
    const res = await getStockPool(buildStockPoolParams())
    if (requestId !== latestStockRequestId) {
      return
    }
    stockPoolMeta.value = res?.meta && typeof res.meta === 'object' ? res.meta : {}
    stocks.value = res.data || []
    await loadRealtimeQuotes(stocks.value, requestId)
    total.value = Number((res?.filteredTotal ?? res?.total) || 0)
    hasLoadedStocks.value = true
    stockPoolStats.value = {
      ...stockPoolStats.value,
      ...(res?.stats || {}),
      filtered_total: Number((res?.stats?.filtered_total ?? res?.filteredTotal ?? res?.total) || 0)
    }
  } catch (error) {
    if (requestId !== latestStockRequestId) {
      return
    }
    stockPoolMeta.value = {}
    hasLoadedStocks.value = true
    console.error('加载股票池失败:', error)
    ElMessage.error('加载股票池失败')
  } finally {
    if (requestId === latestStockRequestId) {
      loading.value = false
    }
  }
}

const scheduleLoadStocks = () => {
  if (stockSearchTimer) {
    window.clearTimeout(stockSearchTimer)
  }
  stockSearchTimer = window.setTimeout(() => {
    stockSearchTimer = null
    loadStocks()
  }, STOCK_POOL_SEARCH_DELAY_MS)
}

const handleSearch = () => {
  currentPage.value = 1
  scheduleLoadStocks()
}

const handleFilterChange = () => {
  currentPage.value = 1
  scheduleLoadStocks()
}

const handleColumnFilter = () => {
  currentPage.value = 1
  scheduleLoadStocks()
}

const showAddDialog = () => {
  addForm.value = { symbol: '', market: 'US', type: 'stock' }
  addDialogVisible.value = true
}

const confirmAdd = async () => {
  try {
    await addStockToPool(addForm.value)
    ElMessage.success('添加成功')
    addDialogVisible.value = false
    loadStocks()
  } catch (error) {
    ElMessage.error('添加失败: ' + error.message)
  }
}

const removeStock = async (row) => {
  try {
    await ElMessageBox.confirm(`确定要从股票池中删除 ${row.symbol} 吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })

    await removeStockFromPool(row.symbol, row.market, row.type)
    ElMessage.success('删除成功')
    loadStocks()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败: ' + error.message)
    }
  }
}

const addToWatchlist = async (row) => {
  const watchlistKey = getWatchlistKey(row)
  watchlistSubmittingSymbol.value = watchlistKey
  try {
    await addWatchlistStock({
      symbol: row.symbol,
      name: row.name,
      market: row.market,
      type: row.type || 'stock'
    })
    watchlistOverrides.value = {
      ...watchlistOverrides.value,
      [watchlistKey]: true
    }
    stocks.value = stocks.value.map((item) => (
      getWatchlistKey(item) === watchlistKey
        ? { ...item, isWatchlisted: true, is_watchlisted: true }
        : item
    ))
    ElMessage.success(`${row.symbol} 已加入自选`)
  } catch (error) {
    const message = error?.data?.detail || error?.data?.message || error.message || '添加自选失败'
    ElMessage.error(String(message).split('\n')[0].slice(0, 120))
  } finally {
    if (watchlistSubmittingSymbol.value === watchlistKey) {
      watchlistSubmittingSymbol.value = ''
    }
  }
}

const analyzeStock = (row) => {
  router.push({
    name: 'AIAnalysis',
    query: { symbol: row.symbol, market: row.market }
  })
}

const viewSymbolDetail = (row) => {
  currentStock.value = { ...row }
  detailDialogVisible.value = true
}

const buyStock = (row) => {
  router.push({
    name: 'Trading',
    query: { symbol: row.symbol, action: 'buy' }
  })
}

const refreshData = () => {
  loadStocks()
}

const syncUniverse = async () => {
  try {
    await ElMessageBox.confirm('将同步美股、港股和 A 股全量基础行情，这可能需要几分钟。', '全量同步', {
      confirmButtonText: '开始同步',
      cancelButtonText: '取消',
      type: 'warning'
    })

    syncing.value = true
    const res = await syncMarketUniverse({ markets: ['US', 'HK', 'CN'] })
    const summary = Object.entries(res?.data?.markets || {})
      .map(([market, result]) => {
        const warningText = result?.warnings?.length ? '，有降级' : ''
        const saved = Number(result?.saved || 0)
        const reused = Number(result?.reused || 0)
        const countText = saved > 0 ? `写入 ${saved}` : `可用 ${reused || result?.available || 0}`
        return `${market}: ${countText}${warningText}`
      })
      .join(' / ')
    const warningCount = Number(res?.data?.warning_count || 0)

    if (warningCount > 0) {
      ElMessage.warning(summary ? `同步完成，写入 ${summary}` : '同步完成，部分数据源已降级')
    } else {
      ElMessage.success(summary ? `同步完成，写入 ${summary}` : '市场数据同步完成')
    }
    loadStocks()
  } catch (error) {
    if (error !== 'cancel') {
      const message = error?.data?.error || error?.data?.message || error.message || '同步失败'
      ElMessage.error(String(message).split('\n')[0].slice(0, 120))
    }
  } finally {
    syncing.value = false
  }
}

const handleSizeChange = (value) => {
  pageSize.value = value
  loadStocks()
}

const handleCurrentChange = (value) => {
  currentPage.value = value
  loadStocks()
}

const getMarketType = (market) => {
  const types = { US: 'primary', CN: 'success', HK: 'warning' }
  return types[market] || 'info'
}

const getChangeClass = (change) => {
  if (change > 0) return 'up'
  if (change < 0) return 'down'
  return 'flat'
}

const getMarketStatusTone = (status = {}) => {
  const tone = String(status?.status || '').toLowerCase()
  if (tone === 'open') return 'is-open'
  if (tone === 'pre' || tone === 'post' || tone === 'night') return 'is-session'
  return 'is-closed'
}

const formatChange = (change) => formatPercent(change || 0)

const formatPrice = (price, market) => {
  const currency = market === 'CN' ? '¥' : market === 'HK' ? 'HK$' : '$'
  return formatCurrency(price, { currency })
}

const formatVolume = (volume) => {
  const amount = Number(volume || 0)
  if (amount >= 1000000) return `${(amount / 1000000).toFixed(2)}M`
  if (amount >= 1000) return `${(amount / 1000).toFixed(2)}K`
  return amount.toLocaleString('zh-CN')
}

const formatMarketCap = (cap) => {
  const amount = Number(cap || 0)
  if (amount >= 1000000000000) return `${(amount / 1000000000000).toFixed(2)}T`
  if (amount >= 1000000000) return `${(amount / 1000000000).toFixed(2)}B`
  if (amount >= 1000000) return `${(amount / 1000000).toFixed(2)}M`
  return amount.toLocaleString('zh-CN')
}

let marketStatusTimer = null
const startMarketStatusTimer = () => {
  if (marketStatusTimer) {
    return
  }
  marketStatusTimer = window.setInterval(() => {
    if (document.visibilityState === 'visible') {
      loadMarketStatus()
    }
  }, MARKET_STATUS_REFRESH_MS)
}

const stopMarketStatusTimer = () => {
  if (marketStatusTimer) {
    window.clearInterval(marketStatusTimer)
    marketStatusTimer = null
  }
}

const handleVisibilityChange = () => {
  if (document.visibilityState === 'visible') {
    loadMarketStatus()
    startMarketStatusTimer()
    return
  }

  stopMarketStatusTimer()
}

onMounted(() => {
  loadStocks()
  loadMarketStatus()
  document.addEventListener('visibilitychange', handleVisibilityChange)
  startMarketStatusTimer()
})

onUnmounted(() => {
  if (stockSearchTimer) {
    window.clearTimeout(stockSearchTimer)
    stockSearchTimer = null
  }
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  stopMarketStatusTimer()
})
</script>

<style scoped lang="scss">
.stock-pool-page {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
}

.hero-panel,
.filter-panel,
.table-card {
  border: 1px solid var(--panel-edge);
  background: var(--panel-surface);
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.hero-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 430px);
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  min-height: 0;
}

.hero-kicker,
.filter-label,
.table-kicker,
.insight-card span {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.hero-copy h2,
.table-head h3 {
  margin: 10px 0 8px;
  color: var(--text-primary);
}

.hero-copy p,
.table-head p,
.insight-card p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.hero-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.hero-tag {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 6px;
  border: 1px solid var(--control-border);
  background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
  color: var(--text-secondary);
  font-size: 11px;
}

.hero-actions {
  display: flex;
  flex-direction: column;
  gap: 14px;
  justify-content: center;
}

.search-input {
  width: 100%;
}

.action-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-primary-button {
  font-weight: 600;
}

.hero-secondary-button {
  color: var(--text-primary);
  border-color: var(--control-border);
  background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
}

.insight-strip,
.stats-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.insight-card,
.stat-card {
  border: 1px solid var(--panel-edge);
  background: var(--panel-surface);
  box-shadow: var(--shadow-soft), var(--panel-inset);
}

.insight-card {
  padding: 8px 10px;
  border-radius: 8px;
}

.insight-card strong {
  display: block;
  margin-top: 4px;
  color: var(--text-primary);
  font-size: 14px;
}

.stats-row {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.stat-content {
  display: flex;
  align-items: center;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 12px;
}

.stat-label {
  font-size: 14px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.filter-panel {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  border-radius: 10px;
}

.filter-group {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.market-status-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.market-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 0 16px;
  border-radius: 999px;
  border: 1px solid var(--panel-edge);
  background: var(--panel-surface);
  box-shadow: var(--shadow-soft), var(--panel-inset);

  span {
    font-size: 12px;
    color: var(--text-muted);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  strong {
    color: var(--text-primary);
    font-size: 14px;
  }

  &.is-open {
    border-color: color-mix(in srgb, var(--success) 42%, var(--panel-edge));

    strong {
      color: var(--success);
    }
  }

  &.is-session {
    border-color: color-mix(in srgb, var(--warning) 46%, var(--panel-edge));

    strong {
      color: var(--warning);
    }
  }

  &.is-closed {
    border-color: color-mix(in srgb, var(--text-muted) 35%, var(--panel-edge));
  }
}

.table-card {
  border-radius: 10px;
}

.table-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.table-meta {
  display: block;
  margin-top: 6px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.symbol-link,
.name-link {
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  font: inherit;
}

.symbol-link {
  font-weight: 700;
  color: var(--accent-strong);
}

.name-link {
  color: var(--text-primary);
  text-align: left;
}

.price {
  font-weight: 600;
  color: var(--text-primary);
}

.change {
  font-weight: 600;
}

.change.up {
  color: var(--success);
}

.change.down {
  color: var(--danger);
}

.change.flat,
.no-data {
  color: var(--text-muted);
}

.pagination {
  margin-top: 8px;
  display: flex;
  justify-content: flex-end;
}

.table-action-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
}

.watchlist-button {
  min-width: 74px;
  border-color: color-mix(in srgb, var(--accent-strong) 56%, var(--control-border));
  color: var(--accent-strong);
  background: color-mix(in srgb, var(--accent-strong) 10%, var(--panel-surface));
  font-weight: 600;
}

.watchlist-button:hover:not(:disabled),
.watchlist-button:focus-visible:not(:disabled) {
  border-color: var(--accent-strong);
  color: var(--accent-strong);
  background: color-mix(in srgb, var(--accent-strong) 16%, var(--panel-surface));
}

.watchlist-button.is-added,
.watchlist-button:disabled {
  border-color: color-mix(in srgb, var(--success) 40%, var(--control-border));
  color: var(--success);
  background: color-mix(in srgb, var(--success) 12%, var(--panel-surface));
  opacity: 1;
}

.watchlist-button.is-pending {
  border-color: color-mix(in srgb, var(--warning) 48%, var(--control-border));
  color: var(--warning);
}

.table-empty-state {
  min-height: 120px;
  display: grid;
  place-items: center;
  gap: 8px;
  padding: 16px 10px;
  text-align: center;

  strong {
    color: var(--text-primary);
    font-size: 16px;
  }

  span {
    max-width: 420px;
    color: var(--text-secondary);
    line-height: 1.7;
    font-size: 13px;
  }
}

.table-card :deep(.el-table),
.table-card :deep(.el-table__expanded-cell) {
  background: transparent !important;
}

.table-card :deep(.el-table__empty-block) {
  min-height: 220px;
}

.table-card :deep(.el-table th.el-table__cell) {
  background: color-mix(in srgb, var(--surface-muted) 84%, transparent) !important;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--table-divider);
}

.table-card :deep(.el-table td.el-table__cell) {
  border-bottom: 1px solid var(--table-divider);
}

.table-card :deep(.el-button.is-disabled),
.table-card :deep(.el-button.is-disabled:hover) {
  opacity: 0.72;
}

.table-card :deep(.action-column .cell) {
  overflow: visible;
}

.table-card :deep(.el-table__inner-wrapper::before) {
  background-color: transparent;
}

@media (max-width: 1180px) {
  .hero-panel,
  .insight-strip,
  .stats-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .stock-pool-page {
    padding: 8px;
  }

  .market-status-pill {
    width: 100%;
    justify-content: space-between;
  }

  .table-head,
  .filter-panel {
    flex-direction: column;
    align-items: flex-start;
  }

  .pagination {
    justify-content: flex-start;
  }
}
</style>

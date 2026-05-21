<template>
  <div class="watchlist-pool-page">
    <section class="hero-panel">
      <div class="hero-copy">
        <div class="eyebrow">Watchlist Workspace</div>
        <h2>自选股票池</h2>
        <div class="hero-tags">
          <span class="hero-tag">{{ `${formatCount(filteredWatchlist.length)} / ${formatCount(watchlist.length)} 标的` }}</span>
          <span class="hero-tag">{{ `${activeSessionLabel}目标 ${formatCount(activeSessionTargetCount)}` }}</span>
          <span class="hero-tag">{{ `市场分组 ${formatCount(groupedWatchlist.length)}` }}</span>
          <span class="hero-tag">{{ realtimeQuoteTag }}</span>
          <span class="hero-tag">{{ scanTargetUpdatedAt ? `目标更新 ${formatDateTime(scanTargetUpdatedAt)}` : '等待扫描目标' }}</span>
        </div>
      </div>

      <div class="hero-actions">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索代码或名称"
          :prefix-icon="Search"
          clearable
          class="search-input"
        />
        <div class="action-row">
          <el-select v-model="marketFilter" placeholder="全部市场" clearable class="filter-select">
            <el-option label="美股" value="US" />
            <el-option label="港股" value="HK" />
            <el-option label="A股" value="CN" />
            <el-option label="新加坡" value="SG" />
          </el-select>
          <el-select v-model="typeFilter" placeholder="全部类型" clearable class="filter-select">
            <el-option label="股票" value="stock" />
            <el-option label="ETF" value="etf" />
            <el-option label="基金" value="fund" />
          </el-select>
          <el-radio-group v-model="activeSession" class="session-switch" size="small">
            <el-radio-button label="开盘前" value="pre_market" />
            <el-radio-button label="收盘后" value="after_market" />
          </el-radio-group>
          <el-button :icon="Refresh" :loading="loadingWatchlist || loadingTargets" @click="refreshAll">
            刷新
          </el-button>
        </div>
      </div>
    </section>

    <section class="stats-row">
      <el-card v-for="stat in stats" :key="stat.label" class="stat-card">
        <div class="stat-content">
          <div class="stat-icon" :style="{ background: stat.color }">
            <el-icon size="18">
              <component :is="stat.icon" />
            </el-icon>
          </div>
          <div class="stat-copy">
            <span>{{ stat.label }}</span>
            <strong>{{ stat.value }}</strong>
            <small>{{ stat.note }}</small>
          </div>
        </div>
      </el-card>
    </section>

    <el-card class="panel-card ledger-card">
      <template #header>
        <div class="panel-head">
          <div>
            <span class="panel-kicker">Watchlist Ledger</span>
            <h3>自选标的台账</h3>
          </div>
          <div class="target-head-meta">
            <el-tag effect="plain" size="large">{{ formatCount(filteredWatchlist.length) }} 条</el-tag>
            <el-button text :icon="Refresh" :loading="loadingTargets" @click="loadScanTargets(activeSession)">
              刷新扫描目标
            </el-button>
          </div>
        </div>
      </template>

      <div class="target-summary">
        <span>{{ targetSummaryText }}</span>
        <span>{{ scanTargetUpdatedAt ? `更新时间 ${formatDateTime(scanTargetUpdatedAt)}` : '尚未返回扫描目标' }}</span>
      </div>

      <el-table
        :data="watchlistLedgerRows"
        v-loading="loadingWatchlist"
        style="width: 100%"
        class="ledger-table"
      >
        <template #empty>
          <div class="panel-empty table-empty">
            <strong>当前没有符合条件的自选标的</strong>
            <span>从股票池添加自选后，这里会按台账展示扫描开关、目标数和最新扫描结果入口。</span>
          </div>
        </template>
        <el-table-column prop="symbol" label="代码" width="122">
          <template #default="{ row }">
            <button type="button" class="symbol-link" @click="openScanResult(row)">
              {{ row.symbol }}
            </button>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="market" label="市场" width="92">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ marketLabel(row.market) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="92">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="长桥实时行情" min-width="230">
          <template #default="{ row }">
            <div class="quote-stack">
              <strong>{{ formatQuotePrice(row.realtimePrice) }}</strong>
              <span>{{ `盘前 ${formatQuotePrice(row.preMarketPrice)} / 盘后 ${formatQuotePrice(row.postMarketPrice)}` }}</span>
              <small>{{ `夜盘 ${formatQuotePrice(row.overnightPrice)} · ${row.quoteTimeLabel}` }}</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="添加时间" min-width="150">
          <template #default="{ row }">{{ formatDateTime(row.addedAt) }}</template>
        </el-table-column>
        <el-table-column label="扫描目标" width="140">
          <template #default="{ row }">
            <div class="scan-count-stack">
              <strong>{{ formatCount(row.scanTargetCount) }}</strong>
              <span>{{ `开盘前 ${formatCount(row.sessionCounts.pre_market)} / 收盘后 ${formatCount(row.sessionCounts.after_market)}` }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="最新扫描" min-width="150">
          <template #default="{ row }">{{ formatDateTime(row.lastScanAt) }}</template>
        </el-table-column>
        <el-table-column label="开盘前" width="96" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.preMarketEnabled"
              :loading="isRowPending(row.key, 'pre_market')"
              @change="toggleScan(row, 'pre_market', $event)"
            />
          </template>
        </el-table-column>
        <el-table-column label="收盘后" width="96" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.afterMarketEnabled"
              :loading="isRowPending(row.key, 'after_market')"
              @change="toggleScan(row, 'after_market', $event)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <div class="table-action-group">
              <el-button size="small" type="primary" link @click="openScanResult(row)">扫描结果</el-button>
              <el-button size="small" type="info" link @click="openAIAnalysis(row)">AI研判</el-button>
              <el-button
                size="small"
                type="danger"
                link
                :loading="isRowRemoving(row.key)"
                @click="removeItem(row)"
              >
                移除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="panel-card targets-ledger-card">
      <template #header>
        <div class="panel-head">
          <div>
            <span class="panel-kicker">Session Targets</span>
            <h3>{{ `${activeSessionLabel}扫描目标` }}</h3>
          </div>
          <el-tag effect="plain" size="large">{{ formatCount(activeSessionTargetCount) }} 个</el-tag>
        </div>
      </template>

      <el-table :data="scanTargets" v-loading="loadingTargets" style="width: 100%">
        <template #empty>
          <div class="panel-empty table-empty">
            <strong>{{ activeSessionLabel }}暂无扫描目标</strong>
            <span>{{ scanTargetError || '启用对应扫描开关后，这里会展示按 session 生成的扫描标的。' }}</span>
          </div>
        </template>
        <el-table-column prop="symbol" label="代码" width="122">
          <template #default="{ row }">
            <button type="button" class="symbol-link" @click="openScanResult(row)">
              {{ row.symbol }}
            </button>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column prop="market" label="市场" width="92">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ marketLabel(row.market) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="92">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="130">
          <template #default="{ row }">{{ row.source || '--' }}</template>
        </el-table-column>
        <el-table-column prop="score" label="评分" width="96">
          <template #default="{ row }">{{ formatScore(row.score) }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="说明" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.reason || '--' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openScanResult(row)">查看结果</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Collection,
  DataLine,
  Refresh,
  Search,
  Star,
  Timer
} from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { request } from '../utils/requestPure.js'

const MARKET_API_BASE = '/svc/market/api/v1/market'
const router = useRouter()
const SESSION_FIELD_MAP = {
  pre_market: 'pre_market_enabled',
  after_market: 'after_market_enabled'
}
const SESSION_LABEL_MAP = {
  pre_market: '开盘前',
  after_market: '收盘后'
}
const MARKET_LABEL_MAP = {
  US: '美股',
  HK: '港股',
  CN: 'A股',
  SG: '新加坡'
}
const TYPE_LABEL_MAP = {
  stock: '股票',
  etf: 'ETF',
  fund: '基金'
}
const MARKET_SORT_ORDER = ['US', 'HK', 'CN', 'SG']
const TYPE_SORT_ORDER = ['stock', 'etf', 'fund']
const SESSION_API_VALUE_MAP = {
  pre_market: 'before_open',
  after_market: 'after_close'
}

const watchlist = ref([])
const scanTargets = ref([])
const loadingWatchlist = ref(false)
const loadingTargets = ref(false)
const loadingRealtimeQuotes = ref(false)
const searchKeyword = ref('')
const marketFilter = ref('')
const typeFilter = ref('')
const activeSession = ref('pre_market')
const scanTargetUpdatedAt = ref('')
const scanTargetError = ref('')
const pendingToggleMap = ref({})
const pendingRemoveMap = ref({})
const realtimeQuoteMap = ref({})
let marketApiModulePromise = null
let isAlive = true

const isFetchAbortLikeError = (error) => {
  const message = String(error?.message || '')
  return message.includes('Failed to fetch') || error?.name === 'AbortError'
}

const fallbackGetWatchlist = (params = {}) => request.get(`${MARKET_API_BASE}/watchlist`, params)
const fallbackUpdateWatchlist = (payload = {}) => request.put(
  `${MARKET_API_BASE}/watchlist/${encodeURIComponent(payload?.symbol || '')}`,
  {
    ...payload,
    scan_before_open: payload?.scan_before_open ?? payload?.pre_market_enabled,
    scan_after_close: payload?.scan_after_close ?? payload?.after_market_enabled
  }
)
const fallbackRemoveWatchlist = (symbol, market, type = 'stock') => request.delete(
  `${MARKET_API_BASE}/watchlist/${encodeURIComponent(symbol)}?market=${encodeURIComponent(market || '')}&type=${encodeURIComponent(type || 'stock')}`
)
const fallbackGetWatchlistScanTargets = (session) => request.post(`${MARKET_API_BASE}/watchlist/scan-targets`, {
  session: SESSION_API_VALUE_MAP[session] || session || ''
})
const fallbackGetStockQuotes = (symbols = []) => request.get(`${MARKET_API_BASE}/longbridge/quotes`, { symbols })

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

const normalizeBoolean = (value, fallback = false) => {
  if (value === null || value === undefined || value === '') {
    return fallback
  }
  if (typeof value === 'boolean') {
    return value
  }
  if (typeof value === 'number') {
    return value > 0
  }
  const normalized = String(value).trim().toLowerCase()
  if (['true', '1', 'yes', 'enabled', 'on'].includes(normalized)) {
    return true
  }
  if (['false', '0', 'no', 'disabled', 'off'].includes(normalized)) {
    return false
  }
  return fallback
}

const toNumber = (value, fallback = 0) => {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

const toNullableNumber = (value) => {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

const normalizeQuoteSession = (sessionQuote = null) => {
  if (!sessionQuote || typeof sessionQuote !== 'object') {
    return null
  }
  return {
    ...sessionQuote,
    price: toNullableNumber(sessionQuote.price ?? sessionQuote.last_price ?? sessionQuote.lastPrice ?? sessionQuote.last),
    timestamp: sessionQuote.timestamp || sessionQuote.updatedAt || sessionQuote.updated_at || ''
  }
}

const normalizeRealtimeQuote = (quote = {}) => {
  const preMarketQuote = normalizeQuoteSession(quote.preMarketQuote ?? quote.pre_market_quote)
  const postMarketQuote = normalizeQuoteSession(quote.postMarketQuote ?? quote.post_market_quote)
  const overnightQuote = normalizeQuoteSession(quote.overnightQuote ?? quote.overnight_quote)
  const timestamp = quote.quoteSnapshotAt || quote.quote_snapshot_at || quote.timestamp || quote.updatedAt || quote.updated_at ||
    preMarketQuote?.timestamp || postMarketQuote?.timestamp || overnightQuote?.timestamp || ''
  return {
    ...quote,
    symbol: String(quote.symbol || '').trim().toUpperCase(),
    price: toNullableNumber(quote.price ?? quote.last_price ?? quote.lastPrice ?? quote.last_done ?? quote.last),
    preMarketQuote,
    postMarketQuote,
    overnightQuote,
    quoteSource: quote.quoteSource || quote.quote_source || quote.dataSource || quote.source || 'longbridge-live',
    timestamp
  }
}

const extractList = (payload, preferredKeys = []) => {
  if (Array.isArray(payload)) {
    return payload
  }
  for (const key of preferredKeys) {
    if (Array.isArray(payload?.[key])) {
      return payload[key]
    }
  }
  if (Array.isArray(payload?.data)) {
    return payload.data
  }
  if (Array.isArray(payload?.payload)) {
    return payload.payload
  }
  if (Array.isArray(payload?.data?.payload)) {
    return payload.data.payload
  }
  if (Array.isArray(payload?.data?.data?.payload)) {
    return payload.data.data.payload
  }
  if (Array.isArray(payload?.items)) {
    return payload.items
  }
  if (Array.isArray(payload?.targets)) {
    return payload.targets
  }
  return []
}

const resolveSessionPayload = (item = {}, session) => {
  const sessions = item?.sessions || item?.scanSettings || item?.scan_settings || {}
  const directSession = sessions?.[session] || {}
  return typeof directSession === 'object' && directSession !== null ? directSession : {}
}

const resolveSessionCount = (item = {}, session) => {
  const sessionPayload = resolveSessionPayload(item, session)
  const nestedCounts = item?.scanTargetCounts || item?.scan_target_counts || {}
  const directCount = item?.[`${session}TargetCount`] ??
    item?.[`${session}_target_count`] ??
    nestedCounts?.[session] ??
    sessionPayload?.count ??
    sessionPayload?.targetCount
  const listLike = sessionPayload?.targets || sessionPayload?.items || item?.scanTargets?.[session] || item?.scan_targets?.[session]
  if (Array.isArray(listLike)) {
    return listLike.length
  }
  return toNumber(directCount, 0)
}

const normalizeWatchlistItem = (item = {}) => {
  const market = String(item?.market || item?.market_code || item?.region || 'US').trim().toUpperCase() || 'US'
  const rawType = String(item?.type || item?.asset_type || item?.security_type || 'stock').trim().toLowerCase()
  const type = rawType || 'stock'
  const preMarketEnabled = normalizeBoolean(
    item?.preMarketEnabled ??
    item?.scan_before_open ??
    item?.scanBeforeOpen ??
    item?.pre_market_enabled ??
    item?.pre_open_scan_enabled ??
    resolveSessionPayload(item, 'pre_market')?.enabled
  )
  const afterMarketEnabled = normalizeBoolean(
    item?.afterMarketEnabled ??
    item?.scan_after_close ??
    item?.scanAfterClose ??
    item?.after_market_enabled ??
    item?.post_close_scan_enabled ??
    resolveSessionPayload(item, 'after_market')?.enabled
  )
  const sessionCounts = {
    pre_market: resolveSessionCount(item, 'pre_market'),
    after_market: resolveSessionCount(item, 'after_market')
  }
  const totalCount = toNumber(
    item?.scanTargetCount ??
    item?.scan_target_count ??
    item?.targetCount,
    sessionCounts.pre_market + sessionCounts.after_market
  )

  return {
    ...item,
    key: `${String(item?.symbol || '').trim().toUpperCase()}|${market}|${type}`,
    symbol: String(item?.symbol || '').trim().toUpperCase(),
    name: String(item?.name || item?.symbol_name || item?.symbol || '').trim(),
    market,
    type,
    addedAt: item?.addedAt || item?.added_at || item?.create_time || item?.created_at || item?.createdAt || '',
    lastScanAt: item?.lastScanAt || item?.last_scan_at || item?.scan_at || item?.scanAt || '',
    preMarketEnabled,
    afterMarketEnabled,
    sessionCounts,
    scanTargetCount: totalCount
  }
}

const normalizeScanTarget = (item = {}) => {
  const market = String(item?.market || item?.market_code || item?.region || 'US').trim().toUpperCase() || 'US'
  const rawType = String(item?.type || item?.asset_type || item?.security_type || 'stock').trim().toLowerCase()
  return {
    ...item,
    symbol: String(item?.symbol || '').trim().toUpperCase(),
    name: String(item?.name || item?.symbol_name || item?.symbol || '').trim(),
    market,
    type: rawType || 'stock',
    score: item?.score ?? item?.priority ?? item?.rank ?? null,
    source: item?.source || item?.strategy || item?.origin || '',
    reason: item?.reason || item?.summary || item?.note || item?.description || ''
  }
}

const formatCount = (value) => Number(value || 0).toLocaleString('zh-CN')
const formatDateTime = (value) => {
  if (!value) {
    return '--'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN')
}
const formatScore = (value) => {
  if (value === null || value === undefined || value === '') {
    return '--'
  }
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : String(value)
}
const formatQuotePrice = (value) => {
  const numeric = toNullableNumber(value)
  return numeric === null ? '--' : numeric.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 3 })
}
const marketLabel = (market) => MARKET_LABEL_MAP[String(market || '').toUpperCase()] || String(market || '--')
const typeLabel = (type) => TYPE_LABEL_MAP[String(type || '').toLowerCase()] || String(type || '--').toUpperCase()

const activeSessionLabel = computed(() => SESSION_LABEL_MAP[activeSession.value] || activeSession.value)
const watchlistLedgerRows = computed(() => filteredWatchlist.value.slice().sort((left, right) => {
  const marketDiff = MARKET_SORT_ORDER.indexOf(left.market) - MARKET_SORT_ORDER.indexOf(right.market)
  if (marketDiff !== 0) return marketDiff
  const typeDiff = TYPE_SORT_ORDER.indexOf(left.type) - TYPE_SORT_ORDER.indexOf(right.type)
  if (typeDiff !== 0) return typeDiff
  return left.symbol.localeCompare(right.symbol)
}).map((item) => {
  const quote = realtimeQuoteMap.value[item.symbol] || {}
  const quoteTimestamp = quote.timestamp || ''
  return {
    ...item,
    realtimePrice: quote.price,
    preMarketPrice: quote.preMarketQuote?.price,
    postMarketPrice: quote.postMarketQuote?.price,
    overnightPrice: quote.overnightQuote?.price,
    quoteSource: quote.quoteSource || '',
    quoteTimestamp,
    quoteTimeLabel: quoteTimestamp ? formatDateTime(quoteTimestamp) : '等待长桥实时'
  }
}))

const filteredWatchlist = computed(() => {
  const keyword = String(searchKeyword.value || '').trim().toLowerCase()
  return watchlist.value.filter((item) => {
    if (marketFilter.value && item.market !== marketFilter.value) {
      return false
    }
    if (typeFilter.value && item.type !== typeFilter.value) {
      return false
    }
    if (!keyword) {
      return true
    }
    return item.symbol.toLowerCase().includes(keyword) || item.name.toLowerCase().includes(keyword)
  })
})

const groupedWatchlist = computed(() => {
  const groupMap = new Map()

  filteredWatchlist.value.forEach((item) => {
    const key = `${item.type}|${item.market}`
    if (!groupMap.has(key)) {
      groupMap.set(key, {
        key,
        market: item.market,
        type: item.type,
        title: `${typeLabel(item.type)} / ${marketLabel(item.market)}`,
        items: [],
        activeSessionTargetCount: 0,
        preEnabledCount: 0,
        afterEnabledCount: 0
      })
    }

    const group = groupMap.get(key)
    group.items.push(item)
    group.activeSessionTargetCount += item.sessionCounts?.[activeSession.value] || 0
    group.preEnabledCount += item.preMarketEnabled ? 1 : 0
    group.afterEnabledCount += item.afterMarketEnabled ? 1 : 0
  })

  return Array.from(groupMap.values())
    .map((group) => ({
      ...group,
      items: group.items.slice().sort((left, right) => left.symbol.localeCompare(right.symbol))
    }))
    .sort((left, right) => {
      const marketDiff = MARKET_SORT_ORDER.indexOf(left.market) - MARKET_SORT_ORDER.indexOf(right.market)
      if (marketDiff !== 0) {
        return marketDiff
      }
      const typeDiff = TYPE_SORT_ORDER.indexOf(left.type) - TYPE_SORT_ORDER.indexOf(right.type)
      if (typeDiff !== 0) {
        return typeDiff
      }
      return left.title.localeCompare(right.title)
    })
})

const activeSessionTargetCount = computed(() => {
  if (scanTargets.value.length) {
    return scanTargets.value.length
  }
  return filteredWatchlist.value.reduce((sum, item) => sum + toNumber(item.sessionCounts?.[activeSession.value], 0), 0)
})
const realtimeQuoteTag = computed(() => {
  if (loadingRealtimeQuotes.value) {
    return '长桥实时加载中'
  }
  const resolvedCount = watchlistLedgerRows.value.filter((item) => item.realtimePrice !== null && item.realtimePrice !== undefined).length
  return resolvedCount ? `长桥实时 ${formatCount(resolvedCount)} / ${formatCount(watchlistLedgerRows.value.length)}` : '等待长桥实时'
})

const stats = computed(() => [
  {
    label: '自选标的',
    value: formatCount(watchlist.value.length),
    note: `${formatCount(groupedWatchlist.value.length)} 个市场分组`,
    icon: Star,
    color: 'linear-gradient(135deg, #1d4f91 0%, #2d7dd2 100%)'
  },
  {
    label: '开盘前扫描',
    value: formatCount(watchlist.value.filter((item) => item.preMarketEnabled).length),
    note: `目标 ${formatCount(watchlist.value.reduce((sum, item) => sum + item.sessionCounts.pre_market, 0))}`,
    icon: Timer,
    color: 'linear-gradient(135deg, #166d7b 0%, #22a6b3 100%)'
  },
  {
    label: '收盘后扫描',
    value: formatCount(watchlist.value.filter((item) => item.afterMarketEnabled).length),
    note: `目标 ${formatCount(watchlist.value.reduce((sum, item) => sum + item.sessionCounts.after_market, 0))}`,
    icon: DataLine,
    color: 'linear-gradient(135deg, #8c4a18 0%, #cf7b2a 100%)'
  },
  {
    label: `${activeSessionLabel.value}目标`,
    value: formatCount(activeSessionTargetCount.value),
    note: scanTargetUpdatedAt.value ? `更新于 ${formatDateTime(scanTargetUpdatedAt.value)}` : '按 session 拉取',
    icon: Collection,
    color: 'linear-gradient(135deg, #36563e 0%, #4f8f63 100%)'
  }
])

const targetSummaryText = computed(() => {
  if (scanTargets.value.length) {
    const marketCount = new Set(scanTargets.value.map((item) => item.market)).size
    const typeCount = new Set(scanTargets.value.map((item) => item.type)).size
    return `${activeSessionLabel.value}返回 ${formatCount(scanTargets.value.length)} 个扫描目标，覆盖 ${formatCount(marketCount)} 个市场 / ${formatCount(typeCount)} 类标的`
  }
  return `${activeSessionLabel.value}按 session 实时获取扫描目标`
})

const setPendingState = (bucket, key, session, value) => {
  const current = { ...(bucket.value || {}) }
  const next = { ...(current[key] || {}) }
  next[session] = value
  current[key] = next
  bucket.value = current
}

const isRowPending = (key, session) => Boolean(pendingToggleMap.value?.[key]?.[session])
const isRowRemoving = (key) => Boolean(pendingRemoveMap.value?.[key]?.remove)

const loadRealtimeQuotes = async (items = watchlist.value) => {
  const symbols = Array.from(new Set(
    (Array.isArray(items) ? items : [])
      .map((item) => String(item.symbol || '').trim().toUpperCase())
      .filter(Boolean)
  ))
  if (!symbols.length) {
    realtimeQuoteMap.value = {}
    return
  }

  loadingRealtimeQuotes.value = true
  try {
    const getStockQuotesApi = await resolveMarketApiMethod('getStockQuotes', fallbackGetStockQuotes)
    const response = await getStockQuotesApi(symbols)
    const rawQuotes = extractList(response, ['quotes', 'payload'])
    realtimeQuoteMap.value = Object.fromEntries(
      rawQuotes
        .map(normalizeRealtimeQuote)
        .map((quote) => [quote.symbol, quote])
        .filter(([symbol]) => Boolean(symbol))
    )
  } catch (error) {
    if (!isAlive && isFetchAbortLikeError(error)) {
      return
    }
    realtimeQuoteMap.value = {}
    console.warn('加载长桥实时行情失败:', error)
  } finally {
    if (isAlive) {
      loadingRealtimeQuotes.value = false
    }
  }
}

const loadWatchlist = async () => {
  loadingWatchlist.value = true
  try {
    const getWatchlistApi = await resolveMarketApiMethod('getWatchlist', fallbackGetWatchlist)
    const response = await getWatchlistApi()
    const rawItems = extractList(response, ['watchlist'])
    watchlist.value = rawItems.map(normalizeWatchlistItem).filter((item) => item.symbol)
    await loadRealtimeQuotes(watchlist.value)
  } catch (error) {
    if (!isAlive && isFetchAbortLikeError(error)) {
      return
    }
    console.error('加载自选股票池失败:', error)
    ElMessage.error('加载自选股票池失败')
  } finally {
    if (isAlive) {
      loadingWatchlist.value = false
    }
  }
}

const loadScanTargets = async (session = activeSession.value) => {
  loadingTargets.value = true
  scanTargetError.value = ''
  try {
    const getWatchlistScanTargetsApi = await resolveMarketApiMethod('getWatchlistScanTargets', fallbackGetWatchlistScanTargets)
    const response = await getWatchlistScanTargetsApi(SESSION_API_VALUE_MAP[session] || session)
    const rawItems = extractList(response, ['targets', 'watchlist'])
    scanTargets.value = rawItems.map(normalizeScanTarget).filter((item) => item.symbol)
    scanTargetUpdatedAt.value = response?.meta?.updatedAt || response?.meta?.updated_at || response?.updatedAt || response?.updated_at || new Date().toISOString()
  } catch (error) {
    if (!isAlive && isFetchAbortLikeError(error)) {
      return
    }
    console.error(`加载 ${session} 扫描目标失败:`, error)
    scanTargets.value = []
    scanTargetError.value = error?.data?.error || error?.message || '获取扫描目标失败'
    ElMessage.error(`${activeSessionLabel.value}扫描目标加载失败`)
  } finally {
    if (isAlive) {
      loadingTargets.value = false
    }
  }
}

const refreshAll = async () => {
  await Promise.all([loadWatchlist(), loadScanTargets(activeSession.value)])
}

const toggleScan = async (item, session, enabled) => {
  const fieldName = SESSION_FIELD_MAP[session]
  if (!fieldName) {
    return
  }

  setPendingState(pendingToggleMap, item.key, session, true)
  try {
    const updateWatchlistApi = await resolveMarketApiMethod('updateWatchlist', fallbackUpdateWatchlist)
    await updateWatchlistApi({
      symbol: item.symbol,
      market: item.market,
      type: item.type,
      [fieldName]: Boolean(enabled),
      scan_before_open: session === 'pre_market' ? Boolean(enabled) : item.preMarketEnabled,
      scan_after_close: session === 'after_market' ? Boolean(enabled) : item.afterMarketEnabled
    })
    await Promise.all([loadWatchlist(), loadScanTargets(activeSession.value)])
    ElMessage.success(`${item.symbol} ${SESSION_LABEL_MAP[session]}扫描已${enabled ? '开启' : '关闭'}`)
  } catch (error) {
    console.error('更新自选扫描开关失败:', error)
    ElMessage.error(error?.data?.error || error?.message || '更新扫描开关失败')
  } finally {
    setPendingState(pendingToggleMap, item.key, session, false)
  }
}

const removeItem = async (item) => {
  try {
    await ElMessageBox.confirm(`确定移除 ${item.symbol} 吗？`, '移除自选', {
      confirmButtonText: '移除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }

  setPendingState(pendingRemoveMap, item.key, 'remove', true)
  try {
    const removeWatchlistApi = await resolveMarketApiMethod('removeWatchlist', fallbackRemoveWatchlist)
    await removeWatchlistApi(item.symbol, item.market, item.type)
    await Promise.all([loadWatchlist(), loadScanTargets(activeSession.value)])
    ElMessage.success(`${item.symbol} 已移出自选股票池`)
  } catch (error) {
    console.error('移除自选标的失败:', error)
    ElMessage.error(error?.data?.error || error?.message || '移除自选标的失败')
  } finally {
    setPendingState(pendingRemoveMap, item.key, 'remove', false)
  }
}

const openScanResult = (item) => {
  router.push({
    name: 'WatchlistScanResult',
    params: { symbol: item.symbol },
    query: { market: item.market, session: activeSession.value }
  })
}

const openAIAnalysis = (item) => {
  router.push({
    name: 'AIAnalysis',
    query: { symbol: item.symbol, market: item.market }
  })
}

watch(activeSession, (session) => {
  loadScanTargets(session)
})

onMounted(() => {
  isAlive = true
  refreshAll()
})

onUnmounted(() => {
  isAlive = false
})
</script>

<style scoped>
.watchlist-pool-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: var(--text-primary);
}

.hero-panel,
.panel-card,
.stat-card {
  border: 1px solid color-mix(in srgb, var(--accent-strong) 14%, transparent);
  background: linear-gradient(180deg, color-mix(in srgb, var(--surface-strong) 94%, transparent), color-mix(in srgb, var(--surface-emphasis) 96%, transparent));
  box-shadow: var(--shadow-strong);
}

.hero-panel {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 18px;
  border-radius: 18px;
}

.hero-copy {
  min-width: 0;
}

.eyebrow,
.panel-kicker {
  display: block;
  margin-bottom: 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.hero-copy h2,
.panel-head h3 {
  margin: 0;
  font-size: 22px;
  line-height: 1.15;
  color: var(--text-emphasis);
}

.hero-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.hero-tag {
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--accent-strong) 16%, transparent);
  background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
  font-size: 12px;
  color: var(--text-secondary);
}

.hero-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(620px, 100%);
}

.search-input {
  width: 100%;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.filter-select {
  width: 120px;
}

.session-switch {
  margin-left: auto;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stat-card {
  border-radius: 16px;
}

.stat-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.stat-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  color: #fff;
}

.stat-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-copy span {
  font-size: 12px;
  color: var(--text-secondary);
}

.stat-copy strong {
  font-size: 20px;
  color: var(--text-emphasis);
}

.stat-copy small {
  font-size: 11px;
  color: var(--text-muted);
}

.panel-card {
  min-width: 0;
}

.panel-card {
  height: 100%;
  border-radius: 18px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.symbol-link {
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--accent-strong);
  font-weight: 700;
  cursor: pointer;
}

.table-action-group {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.scan-count-stack {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.scan-count-stack strong {
  color: var(--text-emphasis);
}

.scan-count-stack span {
  font-size: 12px;
  color: var(--text-secondary);
}

.quote-stack {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.35;
}

.quote-stack strong {
  color: var(--text-emphasis);
}

.quote-stack span,
.quote-stack small {
  font-size: 12px;
  color: var(--text-secondary);
}

.ledger-card :deep(.el-card__body),
.targets-ledger-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.target-head-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.target-summary {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.targets-table {
  flex: 1;
}

.panel-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 220px;
  color: var(--text-secondary);
}

.table-empty strong {
  color: var(--text-emphasis);
}

.table-empty span {
  max-width: 320px;
  text-align: center;
  color: var(--text-muted);
}
</style>

<template>
  <div class="dashboard-page">
    <div v-if="initialLoading" class="dashboard-loading-shell">
      <div class="loading-hero">
        <el-skeleton-item variant="text" class="loading-kicker" />
        <el-skeleton-item variant="h1" class="loading-title" />
        <el-skeleton-item variant="text" class="loading-line wide" />
        <el-skeleton-item variant="text" class="loading-line" />
      </div>
      <div class="loading-pill-row">
        <div v-for="item in 3" :key="`pill-${item}`" class="loading-pill">
          <el-skeleton-item variant="text" class="loading-pill-label" />
          <el-skeleton-item variant="text" class="loading-pill-value" />
        </div>
      </div>
      <div class="loading-stat-grid">
        <div v-for="item in 4" :key="`stat-${item}`" class="loading-stat-card">
          <el-skeleton-item variant="circle" class="loading-stat-icon" />
          <div class="loading-stat-copy">
            <el-skeleton-item variant="text" class="loading-stat-label" />
            <el-skeleton-item variant="text" class="loading-stat-value" />
          </div>
        </div>
      </div>
      <div class="loading-panel-grid">
        <div v-for="item in 4" :key="`panel-${item}`" class="loading-panel">
          <el-skeleton-item variant="text" class="loading-panel-title" />
          <el-skeleton-item variant="text" class="loading-panel-line" />
          <el-skeleton-item variant="text" class="loading-panel-line" />
          <el-skeleton-item variant="text" class="loading-panel-line short" />
        </div>
      </div>
    </div>

    <template v-else>
      <PageHero
        title="工作台"
        :chips="dashboardHeroChips"
        :compact="isPhoneLayout"
      >
        <template #actions>
          <div class="header-actions page-hero-actions">
            <el-select v-model="selectedAccount" placeholder="选择账户" style="width: 220px">
              <el-option
                v-for="account in accounts"
                :key="account.id"
                :label="account.name"
                :value="account.id"
              />
            </el-select>
            <el-select v-model="timeRange" placeholder="时间范围" style="width: 120px">
              <el-option label="今日" value="today" />
              <el-option label="本周" value="week" />
              <el-option label="本月" value="month" />
              <el-option label="本年" value="year" />
            </el-select>
            <el-button type="primary" :icon="Refresh" @click="handleRefresh" :loading="refreshing">
              实时刷新
            </el-button>
          </div>
        </template>
      </PageHero>

      <div v-if="isPhoneLayout" class="mobile-home-stack">
        <section class="mobile-action-grid">
          <button
            v-for="item in mobileQuickActions"
            :key="item.title"
            type="button"
            class="mobile-action-card"
            @click="router.push(item.target)"
          >
            <strong>{{ item.title }}</strong>
          </button>
        </section>

        <el-card v-if="activeMobileSection === 'overview'" class="mobile-feed-card">
          <template #header>
            <SectionCardHeader title="下一步动作" />
          </template>
          <div class="mobile-feed-list">
            <article
              v-for="item in roleWorkflowCards"
              :key="item.id"
              class="mobile-feed-item mobile-feed-item--button"
              @click="router.push(item.target)"
            >
              <div class="mobile-feed-head">
                <strong>{{ item.title }}</strong>
              </div>
            </article>
          </div>
        </el-card>

        <MobileSegmentControl
          v-model="activeMobileSection"
          class="mobile-dashboard-rail"
          label="工作台分段"
          :items="dashboardMobileSections"
        />

        <section v-if="activeMobileSection === 'overview'" class="mobile-glance-grid">
          <article v-for="item in heroStatusCards.slice(0, 4)" :key="`mobile-${item.label}`" class="mobile-glance-card">
            <span>{{ item.label }}</span>
            <strong :class="item.tone">{{ item.value }}</strong>
          </article>
        </section>

        <el-card v-if="activeMobileSection === 'overview'" class="mobile-feed-card">
          <template #header>
            <SectionCardHeader title="账户摘要" :badge="accountSourceTag.text" :badge-type="accountSourceTag.type" />
          </template>
          <div class="mobile-glance-grid compact">
            <article v-for="item in assetStats" :key="`asset-${item.label}`" class="mobile-glance-card">
              <span>{{ item.label }}</span>
              <strong :class="item.class">{{ item.value }}</strong>
            </article>
          </div>
        </el-card>

        <el-card v-if="activeMobileSection === 'activity'" class="mobile-feed-card">
          <template #header>
            <SectionCardHeader title="交易脉搏" >
              <template #actions>
                <el-button type="primary" link @click="$router.push('/orders')">全部订单</el-button>
              </template>
            </SectionCardHeader>
          </template>
          <div v-if="displayRecentTrades.length" class="mobile-feed-list">
            <article v-for="row in displayRecentTrades.slice(0, 4)" :key="`${row.symbol}-${row.createTime}`" class="mobile-feed-item">
              <div class="mobile-feed-head">
                <strong>{{ row.symbol }}</strong>
                <el-tag size="small" :type="row.action === 'buy' ? 'success' : 'danger'">
                  {{ row.action === 'buy' ? '买入' : '卖出' }}
                </el-tag>
              </div>
              <p>{{ formatTime(row.createTime) }} · {{ row.quantity }} 股 · {{ formatOrderPrice(row) }}</p>
            </article>
          </div>
          <el-empty v-else description="暂无交易快照" />
        </el-card>

        <el-card v-if="activeMobileSection === 'activity'" class="mobile-feed-card">
          <template #header>
            <SectionCardHeader title="仓位温度" >
              <template #actions>
                <el-button type="primary" link @click="$router.push('/positions')">全部持仓</el-button>
              </template>
            </SectionCardHeader>
          </template>
          <div v-if="displayPositions.length" class="mobile-feed-list">
            <article v-for="row in displayPositions.slice(0, 3)" :key="row.symbol" class="mobile-feed-item">
              <div class="mobile-feed-head">
                <strong>{{ row.symbol }}</strong>
                <span class="mobile-score" :class="Number(row.pnl || 0) >= 0 ? 'healthy' : 'down'">
                  {{ formatSignedNumberValue(row.pnlPercent) }}%
                </span>
              </div>
              <p>
                市值 {{ formatCurrency(row.marketValue) }} · 成本 {{ formatCurrency(row.avgPrice || row.avg_price) }}
              </p>
            </article>
          </div>
          <el-empty v-else description="暂无持仓快照" />
        </el-card>

        <el-card v-if="activeMobileSection === 'activity'" class="mobile-feed-card">
          <template #header>
            <SectionCardHeader title="AI 推荐" >
              <template #actions>
                <el-button type="primary" link @click="$router.push('/ai-analysis')">去策略</el-button>
              </template>
            </SectionCardHeader>
          </template>
          <div v-if="recommendationItems.length" class="mobile-feed-list">
            <article v-for="item in recommendationItems.slice(0, 3)" :key="item.symbol" class="mobile-feed-item">
              <div class="mobile-feed-head">
                <strong>{{ item.symbol }}</strong>
                <el-tag size="small" :type="item.is_top_pick ? 'success' : 'info'">
                  {{ item.is_top_pick ? '重点' : '候选' }}
                </el-tag>
              </div>
              <p v-if="item.thesis">{{ item.thesis }}</p>
            </article>
          </div>
          <el-empty v-else description="暂无智能推荐" />
        </el-card>

        <el-card v-if="activeMobileSection === 'market'" class="mobile-feed-card">
          <template #header>
            <SectionCardHeader title="市场快照" >
              <template #actions>
                <el-button type="primary" link @click="$router.push('/market')">去行情</el-button>
              </template>
            </SectionCardHeader>
          </template>
          <div v-if="marketInsights.length" class="mobile-feed-list">
            <article v-for="item in marketInsights.slice(0, 3)" :key="item.market" class="mobile-feed-item">
              <div class="mobile-feed-head">
                <strong>{{ item.marketLabel || item.market }}</strong>
                <span class="mobile-score" :class="item.regime">{{ formatSignedNumberValue(item.marketScore) }}</span>
              </div>
              <p>{{ item.summary }}</p>
            </article>
          </div>
          <el-empty v-else description="暂无市场快照" />
        </el-card>

        <el-card v-if="activeMobileSection === 'market'" class="mobile-feed-card">
          <template #header>
            <SectionCardHeader title="财经快讯" >
              <template #actions>
                <el-button type="primary" link @click="$router.push('/finance-news')">全部快讯</el-button>
              </template>
            </SectionCardHeader>
          </template>
          <div v-if="financeBriefings.length" class="mobile-feed-list">
            <article v-for="item in financeBriefings.slice(0, 3)" :key="item.id" class="mobile-feed-item">
              <div class="mobile-feed-head">
                <strong>{{ item.headline }}</strong>
                <el-tag size="small" :type="getMarketTagType(item.market)">{{ item.market || 'ALL' }}</el-tag>
              </div>
              <p>{{ item.summary }}</p>
            </article>
          </div>
          <el-empty v-else description="暂无财经快讯" />
        </el-card>

        <el-card v-if="activeMobileSection === 'ops'" class="mobile-feed-card">
          <template #header>
            <SectionCardHeader title="服务状态墙" >
              <template #actions>
                <el-button type="primary" link :loading="healthLoading" @click="loadSystemHealth(false)">刷新</el-button>
              </template>
            </SectionCardHeader>
          </template>
          <div class="mobile-glance-grid compact">
            <article v-for="item in systemHealthCards.slice(0, 4)" :key="`health-${item.key}`" class="mobile-glance-card">
              <span>{{ item.label }}</span>
              <strong :class="item.tone">{{ item.value }}</strong>
            </article>
          </div>
        </el-card>

        <el-card v-if="activeMobileSection === 'ops'" class="mobile-feed-card">
          <template #header>
            <SectionCardHeader
              title="数据状态"
              :badge="quotesConnected ? '报价在线' : '快照'"
              :badge-type="quotesConnected ? 'success' : 'info'"
            />
          </template>
          <div class="mobile-feed-list">
            <article class="mobile-feed-item">
              <div class="mobile-feed-head">
                <strong>账户</strong>
                <el-tag size="small" :type="accountSourceTag.type">{{ accountSourceTag.text }}</el-tag>
              </div>
            </article>
            <article class="mobile-feed-item">
              <div class="mobile-feed-head">
                <strong>服务巡检</strong>
                <span class="mobile-score">{{ serviceHealthSnapshot }}</span>
              </div>
            </article>
          </div>
        </el-card>
      </div>

      <template v-if="!isPhoneLayout">

      <MetricStrip :items="assetMetricStripItems" />

      <ReadModelSourceStrip
        label="账户状态"
        :status-text="dashboardAccountSourceSummary.statusText"
        :status-type="dashboardAccountSourceSummary.statusType"
        :updated-at="dashboardAccountSourceUpdatedAt"
        :updated-prefix="dashboardAccountSourceSummary.updatedPrefix"
        :tags="dashboardAccountSourceSummary.tags"
      />

      <div class="dashboard-grid analytics-grid">
        <el-card class="chart-card">
          <template #header>
            <SectionCardHeader title="资产走势" />
          </template>
          <DeferredBlock :active="chartsReady" :delay="0" min-height="320px">
            <template #fallback>
              <div class="chart-placeholder" />
            </template>
            <div class="chart-container">
              <v-chart class="chart" :option="equityChartOption" autoresize />
            </div>
          </DeferredBlock>
        </el-card>

        <el-card class="chart-card">
          <template #header>
            <SectionCardHeader title="持仓分布" />
          </template>
          <DeferredBlock :active="chartsReady" :delay="0" min-height="320px">
            <template #fallback>
              <div class="chart-placeholder" />
            </template>
            <div class="chart-container">
              <v-chart class="chart" :option="positionChartOption" autoresize />
            </div>
          </DeferredBlock>
        </el-card>
      </div>

      <div class="dashboard-grid desktop-snapshot-grid">
        <el-card class="panel-card">
          <template #header>
            <SectionCardHeader title="最近订单">
              <template #actions>
                <div class="card-actions">
                <el-tag size="small" :type="orderStreamConnected ? 'success' : 'info'">
                  {{ orderStreamConnected ? '订单更新中' : '订单快照' }}
                </el-tag>
                <el-button type="primary" link @click="$router.push('/orders')">
                  查看全部
                </el-button>
                </div>
              </template>
            </SectionCardHeader>
          </template>
          <el-table :data="displayRecentTrades" style="width: 100%" v-loading="tradesLoading">
            <el-table-column prop="createTime" label="时间" width="150">
              <template #default="{ row }">
                {{ formatTime(row?.createTime) }}
              </template>
            </el-table-column>
            <el-table-column prop="symbol" label="股票" width="100" />
            <el-table-column prop="action" label="操作" width="80">
              <template #default="{ row }">
                <el-tag :type="row?.action === 'buy' ? 'success' : 'danger'" size="small">
                  {{ row?.action === 'buy' ? '买入' : '卖出' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="quantity" label="数量" width="80" />
            <el-table-column prop="price" label="价格">
              <template #default="{ row }">
                {{ formatOrderPrice(row) }}
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row?.status === 'filled' ? 'success' : 'warning'" size="small">
                  {{ getStatusText(row?.status) }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!displayRecentTrades.length && !tradesLoading" description="暂无可用交易快照" />
        </el-card>

        <el-card class="panel-card">
          <template #header>
            <SectionCardHeader
              title="市场动态"
              :badge="marketInsightSourceSummary.updatedAt ? `更新于 ${formatTime(marketInsightSourceSummary.updatedAt)}` : ''"
            />
          </template>
          <ReadModelSourceStrip
            v-if="marketInsights.length"
            label="行情状态"
            :detail="marketInsightSourceSummary.detail"
            :status-text="marketInsightSourceSummary.statusText"
            :status-type="marketInsightSourceSummary.statusType"
            :updated-at="marketInsightSourceSummary.updatedAt ? formatTime(marketInsightSourceSummary.updatedAt) : ''"
            :tags="marketInsightSourceTags"
            compact
          />
          <div class="market-insight-list" v-if="marketInsights.length">
            <div v-for="item in marketInsights" :key="item.market" class="market-insight-item">
              <div class="insight-top">
                <div class="insight-market">
                  <el-tag size="small" :type="getMarketTagType(item.market)">
                    {{ item.marketLabel || item.market }}
                  </el-tag>
                  <span class="headline">{{ item.headline }}</span>
                </div>
                <div class="insight-meta">
                  <span class="status-pill" :class="item.status">{{ item.statusText }}</span>
                  <span class="score" :class="item.regime">{{ formatSignedNumberValue(item.marketScore) }}</span>
                </div>
              </div>

              <p class="insight-summary">{{ item.summary }}</p>
              <div class="insight-source-strip">
                <el-tag size="small" type="info">分析快照</el-tag>
                <el-tag size="small" :type="item.quoteReadyCount ? 'success' : 'warning'">
                  {{ item.quoteSourceTag }}
                </el-tag>
                <span v-if="item.quoteSnapshotAt" class="insight-source-time">
                  长桥实时 {{ formatTime(item.quoteSnapshotAt) }}
                </span>
              </div>

              <div class="benchmark-strip">
                <div v-for="benchmark in (item.benchmarks || []).slice(0, 3)" :key="benchmark.symbol" class="benchmark-chip">
                  <span class="chip-name">{{ benchmark.name }}</span>
                  <span class="chip-price">{{ formatMarketCurrency(benchmark.price, item.market) }}</span>
                  <span class="chip-change" :class="benchmark.changePercent >= 0 ? 'up' : 'down'">
                    {{ formatPercentValue(benchmark.changePercent) }}
                  </span>
                  <span class="chip-source">
                    {{ benchmark.quoteReady ? `长桥实时 ${formatTime(benchmark.quoteSnapshotAt)}` : '等待长桥实时' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <el-empty v-else description="暂无市场数据" />
        </el-card>
      </div>

      <div class="dashboard-grid desktop-intelligence-grid">
        <el-card class="panel-card">
          <template #header>
            <SectionCardHeader
              title="推荐"
              :badge="recommendationGeneratedAt ? `更新于 ${formatTime(recommendationGeneratedAt)}` : recommendationSourceSummary.sourceLabel"
            />
          </template>
          <ReadModelSourceStrip
            label="推荐状态"
            :detail="recommendationSourceSummary.detail"
            :status-text="recommendationSourceSummary.sourceLabel"
            :status-type="recommendationSourceSummary.statusType"
            :updated-at="recommendationSourceSummary.updatedAt ? formatTime(recommendationSourceSummary.updatedAt) : ''"
            :tags="recommendationSourceTags"
            compact
          />
          <div class="recommendation-summary" v-if="recommendationSummary">
            {{ recommendationSummary }}
          </div>
          <div class="recommendation-list" v-if="recommendationItems.length">
            <div v-for="item in recommendationItems" :key="item.symbol" class="recommendation-item">
              <div class="recommendation-head">
                <div>
                  <strong>{{ item.symbol }}</strong>
                  <span>{{ item.name }}</span>
                </div>
                <el-tag size="small" :type="item.is_top_pick ? 'success' : 'info'">
                  {{ item.is_top_pick ? '重点' : '候选' }}
                </el-tag>
              </div>
              <div class="recommendation-meta">
                <span>{{ item.market }}</span>
                <span v-if="item.quoteReady">现价 {{ formatMarketCurrency(item.price, item.market) }}</span>
                <span v-if="item.quoteReady" :class="Number(item.changePercent || item.change_percent || 0) >= 0 ? 'up' : 'down'">
                  {{ formatPercentValue(item.changePercent ?? item.change_percent ?? 0) }}
                </span>
                <span>AI {{ Number(item.ai_score || 0).toFixed(2) }}</span>
                <span>预期 {{ formatPercentValue(item.expected_return || 0) }}</span>
                <span>置信度 {{ Number(item.confidence || 0).toFixed(2) }}%</span>
              </div>
              <p v-if="item.thesis">{{ item.thesis }}</p>
            </div>
          </div>
          <el-empty v-else description="暂无智能推荐" />
        </el-card>

      </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, defineAsyncComponent, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Wallet, TrendCharts, Coin, Money } from '@element-plus/icons-vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { getFinanceBriefings, getRecommendations } from '../api/analysis.js'
import { getDashboardMarketInsights, getStockQuotes } from '../api/market.js'
import { getApiHealth } from '../api/platform.js'
import { getAssetTrend, getBrokerAccounts, getDashboardSummary, getPositionsSnapshot, getProjectedOrders } from '../api/trade.js'
import { useOrderStream, useStockQuotes } from '../composables/useWebSocket.js'
import { getAccess, getCurrentUser, getMenus } from '../utils/auth.js'
import { useTheme } from '../composables/useTheme.js'
import { useAdaptiveLayout } from '../composables/useAdaptiveLayout.js'
import { formatCurrency as formatCurrencyValue, formatOrderPrice, formatPercent as formatPercentDisplay, formatSignedNumber } from '../utils/formatters.js'
import { buildQuoteSnapshotMap, mergeQuoteSnapshots, summarizeQuoteSnapshotCoverage } from '../utils/quoteSnapshot.js'
import { buildAccountReadModelSummary, buildFinanceBriefingReadModelSummary, buildMarketInsightReadModelSummary, buildRecommendationReadModelSummary, formatQuoteCoverageLabel, formatReadModelSourceLabel } from '../utils/readModelSource.js'
import { buildRoleWorkflowCards } from '../utils/workbench.js'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import MobileSegmentControl from '../components/common/MobileSegmentControl.vue'
import PageHero from '../components/common/PageHero.vue'
import MetricStrip from '../components/common/MetricStrip.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'
import DeferredBlock from '../components/common/DeferredBlock.vue'

use([CanvasRenderer, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent])

const VChart = defineAsyncComponent(() => import('vue-echarts'))

const router = useRouter()
const { isPhoneLayout } = useAdaptiveLayout()
const activeMobileSection = ref('overview')
const chartsReady = ref(false)
const timeRange = ref('today')
const initialLoading = ref(true)
const refreshing = ref(false)
const tradesLoading = ref(false)
const healthLoading = ref(false)
const accounts = ref([])
const selectedAccount = ref(null)
const accountData = ref(null)
const accountDataMeta = ref({
  dataSource: 'snapshot',
  snapshotAt: '',
  sources: {},
  realtimeOverlay: [],
  defaultMode: 'database',
  warning: ''
})
const positionsData = ref([])
const positionsDataMeta = ref({
  dataSource: 'snapshot',
  snapshotAt: '',
  sources: {},
  realtimeOverlay: [],
  positionCount: 0
})
const trendData = ref([])
const snapshotRecentTrades = ref([])
const recentTradeMeta = ref({
  dataSource: 'order-projection',
  snapshotAt: '',
  sources: {},
  realtimeOverlay: [],
  orderCount: 0
})
const marketInsights = ref([])
const marketInsightMeta = ref({})
const financeBriefings = ref([])
const financeBriefingMeta = ref({})
const recommendationItems = ref([])
const recommendationSummary = ref('')
const recommendationGeneratedAt = ref(null)
const recommendationMeta = ref({})
const systemHealth = ref({ status: 'unknown', services: {}, environment: 'development', summary: {} })
const healthCheckedAt = ref(null)
const HEALTH_REFRESH_INTERVAL = 60000
let healthTimer = null
let chartsReadyTimer = null
const { activeTheme } = useTheme()
const currentUser = getCurrentUser() || {}
const access = getAccess() || {}
const visibleMenus = computed(() => getMenus())
const visibleMenuRoutes = computed(() => visibleMenus.value.map((item) => item?.routeName).filter(Boolean))
const visibleCapabilities = computed(() => Array.isArray(access?.capabilities) ? access.capabilities : [])
const orderStreamStatus = ref('')
const roleLabel = {
  admin: '系统管理员',
  user: '普通用户',
  trader: '交易用户',
  analyst: '普通用户',
  viewer: '普通用户'
}[currentUser.roleCode || currentUser.role] || '平台用户'
const streamSymbols = computed(() => positionsData.value.map((item) => String(item.symbol || '').trim().toUpperCase()).filter(Boolean))
const { quotes: liveQuoteMap, isConnected: quotesConnected } = useStockQuotes(streamSymbols, {
  userId: currentUser?.id || null
})
const {
  orders: streamedOrders,
  isConnected: orderStreamConnected,
  meta: orderStreamMeta,
  subscriptionAccountId,
  subscriptionStatus
} = useOrderStream(selectedAccount, orderStreamStatus, { limit: 12 })

const HEALTH_CARD_META = [
  { key: 'gateway', label: '网关' },
  { key: 'user_center', label: '用户中心' },
  { key: 'market_service', label: '市场服务' },
  { key: 'analysis_service', label: '分析服务' },
  { key: 'strategy_service', label: '策略服务' },
  { key: 'trade_service', label: '交易服务' },
  { key: 'sentiment_service', label: '舆情服务' },
  { key: 'scheduler_service', label: '调度中心' },
  { key: 'risk_service', label: '风控服务' },
  { key: 'agno_sidecar', label: 'Agno Sidecar' }
]

const overallHealthLabel = computed(() => {
  const status = systemHealth.value?.status
  if (status === 'healthy') return '全部正常'
  if (status === 'degraded') return '部分降级'
  if (status === 'unhealthy') return '存在异常'
  return '检测中'
})

const selectedAccountName = computed(() => {
  const matched = accounts.value.find((item) => item.id === selectedAccount.value)
  return matched?.name || '未绑定账户'
})

const serviceHealthSnapshot = computed(() => {
  const healthy = Number(systemHealth.value?.summary?.healthy || 0)
  const total = Number(systemHealth.value?.summary?.total || systemHealthCards.value.length || 0)
  return total ? `${healthy}/${total} 正常` : '等待检测'
})

const serviceHealthSourceLabel = computed(() => {
  const source = String(systemHealth.value?.source || '')
  const catalogSource = String(systemHealth.value?.catalog_source || '')
  if (source.includes('api-gateway') && catalogSource.includes('catalog')) {
    return 'Gateway 观测 · Catalog 已同步'
  }
  if (source.includes('api-gateway')) {
    return 'Gateway 观测'
  }
  if (source.includes('direct')) {
    return '直连健康检查'
  }
  return '等待 Gateway 观测'
})


const dashboardAccountSources = computed(() => (
  accountDataMeta.value?.sources && typeof accountDataMeta.value.sources === 'object'
    ? accountDataMeta.value.sources
    : {}
))
const dashboardPositionSources = computed(() => (
  positionsDataMeta.value?.sources && typeof positionsDataMeta.value.sources === 'object'
    ? positionsDataMeta.value.sources
    : {}
))
const dashboardRecentTradeSources = computed(() => (
  recentTradeMeta.value?.sources && typeof recentTradeMeta.value.sources === 'object'
    ? recentTradeMeta.value.sources
    : {}
))
const dashboardOrderStreamSources = computed(() => (
  orderStreamMeta.value?.sources && typeof orderStreamMeta.value.sources === 'object'
    ? orderStreamMeta.value.sources
    : {}
))
const dashboardAccountSourceLabel = computed(() => formatReadModelSourceLabel(dashboardAccountSources.value.account || 'account_asset_snapshots'))
const dashboardPositionSourceLabel = computed(() => (
  formatReadModelSourceLabel(dashboardPositionSources.value.positions || dashboardAccountSources.value.positions || 'position_snapshots')
))
const dashboardOrderSourceLabel = computed(() => (
  formatReadModelSourceLabel(dashboardOrderStreamSources.value.orders || dashboardRecentTradeSources.value.orders || dashboardAccountSources.value.orders || 'account_asset_snapshots.payload.recentOrders')
))
const dashboardRealtimeOverlayLabel = computed(() => {
  const overlays = new Set([
    ...(Array.isArray(accountDataMeta.value?.realtimeOverlay) ? accountDataMeta.value.realtimeOverlay : []),
    ...(Array.isArray(positionsDataMeta.value?.realtimeOverlay) ? positionsDataMeta.value.realtimeOverlay : []),
    ...(Array.isArray(orderStreamMeta.value?.realtimeOverlay) ? orderStreamMeta.value.realtimeOverlay : [])
  ])
  if (quotesConnected.value) {
    overlays.add('quotes')
  }
  if (hasOrderStreamCoverage.value) {
    overlays.add('order-stream')
  }
  return Array.from(overlays).filter(Boolean).join(' / ')
})

const dashboardAccountSourceSummary = computed(() => {
  if (!selectedAccount.value) {
    return {
      detail: '先选择账户，再接入账户摘要、持仓快照和最近订单。',
      statusText: '等待账户接入',
      statusType: 'warning',
      updatedAt: '',
      updatedPrefix: '快照于',
      tags: [
        { type: 'warning', text: '未选择账户' },
        { type: 'info', text: '市场与推荐可用' }
      ]
    }
  }

  const normalizedSource = String(accountDataMeta.value.dataSource || '').includes('live') ? 'realtime' : 'snapshot'
  const summary = buildAccountReadModelSummary({
    source: normalizedSource,
    snapshotAt: accountDataMeta.value.snapshotAt,
    accountLabel: selectedAccountName.value,
    quotesConnected: quotesConnected.value,
    orderStreamConnected: hasOrderStreamCoverage.value,
    positionCount: displayPositions.value.length,
    orderCount: displayRecentTrades.value.length
  })

  return {
    ...summary,
      detail: '工作台展示账户、持仓、行情和订单。',
    tags: [
      ...summary.tags,
      {
        type: positionsDataMeta.value.snapshotAt ? 'info' : 'warning',
        text: positionsDataMeta.value.snapshotAt ? `持仓 ${dashboardPositionSourceLabel.value}` : '等待持仓快照'
      },
      {
        type: recentTradeMeta.value.snapshotAt ? 'info' : 'warning',
        text: recentTradeMeta.value.snapshotAt ? `订单 ${dashboardOrderSourceLabel.value}` : '等待订单快照'
      },
      ...(dashboardRealtimeOverlayLabel.value
        ? [{ type: hasOrderStreamCoverage.value || quotesConnected.value ? 'success' : 'info', text: '实时更新' }]
        : []),
      ...(accountDataMeta.value.warning ? [{ type: 'warning', text: '账户摘要已回退' }] : [])
    ]
  }
})

const dashboardAccountSourceUpdatedAt = computed(() => (
  dashboardAccountSourceSummary.value.updatedAt ? formatTime(dashboardAccountSourceSummary.value.updatedAt) : ''
))

const accountSourceTag = computed(() => ({
  type: dashboardAccountSourceSummary.value.statusType,
  text: dashboardAccountSourceSummary.value.statusText
}))

const heroStatusCards = computed(() => [
  {
    label: '角色',
    value: roleLabel,
    tone: ''
  },
  {
    label: '交易能力',
    value: access.canUseQuantTrading ? '可交易' : '仅查看',
    tone: access.canUseQuantTrading ? 'healthy' : 'warning'
  },
  {
    label: '服务状态',
    value: overallHealthLabel.value,
    tone: systemHealth.value?.status === 'healthy' ? 'healthy' : systemHealth.value?.status === 'degraded' ? 'warning' : systemHealth.value?.status === 'unhealthy' ? 'error' : ''
  },
  {
    label: '最近检查',
    value: healthCheckedAt.value ? formatTime(healthCheckedAt.value) : serviceHealthSnapshot.value,
    tone: ''
  },
  {
    label: '账户来源',
    value: String(accountDataMeta.value.dataSource || '').includes('live') ? '实时' : '快照',
    tone: String(accountDataMeta.value.dataSource || '').includes('live') ? 'healthy' : 'warning'
  },
  {
    label: '账户时间',
    value: accountDataMeta.value.snapshotAt ? formatTime(accountDataMeta.value.snapshotAt) : '等待快照',
    tone: ''
  },
  {
    label: '持仓行情',
    value: quotesConnected.value ? '在线' : '快照',
    tone: quotesConnected.value ? 'healthy' : 'warning'
  },
  {
    label: '订单状态',
    value: orderStreamConnected.value ? '更新中' : '快照',
    tone: orderStreamConnected.value ? 'healthy' : 'warning'
  }
])

const dashboardHeroChips = computed(() => ([
  { text: '账户快照' },
  { text: accountSourceTag.value.text, tone: accountSourceTag.value.type },
  { text: quotesConnected.value ? '持仓在线' : '持仓快照', tone: quotesConnected.value ? 'healthy' : 'warning' },
  { text: orderStreamConnected.value ? '订单在线' : '订单快照', tone: orderStreamConnected.value ? 'healthy' : 'warning' }
]))

const mobileQuickActions = computed(() => ([
  ...roleWorkflowCards.value,
  {
    id: 'profile-setup',
    title: '账户设置',
    kicker: 'Me',
    note: '维护券商连接和量化配置',
    target: { name: 'Profile' }
  }
].slice(0, 4)))

const dashboardMobileSections = computed(() => ([
  { value: 'overview', label: '总览', note: selectedAccountName.value || '账户摘要' },
  { value: 'activity', label: '交易', note: `${displayRecentTrades.value.length} 条动态` },
  { value: 'market', label: '市场', note: `${marketInsights.value.length} 组快照` },
  { value: 'ops', label: '运维', note: overallHealthLabel.value }
]))

const roleWorkflowCards = computed(() => buildRoleWorkflowCards({
  roleCode: currentUser.roleCode || currentUser.role,
  access,
  menuRoutes: visibleMenuRoutes.value,
  capabilities: visibleCapabilities.value,
  selectedAccountName: selectedAccountName.value,
  recommendationItems: recommendationItems.value,
  positions: displayPositions.value,
  overallHealthLabel: overallHealthLabel.value,
}))

const displayPositions = computed(() => {
  return positionsData.value.map((item) => {
    const symbol = String(item.symbol || '').trim().toUpperCase()
    const liveQuote = liveQuoteMap.value[symbol] || {}
    const quantity = Number(item.quantity || 0)
    const avgPrice = Number(item.avgPrice ?? item.avg_price ?? 0)
    const currentPrice = Number(liveQuote.last_price ?? liveQuote.price ?? item.currentPrice ?? item.current_price ?? 0)
    const marketValue = quantity * currentPrice
    const pnl = (currentPrice - avgPrice) * quantity
    const pnlPercent = avgPrice > 0 ? ((currentPrice - avgPrice) / avgPrice) * 100 : 0
    return {
      ...item,
      currentPrice,
      current_price: currentPrice,
      marketValue,
      market_value: marketValue,
      pnl,
      pnlPercent,
      pnl_ratio: pnlPercent,
      changePercent: Number(liveQuote.change_percent ?? liveQuote.changePercent ?? item.changePercent ?? item.change_percent ?? pnlPercent)
    }
  })
})

const effectiveAccountData = computed(() => {
  if (!accountData.value) {
    return null
  }
  if (!displayPositions.value.length) {
    return accountData.value
  }

  const marketValue = displayPositions.value.reduce((sum, item) => sum + Number(item.marketValue ?? item.market_value ?? 0), 0)
  const totalPnl = displayPositions.value.reduce((sum, item) => sum + Number(item.pnl ?? 0), 0)
  const totalCost = displayPositions.value.reduce((sum, item) => {
    const quantity = Number(item.quantity || 0)
    const avgPrice = Number(item.avgPrice ?? item.avg_price ?? 0)
    return sum + quantity * avgPrice
  }, 0)
  const cash = Number(accountData.value.cash || 0)
  return {
    ...accountData.value,
    market_value: marketValue,
    daily_pnl: totalPnl,
    today_pnl: totalPnl,
    pnl_ratio: totalCost > 0 ? (totalPnl / totalCost) * 100 : Number(accountData.value.pnl_ratio || 0),
    total_assets: cash + marketValue
  }
})

const hasOrderStreamCoverage = computed(() => {
  const currentAccountId = selectedAccount.value ? Number(selectedAccount.value) : null
  const streamAccountId = subscriptionAccountId.value !== null && subscriptionAccountId.value !== undefined
    ? Number(subscriptionAccountId.value)
    : null
  return currentAccountId !== null && currentAccountId === streamAccountId && String(subscriptionStatus.value || '') === ''
})

const displayRecentTrades = computed(() => {
  if (hasOrderStreamCoverage.value && streamedOrders.value.length) {
    return streamedOrders.value.slice(0, 5)
  }
  return snapshotRecentTrades.value
})

const systemHealthCards = computed(() => {
  const services = systemHealth.value?.services || {}
  return HEALTH_CARD_META.map((item) => {
    const payload = services[item.key]
    const alertCount = Number(payload?.alert_count || 0)
    const basePath = payload?.basePath || ''
    const port = payload?.port ? `:${payload.port}` : ''
    return {
      key: item.key,
      label: item.label,
      value: formatServiceStatus(payload),
      tone: serviceTone(payload),
      endpoint: basePath || payload?.service || '等待目录',
      hint: alertCount
        ? `${alertCount} 条告警`
        : port
          ? port
          : payload?.version
          ? `v${payload.version}`
          : payload?.description || '等待检查'
    }
  })
})

const readThemeValue = (variableName, fallback) => {
  activeTheme.value
  if (typeof window === 'undefined') {
    return fallback
  }

  const value = getComputedStyle(document.documentElement).getPropertyValue(variableName).trim()
  return value || fallback
}

const withAlpha = (color, alpha) => {
  if (!color) {
    return `rgba(83, 185, 255, ${alpha})`
  }

  const normalized = color.trim()
  if (normalized.startsWith('#')) {
    const hex = normalized.slice(1)
    const size = hex.length === 3 ? 1 : 2
    const values = hex.length === 3
      ? hex.split('').map((item) => parseInt(item.repeat(2), 16))
      : [0, 2, 4].map((index) => parseInt(hex.slice(index, index + size), 16))
    return `rgba(${values[0]}, ${values[1]}, ${values[2]}, ${alpha})`
  }

  if (normalized.startsWith('rgb(')) {
    return normalized.replace('rgb(', 'rgba(').replace(')', `, ${alpha})`)
  }

  if (normalized.startsWith('rgba(')) {
    return normalized.replace(/rgba\(([^,]+),([^,]+),([^,]+),[^)]+\)/, `rgba($1,$2,$3,${alpha})`)
  }

  return normalized
}

const getChartPalette = () => ({
  axis: readThemeValue('--chart-axis', 'rgba(210, 225, 248, 0.7)'),
  grid: readThemeValue('--chart-grid', 'rgba(255, 255, 255, 0.1)'),
  accent: readThemeValue('--accent-strong', '#53b9ff'),
  accentSoft: readThemeValue('--accent', '#78e6ff'),
  text: readThemeValue('--text-primary', '#ffffff'),
  muted: readThemeValue('--text-secondary', 'rgba(226, 236, 255, 0.74)'),
  border: readThemeValue('--surface-emphasis', 'rgba(13, 26, 49, 0.72)')
})

const assetStats = computed(() => {
  if (!effectiveAccountData.value) {
    return [
      { label: '总资产', value: '--', change: null, icon: Wallet, color: '#409eff', class: '' },
      { label: '可用资金', value: '--', change: null, icon: Money, color: '#67c23a', class: '' },
      { label: '持仓市值', value: '--', change: null, icon: Coin, color: '#e6a23c', class: '' },
      { label: '今日盈亏', value: '--', change: null, icon: TrendCharts, color: '#f56c6c', class: '' }
    ]
  }
  const d = effectiveAccountData.value
  const pnl = parseFloat(d.daily_pnl) || 0
  const pnlRatio = parseFloat(d.pnl_ratio) || 0
  return [
    { label: '总资产', value: formatCurrency(d.total_assets || d.total_val), change: pnlRatio, icon: Wallet, color: '#409eff', class: '' },
    { label: '可用资金', value: formatCurrency(d.cash), change: null, icon: Money, color: '#67c23a', class: '' },
    { label: '持仓市值', value: formatCurrency(d.market_value || d.mkt_val), change: null, icon: Coin, color: '#e6a23c', class: '' },
    { label: '今日盈亏', value: (pnl >= 0 ? '+' : '') + formatCurrency(Math.abs(pnl)), change: pnlRatio, icon: TrendCharts, color: '#f56c6c', class: pnl >= 0 ? 'up' : 'down' }
  ]
})

const assetMetricStripItems = computed(() => (
  assetStats.value.map((item) => ({
    label: item.label,
    value: item.value,
    note: item.change !== null ? `较上期 ${formatPercentValue(item.change)}` : '账户摘要',
    tone: item.class === 'up' ? 'healthy' : (item.class === 'down' ? 'error' : '')
  }))
))

const scheduleChartsReady = () => {
  if (chartsReady.value || isPhoneLayout.value || typeof window === 'undefined') {
    return
  }

  const finish = () => {
    chartsReady.value = true
    chartsReadyTimer = null
  }

  if (typeof window.requestIdleCallback === 'function') {
    chartsReadyTimer = window.requestIdleCallback(finish, { timeout: 600 })
    return
  }

  chartsReadyTimer = window.setTimeout(finish, 180)
}

const clearChartsReadyTimer = () => {
  if (!chartsReadyTimer || typeof window === 'undefined') {
    chartsReadyTimer = null
    return
  }

  if (typeof chartsReadyTimer === 'number') {
    window.clearTimeout(chartsReadyTimer)
  } else if (typeof window.cancelIdleCallback === 'function') {
    window.cancelIdleCallback(chartsReadyTimer)
  }
  chartsReadyTimer = null
}

const marketInsightQuoteCoverage = computed(() => {
  const coverage = summarizeQuoteSnapshotCoverage(marketInsights.value.flatMap((item) => item?.benchmarks || []))
  return {
    ...coverage,
    label: formatQuoteCoverageLabel(coverage, { prefix: '基准长桥实时', emptyLabel: '等待基准长桥实时' })
  }
})
const marketInsightSourceSummary = computed(() => buildMarketInsightReadModelSummary(
  marketInsightMeta.value,
  {
    count: marketInsights.value.length,
    quoteCoverageLabel: marketInsightQuoteCoverage.value.label,
    label: '市场动态'
  }
))
const marketInsightSourceTags = computed(() => marketInsightSourceSummary.value.tags || [])
const recommendationQuoteSourceTag = computed(() => {
  const coverage = summarizeQuoteSnapshotCoverage(recommendationItems.value)
  return formatQuoteCoverageLabel(coverage, { prefix: '推荐长桥实时', emptyLabel: '等待推荐长桥实时' })
})
const financeBriefingSourceSummary = computed(() => {
  const summary = buildFinanceBriefingReadModelSummary(
    financeBriefingMeta.value,
    {
      count: financeBriefings.value.length,
      marketLabel: '工作台'
    }
  )
  return {
    ...summary,
    sourceLabel: summary.statusText,
    sourceDetail: summary.detail
  }
})
const financeBriefingSourceTags = computed(() => ([
  ...(financeBriefingSourceSummary.value.tags || []),
  { text: '工作台', type: 'info' }
]))
const recommendationSourceSummary = computed(() => {
  const summary = buildRecommendationReadModelSummary(
    recommendationMeta.value,
    {
      count: recommendationItems.value.length,
      profileLabel: '动量型',
      quoteCoverageLabel: recommendationQuoteSourceTag.value
    }
  )
  return {
    ...summary,
    sourceLabel: summary.statusText
  }
})
const recommendationSourceTags = computed(() => recommendationSourceSummary.value.tags || [])

const equityChartOption = computed(() => {
  const palette = getChartPalette()
  const seriesData = trendData.value.length > 0
    ? trendData.value
    : [{
        date: new Date().toLocaleDateString('zh-CN'),
        total_assets: effectiveAccountData.value?.total_assets || 0
      }]

  return {
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: seriesData.map((item) => item.date),
      axisLine: { lineStyle: { color: palette.grid } },
      axisLabel: { color: palette.axis }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: palette.grid, type: 'dashed' } },
      axisLabel: { color: palette.axis }
    },
    series: [{
      name: '总资产',
      data: seriesData.map((item) => Number(item.total_assets || 0)),
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { color: palette.accent, width: 2 },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: withAlpha(palette.accentSoft, 0.28) },
            { offset: 1, color: withAlpha(palette.accentSoft, 0.04) }
          ]
        }
      }
    }],
    tooltip: {
      trigger: 'axis',
      backgroundColor: readThemeValue('--surface-emphasis', 'rgba(13, 26, 49, 0.92)'),
      borderColor: palette.grid,
      textStyle: { color: palette.text },
      formatter: (params) => {
        return `时间: ${params[0].axisValue}<br/>总资产: $${Number(params[0].value || 0).toFixed(2)}`
      }
    }
  }
})

const positionChartOption = computed(() => {
  const palette = getChartPalette()
  const pieData = positionsData.value.length > 0
    ? displayPositions.value.map(p => ({
        name: p.symbol,
        value: Number(p.marketValue ?? p.market_value ?? 0)
      }))
    : [{ name: '无持仓', value: 1 }]

  return {
    tooltip: {
      trigger: 'item',
      backgroundColor: readThemeValue('--surface-emphasis', 'rgba(13, 26, 49, 0.92)'),
      borderColor: palette.grid,
      textStyle: { color: palette.text },
      formatter: '{b}: ${c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      right: '10%',
      top: 'center',
      textStyle: { color: palette.axis }
    },
    series: [{
      type: 'pie',
      radius: ['30%', '50%'],
      center: ['40%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderRadius: 10,
        borderColor: palette.border,
        borderWidth: 2
      },
      label: {
        show: false
      },
      data: pieData
    }]
  }
})

const formatCurrency = (value) => {
  return formatCurrencyValue(value, { currency: '$', fallback: '--' })
}

const formatPercentValue = (value) => formatPercentDisplay(value)
const formatSignedNumberValue = (value) => formatSignedNumber(value, 2, '--')

const formatMarketCurrency = (value, market = 'US') => {
  const currency = market === 'CN' ? '¥' : market === 'HK' ? 'HK$' : '$'
  return formatCurrencyValue(value, { currency, fallback: '--' })
}

const resolveServiceStatus = (service) => {
  if (!service) return ''
  if (typeof service === 'string') return service
  return service.status || service.status_text || ''
}

const serviceTone = (service) => {
  const normalized = String(resolveServiceStatus(service) || '').toLowerCase()
  if (!normalized) return 'neutral'
  if (normalized.includes('connected') || normalized.includes('healthy') || normalized.includes('ready') || normalized.includes('ok')) {
    return 'healthy'
  }
  if (normalized.includes('degraded')) {
    return 'warning'
  }
  if (normalized.includes('error') || normalized.includes('unhealthy') || normalized.includes('disconnected') || normalized.includes('fail')) {
    return 'error'
  }
  return 'neutral'
}

const formatServiceStatus = (service) => {
  if (!service) {
    return '待检查'
  }
  const normalized = String(resolveServiceStatus(service)).trim().toLowerCase()
  if (normalized === 'connected') return '已连接'
  if (normalized === 'healthy') return '运行正常'
  if (normalized === 'ready') return '就绪'
  if (normalized === 'ok') return '运行正常'
  if (normalized === 'degraded') return '部分受限'
  if (normalized === 'unhealthy') return '异常'
  if (normalized === 'disconnected') return '未连接'
  return service.status_text || normalized || '待检查'
}

const getMarketTagType = (market) => {
  if (market === 'US') return 'primary'
  if (market === 'CN') return 'success'
  if (market === 'HK') return 'warning'
  return 'info'
}

const formatTime = (time) => {
  if (!time) return '--'
  const d = new Date(time)
  return d.toLocaleString('zh-CN')
}

const getStatusText = (status) => {
  const map = { filled: '已成交', pending: '待成交', partial: '部分成交', cancelled: '已撤单', submitted: '已提交', rejected: '已拒绝' }
  return map[status] || status || '--'
}

const loadAccounts = async () => {
  try {
    const res = await getBrokerAccounts()
    accounts.value = res.data || []
    if (!selectedAccount.value && accounts.value.length > 0) {
      const defaultAccount = accounts.value.find(account => account.isDefault || account.is_default)
      selectedAccount.value = defaultAccount?.id || accounts.value[0].id
      return
    }
    if (!accounts.value.length) {
      initialLoading.value = false
      await Promise.all([
        loadEnhancementData(),
        loadTrendData()
      ])
    }
  } catch (error) {
    console.error('Failed to load accounts:', error)
    accounts.value = []
    initialLoading.value = false
  }
}

const loadAccountData = async (forceRealtime = false) => {
  try {
    if (!selectedAccount.value) {
      accountData.value = null
      accountDataMeta.value = { dataSource: 'snapshot', snapshotAt: '', sources: {}, realtimeOverlay: [], defaultMode: 'database', warning: '' }
      return
    }
    const res = await getDashboardSummary(selectedAccount.value, { realtime: forceRealtime })
    if (res.success) {
      accountData.value = res.data
      accountDataMeta.value = {
        dataSource: res.data?.meta?.dataSource || res.data?.source || (forceRealtime ? 'realtime' : 'snapshot'),
        snapshotAt: res.data?.meta?.snapshotAt || res.data?.snapshot_at || '',
        sources: res.data?.meta?.sources || {},
        realtimeOverlay: Array.isArray(res.data?.meta?.realtimeOverlay) ? res.data.meta.realtimeOverlay : [],
        defaultMode: res.data?.meta?.defaultMode || (forceRealtime ? 'realtime' : 'database'),
        warning: res.data?.warning || ''
      }
    }
  } catch (e) {
    console.error('Failed to load account data:', e)
  }
}

const loadPositionsData = async () => {
  try {
    if (!selectedAccount.value) {
      positionsData.value = []
      positionsDataMeta.value = { dataSource: 'snapshot', snapshotAt: '', sources: {}, realtimeOverlay: [], positionCount: 0 }
      return
    }
    const res = await getPositionsSnapshot(selectedAccount.value)
    positionsData.value = res.data || []
    positionsDataMeta.value = {
      dataSource: res.meta?.dataSource || 'snapshot',
      snapshotAt: res.meta?.snapshotAt || '',
      sources: res.meta?.sources || {},
      realtimeOverlay: Array.isArray(res.meta?.realtimeOverlay) ? res.meta.realtimeOverlay : [],
      positionCount: Number(res.meta?.positionCount || positionsData.value.length)
    }
  } catch (e) {
    console.error('Failed to load positions:', e)
    positionsData.value = []
    positionsDataMeta.value = { dataSource: 'snapshot', snapshotAt: '', sources: {}, realtimeOverlay: [], positionCount: 0 }
  }
}

const buildDashboardAccountSummary = (state = {}) => {
  const accountInfo = state?.accountInfo || {}
  const positions = Array.isArray(state?.positions) ? state.positions : []
  const totalPnl = positions.reduce((sum, item) => sum + Number(item.pnl ?? item.unrealized_pnl ?? 0), 0)
  const totalCost = positions.reduce((sum, item) => {
    const quantity = Number(item.quantity || 0)
    const avgPrice = Number(item.avgPrice ?? item.avg_price ?? item.average_cost ?? 0)
    return sum + avgPrice * quantity
  }, 0)
  const pnlRatio = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0
  return {
    account_id: state?.account?.account_id || '',
    currency: accountInfo.currency || 'USD',
    total_assets: Number(accountInfo.total_equity ?? accountInfo.totalAssets ?? 0),
    daily_pnl: totalPnl,
    today_pnl: totalPnl,
    today_pnl_percent: pnlRatio,
    pnl_ratio: pnlRatio,
    cash: Number(accountInfo.cash || 0),
    market_value: Number(accountInfo.market_value ?? accountInfo.marketValue ?? 0),
    buying_power: Number(accountInfo.buying_power ?? accountInfo.buyingPower ?? accountInfo.cash ?? 0),
    maintenance_margin: Number(accountInfo.maintenance_margin ?? accountInfo.maintenanceMargin ?? 0),
    source: state?.dataSource || 'snapshot',
    snapshot_at: state?.snapshotAt || ''
  }
}

const loadRecentTrades = async () => {
  tradesLoading.value = true
  try {
    if (!selectedAccount.value) {
      snapshotRecentTrades.value = []
      recentTradeMeta.value = { dataSource: 'order-projection', snapshotAt: '', sources: {}, realtimeOverlay: [], orderCount: 0 }
      return
    }
    const projectionRes = await getProjectedOrders({
      account_id: selectedAccount.value,
      limit: 12
    })
    const rows = Array.isArray(projectionRes?.data?.list) ? projectionRes.data.list : []
    snapshotRecentTrades.value = rows.slice(0, 5)
    recentTradeMeta.value = {
      dataSource: projectionRes?.data?.meta?.dataSource || projectionRes?.data?.dataSource || 'order-projection',
      snapshotAt: projectionRes?.data?.meta?.snapshotAt || projectionRes?.data?.snapshotAt || '',
      sources: projectionRes?.data?.meta?.sources || {},
      realtimeOverlay: Array.isArray(projectionRes?.data?.meta?.realtimeOverlay) ? projectionRes.data.meta.realtimeOverlay : [],
      orderCount: Number(projectionRes?.data?.meta?.count || projectionRes?.data?.total || rows.length)
    }
  } catch (e) {
    console.error('Failed to load trades:', e)
    snapshotRecentTrades.value = []
    recentTradeMeta.value = { dataSource: 'order-projection', snapshotAt: '', sources: {}, realtimeOverlay: [], orderCount: 0 }
  } finally {
    tradesLoading.value = false
  }
}

const loadMarketData = async () => {
  try {
    const res = await getDashboardMarketInsights()
    if (res.success) {
      const baseInsights = Array.isArray(res.data) ? res.data : []
      const benchmarkSymbols = [...new Set(
        baseInsights.flatMap((item) => (Array.isArray(item?.benchmarks) ? item.benchmarks : []))
          .map((item) => String(item?.symbol || '').trim().toUpperCase())
          .filter(Boolean)
      )]
      let quoteMap = {}
      if (benchmarkSymbols.length) {
        try {
          const quoteRes = await getStockQuotes(benchmarkSymbols)
          quoteMap = buildQuoteSnapshotMap(quoteRes?.data || [])
        } catch (quoteError) {
          console.error('Failed to load market benchmark Longbridge quotes:', quoteError)
        }
      }

      marketInsightMeta.value = res?.meta && typeof res.meta === 'object' ? res.meta : {}
      marketInsights.value = baseInsights.map((item) => {
        const mergedBenchmarks = mergeQuoteSnapshots(item?.benchmarks || [], quoteMap)
        const coverage = summarizeQuoteSnapshotCoverage(mergedBenchmarks)
        return {
          ...item,
          benchmarks: mergedBenchmarks,
          quoteReadyCount: coverage.readyCount,
          benchmarkCount: coverage.totalCount,
          quoteSourceTag: formatQuoteCoverageLabel(coverage, { prefix: '长桥实时', emptyLabel: '等待长桥实时' }),
          quoteSnapshotAt: coverage.latestSnapshotAt || null
        }
      })
    }
  } catch (e) {
    console.error('Failed to load market data:', e)
    marketInsightMeta.value = {}
    marketInsights.value = []
  }
}

const loadPrimaryWorkbenchData = async (forceRealtime = false) => {
  await Promise.all([
    loadAccountData(forceRealtime),
    loadPositionsData(),
    loadRecentTrades()
  ])
}

const loadSystemHealth = async (silent = true) => {
  healthLoading.value = true
  try {
    const res = await getApiHealth()
    systemHealth.value = res?.data || { status: 'unknown', services: {}, environment: 'development', summary: {} }
    healthCheckedAt.value = new Date().toISOString()
  } catch (error) {
    console.error('Failed to load system health:', error)
    const payload = error?.data || error?.response?.data
    if (payload && typeof payload === 'object') {
      systemHealth.value = {
        status: payload.status || 'unknown',
        services: payload.services || {},
        environment: payload.environment || systemHealth.value?.environment || 'development',
        phase: payload.phase || systemHealth.value?.phase || '',
        summary: payload.summary || systemHealth.value?.summary || {}
      }
      healthCheckedAt.value = new Date().toISOString()
      return
    }
    systemHealth.value = {
      status: 'unhealthy',
      services: {},
      environment: systemHealth.value?.environment || 'development',
      phase: systemHealth.value?.phase || '',
      summary: systemHealth.value?.summary || {}
    }
    if (!silent) {
      ElMessage.error('服务状态检查失败')
    }
  } finally {
    healthLoading.value = false
  }
}

const loadTrendData = async () => {
  try {
    const daysMap = { today: 1, week: 7, month: 30, year: 365 }
    const res = await getAssetTrend({ days: daysMap[timeRange.value] || 30 })
    trendData.value = Array.isArray(res.data) ? res.data : []
  } catch (error) {
    console.error('Failed to load asset trend:', error)
    trendData.value = []
  }
}

const loadWorkbenchInsights = async () => {
  try {
    const [briefingsRes, recommendationRes] = await Promise.all([
      getFinanceBriefings({ limit: 4 }),
      getRecommendations({ profile: 'momentum' })
    ])

    financeBriefings.value = Array.isArray(briefingsRes?.data) ? briefingsRes.data : []
    financeBriefingMeta.value = briefingsRes?.meta && typeof briefingsRes.meta === 'object' ? briefingsRes.meta : {}

    const recommendationPayload = recommendationRes?.data || {}
    const baseItems = Array.isArray(recommendationPayload.items)
      ? recommendationPayload.items.slice(0, 4)
      : []
    const quoteRes = await getStockQuotes(baseItems.map((item) => item.symbol))
    const quoteMap = buildQuoteSnapshotMap(quoteRes?.data || [])
    recommendationItems.value = mergeQuoteSnapshots(baseItems, quoteMap)
    recommendationSummary.value = recommendationPayload.summary || ''
    recommendationMeta.value = recommendationRes?.meta && typeof recommendationRes.meta === 'object' ? recommendationRes.meta : {}
    recommendationGeneratedAt.value = recommendationPayload.generated_at || recommendationMeta.value.generatedAt || recommendationMeta.value.snapshotAt || null
  } catch (error) {
    console.error('Failed to load workbench insights:', error)
    financeBriefings.value = []
    financeBriefingMeta.value = {}
    recommendationItems.value = []
    recommendationSummary.value = ''
    recommendationGeneratedAt.value = null
    recommendationMeta.value = {}
  }
}

const loadEnhancementData = async () => {
  await Promise.all([
    loadMarketData(),
    loadWorkbenchInsights()
  ])
}

const loadSnapshotData = async (showError = false, useSkeleton = false, forceRealtime = false) => {
  if (useSkeleton) {
    initialLoading.value = true
  } else {
    refreshing.value = true
  }
  try {
    await loadPrimaryWorkbenchData(forceRealtime)
    void loadEnhancementData().catch((error) => {
      console.error('Failed to load enhancement data:', error)
    })
  } catch (error) {
    if (showError) {
      ElMessage.error('加载工作台数据失败')
    }
  } finally {
    initialLoading.value = false
    refreshing.value = false
  }
}

const handleRefresh = async () => {
  refreshing.value = true
  try {
    await Promise.all([
      loadPrimaryWorkbenchData(true),
      loadTrendData(),
      loadSystemHealth(false)
    ])
    void loadEnhancementData().catch((error) => {
      console.error('Failed to refresh enhancement data:', error)
    })
  } finally {
    refreshing.value = false
  }
}

const stopHealthRefresh = () => {
  if (healthTimer) {
    window.clearInterval(healthTimer)
    healthTimer = null
  }
}

const startHealthRefresh = () => {
  stopHealthRefresh()
  healthTimer = window.setInterval(() => {
    loadSystemHealth(true)
  }, HEALTH_REFRESH_INTERVAL)
}

watch(selectedAccount, async (newValue, oldValue) => {
  if (!newValue || newValue === oldValue) return
  await Promise.all([
    loadSnapshotData(true, !accountData.value, false),
    loadTrendData()
  ])
})

watch(timeRange, () => {
  loadTrendData()
})

watch(isPhoneLayout, (isPhone) => {
  if (isPhone) {
    clearChartsReadyTimer()
    return
  }
  scheduleChartsReady()
})

onMounted(() => {
  loadAccounts()
  loadSystemHealth(true)
  startHealthRefresh()
  scheduleChartsReady()
})

onUnmounted(() => {
  stopHealthRefresh()
  clearChartsReadyTimer()
})
</script>

<style scoped lang="scss">
.dashboard-page {
  padding: 20px;
}

.chart-placeholder {
  min-height: 320px;
  border-radius: 24px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.02)),
    color-mix(in srgb, var(--surface-soft) 92%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-soft) 80%, transparent);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.asset-overview {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.dashboard-page :deep(.readmodel-source-strip) {
  margin-bottom: 20px;
}

.dashboard-loading-shell {
  display: grid;
  gap: 18px;
}

.loading-hero,
.loading-pill,
.loading-stat-card,
.loading-panel {
  border: 1px solid var(--border-soft);
  background: var(--surface-strong);
  box-shadow: var(--shadow-soft);
}

.loading-hero {
  display: grid;
  gap: 14px;
  padding: 24px;
  border-radius: 26px;
}

.loading-kicker {
  width: 120px;
}

.loading-title {
  width: min(520px, 100%);
  height: 40px;
}

.loading-line {
  width: 100%;
  height: 16px;

  &.wide {
    width: min(760px, 100%);
  }
}

.loading-pill-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.loading-pill {
  display: grid;
  gap: 10px;
  padding: 16px;
  border-radius: 18px;
}

.loading-pill-label {
  width: 72px;
}

.loading-pill-value {
  width: 110px;
  height: 20px;
}

.loading-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.loading-stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px;
  border-radius: 20px;
}

.loading-stat-icon {
  width: 56px;
  height: 56px;
}

.loading-stat-copy {
  display: grid;
  gap: 8px;
  flex: 1;
}

.loading-stat-label {
  width: 88px;
}

.loading-stat-value {
  width: 126px;
  height: 22px;
}

.loading-panel-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.loading-panel {
  display: grid;
  gap: 12px;
  padding: 20px;
  border-radius: 22px;
}

.loading-panel-title {
  width: 140px;
  height: 18px;
}

.loading-panel-line {
  width: 100%;
  height: 14px;

  &.short {
    width: 68%;
  }
}

.workbench-hero,
.hero-main,
.hero-strip-item,
.recommendation-head,
.recommendation-meta,
.briefing-head {
  display: flex;
  align-items: center;
}

.mobile-home-stack {
  display: none;
}

.workbench-hero {
  display: grid;
  gap: 16px;
  margin-bottom: 20px;
  padding: 22px 24px;
  border-radius: 24px;
  border: 1px solid var(--border-soft);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 8%, transparent), transparent 54%),
    var(--surface-strong);
  box-shadow: var(--shadow-strong);
}

.hero-main {
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
}

.hero-copy {
  max-width: 760px;
  display: grid;
  gap: 10px;

  h3 {
    margin: 0;
    color: var(--text-primary);
    font-size: 28px;
    line-height: 1.2;
  }

  p {
    margin: 0;
    color: var(--text-secondary);
    line-height: 1.6;
    font-size: 14px;
  }
}

.hero-copy-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.hero-account-panel {
  min-width: 220px;
  display: grid;
  gap: 10px;
  padding: 16px 18px;
  border-radius: 20px;
  border: 1px solid color-mix(in srgb, var(--border-soft) 90%, transparent);
  background: color-mix(in srgb, var(--surface-soft) 94%, transparent);

  span {
    color: var(--text-muted);
    font-size: 12px;
  }

  strong {
    color: var(--text-primary);
    font-size: 20px;
    line-height: 1.35;
  }

  small {
    color: var(--text-muted);
    font-size: 12px;
  }
}

.hero-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.hero-strip-item {
  min-height: 80px;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 18px;
  background: var(--surface-soft);
  border: 1px solid var(--border-soft);

  span {
    color: var(--text-muted);
    font-size: 12px;
  }

  strong {
    color: var(--text-primary);
    font-size: 16px;
    line-height: 1.4;

    &.healthy {
      color: var(--success);
    }

    &.warning {
      color: var(--warning);
    }

    &.error {
      color: var(--danger);
    }
  }
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.recommendation-summary {
  margin-bottom: 14px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.operations-card {
  margin-bottom: 14px;
  border: 1px solid var(--border-soft);
  background: linear-gradient(180deg, color-mix(in srgb, var(--surface-soft) 60%, transparent), transparent 36%), var(--surface-strong);
  box-shadow: none;
}

.service-health-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
}

.service-wall-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.service-pill {
  min-height: 68px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  position: relative;
  overflow: hidden;

  &::before {
    content: none;
  }

  .service-name {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  strong {
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: normal;
    line-height: 1.2;

    &.healthy {
      color: var(--success);
    }

    &.warning {
      color: var(--warning);
    }

    &.error {
      color: var(--danger);
    }
  }
}

.service-copy,
.service-endpoint {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.service-endpoint {
  grid-column: 2;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.25;

  span,
  small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.service-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--text-muted);

  &.healthy {
    background: var(--success);
  }

  &.warning {
    background: var(--warning);
  }

  &.error {
    background: var(--danger);
  }
}

.service-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.recommendation-list,
.briefing-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.recommendation-item,
.briefing-item {
  padding: 16px 18px;
  border-radius: 20px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    border-color: color-mix(in srgb, var(--accent) 32%, var(--border-soft));
    box-shadow: var(--shadow-soft);
  }
}

.recommendation-head,
.briefing-head {
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;

  strong {
    display: block;
    color: var(--text-primary);
  }

  span {
    color: var(--text-muted);
  }
}

.recommendation-meta {
  gap: 14px;
  margin: 10px 0;
  color: var(--text-muted);
  font-size: 13px;
  flex-wrap: wrap;
}

.recommendation-item p,
.briefing-item p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.mobile-action-grid,
.mobile-glance-grid {
  display: grid;
  gap: 12px;
}

.mobile-action-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.mobile-action-card {
  min-width: 0;
  display: grid;
  gap: 6px;
  padding: 16px;
  border: 1px solid var(--border-soft);
  border-radius: 22px;
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 10%, transparent), transparent 72%),
    var(--surface-strong);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
}

.mobile-action-card span,
.mobile-glance-card span {
  color: var(--text-muted);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.mobile-action-card strong,
.mobile-glance-card strong {
  color: var(--text-primary);
  font-size: 17px;
  line-height: 1.35;
}

.mobile-action-card small {
  color: var(--text-secondary);
  line-height: 1.5;
}

.mobile-glance-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.mobile-glance-grid.compact {
  gap: 10px;
}

.mobile-glance-card,
.mobile-feed-item {
  padding: 15px 16px;
  border-radius: 20px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
}

.mobile-feed-card {
  border: 1px solid var(--border-soft);
  background: var(--surface-strong);
  box-shadow: var(--shadow-soft);
}

.mobile-feed-list {
  display: grid;
  gap: 12px;
}

.mobile-feed-item--button {
  cursor: pointer;
}

.mobile-feed-summary {
  margin-top: 12px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.mobile-feed-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.mobile-feed-item strong {
  color: var(--text-primary);
}

.mobile-feed-item p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.65;
}

.mobile-score.up,
.mobile-score.healthy {
  color: var(--success);
}

.mobile-score.down,
.mobile-score.error {
  color: var(--danger);
}

.stat-card {
  .stat-content {
    display: flex;
    align-items: center;

    .stat-icon {
      width: 60px;
      height: 60px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-right: 16px;
    }

    .stat-info {
      .stat-label {
        color: var(--text-muted);
        font-size: 14px;
        margin-bottom: 4px;
      }

      .stat-value {
        font-size: 24px;
        font-weight: 600;
        color: var(--text-primary);

        &.up { color: var(--success); }
        &.down { color: var(--danger); }
      }

      .stat-change {
        font-size: 12px;
        margin-top: 4px;

        .up { color: var(--success); }
        .down { color: var(--danger); }
        .change-label { color: var(--text-muted); margin-left: 4px; }
      }
    }
  }
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.chart-card {
  .chart-container {
    height: 240px;
  }

  .chart {
    width: 100%;
    height: 100%;
  }
}

.market-updated-at {
  color: var(--text-muted);
  font-size: 12px;
}

.market-source-strip,
.insight-source-strip,
.briefing-source-strip,
.recommendation-source-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.market-source-strip,
.briefing-source-strip,
.recommendation-source-strip {
  margin-bottom: 12px;
}

.market-insight-list {
  display: grid;
  gap: 14px;
}

.market-insight-item {
  padding: 14px 16px;
  border: 1px solid var(--panel-stroke);
  border-radius: 18px;
  background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
}

.insight-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
}

.insight-market {
  display: flex;
  gap: 10px;
  align-items: center;

  .headline {
    font-weight: 600;
    color: var(--text-primary);
  }
}

.insight-meta {
  display: flex;
  align-items: center;
  gap: 10px;

  .status-pill {
    font-size: 12px;
    color: var(--text-muted);

    &.open {
      color: var(--success);
    }

    &.closed {
      color: var(--warning);
    }
  }

  .score {
    font-size: 12px;
    font-weight: 600;

    &.risk_on {
      color: var(--success);
    }

    &.risk_off {
      color: var(--danger);
    }

    &.balanced {
      color: var(--text-secondary);
    }
  }
}

.insight-summary {
  margin: 0 0 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.insight-source-strip {
  margin-bottom: 12px;
}

.insight-source-time {
  color: var(--text-muted);
  font-size: 12px;
}

.benchmark-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.panel-card {
  border: 1px solid var(--border-soft);
  background: var(--surface-strong);
  box-shadow: var(--shadow-soft);
}

.benchmark-chip {
  padding: 10px 12px;
  border-radius: 14px;
  background: var(--surface-soft);
  border: 1px solid var(--panel-stroke);
  display: grid;
  gap: 4px;

  .chip-name {
    font-size: 12px;
    color: var(--text-muted);
  }

  .chip-price {
    font-weight: 600;
    color: var(--text-primary);
  }

  .chip-change {
    font-size: 12px;

    &.up { color: var(--success); }
    &.down { color: var(--danger); }
  }

  .chip-source {
    font-size: 11px;
    color: var(--text-muted);
  }
}

.ai-overview {
  margin-top: 20px;
}

@media (max-width: 1280px) {
  .loading-stat-grid,
  .asset-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .hero-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .loading-panel-grid,
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .service-health-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 860px) {
  .loading-pill-row,
  .loading-stat-grid {
    grid-template-columns: 1fr;
  }

  .workbench-hero {
    padding: 22px;
  }

  .hero-main {
    flex-direction: column;
  }

  .hero-strip,
  .service-health-grid,
  .asset-overview {
    grid-template-columns: 1fr;
  }

  .hero-account-panel {
    width: 100%;
    min-width: 0;
  }

  .benchmark-strip {
    grid-template-columns: 1fr;
  }

  .service-health-grid {
    grid-template-columns: 1fr;
  }

  .dashboard-page {
    padding: 10px;
  }

  .mobile-home-stack {
    display: grid;
    gap: 14px;
    margin-bottom: 18px;
  }

  .analytics-grid,
  .desktop-snapshot-grid,
  .desktop-intelligence-grid {
    display: none;
  }
}
</style>

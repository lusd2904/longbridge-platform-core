<template>
  <div class="orders-page">
    <PageHero
      title="订单管理"
      :chips="ordersHeroChips"
      :metrics="ordersHeroMetrics"
    >
      <template #actions>
        <div class="orders-hero-actions">
          <el-select v-model="selectedAccount" placeholder="选择账户" class="orders-account-select">
            <el-option
              v-for="account in accounts"
              :key="account.id"
              :label="account.name"
              :value="account.id"
            />
          </el-select>
          <el-select v-model="filterStatus" placeholder="订单状态" class="orders-status-select">
            <el-option label="全部" value="" />
            <el-option label="待成交" value="pending" />
            <el-option label="已成交" value="filled" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            class="orders-date-range"
          />
          <el-button type="primary" @click="refreshOrders">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>
    </PageHero>

    <MetricStrip class="orders-overview-strip" :items="orderMetricItems" />

    <MobileSegmentControl
      v-if="isPhoneLayout"
      v-model="activeMobileSection"
      class="orders-mobile-rail"
      label="订单管理分段"
      :items="orderMobileSections"
    />

    <el-card v-if="!isPhoneLayout || activeMobileSection === 'overview'" class="orders-summary-card">
      <SectionCardHeader
        title="订单状态"
        :badge="orderReadModelStatus"
        :badge-type="orderReadModelStatusType"
      />
      <ReadModelSourceStrip
        class="orders-source-strip"
        label="订单状态"
        :status-text="orderReadModelStatus"
        :status-type="orderReadModelStatusType"
        :updated-at="orderReadModelUpdatedAt"
        :updated-prefix="hasStreamCoverage ? '状态于' : '快照于'"
        :tags="orderReadModelTags"
      />
      <div class="orders-filter-chip-row">
        <span v-for="chip in activeFilterChips" :key="chip" class="orders-filter-chip">
          {{ chip }}
        </span>
      </div>
    </el-card>

    <el-card v-if="!isPhoneLayout || activeMobileSection === 'orders'" class="orders-table">
      <template #header>
        <SectionCardHeader
          title="订单明细"
          :badge="`${filteredOrders.length} 条`"
          badge-type="info"
        />
      </template>
      <el-table
        v-if="!isPhoneLayout"
        :data="pagedOrders"
        style="width: 100%"
        v-loading="loading"
        :default-sort="{ prop: 'createTime', order: 'descending' }"
      >
        <el-table-column prop="orderId" label="订单号" width="180" />
        <el-table-column prop="symbol" label="股票代码" width="120" />
        <el-table-column prop="name" label="股票名称" />
        <el-table-column prop="action" label="操作" width="100">
          <template #default="{ row }">
            <el-tag :type="row.action === 'buy' ? 'success' : 'danger'">
              {{ row.action === 'buy' ? '买入' : '卖出' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="orderType" label="订单类型" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.orderType === 'market' ? '市价' : '限价' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="price" label="价格" width="120">
          <template #default="{ row }">
            {{ formatOrderPrice(row) }}
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="100" />
        <el-table-column prop="filledQuantity" label="成交数量" width="100" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="createTime" label="下单时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.createTime) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="['pending', 'submitted', 'partial'].includes(row.status)"
              type="danger"
              size="small"
              @click="cancelOrder(row)"
            >
              撤单
            </el-button>
            <el-button type="primary" size="small" link @click="viewDetail(row)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="mobile-order-list" v-loading="loading">
        <article v-for="row in pagedOrders" :key="row.orderId" class="mobile-order-card">
          <div class="mobile-order-head">
            <div>
              <strong>{{ row.symbol }}</strong>
              <span>{{ row.name || row.orderId }}</span>
            </div>
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </div>
          <div class="mobile-order-meta">
            <span>{{ row.action === 'buy' ? '买入' : '卖出' }} · {{ row.orderType === 'market' ? '市价' : '限价' }}</span>
            <span>价格 {{ formatOrderPrice(row) }}</span>
            <span>数量 {{ row.quantity }} / 成交 {{ row.filledQuantity || 0 }}</span>
            <span>{{ formatDate(row.createTime) }}</span>
          </div>
          <div class="mobile-order-actions">
            <el-button type="primary" size="small" plain @click="viewDetail(row)">详情</el-button>
            <el-button
              v-if="['pending', 'submitted', 'partial'].includes(row.status)"
              type="danger"
              size="small"
              @click="cancelOrder(row)"
            >
              撤单
            </el-button>
          </div>
        </article>
        <el-empty v-if="!pagedOrders.length && !loading" description="暂无订单" />
      </div>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          :layout="paginationLayout"
          :small="isPhoneLayout"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 订单详情对话框 -->
    <el-dialog v-model="detailVisible" title="订单详情" width="600px">
      <el-descriptions :column="2" border v-if="selectedOrder">
        <el-descriptions-item label="订单号">{{ selectedOrder.orderId }}</el-descriptions-item>
        <el-descriptions-item label="股票代码">{{ selectedOrder.symbol }}</el-descriptions-item>
        <el-descriptions-item label="股票名称">{{ selectedOrder.name }}</el-descriptions-item>
        <el-descriptions-item label="操作">
          <el-tag :type="selectedOrder.action === 'buy' ? 'success' : 'danger'">
            {{ selectedOrder.action === 'buy' ? '买入' : '卖出' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="订单类型">
          {{ selectedOrder.orderType === 'market' ? '市价单' : '限价单' }}
        </el-descriptions-item>
        <el-descriptions-item label="委托价格">{{ formatOrderPrice(selectedOrder) }}</el-descriptions-item>
        <el-descriptions-item label="委托数量">{{ selectedOrder.quantity }}</el-descriptions-item>
        <el-descriptions-item label="成交数量">{{ selectedOrder.filledQuantity }}</el-descriptions-item>
        <el-descriptions-item label="成交金额">{{ formatCurrency(selectedOrder.filledAmount) }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(selectedOrder.status)">
            {{ getStatusText(selectedOrder.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="下单时间">{{ formatDate(selectedOrder.createTime) }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ formatDate(selectedOrder.updateTime) }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Document, CircleCheck, CircleClose, Timer } from '@element-plus/icons-vue'
import { useOrderStream } from '../composables/useWebSocket.js'
import { useAdaptiveLayout } from '../composables/useAdaptiveLayout.js'
import MetricStrip from '../components/common/MetricStrip.vue'
import MobileSegmentControl from '../components/common/MobileSegmentControl.vue'
import PageHero from '../components/common/PageHero.vue'
import ReadModelSourceStrip from '../components/common/ReadModelSourceStrip.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'
import { cancelOrder as apiCancelOrder, getBrokerAccounts, getProjectedOrders } from '../api/trade.js'
import { formatCurrency as formatCurrencyValue, formatOrderPrice } from '../utils/formatters.js'
import { buildOrderProjectionReadModelSummary, formatReadModelSourceLabel } from '../utils/readModelSource.js'

const loading = ref(false)
const { isPhoneLayout } = useAdaptiveLayout()
const accounts = ref([])
const selectedAccount = ref(null)
const snapshotOrders = ref([])
const snapshotMeta = ref({
  dataSource: 'order-projection',
  snapshotAt: '',
  warnings: [],
  sources: {},
  query: {},
  realtimeOverlay: []
})
const filterStatus = ref('')
const dateRange = ref([])
const currentPage = ref(1)
const pageSize = ref(10)
const activeMobileSection = ref('overview')
const detailVisible = ref(false)
const selectedOrder = ref(null)

const {
  orders: streamedOrders,
  dataSource: streamedDataSource,
  snapshotAt: streamedSnapshotAt,
  meta: streamedMeta,
  lastReceivedAt,
  subscriptionAccountId,
  subscriptionStatus,
  isConnected: streamConnected
} = useOrderStream(selectedAccount, filterStatus, { limit: 200 })

const hasStreamCoverage = computed(() => {
  if (!lastReceivedAt.value) {
    return false
  }
  const currentAccountId = selectedAccount.value ? Number(selectedAccount.value) : null
  const streamAccount = subscriptionAccountId.value !== null && subscriptionAccountId.value !== undefined
    ? Number(subscriptionAccountId.value)
    : null
  return currentAccountId === streamAccount && String(subscriptionStatus.value || '') === String(filterStatus.value || '')
})

const activeOrders = computed(() => (hasStreamCoverage.value ? streamedOrders.value : snapshotOrders.value))
const activeOrderMeta = computed(() => {
  if (hasStreamCoverage.value) {
    return streamedMeta.value && typeof streamedMeta.value === 'object'
      ? streamedMeta.value
      : {}
  }
  return snapshotMeta.value
})
const activeSnapshotAt = computed(() => (
  activeOrderMeta.value?.snapshotAt || streamedSnapshotAt.value || snapshotMeta.value.snapshotAt || ''
))
const selectedAccountName = computed(() => {
  return accounts.value.find((account) => account.id === selectedAccount.value)?.name || ''
})
const activeDataSource = computed(() => (
  activeOrderMeta.value?.dataSource || streamedDataSource.value || snapshotMeta.value.dataSource || 'order-projection'
))
const activeOrderSources = computed(() => (
  activeOrderMeta.value?.sources && typeof activeOrderMeta.value.sources === 'object'
    ? activeOrderMeta.value.sources
    : {}
))
const activeOrderQuery = computed(() => (
  activeOrderMeta.value?.query && typeof activeOrderMeta.value.query === 'object'
    ? activeOrderMeta.value.query
    : {}
))
const orderProjectionSourceLabel = computed(() => formatReadModelSourceLabel(activeOrderSources.value.orders || 'trade_order_projections'))
const orderOverlayLabel = computed(() => {
  const overlays = Array.isArray(activeOrderMeta.value?.realtimeOverlay) ? activeOrderMeta.value.realtimeOverlay : []
  if (overlays.includes('order-stream')) {
    return '订单推送'
  }
  return ''
})
const orderReadModelSummary = computed(() => buildOrderProjectionReadModelSummary({
  meta: {
    ...activeOrderMeta.value,
    snapshotAt: hasStreamCoverage.value ? (lastReceivedAt.value || activeSnapshotAt.value) : activeSnapshotAt.value,
    dataSource: activeDataSource.value,
    query: activeOrderQuery.value,
    warnings: snapshotMeta.value.warnings || []
  },
  accountLabel: selectedAccountName.value,
  hasStreamCoverage: hasStreamCoverage.value,
  activeOrderCount: activeOrders.value.length,
  filterLabel: filterStatus.value ? getStatusText(filterStatus.value) : ''
}))
const orderReadModelStatus = computed(() => orderReadModelSummary.value.statusText)
const orderReadModelStatusType = computed(() => orderReadModelSummary.value.statusType)
const orderReadModelUpdatedAt = computed(() => (
  orderReadModelSummary.value.updatedAt ? formatDate(orderReadModelSummary.value.updatedAt) : ''
))
const orderReadModelTags = computed(() => orderReadModelSummary.value.tags || [])

const orderStats = computed(() => {
  const rows = activeOrders.value
  const pending = rows.filter(o => ['pending', 'submitted', 'partial'].includes(o.status)).length
  const filled = rows.filter(o => o.status === 'filled').length
  const cancelled = rows.filter(o => o.status === 'cancelled').length

  return [
    { title: '当前订单', value: rows.length, icon: Document, color: '#409eff' },
    { title: '待成交', value: pending, icon: Timer, color: '#e6a23c' },
    { title: '已成交', value: filled, icon: CircleCheck, color: '#67c23a' },
    { title: '已取消', value: cancelled, icon: CircleClose, color: '#909399' }
  ]
})
const orderMetricItems = computed(() => orderStats.value.map((stat) => ({
  label: stat.title,
  value: String(stat.value),
  note: stat.title === '当前订单'
    ? '当前筛选范围内的订单数量'
    : stat.title === '待成交'
      ? '仍可继续观察或撤单'
      : stat.title === '已成交'
        ? '已落地的执行记录'
        : '已终止或撤销的订单',
  tone: stat.title === '已成交'
    ? 'healthy'
    : stat.title === '待成交'
      ? 'warning'
      : stat.title === '已取消'
        ? 'error'
        : ''
})))
const ordersHeroChips = computed(() => ([
  { text: selectedAccountName.value || '未选择账户', tone: selectedAccount.value ? 'success' : 'warning' },
  { text: hasStreamCoverage.value ? '订单更新中' : '订单快照', tone: hasStreamCoverage.value ? 'success' : 'info' },
  { text: filterStatus.value ? `筛选 ${getStatusText(filterStatus.value)}` : '筛选 全部状态', tone: 'info' }
]))
const ordersHeroMetrics = computed(() => ([
  {
    label: '快照时间',
    value: activeSnapshotAt.value ? formatDate(activeSnapshotAt.value) : '--',
    note: hasStreamCoverage.value ? '状态时间' : '快照时间'
  },
  {
    label: '明细数量',
    value: `${filteredOrders.value.length} 条`,
    note: filterStatus.value ? `已按 ${getStatusText(filterStatus.value)} 收敛` : '当前筛选结果'
  },
  {
    label: '更新方式',
    value: hasStreamCoverage.value ? '实时更新' : '快照',
    note: orderProjectionSourceLabel.value
  }
]))
const activeFilterChips = computed(() => {
  const chips = [
    selectedAccountName.value || '未选择账户',
    filterStatus.value ? `状态 ${getStatusText(filterStatus.value)}` : '状态 全部'
  ]
  if (dateRange.value?.length === 2) {
    chips.push(`时间 ${formatDate(dateRange.value[0])} 至 ${formatDate(dateRange.value[1])}`)
  } else {
    chips.push('时间 最近快照')
  }
  chips.push(hasStreamCoverage.value ? '订单更新中' : '订单快照')
  return chips
})
const orderMobileSections = computed(() => ([
  { value: 'overview', label: '概览', note: orderReadModelStatus.value },
  { value: 'orders', label: '订单', note: `${filteredOrders.value.length} 条` }
]))
const paginationLayout = computed(() => (
  isPhoneLayout.value ? 'prev, pager, next' : 'total, sizes, prev, pager, next, jumper'
))

const filteredOrders = computed(() => {
  let result = activeOrders.value

  if (filterStatus.value) {
    result = result.filter(o => o.status === filterStatus.value)
  }

  if (dateRange.value && dateRange.value.length === 2) {
    const start = new Date(dateRange.value[0]).getTime()
    const end = new Date(dateRange.value[1]).getTime()
    result = result.filter(o => {
      const time = new Date(o.createTime).getTime()
      return time >= start && time <= end
    })
  }

  return result
})

const pagedOrders = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredOrders.value.slice(start, end)
})

const total = computed(() => filteredOrders.value.length)

const loadAccounts = async () => {
  try {
    const res = await getBrokerAccounts()
    accounts.value = res.data || []
    if (!selectedAccount.value && accounts.value.length > 0) {
      const defaultAccount = accounts.value.find(account => account.isDefault || account.is_default)
      selectedAccount.value = defaultAccount?.id || accounts.value[0].id
    }
  } catch (error) {
    console.error('加载账户失败:', error)
    accounts.value = []
  }
}

const loadOrders = async () => {
  if (!selectedAccount.value) {
    snapshotOrders.value = []
    snapshotMeta.value = {
      dataSource: 'order-projection',
      snapshotAt: '',
      warnings: [],
      sources: {},
      query: {},
      realtimeOverlay: []
    }
    return
  }

  loading.value = true
  try {
    const res = await getProjectedOrders({
      account_id: selectedAccount.value,
      status: filterStatus.value,
      limit: 200
    })
    snapshotOrders.value = res.data?.list || []
    snapshotMeta.value = {
      dataSource: res.data?.dataSource || 'order-projection',
      snapshotAt: res.data?.snapshotAt || '',
      warnings: res.data?.warnings || [],
      ...(res.data?.meta && typeof res.data.meta === 'object' ? res.data.meta : {})
    }
    if (snapshotMeta.value.warnings.length > 0) {
      ElMessage.warning(snapshotMeta.value.warnings[0])
    }
  } catch (error) {
    console.error('加载订单失败:', error)
    ElMessage.error('加载订单失败')
  } finally {
    loading.value = false
  }
}

const cancelOrder = async (row) => {
  try {
    await ElMessageBox.confirm('确定要撤销该订单吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })

    await apiCancelOrder(row.orderId, row.accountId || selectedAccount.value)
    ElMessage.success('撤单成功')
    await loadOrders()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('撤单失败: ' + error.message)
    }
  }
}

const viewDetail = (row) => {
  selectedOrder.value = row
  detailVisible.value = true
}

const refreshOrders = () => {
  loadOrders()
}

const handleSizeChange = (val) => {
  pageSize.value = val
  currentPage.value = 1
}

const handleCurrentChange = (val) => {
  currentPage.value = val
}

const getStatusType = (status) => {
  const types = {
    pending: 'warning',
    submitted: 'warning',
    partial: 'warning',
    filled: 'success',
    cancelled: 'info',
    rejected: 'danger'
  }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = {
    pending: '待成交',
    submitted: '已提交',
    partial: '部分成交',
    filled: '已成交',
    cancelled: '已取消',
    rejected: '已拒绝'
  }
  return texts[status] || status
}

const formatCurrency = (value) => {
  return formatCurrencyValue(value, { currency: '$' })
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString('zh-CN')
}

watch(selectedAccount, (newValue, oldValue) => {
  if (!newValue || newValue === oldValue) return
  currentPage.value = 1
  loadOrders()
})

watch(filterStatus, () => {
  currentPage.value = 1
  loadOrders()
})

watch(dateRange, () => {
  currentPage.value = 1
})

onMounted(() => {
  loadAccounts()
})
</script>

<style scoped lang="scss">
.orders-page {
  display: grid;
  gap: 18px;
  padding: 20px;
}

.orders-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.orders-account-select {
  width: 220px;
}

.orders-status-select {
  width: 140px;
}

.orders-date-range {
  min-width: min(100%, 320px);
}

.orders-summary-card,
.orders-table {
  border: 1px solid var(--panel-edge);
  background: var(--panel-surface);
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
  border-radius: 28px;
}

.orders-source-strip {
  margin-top: 16px;
}

.orders-filter-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}

.orders-filter-chip {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 14px;
  border-radius: 999px;
  border: 1px solid var(--control-border);
  background: color-mix(in srgb, var(--surface-soft) 88%, transparent);
  color: var(--text-secondary);
  font-size: 13px;
}

.orders-table {
  .pagination {
    margin-top: 20px;
    display: flex;
    justify-content: flex-end;
  }
}

.mobile-order-list {
  display: grid;
  gap: 12px;
}

.mobile-order-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
}

.mobile-order-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.mobile-order-head strong {
  display: block;
  color: var(--text-primary);
}

.mobile-order-head span {
  color: var(--text-muted);
  font-size: 12px;
}

.mobile-order-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.mobile-order-actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}

.orders-mobile-rail {
  margin-top: -4px;
}

@media (max-width: 860px) {
  .orders-page {
    padding: 16px;
  }

  .pagination {
    justify-content: center;
  }

  .orders-hero-actions,
  .orders-account-select,
  .orders-status-select,
  .orders-date-range {
    width: 100%;
  }
}
</style>

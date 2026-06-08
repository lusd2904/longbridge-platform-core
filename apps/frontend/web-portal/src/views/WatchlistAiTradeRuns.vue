<template>
  <div class="ai-trade-runs-page">
    <section class="page-header">
      <div>
        <span class="eyebrow">Watchlist AI Trade</span>
        <h2>AI交易扫描记录</h2>
        <div class="header-meta">
          <el-tag effect="plain">自选股票池</el-tag>
          <el-tag effect="plain">美股开盘任务</el-tag>
          <el-tag :type="autoTradeEnabled ? 'success' : 'info'" effect="plain">
            {{ autoTradeEnabled ? '自动交易已开启' : '自动交易未开启' }}
          </el-tag>
        </div>
      </div>
      <div class="header-actions">
        <el-select v-model="limit" class="limit-select" @change="loadRuns">
          <el-option label="最近 20 次" :value="20" />
          <el-option label="最近 50 次" :value="50" />
          <el-option label="最近 100 次" :value="100" />
        </el-select>
        <el-button :icon="Refresh" :loading="loading" type="primary" plain @click="loadRuns">刷新</el-button>
      </div>
    </section>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
    />

    <section class="metric-grid">
      <div class="metric-card">
        <span>记录数</span>
        <strong>{{ runs.length }}</strong>
      </div>
      <div class="metric-card">
        <span>已完成</span>
        <strong>{{ summary.completed }}</strong>
      </div>
      <div class="metric-card">
        <span>有机会</span>
        <strong>{{ summary.withOpportunity }}</strong>
      </div>
      <div class="metric-card">
        <span>已提交</span>
        <strong>{{ summary.submitted }}</strong>
      </div>
    </section>

    <section class="table-panel" v-loading="loading">
      <el-table
        :data="runs"
        class="runs-table"
        row-key="cycleId"
        stripe
        empty-text="暂无AI交易扫描记录"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="run-detail">
              <div class="detail-section">
                <div class="detail-title">
                  <strong>机会标的</strong>
                  <el-tag size="small" effect="plain">{{ row.opportunities.length }}</el-tag>
                </div>
                <div v-if="row.opportunities.length" class="symbol-list">
                  <div v-for="item in row.opportunities" :key="`${row.cycleId}-${item.symbol}-${item.side}`" class="symbol-item opportunity">
                    <span>{{ item.symbol }}</span>
                    <el-tag :type="sideTagType(item.side)" size="small" effect="plain">{{ sideLabel(item.side) }}</el-tag>
                    <strong>{{ formatPercent(item.confidence) }}</strong>
                    <em>{{ item.reason || item.summary || '暂无说明' }}</em>
                  </div>
                </div>
                <div v-else class="detail-empty">本次没有达到买卖条件的标的</div>
              </div>

              <div class="detail-section">
                <div class="detail-title">
                  <strong>候选快照</strong>
                  <el-tag size="small" effect="plain">{{ row.candidates.length }}</el-tag>
                </div>
                <div v-if="row.candidates.length" class="symbol-list compact">
                  <div v-for="item in row.candidates.slice(0, 12)" :key="`${row.cycleId}-${item.symbol}`" class="symbol-item">
                    <span>{{ item.symbol }}</span>
                    <el-tag :type="riskTagType(item.riskLevel)" size="small" effect="plain">{{ riskLabel(item.riskLevel) }}</el-tag>
                    <strong>{{ formatPercent(item.confidence) }}</strong>
                    <em>{{ item.reason || item.summary || '持续观察' }}</em>
                  </div>
                </div>
                <div v-else class="detail-empty">没有候选快照</div>
              </div>

              <div class="detail-section">
                <div class="detail-title">
                  <strong>跳过与下单</strong>
                  <el-tag size="small" effect="plain">{{ row.skipped.length }}</el-tag>
                </div>
                <div class="control-grid">
                  <div>
                    <span>目标持仓</span>
                    <strong>{{ formatRatio(row.positionControl.targetPortfolioRatio) }}</strong>
                  </div>
                  <div>
                    <span>最多买入</span>
                    <strong>{{ row.positionControl.maxSymbols || row.settings.maxSymbols || '--' }}</strong>
                  </div>
                  <div>
                    <span>最低置信</span>
                    <strong>{{ formatPercent(row.positionControl.minConfidence || row.settings.minConfidence) }}</strong>
                  </div>
                  <div>
                    <span>账户边界</span>
                    <strong>{{ paperBoundaryLabel(row) }}</strong>
                  </div>
                  <div>
                    <span>实时价刷新</span>
                    <strong>{{ priceRefreshLabel(row) }}</strong>
                  </div>
                  <div>
                    <span>当日订单</span>
                    <strong>{{ dailyOrderLabel(row.positionControl) }}</strong>
                  </div>
                  <div>
                    <span>当日金额</span>
                    <strong>{{ dailyNotionalLabel(row.positionControl) }}</strong>
                  </div>
                  <div>
                    <span>金额上限</span>
                    <strong>{{ dailyNotionalLimitLabel(row.positionControl) }}</strong>
                  </div>
                </div>
                <div v-if="row.skipped.length" class="skip-list">
                  <span v-for="item in row.skipped.slice(0, 8)" :key="`${row.cycleId}-${item.symbol || item.reason}`">
                    {{ item.symbol || '任务' }}：{{ item.reason || item.message || '已跳过' }}
                  </span>
                </div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="启动时间" min-width="170">
          <template #default="{ row }">
            <div class="time-cell">
              <strong>{{ formatDateTime(row.startedAt) }}</strong>
              <span>{{ row.finishedAt ? `完成 ${formatDateTime(row.finishedAt)}` : '运行中' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" effect="plain">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="触发来源" prop="source" width="130" />
        <el-table-column label="扫描结果" min-width="210">
          <template #default="{ row }">
            <div class="result-cell">
              <strong>{{ reasonLabel(row.reason) }}</strong>
              <span>{{ row.message || row.error || '--' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="标的" width="92" align="right">
          <template #default="{ row }">{{ row.targetCount }}</template>
        </el-table-column>
        <el-table-column label="已评估" width="92" align="right">
          <template #default="{ row }">{{ row.evaluatedCount }}</template>
        </el-table-column>
        <el-table-column label="机会" width="92" align="right">
          <template #default="{ row }">{{ row.opportunityCount }}</template>
        </el-table-column>
        <el-table-column label="已提交" width="92" align="right">
          <template #default="{ row }">{{ row.submittedCount }}</template>
        </el-table-column>
        <el-table-column label="仓位目标" width="110" align="right">
          <template #default="{ row }">{{ formatRatio(row.positionControl.targetPortfolioRatio || row.settings.targetPortfolioRatio) }}</template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { getWatchlistUsOpenAiTradeRuns } from '../api/analysis.js'

const loading = ref(false)
const errorMessage = ref('')
const runs = ref([])
const limit = ref(50)

const STATUS_LABEL_MAP = {
  running: '运行中',
  skipped: '已跳过',
  completed: '已完成',
  failed: '失败'
}

const REASON_LABEL_MAP = {
  executed: '已执行',
  'no-opportunities': '无机会',
  'outside-us-regular-session': '非交易时段',
  'auto-trade-disabled': '开关关闭',
  failed: '执行失败'
}

const RISK_LABEL_MAP = {
  low: '低风险',
  medium: '中风险',
  high: '高风险'
}

const summary = computed(() => ({
  completed: runs.value.filter((item) => item.status === 'completed').length,
  withOpportunity: runs.value.filter((item) => Number(item.opportunityCount || 0) > 0).length,
  submitted: runs.value.reduce((total, item) => total + Number(item.submittedCount || 0), 0)
}))

const autoTradeEnabled = computed(() => runs.value.some((item) => item.settings?.autoTradeEnabled || item.autoTrade?.enabled))

const normalizeArray = (value) => Array.isArray(value) ? value : []
const normalizeObject = (value) => value && typeof value === 'object' && !Array.isArray(value) ? value : {}

const normalizeRun = (item = {}) => ({
  ...item,
  cycleId: item.cycleId || item.cycle_id || '',
  source: item.source || 'scheduler',
  status: item.status || 'running',
  reason: item.reason || '',
  message: item.message || '',
  targetCount: Number(item.targetCount ?? item.target_count ?? 0),
  evaluatedCount: Number(item.evaluatedCount ?? item.evaluated_count ?? 0),
  opportunityCount: Number(item.opportunityCount ?? item.opportunity_count ?? 0),
  submittedCount: Number(item.submittedCount ?? item.submitted_count ?? 0),
  skippedCount: Number(item.skippedCount ?? item.skipped_count ?? 0),
  executed: Boolean(item.executed),
  settings: normalizeObject(item.settings),
  autoTrade: normalizeObject(item.autoTrade ?? item.auto_trade),
  positionControl: normalizeObject(item.positionControl ?? item.position_control),
  candidates: normalizeArray(item.candidates),
  opportunities: normalizeArray(item.opportunities),
  skipped: normalizeArray(item.skipped),
  error: item.error || '',
  startedAt: item.startedAt || item.started_at || '',
  finishedAt: item.finishedAt || item.finished_at || ''
})

const loadRuns = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const res = await getWatchlistUsOpenAiTradeRuns({ limit: limit.value })
    const payload = res?.data || {}
    const items = Array.isArray(payload.items) ? payload.items : Array.isArray(payload) ? payload : []
    runs.value = items.map(normalizeRun)
  } catch (error) {
    const message = error?.response?.data?.detail || error?.message || 'AI交易扫描记录加载失败'
    errorMessage.value = message
    ElMessage.error(message)
  } finally {
    loading.value = false
  }
}

const statusLabel = (value) => STATUS_LABEL_MAP[String(value || '').toLowerCase()] || value || '未知'
const reasonLabel = (value) => REASON_LABEL_MAP[String(value || '').toLowerCase()] || value || '待记录'
const riskLabel = (value) => RISK_LABEL_MAP[String(value || '').toLowerCase()] || '中风险'
const sideLabel = (value) => String(value || '').toUpperCase() === 'SELL' ? '卖出' : '买入'
const paperBoundaryLabel = (row) => {
  const boundary = row.autoTrade?.executionBoundary || row.executionBoundary || ''
  return String(boundary).toLowerCase().includes('paper') || row.autoTrade?.accountId ? '纸账户' : '受控'
}

const priceRefreshLabel = (row) => {
  const refresh = normalizeObject(row.autoTrade?.priceRefresh)
  if (!refresh.enabled && !row.positionControl?.refreshRealtimePrice && !row.settings?.refreshRealtimePrice) return '未开启'
  const refreshed = Number(refresh.refreshedCount || 0)
  const requested = Number(refresh.requestedCount || row.opportunityCount || 0)
  if (refresh.required && Number(refresh.skippedCount || 0) > 0) return `缺价跳过 ${refresh.skippedCount}`
  return requested ? `${refreshed}/${requested}` : '已开启'
}

const dailyOrderLabel = (positionControl = {}) => {
  const used = Number(positionControl.dailySubmittedCount ?? 0)
  const limit = Number(positionControl.maxDailySubmittedOrders ?? 0)
  return limit > 0 ? `${used}/${limit}` : `${used}/不限`
}

const formatCurrency = (value) => {
  const number = Number(value)
  if (!Number.isFinite(number)) return '--'
  return number.toLocaleString('zh-CN', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0
  })
}

const dailyNotionalLabel = (positionControl = {}) => formatCurrency(positionControl.dailySubmittedNotional)
const dailyNotionalLimitLabel = (positionControl = {}) => {
  const limit = Number(positionControl.maxDailyNotional || 0)
  return limit > 0 ? formatCurrency(limit) : '不限'
}

const statusTagType = (value) => {
  const status = String(value || '').toLowerCase()
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'skipped') return 'info'
  return 'warning'
}

const sideTagType = (value) => String(value || '').toUpperCase() === 'SELL' ? 'danger' : 'success'

const riskTagType = (value) => {
  const risk = String(value || '').toLowerCase()
  if (risk === 'low') return 'success'
  if (risk === 'high') return 'danger'
  return 'warning'
}

const formatPercent = (value) => {
  const number = Number(value)
  if (!Number.isFinite(number)) return '--'
  const normalized = number > 0 && number <= 1 ? number * 100 : number
  return `${normalized.toLocaleString('zh-CN', { maximumFractionDigits: 1 })}%`
}

const formatRatio = (value) => {
  const number = Number(value)
  if (!Number.isFinite(number)) return '--'
  return `${(number * 100).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}%`
}

const formatDateTime = (value) => {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(loadRuns)
</script>

<style scoped>
.ai-trade-runs-page {
  padding: 24px;
  background: #f6f8fb;
  color: #0f172a;
  min-height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.eyebrow {
  display: block;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  margin-bottom: 4px;
}

h2 {
  margin: 0;
  color: #0f172a;
  font-size: 26px;
  line-height: 1.2;
}

.header-meta,
.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  color: #0f172a;
}

.header-meta {
  margin-top: 10px;
}

.limit-select {
  width: 128px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0;
}

.metric-card {
  background: #fff;
  border: 1px solid #dce4ef;
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.metric-card span {
  color: #64748b;
  font-size: 13px;
}

.metric-card strong {
  color: #0f172a;
  font-size: 24px;
}

.table-panel {
  background: #fff;
  border: 1px solid #dce4ef;
  border-radius: 8px;
  padding: 8px;
}

.runs-table {
  width: 100%;
}

.ai-trade-runs-page :deep(.el-table) {
  --el-table-text-color: #1e293b;
  --el-table-header-text-color: #334155;
  --el-table-row-hover-bg-color: #f1f5f9;
  color: #1e293b;
}

.ai-trade-runs-page :deep(.el-table th.el-table__cell) {
  background: #f8fafc;
  color: #334155;
}

.ai-trade-runs-page :deep(.el-table .cell) {
  color: #1e293b;
}

.ai-trade-runs-page :deep(.el-table__inner-wrapper),
.ai-trade-runs-page :deep(.el-table__body),
.ai-trade-runs-page :deep(.el-table__body tbody),
.ai-trade-runs-page :deep(.el-table__row) {
  color: #1e293b !important;
  background: #ffffff;
}

.ai-trade-runs-page :deep(.el-table__row--striped) {
  background: #f8fafc;
}

.ai-trade-runs-page :deep(.el-button--primary.is-plain) {
  --el-button-text-color: #ffffff;
  --el-button-bg-color: #0f5f8f;
  --el-button-border-color: #0b4f78;
  --el-button-hover-text-color: #ffffff;
  --el-button-hover-bg-color: #0b4f78;
  --el-button-hover-border-color: #08415f;
  --el-button-active-bg-color: #083d59;
  --el-button-active-border-color: #083d59;
  color: #ffffff !important;
  background: #0f5f8f !important;
  border-color: #0b4f78 !important;
}

.ai-trade-runs-page :deep(.el-button--primary.is-plain span) {
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
}

.ai-trade-runs-page :deep(.el-tag) {
  color: #1e3a8a !important;
  background: #eff6ff !important;
  border-color: #bfdbfe !important;
}

.ai-trade-runs-page :deep(.el-tag__content) {
  color: #1e3a8a !important;
  -webkit-text-fill-color: #1e3a8a !important;
}

.time-cell,
.result-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.time-cell strong,
.result-cell strong {
  color: #0f172a;
  font-weight: 700;
}

.time-cell span,
.result-cell span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

.run-detail {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  padding: 12px 16px 18px 48px;
  background: #f8fafc;
}

.detail-section {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  min-width: 0;
}

.detail-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.symbol-list,
.skip-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.symbol-list.compact {
  gap: 6px;
}

.symbol-item {
  display: grid;
  grid-template-columns: minmax(80px, 1fr) auto auto;
  gap: 8px;
  align-items: center;
}

.symbol-item em {
  grid-column: 1 / -1;
  color: #64748b;
  font-size: 12px;
  font-style: normal;
  line-height: 1.4;
}

.symbol-item span,
.symbol-item strong {
  color: #0f172a;
}

.control-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.control-grid div {
  background: #f8fafc;
  border-radius: 6px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.control-grid span,
.skip-list span,
.detail-empty {
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.control-grid strong {
  color: #0f172a;
}

.skip-list {
  margin-top: 10px;
}

@media (max-width: 980px) {
  .page-header {
    flex-direction: column;
  }

  .metric-grid,
  .run-detail {
    grid-template-columns: 1fr;
  }

  .run-detail {
    padding-left: 12px;
  }
}
</style>

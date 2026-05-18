<template>
  <div class="backtest-page">
    <div class="page-header">
      <h2>策略回测</h2>
      <el-button type="primary" :icon="VideoPlay" @click="showRunDialog">
        运行回测
      </el-button>
    </div>

    <div class="backtest-container">
      <!-- 左侧：回测列表 -->
      <div class="backtest-list">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>回测历史</span>
              <el-button type="primary" link @click="refreshList">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
          </template>
          <el-table
            :data="backtests"
            style="width: 100%"
            highlight-current-row
            @row-click="selectBacktest"
            v-loading="loading"
          >
            <el-table-column prop="name" label="回测名称" min-width="150" />
            <el-table-column prop="strategyName" label="策略" width="120" />
            <el-table-column prop="totalReturn" label="总收益" width="100">
              <template #default="{ row }">
                <span :class="row.totalReturn >= 0 ? 'up' : 'down'">
                  {{ formatPercent(row.totalReturn) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="getStatusType(row.status)">
                  {{ getStatusText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="createdAt" label="时间" width="150">
              <template #default="{ row }">
                {{ formatDate(row.createdAt) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>

      <!-- 右侧：回测详情 -->
      <div class="backtest-detail" v-if="selectedBacktest">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>{{ selectedBacktest.name }}</span>
              <div class="header-actions">
                <el-button type="primary" link @click="exportReport">
                  <el-icon><Download /></el-icon> 导出报告
                </el-button>
              </div>
            </div>
          </template>

          <!-- 绩效指标 -->
          <div class="performance-metrics">
            <div class="metric-item" v-for="metric in performanceMetrics" :key="metric.label">
              <div class="metric-label">{{ metric.label }}</div>
              <div class="metric-value" :class="metric.class">{{ metric.value }}</div>
            </div>
          </div>

          <!-- 收益曲线 -->
          <div class="chart-section">
            <h4>收益曲线</h4>
            <div class="chart-container">
              <v-chart class="chart" :option="equityChartOption" autoresize />
            </div>
          </div>

          <!-- 交易记录 -->
          <div class="trades-section">
            <h4>交易记录</h4>
            <el-table :data="selectedBacktest.trades" height="300">
              <el-table-column prop="date" label="日期" width="120" />
              <el-table-column prop="symbol" label="代码" width="100" />
              <el-table-column prop="action" label="操作" width="80">
                <template #default="{ row }">
                  <el-tag :type="row.action === 'buy' ? 'success' : 'danger'" size="small">
                    {{ row.action === 'buy' ? '买入' : '卖出' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="price" label="价格" width="100">
                <template #default="{ row }">
                  {{ formatCurrency(row.price) }}
                </template>
              </el-table-column>
              <el-table-column prop="quantity" label="数量" width="80" />
              <el-table-column prop="pnl" label="盈亏">
                <template #default="{ row }">
                  <span :class="row.pnl >= 0 ? 'up' : 'down'">
                    {{ formatCurrency(row.pnl) }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </div>

      <!-- 空状态 -->
      <div class="backtest-empty" v-else>
        <el-empty description="选择一个回测查看详情" />
      </div>
    </div>

    <!-- 运行回测对话框 -->
    <el-dialog v-model="runDialogVisible" title="运行回测" width="500px">
      <el-form :model="runForm" label-width="100px">
        <el-form-item label="选择策略">
          <el-select v-model="runForm.strategyId" style="width: 100%">
            <el-option
              v-for="strategy in strategies"
              :key="strategy.id"
              :label="strategy.name"
              :value="strategy.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="股票代码">
          <el-input v-model="runForm.symbol" placeholder="输入股票代码" />
        </el-form-item>
        <el-form-item label="回测区间">
          <el-date-picker
            v-model="runForm.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="初始资金">
          <el-input-number v-model="runForm.initialCapital" :min="10000" :step="10000" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="runDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="runBacktest" :loading="running">
          开始回测
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPlay, Refresh, Download } from '@element-plus/icons-vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { getBacktestList, getStrategies, runStrategyBacktest } from '../api/analysis.js'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent])

const loading = ref(false)
const running = ref(false)
const backtests = ref([])
const strategies = ref([])
const selectedBacktest = ref(null)
const runDialogVisible = ref(false)
const runForm = ref({
  strategyId: '',
  symbol: '',
  dateRange: [],
  initialCapital: 100000
})

const SYMBOL_PATTERN = /^[A-Z0-9]+(?:\.[A-Z]{2,3})?$/
const getThemeValue = (name, fallback) => {
  if (typeof window === 'undefined') {
    return fallback
  }
  const value = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

const performanceMetrics = computed(() => {
  if (!selectedBacktest.value) return []
  const p = selectedBacktest.value.performance || {}
  
  return [
    { label: '总收益', value: formatPercent(p.totalReturn), class: p.totalReturn >= 0 ? 'up' : 'down' },
    { label: '年化收益', value: formatPercent(p.annualReturn), class: p.annualReturn >= 0 ? 'up' : 'down' },
    { label: '夏普比率', value: p.sharpeRatio?.toFixed(2) || '-', class: '' },
    { label: '最大回撤', value: formatPercent(p.maxDrawdown), class: 'down' },
    { label: '胜率', value: formatPercent(p.winRate), class: '' },
    { label: '交易次数', value: p.tradeCount || 0, class: '' }
  ]
})

const equityChartOption = computed(() => {
  if (!selectedBacktest.value?.equityCurve) return {}
  const axisColor = getThemeValue('--chart-axis', 'rgba(214, 226, 245, 0.72)')
  const gridColor = getThemeValue('--chart-grid', 'rgba(101, 150, 255, 0.12)')
  const textColor = getThemeValue('--text-secondary', '#d6e2f5')
  const tooltipBg = getThemeValue('--surface-emphasis', '#10203a')
  const tooltipText = getThemeValue('--text-primary', '#f1f7ff')
  
  return {
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: tooltipBg,
      borderColor: gridColor,
      textStyle: { color: tooltipText }
    },
    xAxis: {
      type: 'category',
      data: selectedBacktest.value.equityCurve.dates,
      axisLine: { lineStyle: { color: axisColor } },
      axisLabel: { color: textColor }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: gridColor, type: 'dashed' } },
      axisLabel: { color: textColor }
    },
    series: [{
      name: '总资产',
      data: selectedBacktest.value.equityCurve.values,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#409eff', width: 2 },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(64, 158, 255, 0.3)' },
            { offset: 1, color: 'rgba(64, 158, 255, 0.05)' }
          ]
        }
      }
    }],
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        return `日期: ${params[0].axisValue}<br/>总资产: $${params[0].value.toFixed(2)}`
      }
    }
  }
})

const loadBacktests = async () => {
  loading.value = true
  try {
    const res = await getBacktestList()
    backtests.value = res.data || []
    if (!selectedBacktest.value && backtests.value.length) {
      selectedBacktest.value = backtests.value[0]
    } else if (
      selectedBacktest.value &&
      !backtests.value.some((item) => item.id === selectedBacktest.value?.id)
    ) {
      selectedBacktest.value = backtests.value[0] || null
    }
  } catch (error) {
    console.error('加载回测列表失败:', error)
    ElMessage.error('加载回测列表失败')
  } finally {
    loading.value = false
  }
}

const loadStrategies = async () => {
  try {
    const res = await getStrategies()
    strategies.value = res.data || []
  } catch (error) {
    console.error('加载策略失败:', error)
  }
}

const selectBacktest = (row) => {
  selectedBacktest.value = row
}

const showRunDialog = () => {
  runForm.value = {
    strategyId: strategies.value[0]?.id || '',
    symbol: '',
    dateRange: [],
    initialCapital: 100000
  }
  runDialogVisible.value = true
}

const runBacktest = async () => {
  const normalizedSymbol = String(runForm.value.symbol || '').trim().toUpperCase()
  const [startDate, endDate] = Array.isArray(runForm.value.dateRange) ? runForm.value.dateRange : []

  if (!runForm.value.strategyId) {
    ElMessage.warning('请选择策略')
    return
  }
  if (!normalizedSymbol) {
    ElMessage.warning('请输入股票代码')
    return
  }
  if (!SYMBOL_PATTERN.test(normalizedSymbol)) {
    ElMessage.warning('股票代码格式不正确，例如 AAPL.US')
    return
  }
  if (!startDate || !endDate) {
    ElMessage.warning('请选择完整回测区间')
    return
  }
  if (startDate >= endDate) {
    ElMessage.warning('开始日期必须早于结束日期')
    return
  }

  running.value = true
  try {
    const data = {
      strategy_id: runForm.value.strategyId,
      symbol: normalizedSymbol,
      start_date: startDate?.toISOString().split('T')[0],
      end_date: endDate?.toISOString().split('T')[0],
      initial_capital: runForm.value.initialCapital
    }
    
    await runStrategyBacktest(data)
    ElMessage.success('回测任务已提交')
    runDialogVisible.value = false
    loadBacktests()
  } catch (error) {
    ElMessage.error('回测失败: ' + (error.businessMessage || error?.data?.error || error.message))
  } finally {
    running.value = false
  }
}

const refreshList = () => {
  loadBacktests()
}

const exportReport = () => {
  ElMessage.success('报告导出成功')
}

const getStatusType = (status) => {
  const types = { running: 'warning', completed: 'success', failed: 'danger' }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = { running: '运行中', completed: '已完成', failed: '失败' }
  return texts[status] || status
}

const formatPercent = (value) => {
  if (value === undefined || value === null) return '-'
  return (value >= 0 ? '+' : '') + value.toFixed(2) + '%'
}

const formatCurrency = (value) => {
  if (!value) return '$0.00'
  return '$' + parseFloat(value).toFixed(2)
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('zh-CN')
}

onMounted(() => {
  loadBacktests()
  loadStrategies()
})
</script>

<style scoped lang="scss">
.backtest-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  
  h2 {
    margin: 0;
    font-size: 24px;
    font-weight: 600;
  }
}

.backtest-container {
  display: grid;
  grid-template-columns: 400px 1fr;
  gap: 20px;
}

.backtest-list {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
}

.backtest-detail {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .performance-metrics {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-bottom: 24px;
    
    .metric-item {
      text-align: center;
      padding: 16px;
      background: var(--surface-soft);
      border: 1px solid var(--border-soft);
      border-radius: 8px;
      
      .metric-label {
        font-size: 14px;
        color: var(--text-secondary);
        margin-bottom: 8px;
      }
      
      .metric-value {
        font-size: 24px;
        font-weight: 600;
      }
    }
  }
  
  .chart-section {
    margin-bottom: 24px;
    
    h4 {
      margin: 0 0 16px 0;
      font-size: 16px;
      color: var(--text-primary);
    }
    
    .chart-container {
      height: 300px;
      
      .chart {
        width: 100%;
        height: 100%;
      }
    }
  }
  
  .trades-section {
    h4 {
      margin: 0 0 16px 0;
      font-size: 16px;
      color: var(--text-primary);
    }
  }
}

.backtest-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 500px;
}

.up {
  color: #67c23a;
}

.down {
  color: #f56c6c;
}
</style>

<template>
  <div class="strategy-page">
    <PageHero
      class="strategy-hero"
      title="策略管理"
      :chips="strategyHeroChips"
      :metrics="strategyHeroMetrics"
    >
      <template #actions>
        <div class="header-actions">
          <el-button type="primary" :icon="Plus" @click="showCreateDialog">
            创建规则
          </el-button>
          <el-button :icon="Timer" :loading="monitoring" @click="runMonitorNow">
            开始监控持仓
          </el-button>
        </div>
      </template>
    </PageHero>

    <MetricStrip class="strategy-overview-strip" :items="strategyOverviewItems" />

    <el-card class="template-library-card">
      <template #header>
        <SectionCardHeader
          title="策略模板库"
          :badge="templateLibraryBadge"
        >
          <template #actions>
            <div class="template-library-meta">
              <el-tag size="small" type="warning">{{ favoriteTemplates.length }} 个收藏</el-tag>
              <el-tag size="small" type="primary">{{ recentTemplates.length }} 个最近使用</el-tag>
              <el-tag size="small" type="success">{{ featuredTemplates.length }} 个推荐模板</el-tag>
            </div>
          </template>
        </SectionCardHeader>
      </template>
      <div class="template-toolbar">
        <el-input
          v-model="templateKeyword"
          placeholder="搜索模板名称、说明、标签"
          clearable
          class="template-search"
        />
        <el-select v-model="activeTemplateCategory" style="width: 180px">
          <el-option label="全部分类" value="all" />
          <el-option
            v-for="category in templateCategories"
            :key="category.value"
            :label="category.label"
            :value="category.value"
          />
        </el-select>
      </div>
      <div v-if="favoriteTemplates.length" class="template-section">
        <div class="section-heading">
          <div>
            <strong>收藏模板</strong>
          </div>
        </div>
        <div class="template-grid">
          <div v-for="template in favoriteTemplates" :key="`favorite-${template.templateCode}`" class="template-item compact">
            <div class="template-head">
              <div>
                <h3>{{ template.name }}</h3>
                <p>{{ template.summary }}</p>
              </div>
              <div class="template-head-actions">
                <el-tag size="small" effect="plain" type="warning">收藏</el-tag>
                <button
                  type="button"
                  class="favorite-btn active"
                  @click="toggleTemplateFavorite(template.templateCode)"
                >
                  <el-icon><Star /></el-icon>
                </button>
              </div>
            </div>
            <div class="template-meta">
              <span>{{ getExecutionModeName(template.executionMode) }}</span>
              <span>{{ formatExecutionConfig(template) }}</span>
            </div>
            <div class="template-actions">
              <el-button size="small" type="primary" @click="showCreateDialog(template)">使用模板</el-button>
              <el-button size="small" @click="openTemplateDrawer(template)">查看详情</el-button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="recentTemplates.length" class="template-section">
        <div class="section-heading">
          <div>
            <strong>最近使用</strong>
          </div>
        </div>
        <div class="template-grid">
          <div v-for="template in recentTemplates" :key="`recent-${template.templateCode}`" class="template-item compact">
            <div class="template-head">
              <div>
                <h3>{{ template.name }}</h3>
                <p>{{ template.summary }}</p>
              </div>
              <div class="template-head-actions">
                <el-tag size="small" effect="plain" type="primary">最近使用</el-tag>
                <button
                  type="button"
                  class="favorite-btn"
                  :class="{ active: isTemplateFavorite(template.templateCode) }"
                  @click="toggleTemplateFavorite(template.templateCode)"
                >
                  <el-icon><Star /></el-icon>
                </button>
              </div>
            </div>
            <div class="template-meta">
              <span>{{ getExecutionModeName(template.executionMode) }}</span>
              <span>{{ formatExecutionConfig(template) }}</span>
            </div>
            <div class="template-actions">
              <el-button size="small" type="primary" @click="showCreateDialog(template)">继续创建</el-button>
              <el-button size="small" @click="previewTemplate(template)">带入表单</el-button>
            </div>
          </div>
        </div>
      </div>
      <div class="template-grid compact-grid">
        <div v-for="template in compactTemplates" :key="template.templateCode" class="template-item">
          <div class="template-head">
            <div>
              <h3>{{ template.name }}</h3>
              <p>{{ template.summary }}</p>
            </div>
            <div class="template-head-actions">
              <el-tag size="small" effect="plain">{{ template.categoryLabel }}</el-tag>
              <button
                type="button"
                class="favorite-btn"
                :class="{ active: isTemplateFavorite(template.templateCode) }"
                @click="toggleTemplateFavorite(template.templateCode)"
              >
                <el-icon><Star /></el-icon>
              </button>
            </div>
          </div>
          <div class="template-meta">
            <span>{{ getExecutionModeName(template.executionMode) }}</span>
            <span>{{ formatExecutionConfig(template) }}</span>
          </div>
          <div class="template-tags">
            <el-tag v-for="tag in (template.tags || []).slice(0, 2)" :key="tag" size="small" type="info" effect="plain">
              {{ tag }}
            </el-tag>
          </div>
          <div class="template-actions">
            <el-button size="small" type="primary" @click="showCreateDialog(template)">使用模板</el-button>
            <el-button size="small" @click="openTemplateDrawer(template)">详情</el-button>
          </div>
        </div>
      </div>
      <el-empty v-if="!filteredTemplates.length" description="暂无模板" />
    </el-card>

    <!-- 策略列表 -->
    <el-card class="strategy-table-card">
      <template #header>
        <SectionCardHeader
          title="策略列表"
          :badge="`${filteredStrategies.length} / ${strategies.length} 条`"
        >
          <template #actions>
            <div class="template-library-meta">
              <el-tag size="small" type="success">{{ strategyViewLabel }}</el-tag>
            </div>
          </template>
        </SectionCardHeader>
      </template>
      <div class="strategy-toolbar">
        <div class="strategy-filter-group">
          <button
            v-for="filter in strategyFilters"
            :key="filter.value"
            type="button"
            class="filter-chip"
            :class="{ active: strategyView === filter.value }"
            @click="strategyView = filter.value"
          >
            <span>{{ filter.label }}</span>
            <strong>{{ getStrategyFilterCount(filter.value) }}</strong>
          </button>
        </div>
        <div class="strategy-toolbar-actions">
          <el-input
            v-model="strategyKeyword"
            clearable
            class="strategy-search"
            placeholder="搜索策略名称、描述或参数"
          />
          <el-select v-model="strategySort" style="width: 220px">
            <el-option
              v-for="item in strategySortOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </div>
      </div>
      <el-table class="strategy-data-table" :data="filteredStrategies" style="width: 100%" v-loading="loading">
        <template #empty>
          <div class="table-empty-state">
            <strong>当前没有匹配的策略</strong>
            <span>可以调整筛选条件，或者直接从上方模板创建新规则。</span>
          </div>
        </template>
        <el-table-column prop="name" label="策略名称" min-width="130">
          <template #default="{ row }">
            <div class="strategy-name">
              <span class="name">{{ row.name }}</span>
              <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">
                {{ row.status === 'active' ? '运行中' : '已停止' }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="策略类型" width="96">
          <template #default="{ row }">
            <el-tag size="small">{{ getStrategyTypeName(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="规则参数" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="strategy-params">
              <span>{{ formatStrategyParams(row) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="执行设置" min-width="178">
          <template #default="{ row }">
            <div class="execution-config">
              <div class="execution-mode">
                <el-tag size="small" :type="row.executionMode === 'auto' ? 'warning' : 'info'">
                  {{ getExecutionModeName(row.executionMode) }}
                </el-tag>
                <span>{{ formatExecutionConfig(row) }}</span>
              </div>
              <span class="execution-last">最近执行: {{ formatDate(row.lastExecutedAt) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="triggerCount" label="触发次数" width="82">
          <template #default="{ row }">
            {{ row.triggerCount || 0 }}
          </template>
        </el-table-column>
        <el-table-column prop="lastTriggeredAt" label="最近触发" width="146" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatDate(row.lastTriggeredAt) }}
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" label="创建时间" width="146" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatDate(row.createdAt) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210">
          <template #default="{ row }">
            <div class="table-action-buttons">
              <el-button type="primary" size="small" link @click="runBacktest(row)">
                回测
              </el-button>
              <el-button
                type="warning"
                size="small"
                link
                :loading="executingStrategyId === row.id"
                @click="runSingleStrategy(row)"
              >
                立即执行
              </el-button>
              <el-button type="success" size="small" link @click="toggleStrategy(row)">
                {{ row.status === 'active' ? '停止' : '启动' }}
              </el-button>
              <el-button type="primary" size="small" link @click="editStrategy(row)">
                编辑
              </el-button>
              <el-button type="danger" size="small" link @click="deleteStrategy(row)">
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="alerts-card">
      <template #header>
        <SectionCardHeader
          title="最近监控告警"
          :badge="monitorOverview.lastRunAt ? formatDate(monitorOverview.lastRunAt) : '尚未运行'"
        />
      </template>
      <el-table :data="monitorAlerts" style="width: 100%" empty-text="暂无告警，规则已就绪">
        <el-table-column prop="symbol" label="标的" width="120" />
        <el-table-column prop="strategyName" label="规则" width="140" />
        <el-table-column prop="message" label="触发说明" min-width="240" show-overflow-tooltip />
        <el-table-column prop="severity" label="级别" width="100">
          <template #default="{ row }">
            <el-tag :type="row.severity === 'high' ? 'danger' : 'warning'" size="small">
              {{ row.severity === 'high' ? '高' : '中' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="actionSuggested" label="建议动作" width="100" />
        <el-table-column prop="createdAt" label="时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.createdAt) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建策略对话框 -->
    <el-dialog v-model="createDialogVisible" title="创建策略" width="720px">
      <el-form :model="strategyForm" label-width="100px">
        <el-form-item label="策略名称">
          <el-input v-model="strategyForm.name" placeholder="输入策略名称" />
        </el-form-item>
        <el-form-item label="策略模板">
          <el-select
            v-model="selectedTemplateCode"
            clearable
            filterable
            placeholder="选择模板快速填充"
            style="width: 100%"
            @change="handleTemplateChange"
          >
            <el-option-group
              v-for="category in templateCategories"
              :key="category.value"
              :label="category.label"
            >
              <el-option
                v-for="item in getTemplatesByCategory(category.value)"
                :key="item.templateCode"
                :label="item.name"
                :value="item.templateCode"
              >
                <div class="template-option">
                  <span>{{ item.name }}</span>
                  <small>{{ item.summary }}</small>
                </div>
              </el-option>
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="策略类型">
          <el-select v-model="strategyForm.type" style="width: 100%" @change="handleStrategyTypeChange">
            <el-option
              v-for="item in strategyTypeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="策略描述">
          <el-input v-model="strategyForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch
            v-model="strategyEnabled"
            inline-prompt
            active-text="启用"
            inactive-text="停用"
          />
        </el-form-item>
        <el-form-item label="执行方式">
          <el-radio-group v-model="strategyForm.executionMode">
            <el-radio-button label="manual">手动执行</el-radio-button>
            <el-radio-button label="auto">自动执行</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="strategyForm.executionMode === 'auto'" label="执行频率">
          <div class="schedule-config">
            <el-input-number v-model="strategyForm.scheduleFrequency" :min="1" :step="1" />
            <span class="schedule-text">每</span>
            <el-select v-model="strategyForm.schedulePeriod" style="width: 140px">
              <el-option
                v-for="item in schedulePeriodOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
            <span class="schedule-text">执行一次</span>
          </div>
        </el-form-item>
        <el-form-item label="调度说明">
          <div class="schedule-hint">
            {{ strategyForm.executionMode === 'auto' ? formatExecutionConfig(strategyForm) : '仅在手动点击监控或后续人工触发时执行。' }}
          </div>
        </el-form-item>
        <el-form-item label="参数配置">
          <div class="param-config">
            <div v-for="(param, index) in strategyForm.params" :key="index" class="param-item">
              <el-input v-model="param.name" placeholder="参数名" style="width: 150px" />
              <el-input v-model="param.value" placeholder="参数值" style="width: 120px; margin: 0 8px" />
              <el-button type="danger" circle size="small" @click="removeParam(index)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
            <el-button type="primary" link @click="addParam">
              <el-icon><Plus /></el-icon> 添加参数
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmCreate">{{ strategyForm.id ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="templateDrawerVisible" title="模板详情" size="420px">
      <div v-if="activeTemplate" class="template-drawer">
        <div class="drawer-head">
          <div>
            <h3>{{ activeTemplate.name }}</h3>
            <p>{{ activeTemplate.summary }}</p>
          </div>
          <el-tag>{{ activeTemplate.categoryLabel }}</el-tag>
        </div>
        <div class="drawer-section">
          <div class="section-label">模板说明</div>
          <div class="section-body">{{ activeTemplate.description }}</div>
        </div>
        <div class="drawer-section">
          <div class="section-label">执行设置</div>
          <div class="section-body">
            {{ getExecutionModeName(activeTemplate.executionMode) }}，{{ formatExecutionConfig(activeTemplate) }}
          </div>
        </div>
        <div class="drawer-section">
          <div class="section-label">默认参数</div>
          <div class="drawer-params">
            <div v-for="(value, key) in activeTemplate.params || {}" :key="key" class="drawer-param-row">
              <span>{{ key }}</span>
              <strong>{{ value }}</strong>
            </div>
          </div>
        </div>
        <div class="drawer-section">
          <div class="section-label">适用标签</div>
          <div class="template-tags">
            <el-tag v-for="tag in activeTemplate.tags || []" :key="tag" size="small" type="info" effect="plain">
              {{ tag }}
            </el-tag>
          </div>
        </div>
        <div class="drawer-actions">
          <el-button type="primary" @click="showCreateDialog(activeTemplate)">使用该模板</el-button>
          <el-button @click="previewTemplate(activeTemplate)">先带入表单</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, TrendCharts, CircleCheck, CircleClose, Timer, Delete, Star } from '@element-plus/icons-vue'
import {
  getStrategies,
  getStrategyTemplates,
  createStrategy,
  updateStrategy,
  deleteStrategy as apiDeleteStrategy,
  getStrategyMonitorSummary,
  runStrategyMonitor
} from '../api/analysis.js'
import { useRouter } from 'vue-router'
import MetricStrip from '../components/common/MetricStrip.vue'
import PageHero from '../components/common/PageHero.vue'
import SectionCardHeader from '../components/common/SectionCardHeader.vue'

const router = useRouter()
const loading = ref(false)
const monitoring = ref(false)
const executingStrategyId = ref(null)
const strategies = ref([])
const monitorSummary = ref({ overview: {}, alerts: [] })
const strategyDataReady = ref(false)
const createDialogVisible = ref(false)
const templateCatalog = ref([])
const templateCategories = ref([])
const selectedTemplateCode = ref('')
const templateKeyword = ref('')
const activeTemplateCategory = ref('all')
const templateDrawerVisible = ref(false)
const activeTemplate = ref(null)
const strategyKeyword = ref('')
const strategyView = ref('all')
const strategySort = ref('created_desc')
const strategyTypeOptions = [
  { label: '固定止损', value: 'stop_loss' },
  { label: '分段止盈', value: 'take_profit' },
  { label: '仓位过重调仓', value: 'overweight_trim' },
  { label: '大盘转弱防守', value: 'market_guard' },
  { label: '自定义策略', value: 'custom' }
]
const strategyTemplates = {
  stop_loss: {
    description: '当单只持仓浮亏达到阈值时触发减仓或退出提醒。',
    executionMode: 'auto',
    scheduleFrequency: 5,
    schedulePeriod: 'minute',
    params: [{ name: 'threshold', value: 6 }, { name: 'action', value: 'SELL' }]
  },
  take_profit: {
    description: '当持仓达到目标收益后，提醒分批锁定利润。',
    executionMode: 'auto',
    scheduleFrequency: 10,
    schedulePeriod: 'minute',
    params: [{ name: 'threshold', value: 12 }, { name: 'action', value: 'REDUCE' }]
  },
  overweight_trim: {
    description: '单只标的仓位过重时提示降低集中度。',
    executionMode: 'manual',
    scheduleFrequency: 1,
    schedulePeriod: 'day',
    params: [{ name: 'threshold', value: 35 }, { name: 'action', value: 'REDUCE' }]
  },
  market_guard: {
    description: '当大盘进入风险规避阶段时，自动加强对弱势持仓的防守。',
    executionMode: 'auto',
    scheduleFrequency: 15,
    schedulePeriod: 'minute',
    params: [{ name: 'threshold', value: 0 }, { name: 'action', value: 'SELL' }]
  },
  custom: {
    description: '',
    executionMode: 'manual',
    scheduleFrequency: 1,
    schedulePeriod: 'day',
    params: [{ name: 'threshold', value: 0 }, { name: 'action', value: 'ALERT' }]
  }
}
const TEMPLATE_FAVORITES_KEY = 'strategy_template_favorites'
const TEMPLATE_RECENTS_KEY = 'strategy_template_recents'
const strategyFilters = [
  { label: '全部', value: 'all' },
  { label: '运行中', value: 'active' },
  { label: '已停止', value: 'stopped' },
  { label: '自动执行', value: 'auto' },
  { label: '手动执行', value: 'manual' }
]
const strategySortOptions = [
  { label: '按创建时间排序', value: 'created_desc' },
  { label: '按触发次数排序', value: 'trigger_desc' },
  { label: '按最近执行排序', value: 'executed_desc' },
  { label: '按最近触发排序', value: 'triggered_desc' },
  { label: '按名称排序', value: 'name_asc' }
]

const readStoredCodes = (key) => {
  if (typeof window === 'undefined') {
    return []
  }
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) || '[]')
    return Array.isArray(parsed) ? parsed.filter(Boolean) : []
  } catch {
    return []
  }
}

const persistStoredCodes = (key, values = []) => {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(key, JSON.stringify(values))
}

const favoriteTemplateCodes = ref(readStoredCodes(TEMPLATE_FAVORITES_KEY))
const recentTemplateCodes = ref(readStoredCodes(TEMPLATE_RECENTS_KEY))

const createEmptyStrategyForm = () => ({
  id: null,
  name: '',
  type: 'stop_loss',
  description: '',
  status: 'active',
  executionMode: 'manual',
  scheduleFrequency: 1,
  schedulePeriod: 'day',
  params: []
})
const strategyForm = ref(createEmptyStrategyForm())
const featuredTemplates = computed(() => templateCatalog.value.filter((item) => item.featured))
const compactTemplates = computed(() => filteredTemplates.value.slice(0, 8))
const templateLibraryBadge = computed(() => {
  const visibleCount = compactTemplates.value.length
  const totalCount = filteredTemplates.value.length
  return totalCount > visibleCount ? `展示 ${visibleCount} / ${totalCount} 个模板` : `${totalCount} 个模板`
})
const matchesTemplateFilters = (template) => {
  if (!template) {
    return false
  }
  if (activeTemplateCategory.value !== 'all' && template.category !== activeTemplateCategory.value) {
    return false
  }
  const keyword = templateKeyword.value.trim().toLowerCase()
  if (!keyword) {
    return true
  }
  const haystack = [
    template.name,
    template.summary,
    template.description,
    template.categoryLabel,
    ...(template.tags || [])
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return haystack.includes(keyword)
}
const filteredTemplates = computed(() => templateCatalog.value.filter((item) => matchesTemplateFilters(item)))
const mapTemplatesByCodes = (codes = []) => {
  const catalogMap = new Map(templateCatalog.value.map((item) => [item.templateCode, item]))
  return codes
    .map((code) => catalogMap.get(code))
    .filter((item) => item && matchesTemplateFilters(item))
}
const favoriteTemplates = computed(() => mapTemplatesByCodes(favoriteTemplateCodes.value))
const recentTemplates = computed(() => mapTemplatesByCodes(recentTemplateCodes.value))
const monitorAlerts = computed(() => monitorSummary.value?.alerts || [])
const schedulePeriodOptions = [
  { label: '分钟', value: 'minute' },
  { label: '小时', value: 'hour' },
  { label: '天', value: 'day' },
  { label: '周', value: 'week' }
]
const strategyEnabled = computed({
  get: () => strategyForm.value.status === 'active',
  set: (enabled) => {
    strategyForm.value.status = enabled ? 'active' : 'stopped'
  }
})
const monitorOverview = computed(() => monitorSummary.value?.overview || {})
const strategyViewLabel = computed(() => {
  return strategyFilters.find((item) => item.value === strategyView.value)?.label || '全部'
})
const resolveMonitorTone = (status = '') => {
  const normalized = String(status || '').toLowerCase()
  if (['running', 'active', 'success'].includes(normalized)) return 'healthy'
  if (['error', 'failed'].includes(normalized)) return 'error'
  if (['warning'].includes(normalized)) return 'warning'
  return 'info'
}
const strategyHeroChips = computed(() => ([
  {
    text: `${templateCatalog.value.length} 个模板`,
    tone: templateCatalog.value.length ? 'healthy' : 'info'
  },
  {
    text: `监控 ${monitorOverview.value.status || 'idle'}`,
    tone: resolveMonitorTone(monitorOverview.value.status)
  },
  {
    text: `${favoriteTemplates.value.length} 个收藏`,
    tone: favoriteTemplates.value.length ? 'warning' : 'info'
  }
]))

const strategyStats = computed(() => {
  const overview = monitorSummary.value?.overview || {}
  const total = strategyDataReady.value
    ? Number(overview.ruleCount ?? strategies.value.length)
    : null
  const active = strategyDataReady.value
    ? Number(overview.activeRuleCount ?? strategies.value.filter((s) => s.status === 'active').length)
    : null
  const alertCount = strategyDataReady.value ? Number(overview.alertCount ?? 0) : null
  const autoActive = strategyDataReady.value ? Number(overview.autoActiveRuleCount ?? 0) : null
  
  return [
    { title: '策略总数', value: total, icon: TrendCharts, color: 'var(--accent-strong)' },
    { title: '运行中', value: active, icon: CircleCheck, color: 'var(--success)' },
    { title: '监控告警', value: alertCount, icon: Timer, color: 'var(--warning)' },
    { title: '自动执行中', value: autoActive, icon: CircleClose, color: 'var(--danger)' }
  ]
})
const strategyHeroMetrics = computed(() => ([
  {
    label: '策略总数',
    value: strategyStats.value[0]?.value === null ? '--' : String(strategyStats.value[0]?.value || 0),
    note: '当前规则池'
  },
  {
    label: '运行中',
    value: strategyStats.value[1]?.value === null ? '--' : String(strategyStats.value[1]?.value || 0),
    note: '活动规则',
    tone: Number(strategyStats.value[1]?.value || 0) > 0 ? 'healthy' : 'info'
  },
  {
    label: '监控告警',
    value: strategyStats.value[2]?.value === null ? '--' : String(strategyStats.value[2]?.value || 0),
    note: monitorOverview.value.lastRunAt ? formatDate(monitorOverview.value.lastRunAt) : '尚未运行',
    tone: Number(strategyStats.value[2]?.value || 0) > 0 ? 'warning' : 'info'
  }
]))
const strategyOverviewItems = computed(() => ([
  {
    label: '自动策略',
    value: strategyDataReady.value ? String(monitorOverview.value.autoRuleCount ?? 0) : '--',
    note: `运行中 ${monitorOverview.value.autoActiveRuleCount || 0}`
  },
  {
    label: '手动策略',
    value: strategyDataReady.value ? String(monitorOverview.value.manualRuleCount ?? 0) : '--',
    note: `运行中 ${monitorOverview.value.manualActiveRuleCount || 0}`
  },
  {
    label: '当前监控状态',
    value: monitorOverview.value.status || 'idle',
    note: monitorOverview.value.message || '等待下一次执行',
    tone: resolveMonitorTone(monitorOverview.value.status)
  },
  {
    label: '当前视图',
    value: strategyViewLabel.value,
    note: `${filteredStrategies.value.length} / ${strategies.value.length} 条`,
    tone: strategyView.value === 'all' ? 'info' : 'healthy'
  }
]))
const toTimestamp = (value) => {
  const time = value ? new Date(value).getTime() : 0
  return Number.isFinite(time) ? time : 0
}
const filteredStrategies = computed(() => {
  const keyword = strategyKeyword.value.trim().toLowerCase()
  const list = strategies.value.filter((item) => {
    if (strategyView.value === 'active' && item.status !== 'active') {
      return false
    }
    if (strategyView.value === 'stopped' && item.status !== 'stopped') {
      return false
    }
    if (strategyView.value === 'auto' && item.executionMode !== 'auto') {
      return false
    }
    if (strategyView.value === 'manual' && item.executionMode === 'auto') {
      return false
    }
    if (!keyword) {
      return true
    }
    const params = Array.isArray(item.params)
      ? item.params.map((entry) => `${entry?.name}:${entry?.value}`).join(' ')
      : Object.entries(item.params || {}).map(([name, value]) => `${name}:${value}`).join(' ')
    const haystack = [
      item.name,
      item.description,
      item.type,
      getStrategyTypeName(item.type),
      params
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(keyword)
  })

  return [...list].sort((a, b) => {
    if (strategySort.value === 'trigger_desc') {
      return Number(b.triggerCount || 0) - Number(a.triggerCount || 0)
    }
    if (strategySort.value === 'executed_desc') {
      return toTimestamp(b.lastExecutedAt) - toTimestamp(a.lastExecutedAt)
    }
    if (strategySort.value === 'triggered_desc') {
      return toTimestamp(b.lastTriggeredAt) - toTimestamp(a.lastTriggeredAt)
    }
    if (strategySort.value === 'name_asc') {
      return String(a.name || '').localeCompare(String(b.name || ''), 'zh-CN')
    }
    return toTimestamp(b.createdAt) - toTimestamp(a.createdAt)
  })
})

const cloneTemplateParams = (params = []) => params.map((item) => ({ ...item }))
const isTemplateFavorite = (templateCode) => favoriteTemplateCodes.value.includes(templateCode)
const toggleTemplateFavorite = (templateCode) => {
  if (!templateCode) {
    return
  }
  const exists = favoriteTemplateCodes.value.includes(templateCode)
  favoriteTemplateCodes.value = exists
    ? favoriteTemplateCodes.value.filter((item) => item !== templateCode)
    : [templateCode, ...favoriteTemplateCodes.value].slice(0, 8)
  persistStoredCodes(TEMPLATE_FAVORITES_KEY, favoriteTemplateCodes.value)
}
const markTemplateUsed = (templateCode) => {
  if (!templateCode) {
    return
  }
  recentTemplateCodes.value = [templateCode, ...recentTemplateCodes.value.filter((item) => item !== templateCode)].slice(0, 6)
  persistStoredCodes(TEMPLATE_RECENTS_KEY, recentTemplateCodes.value)
}

const applyStrategyTemplate = (type, preserveName = true) => {
  const template = strategyTemplates[type] || strategyTemplates.custom
  strategyForm.value = {
    ...strategyForm.value,
    type,
    description: template.description,
    executionMode: template.executionMode,
    scheduleFrequency: template.scheduleFrequency,
    schedulePeriod: template.schedulePeriod,
    params: cloneTemplateParams(template.params),
    name: preserveName ? strategyForm.value.name : ''
  }
}

const normalizeTemplateToForm = (template) => ({
  type: template.type || 'custom',
  description: template.description || '',
  executionMode: template.executionMode || 'manual',
  scheduleFrequency: Number(template.scheduleFrequency || 1),
  schedulePeriod: template.schedulePeriod || 'day',
  params: Object.entries(template.params || {}).map(([name, value]) => ({ name, value }))
})

const applyTemplate = (template, preserveName = true) => {
  if (!template) return
  const next = normalizeTemplateToForm(template)
  strategyForm.value = {
    ...strategyForm.value,
    ...next,
    name: preserveName ? strategyForm.value.name : template.name
  }
  selectedTemplateCode.value = template.templateCode || ''
  markTemplateUsed(template.templateCode)
}

const getTemplatesByCategory = (category) => templateCatalog.value.filter((item) => item.category === category)

const loadStrategies = async () => {
  loading.value = true
  try {
    const res = await getStrategies()
    strategies.value = res.data || []
  } catch (error) {
    console.error('加载策略失败:', error)
    ElMessage.error('加载策略失败')
  } finally {
    loading.value = false
  }
}

const loadMonitorSummary = async () => {
  try {
    const res = await getStrategyMonitorSummary()
    monitorSummary.value = res.data || { overview: {}, alerts: [] }
  } catch (error) {
    console.error('加载监控摘要失败:', error)
  }
}

const loadStrategyTemplates = async () => {
  try {
    const res = await getStrategyTemplates()
    const data = res?.data || {}
    templateCatalog.value = Array.isArray(data.templates) ? data.templates : []
    templateCategories.value = Array.isArray(data.categories) ? data.categories : []
  } catch (error) {
    console.error('加载策略模板失败:', error)
    templateCatalog.value = []
    templateCategories.value = []
  }
}

const showCreateDialog = (template = null) => {
  strategyForm.value = createEmptyStrategyForm()
  if (template) {
    applyTemplate(template, false)
  } else {
    applyStrategyTemplate('stop_loss', false)
  }
  selectedTemplateCode.value = template?.templateCode || ''
  createDialogVisible.value = true
}

const handleStrategyTypeChange = (type) => {
  applyStrategyTemplate(type)
  selectedTemplateCode.value = ''
}

const handleTemplateChange = (templateCode) => {
  const template = templateCatalog.value.find((item) => item.templateCode === templateCode)
  if (template) {
    applyTemplate(template, false)
  }
}

const previewTemplate = (template) => {
  strategyForm.value = createEmptyStrategyForm()
  applyTemplate(template, false)
  createDialogVisible.value = true
}

const openTemplateDrawer = (template) => {
  activeTemplate.value = template
  templateDrawerVisible.value = true
}

const addParam = () => {
  strategyForm.value.params.push({ name: '', value: 0 })
}

const removeParam = (index) => {
  strategyForm.value.params.splice(index, 1)
}

const confirmCreate = async () => {
  try {
    if (!strategyForm.value.name?.trim()) {
      ElMessage.warning('请输入策略名称')
      return
    }
    const payload = {
      ...strategyForm.value,
      params: strategyForm.value.params
    }
    if (strategyForm.value.id) {
      await updateStrategy(strategyForm.value.id, payload)
      ElMessage.success('保存成功')
    } else {
      await createStrategy(payload)
      ElMessage.success('创建成功')
    }
    markTemplateUsed(selectedTemplateCode.value)
    createDialogVisible.value = false
    refreshData()
  } catch (error) {
      ElMessage.error('保存失败: ' + (error.message || '未知错误'))
  }
}

const runBacktest = (row) => {
  router.push({
    name: 'Backtest',
    query: { strategyId: row.id }
  })
}

const runSingleStrategy = async (row) => {
  executingStrategyId.value = row.id
  try {
    const res = await runStrategyMonitor({ strategy_id: row.id })
    const count = Number(res?.data?.alertCount || 0)
    ElMessage.success(count > 0 ? `执行完成，命中 ${count} 条提醒` : '执行完成，当前没有触发提醒')
    await refreshData()
  } catch (error) {
    ElMessage.error('执行失败: ' + (error.message || '未知错误'))
  } finally {
    executingStrategyId.value = null
  }
}

const toggleStrategy = async (row) => {
  try {
    const newStatus = row.status === 'active' ? 'stopped' : 'active'
    await updateStrategy(row.id, { status: newStatus })
    ElMessage.success(newStatus === 'active' ? '策略已启动' : '策略已停止')
    if (newStatus === 'active') {
      await runStrategyMonitor()
    }
    refreshData()
  } catch (error) {
    ElMessage.error('操作失败: ' + error.message)
  }
}

const editStrategy = (row) => {
  const params = row.params || {}
  selectedTemplateCode.value = ''
  strategyForm.value = {
    ...createEmptyStrategyForm(),
    ...row,
    params: Object.entries(params).map(([name, value]) => ({ name, value }))
  }
  createDialogVisible.value = true
}

const deleteStrategy = async (row) => {
  try {
    await ElMessageBox.confirm(`确定要删除策略 "${row.name}" 吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    await apiDeleteStrategy(row.id)
    ElMessage.success('删除成功')
    refreshData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败: ' + error.message)
    }
  }
}

const getStrategyTypeName = (type) => {
  const names = {
    stop_loss: '固定止损',
    take_profit: '分段止盈',
    overweight_trim: '仓位调仓',
    market_guard: '大盘防守',
    ma_cross: '均线交叉',
    rsi_reversion: 'RSI回归',
    momentum: '动量策略',
    custom: '自定义'
  }
  return names[type] || type
}

const formatStrategyParams = (row) => {
  const params = Array.isArray(row.params)
    ? row.params
        .filter((item) => item?.name && item?.value !== null && item?.value !== undefined && item?.value !== '')
        .slice(0, 3)
        .map((item) => `${item.name}: ${item.value}`)
    : Object.entries(row.params || {})
        .filter(([, value]) => value !== null && value !== undefined && value !== '')
        .slice(0, 3)
        .map(([name, value]) => `${name}: ${value}`)

  return params.length ? params.join(' / ') : '未配置参数'
}

const getExecutionModeName = (mode) => {
  return mode === 'auto' ? '自动执行' : '手动执行'
}

const getSchedulePeriodName = (period) => {
  return schedulePeriodOptions.find(item => item.value === period)?.label || period
}

const formatExecutionConfig = (row) => {
  if (row.executionMode !== 'auto') {
    return '仅支持手动触发'
  }
  return `每 ${row.scheduleFrequency || 1} ${getSchedulePeriodName(row.schedulePeriod || 'day')} 执行一次`
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString('zh-CN')
}

const runMonitorNow = async () => {
  monitoring.value = true
  try {
    const res = await runStrategyMonitor()
    const count = Number(res?.data?.alertCount || 0)
    ElMessage.success(count > 0 ? `监控完成，发现 ${count} 条告警` : '监控完成，当前没有触发告警')
    refreshData()
  } catch (error) {
    ElMessage.error('监控失败: ' + (error.message || '未知错误'))
  } finally {
    monitoring.value = false
  }
}

const refreshData = async () => {
  strategyDataReady.value = false
  try {
    await Promise.all([loadStrategies(), loadMonitorSummary(), loadStrategyTemplates()])
  } finally {
    strategyDataReady.value = true
  }
}

const getStrategyFilterCount = (filterValue) => {
  if (filterValue === 'active') {
    return strategies.value.filter((item) => item.status === 'active').length
  }
  if (filterValue === 'stopped') {
    return strategies.value.filter((item) => item.status === 'stopped').length
  }
  if (filterValue === 'auto') {
    return strategies.value.filter((item) => item.executionMode === 'auto').length
  }
  if (filterValue === 'manual') {
    return strategies.value.filter((item) => item.executionMode !== 'auto').length
  }
  return strategies.value.length
}

onMounted(() => {
  refreshData()
})
</script>

<style scoped lang="scss">
.strategy-page {
  --strategy-template-surface:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--surface-soft) 88%, var(--surface-emphasis) 12%),
      color-mix(in srgb, var(--surface-muted) 82%, var(--surface-strong) 18%)
    );
  --strategy-template-surface-compact:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--surface-soft) 84%, var(--surface-emphasis) 16%),
      color-mix(in srgb, var(--surface-muted) 78%, var(--surface-strong) 22%)
    );
  --strategy-template-border: color-mix(in srgb, var(--accent-strong) 20%, var(--border-soft));
  --strategy-template-border-hover: color-mix(in srgb, var(--accent) 42%, var(--border-strong));
  --strategy-template-shadow: var(--panel-inset), 0 14px 32px color-mix(in srgb, var(--surface-strong) 44%, transparent);
  --strategy-chip-bg: color-mix(in srgb, var(--accent-strong) 14%, var(--surface-soft));
  --strategy-chip-border: color-mix(in srgb, var(--accent-strong) 28%, var(--border-soft));
  --strategy-muted-chip-bg: color-mix(in srgb, var(--text-muted) 16%, var(--surface-soft));
  --strategy-muted-chip-border: color-mix(in srgb, var(--text-muted) 20%, var(--border-soft));
  padding: 20px;
}

.strategy-hero {
  margin-bottom: 20px;
}

.strategy-hero-aside {
  display: grid;
  gap: 6px;
  min-width: min(100%, 280px);
  padding: 16px 18px;
  border-radius: 22px;
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-soft) 84%, transparent);
}

.strategy-hero-aside span,
.strategy-hero-aside small {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.strategy-hero-aside strong {
  color: var(--text-emphasis);
  font-size: 18px;
}

.header-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.strategy-overview-strip {
  margin-bottom: 20px;
}

.template-library-card {
  margin-bottom: 20px;
}

.template-library-card :deep(.el-card__body) {
  padding: 14px 20px 18px;
}

.template-library-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.template-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.template-section {
  margin-bottom: 18px;
}

.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 12px;
  margin-bottom: 12px;

  strong {
    color: var(--text-primary);
    font-size: 15px;
  }

  p {
    margin: 6px 0 0;
    color: var(--text-secondary);
    font-size: 12px;
  }
}

.template-search {
  flex: 1;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(272px, 1fr));
  gap: 12px;
}

.compact-grid {
  grid-template-columns: repeat(auto-fit, minmax(248px, 1fr));
}

.template-item {
  display: flex;
  flex-direction: column;
  gap: 9px;
  min-height: 150px;
  padding: 12px !important;
  border-radius: 10px !important;
  border: 1px solid var(--strategy-template-border);
  background: var(--strategy-template-surface);
  box-shadow: var(--strategy-template-shadow);
  color: var(--text-primary);
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;

  &:hover {
    border-color: var(--strategy-template-border-hover);
    box-shadow: var(--panel-inset), 0 18px 38px color-mix(in srgb, var(--accent-strong) 16%, transparent);
    transform: translateY(-1px);
  }
}

.compact-grid .template-item {
  min-height: 138px;
  padding: 10px !important;
}

.template-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;

  > div:first-child {
    min-width: 0;
  }

  h3 {
    margin: 0;
    color: var(--text-emphasis);
    font-size: 14px !important;
    font-weight: 650;
    line-height: 1.25;
    overflow-wrap: anywhere;
  }

  p {
    margin: 5px 0 0;
    color: var(--text-secondary);
    line-height: 1.45;
    font-size: 12px;
    overflow-wrap: anywhere;
  }
}

.template-head-actions {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  flex-shrink: 0;
}

.template-head-actions :deep(.el-tag) {
  --el-tag-bg-color: var(--strategy-chip-bg);
  --el-tag-border-color: var(--strategy-chip-border);
  --el-tag-text-color: var(--accent);
  color: var(--accent);
  background: var(--strategy-chip-bg);
  border-color: var(--strategy-chip-border);
  font-weight: 600;
}

.favorite-btn {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--text-muted) 24%, var(--border-soft));
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface-muted) 82%, transparent);
  color: var(--text-secondary);
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease, color 0.18s ease;

  &:hover {
    color: var(--text-emphasis);
    background: color-mix(in srgb, var(--surface-soft) 84%, var(--surface-emphasis) 16%);
    border-color: color-mix(in srgb, var(--accent) 34%, var(--border-soft));
  }

  &.active {
    color: var(--warning);
    background: color-mix(in srgb, var(--warning) 14%, var(--surface-soft));
    border-color: color-mix(in srgb, var(--warning) 34%, var(--border-soft));
  }
}

.template-meta,
.template-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.template-meta {
  justify-content: space-between;
  flex-wrap: wrap;

  span {
    color: var(--text-secondary);
    line-height: 1.35;
  }
}

.template-actions {
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-top: auto;
}

.compact-grid .template-actions {
  gap: 6px;
}

.template-actions :deep(.el-button) {
  margin-left: 0 !important;
  border-radius: 7px;
  font-weight: 600;
}

.template-actions :deep(.el-button--primary) {
  --el-button-bg-color: var(--button-primary-bg);
  --el-button-border-color: var(--button-primary-border);
  --el-button-hover-bg-color: var(--button-primary-bg-hover);
  --el-button-hover-border-color: color-mix(in srgb, var(--accent) 42%, var(--button-primary-border));
  --el-button-text-color: var(--button-primary-text);
  background: var(--button-primary-bg);
  border-color: var(--button-primary-border);
  color: var(--button-primary-text);
}

.template-actions :deep(.el-button:not(.el-button--primary):not(.is-link)) {
  color: var(--button-secondary-text);
  background: var(--button-secondary-bg);
  border-color: var(--button-secondary-border);
}

.template-actions :deep(.el-button.is-link) {
  color: var(--button-link-color);
  padding: 4px 0;
}

.template-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.template-tags :deep(.el-tag) {
  --el-tag-bg-color: var(--strategy-muted-chip-bg);
  --el-tag-border-color: var(--strategy-muted-chip-border);
  --el-tag-text-color: var(--text-secondary);
  color: var(--text-secondary);
  background: var(--strategy-muted-chip-bg);
  border-color: var(--strategy-muted-chip-border);
}

.template-option {
  display: flex;
  flex-direction: column;
  gap: 2px;

  small {
    color: var(--text-secondary);
  }
}

.compact {
  min-height: 132px;
  background: var(--strategy-template-surface-compact);
}

.template-drawer {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.drawer-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;

  h3 {
    margin: 0;
    color: var(--text-primary);
  }

  p {
    margin: 6px 0 0;
    color: var(--text-secondary);
    line-height: 1.7;
  }
}

.drawer-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-label {
  font-size: 12px;
  color: var(--text-muted);
}

.section-body {
  color: var(--text-primary);
  line-height: 1.8;
}

.drawer-params {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-radius: 10px;
  background: var(--surface-strong);
  border: 1px solid var(--border-soft);
}

.drawer-param-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-secondary);

  strong {
    color: var(--text-primary);
  }
}

.drawer-actions {
  display: flex;
  gap: 12px;
}

.strategy-table-card {
  margin-top: 20px;
}

.strategy-table-card :deep(.el-card__body),
.alerts-card :deep(.el-card__body) {
  overflow-x: auto;
}

.strategy-data-table {
  min-width: 1120px;
}

.strategy-data-table :deep(.el-table__cell) {
  overflow: hidden;
}

.table-action-buttons {
  display: flex;
  align-items: center;
  gap: 4px 8px;
  flex-wrap: wrap;
  min-width: 0;
}

.table-action-buttons :deep(.el-button) {
  margin-left: 0 !important;
  padding: 2px 0;
  font-weight: 600;
}

.strategy-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.strategy-filter-group,
.strategy-toolbar-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}

.strategy-toolbar-actions {
  margin-left: auto;
}

.strategy-search {
  width: 280px;
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 14px;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;

  strong {
    color: var(--text-primary);
    font-size: 12px;
  }

  &.active {
    background: color-mix(in srgb, var(--accent) 12%, var(--surface-soft));
    border-color: color-mix(in srgb, var(--accent) 28%, transparent);
    color: var(--accent-strong);
  }
}

.table-empty-state {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 32px 0;
  text-align: center;

  strong {
    color: var(--text-primary);
  }

  span {
    color: var(--text-secondary);
    font-size: 13px;
  }
}

.stat-card {
  .stat-content {
    display: flex;
    align-items: center;
    
    .stat-icon {
      width: 48px;
      height: 48px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-right: 12px;
    }
    
    .stat-info {
      .stat-title {
        font-size: 14px;
        color: var(--text-secondary);
        margin-bottom: 4px;
      }
      
      .stat-value {
        font-size: 24px;
        font-weight: 600;
        color: var(--text-primary);
      }
    }
  }
}

.strategy-name {
  display: flex;
  align-items: center;
  gap: 8px;
  
  .name {
    font-weight: 600;
  }
}

.strategy-params {
  color: var(--text-secondary);
  font-size: 13px;
}

.execution-config {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.execution-mode {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
}

.execution-last,
.schedule-hint {
  color: var(--text-secondary);
  line-height: 1.6;
}

.alerts-card {
  margin-top: 20px;
}

.param-config {
  .param-item {
    display: flex;
    align-items: center;
    margin-bottom: 8px;
  }
}

.schedule-config {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.schedule-text {
  color: var(--text-secondary);
}

.up {
  color: var(--success);
}

.down {
  color: var(--danger);
}

@media (max-width: 1100px) {
  .template-grid,
  .summary-strip,
  .stats-row {
    grid-template-columns: 1fr;
  }

  .template-toolbar,
  .drawer-actions,
  .strategy-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .strategy-toolbar-actions {
    margin-left: 0;
  }

  .strategy-search {
    width: 100%;
  }
}
</style>

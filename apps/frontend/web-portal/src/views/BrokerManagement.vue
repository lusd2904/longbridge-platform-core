<!--
  券商账户管理页面
  支持多券商配置：长桥证券、老虎证券
-->
<template>
  <div class="broker-management">
    <el-card class="page-header">
      <template #header>
        <div class="header-content">
          <div class="title-section">
            <h2>券商连接</h2>
          </div>
          <el-button type="primary" @click="openAddDialog">
            <el-icon><Plus /></el-icon>
            添加账户
          </el-button>
        </div>
      </template>

      <!-- 账户统计 -->
      <div class="stats-row">
        <el-statistic title="总账户数" :value="accounts.length" />
        <el-statistic title="默认账户" :value="defaultAccount ? 1 : 0">
          <template #suffix>
            <span v-if="defaultAccount" class="default-badge">{{ defaultAccount.broker_name }}</span>
          </template>
        </el-statistic>
        <el-statistic title="活跃账户" :value="activeAccounts.length" />
      </div>

      <div class="security-summary">
        <div class="security-item">
          <span>密钥显示</span>
          <strong>不明文回显</strong>
        </div>
        <div class="security-item">
          <span>编辑规则</span>
          <strong>留空即保留原值</strong>
        </div>
        <div class="security-item">
          <span>存储方式</span>
          <strong>加密保存</strong>
        </div>
      </div>
    </el-card>

    <!-- 账户列表 -->
    <el-card class="accounts-list">
      <el-table v-if="!isPhoneLayout" :data="accounts" v-loading="loading" stripe>
        <el-table-column prop="broker_name" label="券商" min-width="120">
          <template #default="{ row }">
            <div class="broker-info">
              <el-icon :size="20" class="broker-icon">
                <OfficeBuilding v-if="row.broker_type === 'longbridge'" />
                <Money v-else-if="row.broker_type === 'tiger'" />
                <Money v-else />
              </el-icon>
              <div class="broker-details">
                <span class="broker-name">{{ row.broker_name }}</span>
                <el-tag size="small" :type="getBrokerTypeTag(row.broker_type)">
                  {{ getBrokerTypeLabel(row.broker_type) }}
                </el-tag>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="account_id" label="账户ID" min-width="150">
          <template #default="{ row }">
            <span class="account-id">{{ maskAccountId(row.account_id) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="120" align="center">
          <template #default="{ row }">
            <div class="status-column">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                {{ row.is_active ? '活跃' : '已禁用' }}
              </el-tag>
              <el-tag v-if="row.is_default" type="warning" size="small" class="default-tag">
                默认
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="连接状态" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="getConnectionStatusType(row.connectionStatus)" size="small">
              {{ getConnectionStatusLabel(row.connectionStatus) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-button 
                size="small" 
                @click="testConnection(row)"
                :loading="row.testing"
              >
                <el-icon><Connection /></el-icon>
                测试
              </el-button>
              <el-button 
                size="small" 
                type="primary" 
                @click="editAccount(row)"
              >
                <el-icon><Edit /></el-icon>
                编辑
              </el-button>
              <el-button 
                v-if="!row.is_default"
                size="small" 
                type="warning" 
                @click="setDefault(row)"
              >
                <el-icon><Star /></el-icon>
                默认
              </el-button>
              <el-button 
                size="small" 
                type="danger" 
                @click="deleteAccount(row)"
              >
                <el-icon><Delete /></el-icon>
                删除
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <div v-else class="mobile-account-list" v-loading="loading">
        <article v-for="row in accounts" :key="row.id" class="mobile-account-card">
          <div class="mobile-account-head">
            <div class="broker-info">
              <el-icon :size="20" class="broker-icon">
                <OfficeBuilding v-if="row.broker_type === 'longbridge'" />
                <Money v-else-if="row.broker_type === 'tiger'" />
                <Money v-else />
              </el-icon>
              <div class="broker-details">
                <span class="broker-name">{{ row.broker_name }}</span>
                <el-tag size="small" :type="getBrokerTypeTag(row.broker_type)">
                  {{ getBrokerTypeLabel(row.broker_type) }}
                </el-tag>
              </div>
            </div>
            <div class="status-column">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                {{ row.is_active ? '活跃' : '已禁用' }}
              </el-tag>
              <el-tag v-if="row.is_default" type="warning" size="small" class="default-tag">
                默认
              </el-tag>
            </div>
          </div>

          <div class="mobile-account-meta">
            <span>账户 {{ maskAccountId(row.account_id) }}</span>
            <span>连接 {{ getConnectionStatusLabel(row.connectionStatus) }}</span>
            <span>创建于 {{ formatDate(row.created_at) }}</span>
          </div>

          <div class="mobile-account-actions">
            <el-button size="small" @click="testConnection(row)" :loading="row.testing">测试</el-button>
            <el-button size="small" type="primary" @click="editAccount(row)">编辑</el-button>
            <el-button v-if="!row.is_default" size="small" type="warning" @click="setDefault(row)">默认</el-button>
            <el-button size="small" type="danger" @click="deleteAccount(row)">删除</el-button>
          </div>
        </article>

        <el-empty v-if="!accounts.length && !loading" description="还没有券商连接" />
      </div>
    </el-card>

    <!-- 添加/编辑账户对话框 -->
    <el-dialog
      v-model="showAddDialog"
      :title="editingAccount ? '编辑账户' : '添加账户'"
      width="600px"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form 
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="120px"
        class="broker-form"
      >
        <el-form-item label="券商类型" prop="broker_type">
          <el-radio-group v-model="form.broker_type" :disabled="!!editingAccount">
            <el-radio-button value="longbridge">
              <el-icon><OfficeBuilding /></el-icon>
              长桥证券
            </el-radio-button>
            <el-radio-button value="tiger">
              <el-icon><Money /></el-icon>
              老虎证券
            </el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- 长桥证券配置 -->
        <template v-if="form.broker_type === 'longbridge'">
          <el-divider>长桥 CLI</el-divider>
          <el-alert
            type="success"
            show-icon
            :closable="false"
            title="已切换为本地长桥 CLI 模拟账户"
            description="授权由本机长桥 CLI 接管，请保持 CLI 登录在模拟账户。"
          />
        </template>

        <!-- 老虎证券配置 -->
        <template v-if="form.broker_type === 'tiger'">
          <el-divider>老虎证券配置</el-divider>
          
          <el-form-item label="Tiger ID" prop="tiger_id">
            <el-input v-model="form.tiger_id" :placeholder="formPlaceholders.tiger_id" />
          </el-form-item>
          
          <el-form-item label="账户" prop="account">
            <el-input v-model="form.account" :placeholder="formPlaceholders.account" />
          </el-form-item>
          
          <el-form-item label="License" prop="license">
            <el-input v-model="form.license" :placeholder="formPlaceholders.license" />
          </el-form-item>
          
          <el-form-item label="私钥 (PK1)" prop="private_key_pk1">
            <el-input 
              v-model="form.private_key_pk1" 
              :placeholder="formPlaceholders.private_key_pk1"
              type="textarea"
              :rows="4"
              show-password
            />
          </el-form-item>
          
          <el-form-item label="私钥 (PK8)">
            <el-input 
              v-model="form.private_key_pk8" 
              :placeholder="formPlaceholders.private_key_pk8"
              type="textarea"
              :rows="4"
              show-password
            />
          </el-form-item>
          
          <el-form-item label="环境">
            <el-radio-group v-model="form.env">
              <el-radio-button value="PROD">生产环境</el-radio-button>
              <el-radio-button value="SANDBOX">沙箱环境</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </template>

        <el-form-item label="设为默认">
          <el-switch v-model="form.is_default" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="saveAccount" :loading="saving">
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 连接测试结果对话框 -->
    <el-dialog
      v-model="showTestResult"
      title="连接测试结果"
      width="400px"
    >
      <div class="test-result">
        <el-result
          :icon="testResult.success ? 'success' : 'error'"
          :title="testResult.success ? '连接成功' : '连接失败'"
          :sub-title="testResult.message"
        >
          <template #extra v-if="testResult.data">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="账户ID">
                {{ testResult.data.account_id }}
              </el-descriptions-item>
              <el-descriptions-item label="币种">
                {{ testResult.data.currency }}
              </el-descriptions-item>
              <el-descriptions-item label="总资产">
                {{ formatMoney(testResult.data.total_equity) }}
              </el-descriptions-item>
            </el-descriptions>
          </template>
        </el-result>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus,
  OfficeBuilding,
  Money,
  Connection,
  Edit,
  Star,
  Delete
} from '@element-plus/icons-vue'
import {
  deleteBrokerAccount,
  getBrokerAccountDetail,
  getBrokerAccounts,
  saveLongbridgeBrokerConfig,
  saveTigerBrokerConfig,
  setDefaultBrokerAccount,
  testBrokerAccountConnection
} from '../api/trade.js'
import { getPlatformBootstrap } from '../api/platform.js'
import { useAdaptiveLayout } from '../composables/useAdaptiveLayout.js'
import { setSession } from '../utils/auth.js'

// 数据
const { isPhoneLayout } = useAdaptiveLayout()
const loading = ref(false)
const accounts = ref([])
const showAddDialog = ref(false)
const showTestResult = ref(false)
const saving = ref(false)
const editingAccount = ref(null)
const testResult = ref({ success: false, message: '', data: null })
const formPlaceholders = ref({})

const formRef = ref(null)
const form = ref({
  broker_type: 'longbridge',
  tiger_id: '',
  account: '',
  license: '',
  private_key_pk1: '',
  private_key_pk8: '',
  env: 'PROD',
  is_default: false
})

const requireWhenCreating = (label, brokerType) => ({
  validator: (_rule, value, callback) => {
    const isSameBroker = form.value.broker_type === brokerType
    const isEditingCurrentBroker = Boolean(editingAccount.value && editingAccount.value.broker_type === brokerType)
    if (!isSameBroker) {
      callback()
      return
    }
    if (isEditingCurrentBroker) {
      callback()
      return
    }
    if (String(value || '').trim()) {
      callback()
      return
    }
    callback(new Error(`请输入${label}`))
  },
  trigger: 'blur'
})

// 表单验证规则
const rules = {
  broker_type: [{ required: true, message: '请选择券商类型', trigger: 'change' }],
  tiger_id: [requireWhenCreating('Tiger ID', 'tiger')],
  account: [requireWhenCreating('账户', 'tiger')],
  license: [requireWhenCreating('License', 'tiger')],
  private_key_pk1: [requireWhenCreating('私钥', 'tiger')]
}

const toBoolean = (value, fallback = false) => {
  if (value === null || value === undefined) {
    return fallback
  }
  return Boolean(value)
}

const normalizeAccountRow = (account = {}) => ({
  ...account,
  id: resolveBrokerAccountId(account),
  broker_type: account.broker_type || account.brokerType || '',
  broker_name: account.broker_name || account.brokerName || '券商账户',
  account_id: account.account_id || account.accountId || '',
  is_default: toBoolean(account.is_default ?? account.isDefault),
  is_active: toBoolean(account.is_active ?? account.isActive, true),
  connectionStatus: account.connectionStatus || 'unknown',
  testing: Boolean(account.testing)
})

const resolveBrokerAccountId = (row = {}) => {
  const primaryId = row.id ?? row.accountId ?? row.account_id ?? null
  if (primaryId === null || primaryId === undefined || primaryId === '') {
    return null
  }

  const numericId = Number(primaryId)
  if (!Number.isInteger(numericId) || numericId <= 0) {
    return null
  }

  return numericId
}

const getErrorMessage = (error, fallback) => {
  return (
    error?.data?.detail ||
    error?.response?.data?.detail ||
    error?.data?.message ||
    error?.response?.data?.message ||
    error?.response?.data?.error ||
    error?.message ||
    fallback
  )
}

// 计算属性
const defaultAccount = computed(() => {
  return accounts.value.find((account) => account.is_default || account.isDefault)
})

const activeAccounts = computed(() => {
  return accounts.value.filter((account) => account.is_active || account.isActive)
})

// 方法
const fetchAccounts = async () => {
  loading.value = true
  try {
    const res = await getBrokerAccounts()
    if (res.success) {
      accounts.value = (Array.isArray(res.data) ? res.data : []).map((account) => normalizeAccountRow(account))
    }
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '获取账户列表失败'))
  } finally {
    loading.value = false
  }
}

const openAddDialog = () => {
  resetForm()
  showAddDialog.value = true
}

const refreshSessionBootstrap = async () => {
  try {
    const bootstrap = await getPlatformBootstrap()
    if (bootstrap?.data) {
      setSession(bootstrap.data)
    }
  } catch (error) {
    console.error('刷新用户会话失败:', error)
  }
}

const testConnection = async (row) => {
  const accountId = resolveBrokerAccountId(row)
  if (accountId === null) {
    ElMessage.error('当前券商账户缺少可用 ID，无法执行测试')
    return
  }
  row.testing = true
  row.connectionStatus = 'testing'
  try {
    const res = await testBrokerAccountConnection(accountId)
    testResult.value = {
      success: Boolean(res.success),
      message: res.message || '连接成功',
      data: res.data || null
    }
    row.connectionStatus = res.success ? 'connected' : 'failed'
    showTestResult.value = true
  } catch (error) {
    testResult.value = {
      success: false,
      message: getErrorMessage(error, '连接测试失败'),
      data: null
    }
    row.connectionStatus = 'failed'
    showTestResult.value = true
  } finally {
    row.testing = false
  }
}

const editAccount = async (row) => {
  const accountId = resolveBrokerAccountId(row)
  if (accountId === null) {
    ElMessage.error('当前券商账户缺少可用 ID，无法加载详情')
    return
  }
  try {
    const res = await getBrokerAccountDetail(accountId)
    const detail = res?.data || {}
    const config = detail?.config || {}
    editingAccount.value = normalizeAccountRow(detail)
    form.value = {
      broker_type: detail.broker_type || row.broker_type,
      tiger_id: '',
      account: '',
      license: '',
      private_key_pk1: '',
      private_key_pk8: '',
      env: config.env || 'PROD',
      is_default: Boolean(detail?.is_default ?? detail?.isDefault ?? row.is_default ?? row.isDefault)
    }
    formPlaceholders.value = form.value.broker_type === 'longbridge'
      ? {}
      : {
          tiger_id: config.tiger_id_masked ? `已保存: ${config.tiger_id_masked}，留空则不修改` : '请输入Tiger ID',
          account: config.account_masked ? `已保存: ${config.account_masked}，留空则不修改` : '请输入账户ID',
          license: config.license_masked ? `已保存: ${config.license_masked}，留空则不修改` : '例如: TBNZ',
          private_key_pk1: config.has_private_key_pk1 ? '已保存，留空则不修改' : '请输入PK1格式私钥',
          private_key_pk8: config.has_private_key_pk8 ? '已保存，留空则不修改' : '请输入PK8格式私钥（可选）'
        }
    showAddDialog.value = true
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '加载账户详情失败'))
  }
}

const setDefault = async (row) => {
  const accountId = resolveBrokerAccountId(row)
  if (accountId === null) {
    ElMessage.error('当前券商账户缺少可用 ID，无法设置默认账户')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定将 ${row.broker_name || '该券商账户'} 设为默认账户吗？`,
      '确认设置',
      {
        type: 'warning',
        confirmButtonText: '设为默认',
        cancelButtonText: '取消'
      }
    )
    
    const res = await setDefaultBrokerAccount(accountId)
    if (res.success) {
      ElMessage.success('默认账户设置成功')
      await Promise.all([fetchAccounts(), refreshSessionBootstrap()])
    }
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getErrorMessage(error, '设置失败'))
    }
  }
}

const deleteAccount = async (row) => {
  const accountId = resolveBrokerAccountId(row)
  if (accountId === null) {
    ElMessage.error('当前券商账户缺少可用 ID，无法执行删除')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除 ${row.broker_name || '该券商账户'} 吗？此操作不可恢复。`,
      '确认删除',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
      }
    )
    
    const res = await deleteBrokerAccount(accountId)
    if (res.success) {
      ElMessage.success('删除成功')
      await Promise.all([fetchAccounts(), refreshSessionBootstrap()])
    }
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getErrorMessage(error, '删除失败'))
    }
  }
}

const saveAccount = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    let res
    if (form.value.broker_type === 'longbridge') {
      res = await saveLongbridgeBrokerConfig({
        account_id: resolveBrokerAccountId(editingAccount.value || {}),
        is_default: form.value.is_default
      })
    } else {
      res = await saveTigerBrokerConfig({
        account_id: resolveBrokerAccountId(editingAccount.value || {}),
        tiger_id: form.value.tiger_id,
        account: form.value.account,
        license: form.value.license,
        private_key_pk1: form.value.private_key_pk1,
        private_key_pk8: form.value.private_key_pk8,
        env: form.value.env,
        is_default: form.value.is_default
      })
    }

    if (res.success) {
      ElMessage.success(editingAccount.value ? '更新成功' : '添加成功')
      showAddDialog.value = false
      await Promise.all([fetchAccounts(), refreshSessionBootstrap()])
      resetForm()
    }
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '保存失败'))
  } finally {
    saving.value = false
  }
}

const resetForm = () => {
  editingAccount.value = null
  formPlaceholders.value = {}
  form.value = {
    broker_type: 'longbridge',
    tiger_id: '',
    account: '',
    license: '',
    private_key_pk1: '',
    private_key_pk8: '',
    env: 'PROD',
    is_default: false
  }
  formRef.value?.resetFields()
}

// 工具函数
const getBrokerTypeLabel = (type) => {
  const labels = {
    longbridge: '长桥',
    tiger: '老虎',
    interactive_brokers: '盈透'
  }
  return labels[type] || type
}

const getBrokerTypeTag = (type) => {
  const tags = {
    longbridge: 'primary',
    tiger: 'success',
    interactive_brokers: 'warning'
  }
  return tags[type] || ''
}

const getConnectionStatusLabel = (status) => {
  const labels = {
    connected: '已连接',
    failed: '失败',
    unknown: '未知',
    testing: '测试中'
  }
  return labels[status] || status
}

const getConnectionStatusType = (status) => {
  const types = {
    connected: 'success',
    failed: 'danger',
    unknown: 'info',
    testing: 'warning'
  }
  return types[status] || 'info'
}

const maskAccountId = (accountId) => {
  const normalized = String(accountId || '')
  if (!normalized || normalized.length <= 4) return '****'
  return normalized.slice(0, 2) + '****' + normalized.slice(-2)
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString('zh-CN')
}

const formatMoney = (value) => {
  if (!value) return '-'
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'USD'
  }).format(value)
}

// 生命周期
onMounted(() => {
  fetchAccounts()
})
</script>

<style scoped>
.broker-management {
  display: grid;
  gap: 20px;
}

.page-header {
  border: 1px solid var(--border-soft);
  background: var(--panel-surface);
  box-shadow: var(--shadow-strong);
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
}

.title-section h2 {
  margin: 0 0 8px 0;
  font-size: 20px;
  color: var(--text-emphasis);
}

.subtitle {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  padding: 20px 0 4px;
}

.security-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.security-item {
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid var(--border-soft);
  background: color-mix(in srgb, var(--surface-soft) 74%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--accent) 10%, transparent);
}

.security-item span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
  margin-bottom: 6px;
}

.security-item strong {
  color: var(--text-primary);
  font-size: 14px;
}

.default-badge {
  margin-left: 8px;
  padding: 2px 8px;
  background: color-mix(in srgb, var(--warning) 24%, transparent);
  color: var(--warning);
  border: 1px solid color-mix(in srgb, var(--warning) 36%, transparent);
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.accounts-list {
  border: 1px solid var(--border-soft);
  background: var(--panel-surface);
  box-shadow: var(--shadow-strong);
}

.mobile-account-list {
  display: grid;
  gap: 14px;
}

.mobile-account-card {
  padding: 18px;
  border-radius: 22px;
  border: 1px solid var(--border-soft);
  background: color-mix(in srgb, var(--surface-soft) 74%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--accent) 8%, transparent);
}

.mobile-account-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.mobile-account-meta {
  margin-top: 14px;
  display: grid;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.mobile-account-actions {
  margin-top: 16px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.broker-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.broker-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 14px;
  color: var(--accent);
  background: color-mix(in srgb, var(--surface-soft) 72%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-soft) 76%, transparent);
}

.broker-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.broker-name {
  font-weight: 500;
  color: var(--text-primary);
}

.account-id {
  font-family: monospace;
  color: var(--text-secondary);
}

.status-column {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
}

.default-tag {
  margin-top: 4px;
}

.broker-form {
  max-height: 500px;
  overflow-y: auto;
  padding-right: 8px;
}

.test-result {
  padding: 20px;
}

:deep(.el-statistic__content) {
  font-size: 24px;
  font-weight: bold;
  color: var(--text-emphasis);
}

:deep(.el-statistic__title) {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

:deep(.page-header .el-card__body),
:deep(.accounts-list .el-card__body) {
  padding: 24px;
}

:deep(.accounts-list .el-table),
:deep(.accounts-list .el-table tr),
:deep(.accounts-list .el-table th.el-table__cell),
:deep(.accounts-list .el-table td.el-table__cell) {
  background: transparent;
  color: var(--text-primary);
}

:deep(.accounts-list .el-table__inner-wrapper::before) {
  background: var(--table-frame);
}

:deep(.accounts-list .el-table th.el-table__cell) {
  background: color-mix(in srgb, var(--surface-soft) 74%, transparent);
  color: var(--text-secondary);
}

:deep(.accounts-list .el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: color-mix(in srgb, var(--surface-soft) 42%, transparent);
}

:deep(.accounts-list .el-table__body tr:hover > td.el-table__cell) {
  background: var(--table-row-hover);
}

:deep(.accounts-list .el-table td.el-table__cell),
:deep(.accounts-list .el-table th.el-table__cell.is-leaf) {
  border-bottom: 1px solid var(--table-divider);
}

:deep(.broker-management .el-dialog) {
  border: 1px solid var(--border-soft);
  border-radius: 24px;
  overflow: hidden;
  background: var(--chrome-surface);
  box-shadow: var(--shadow-strong);
}

:deep(.broker-management .el-dialog__header),
:deep(.broker-management .el-dialog__body),
:deep(.broker-management .el-dialog__footer) {
  background: transparent;
}

:deep(.broker-management .el-dialog__title),
:deep(.broker-management .el-form-item__label),
:deep(.broker-management .el-divider__text) {
  color: var(--text-primary);
}

:deep(.broker-management .el-input__wrapper),
:deep(.broker-management .el-textarea__inner) {
  background: color-mix(in srgb, var(--surface-soft) 76%, transparent);
  box-shadow: 0 0 0 1px var(--border-soft) inset;
  color: var(--text-primary);
}

:deep(.broker-management .el-input__inner),
:deep(.broker-management .el-textarea__inner) {
  color: var(--text-primary);
}

:deep(.broker-management .el-radio-button__inner),
:deep(.broker-management .el-button:not(.el-button--primary)) {
  background: color-mix(in srgb, var(--surface-soft) 74%, transparent);
  border-color: var(--border-soft);
  color: var(--text-primary);
}

:deep(.broker-management .el-button--danger) {
  color: var(--el-color-white);
}

:deep(.broker-management .el-button--danger:not(.is-link):not(.is-text)) {
  background-image: linear-gradient(135deg, color-mix(in srgb, var(--danger) 88%, white 12%), color-mix(in srgb, var(--danger) 76%, var(--warning) 8%));
  border-color: color-mix(in srgb, var(--danger) 48%, transparent);
  color: var(--el-color-white);
}

:deep(.broker-management .el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: var(--button-primary-bg);
  border-color: transparent;
  color: var(--button-primary-text);
}

:deep(.broker-management .el-message-box__title),
:deep(.broker-management .el-message-box__content),
:deep(.broker-management .el-message-box__message),
:deep(.broker-management .el-message-box__message p) {
  color: var(--text-primary);
}

@media (max-width: 960px) {
  .header-content {
    flex-direction: column;
    gap: 16px;
  }

  .stats-row,
  .security-summary {
    grid-template-columns: 1fr;
    gap: 16px;
  }
}
</style>

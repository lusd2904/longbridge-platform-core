<!--
  系统配置管理页面
  合并原配置管理和券商账户管理功能
-->
<template>
  <div class="config-management">
    <div class="page-header">
      <h1>系统配置</h1>
    </div>

    <el-tabs type="border-card" v-model="activeTab">
      <!-- 券商账户配置 -->
      <el-tab-pane label="券商账户" name="broker">
        <div class="broker-section">
          <div class="section-header">
            <div class="stats-row">
              <el-statistic title="总账户数" :value="accounts.length" />
              <el-statistic title="默认账户" :value="defaultAccount ? 1 : 0">
                <template #suffix>
                  <span v-if="defaultAccount" class="default-badge">{{ defaultAccount.broker_name }}</span>
                </template>
              </el-statistic>
              <el-statistic title="活跃账户" :value="activeAccounts.length" />
            </div>
            <el-button type="primary" @click="showAddBrokerDialog = true">
              <el-icon><Plus /></el-icon>
              添加券商账户
            </el-button>
          </div>

          <el-table :data="accounts" v-loading="brokerLoading" stripe>
            <el-table-column prop="broker_name" label="券商" min-width="120">
              <template #default="{ row }">
                <div class="broker-info">
                  <el-icon :size="20" class="broker-icon">
                    <OfficeBuilding v-if="row.broker_type === 'longbridge'" />
                    <Money v-else-if="row.broker_type === 'tiger'" />
                    <Wallet v-else />
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
                    @click="testBrokerConnection(row)"
                    :loading="row.testing"
                  >
                    <el-icon><Connection /></el-icon>
                    测试
                  </el-button>
                  <el-button 
                    size="small" 
                    type="primary" 
                    @click="editBrokerAccount(row)"
                  >
                    <el-icon><Edit /></el-icon>
                    编辑
                  </el-button>
                  <el-button 
                    v-if="!row.is_default"
                    size="small" 
                    type="warning" 
                    @click="setDefaultBroker(row)"
                  >
                    <el-icon><Star /></el-icon>
                    默认
                  </el-button>
                  <el-button 
                    size="small" 
                    type="danger" 
                    @click="deleteBrokerAccount(row)"
                  >
                    <el-icon><Delete /></el-icon>
                    删除
                  </el-button>
                </el-button-group>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- AI 配置 -->
      <el-tab-pane label="AI 配置" name="ai">
        <el-card class="config-card">
          <template #header>
            <div class="card-header">
              <span>AI 模型配置</span>
              <el-button type="primary" size="small" @click="saveConfig" :loading="loading">
                <el-icon><Check /></el-icon>
                保存配置
              </el-button>
            </div>
          </template>

          <el-form :model="form" label-width="150px" class="config-form">
            <el-form-item label="AI API URL">
              <el-input v-model="form.ai_url" placeholder="请输入 AI 模型 API URL" />
            </el-form-item>
            <el-form-item label="AI 超时时间">
              <el-input-number v-model="form.ai_timeout" :min="10" :max="300" :step="10" />
              <span class="unit">秒</span>
            </el-form-item>
            <el-form-item label="线程数">
              <el-input-number v-model="form.num_thread" :min="1" :max="16" :step="1" />
            </el-form-item>
            <el-form-item label="生成温度">
              <el-slider v-model="form.temperature" :min="0" :max="1" :step="0.1" />
              <span class="slider-value">{{ form.temperature }}</span>
            </el-form-item>
            <el-form-item label="预测数量">
              <el-input-number v-model="form.num_predict" :min="50" :max="500" :step="50" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- 策略配置 -->
      <el-tab-pane label="策略配置" name="strategy">
        <el-card class="config-card">
          <template #header>
            <div class="card-header">
              <span>交易策略配置</span>
              <el-button type="primary" size="small" @click="saveConfig" :loading="loading">
                <el-icon><Check /></el-icon>
                保存配置
              </el-button>
            </div>
          </template>

          <el-form :model="form" label-width="180px" class="config-form">
            <el-form-item label="RSI 超买阈值">
              <el-input-number v-model="form.rsi_over_buy" :min="50" :max="90" :step="5" />
            </el-form-item>
            <el-form-item label="RSI 超卖阈值">
              <el-input-number v-model="form.rsi_over_sell" :min="10" :max="50" :step="5" />
            </el-form-item>
            <el-form-item label="扫描间隔">
              <el-input-number v-model="form.scan_interval" :min="60" :max="3600" :step="60" />
              <span class="unit">秒</span>
            </el-form-item>
            <el-form-item label="启用撤单策略">
              <el-switch v-model="form.enable_cancel_strategy" />
            </el-form-item>
            <el-form-item label="订单超时阈值">
              <el-input-number v-model="form.cancel_order_threshold_seconds" :min="60" :max="1800" :step="30" />
              <span class="unit">秒</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 添加/编辑券商账户对话框 -->
    <el-dialog
      v-model="showAddBrokerDialog"
      :title="editingBroker ? '编辑券商账户' : '添加券商账户'"
      width="600px"
      destroy-on-close
    >
      <el-form ref="brokerFormRef" :model="brokerForm" :rules="brokerRules" label-width="120px">
        <el-form-item label="券商类型" prop="broker_type">
          <el-radio-group v-model="brokerForm.broker_type" :disabled="!!editingBroker">
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
        <template v-if="brokerForm.broker_type === 'longbridge'">
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
        <template v-if="brokerForm.broker_type === 'tiger'">
          <el-divider>老虎证券配置</el-divider>
          <el-form-item label="Tiger ID" prop="tiger_id">
            <el-input v-model="brokerForm.tiger_id" placeholder="请输入Tiger ID" />
          </el-form-item>
          <el-form-item label="账户" prop="account">
            <el-input v-model="brokerForm.account" placeholder="请输入账户ID" />
          </el-form-item>
          <el-form-item label="License" prop="license">
            <el-input v-model="brokerForm.license" placeholder="例如: TBNZ" />
          </el-form-item>
          <el-form-item label="私钥 (PK1)" prop="private_key_pk1">
            <el-input v-model="brokerForm.private_key_pk1" placeholder="请输入PK1格式私钥" type="textarea" :rows="4" show-password />
          </el-form-item>
          <el-form-item label="私钥 (PK8)">
            <el-input v-model="brokerForm.private_key_pk8" placeholder="请输入PK8格式私钥（可选）" type="textarea" :rows="4" show-password />
          </el-form-item>
          <el-form-item label="环境">
            <el-radio-group v-model="brokerForm.env">
              <el-radio-button value="PROD">生产环境</el-radio-button>
              <el-radio-button value="SANDBOX">沙箱环境</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </template>

        <el-form-item label="设为默认">
          <el-switch v-model="brokerForm.is_default" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showAddBrokerDialog = false">取消</el-button>
        <el-button type="primary" @click="saveBrokerAccount" :loading="brokerSaving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 连接测试结果对话框 -->
    <el-dialog v-model="showTestResult" title="连接测试结果" width="400px">
      <div class="test-result">
        <el-result
          :icon="testResult.success ? 'success' : 'error'"
          :title="testResult.success ? '连接成功' : '连接失败'"
          :sub-title="testResult.message"
        >
          <template #extra v-if="testResult.data">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="账户ID">{{ testResult.data.account_id }}</el-descriptions-item>
              <el-descriptions-item label="币种">{{ testResult.data.currency }}</el-descriptions-item>
              <el-descriptions-item label="现金">{{ formatMoney(testResult.data.cash, testResult.data.currency) }}</el-descriptions-item>
              <el-descriptions-item label="持仓市值">{{ formatMoney(testResult.data.market_value, testResult.data.currency) }}</el-descriptions-item>
              <el-descriptions-item label="总资产">{{ formatMoney(testResult.data.total_equity, testResult.data.currency) }}</el-descriptions-item>
              <el-descriptions-item label="购买力">{{ formatMoney(testResult.data.buying_power, testResult.data.currency) }}</el-descriptions-item>
            </el-descriptions>
          </template>
        </el-result>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Check, OfficeBuilding, Money, Wallet, Connection, Edit, Star, Delete
} from '@element-plus/icons-vue'
import { getConfig, updateConfig } from '../api/user.js'
import request from '../utils/request'

// 当前激活的标签页
const activeTab = ref('broker')

// ============ 系统配置 ============
const loading = ref(false)
const message = ref('')
const messageType = ref('success')

const form = reactive({
  ai_url: '',
  ai_timeout: 120,
  num_thread: 4,
  temperature: 0.4,
  num_predict: 100,
  rsi_over_buy: 70,
  rsi_over_sell: 30,
  scan_interval: 600,
  enable_cancel_strategy: true,
  cancel_order_threshold_seconds: 300
})

// ============ 券商账户 ============
const brokerLoading = ref(false)
const accounts = ref([])
const showAddBrokerDialog = ref(false)
const showTestResult = ref(false)
const brokerSaving = ref(false)
const editingBroker = ref(null)
const testResult = ref({ success: false, message: '', data: null })

const brokerFormRef = ref(null)
const brokerForm = reactive({
  broker_type: 'longbridge',
  tiger_id: '',
  account: '',
  license: '',
  private_key_pk1: '',
  private_key_pk8: '',
  env: 'PROD',
  is_default: false
})

const brokerRules = {
  broker_type: [{ required: true, message: '请选择券商类型', trigger: 'change' }],
  tiger_id: [{ required: true, message: '请输入Tiger ID', trigger: 'blur' }],
  account: [{ required: true, message: '请输入账户', trigger: 'blur' }],
  license: [{ required: true, message: '请输入License', trigger: 'blur' }],
  private_key_pk1: [{ required: true, message: '请输入私钥', trigger: 'blur' }]
}

// 计算属性
const defaultAccount = computed(() => accounts.value.find(a => a.is_default))
const activeAccounts = computed(() => accounts.value.filter(a => a.is_active))

// ============ 方法 ============

// 获取系统配置
const fetchConfig = async () => {
  try {
    loading.value = true
    const res = await getConfig()
    if (res.success && res.data) {
      Object.assign(form, res.data)
    }
  } catch (error) {
    console.error('获取配置失败:', error)
    ElMessage.error('获取配置失败')
  } finally {
    loading.value = false
  }
}

// 保存系统配置
const saveConfig = async () => {
  try {
    loading.value = true
    const res = await updateConfig({ configs: form })
    if (res.success) {
      message.value = res.message || '配置保存成功'
      messageType.value = 'success'
      ElMessage.success('配置保存成功')
    } else {
      message.value = res.error || '配置保存失败'
      messageType.value = 'error'
      ElMessage.error('配置保存失败')
    }
  } catch (error) {
    console.error('保存配置失败:', error)
    ElMessage.error('保存配置失败')
  } finally {
    loading.value = false
  }
}

// 获取券商账户列表
const fetchBrokerAccounts = async () => {
  brokerLoading.value = true
  try {
    const res = await request.get('/broker/accounts')
    if (res.success) {
      accounts.value = res.data.map(a => ({
        ...a,
        connectionStatus: 'unknown',
        testing: false
      }))
    }
  } catch (error) {
    ElMessage.error('获取账户列表失败')
  } finally {
    brokerLoading.value = false
  }
}

// 测试券商连接
const testBrokerConnection = async (row) => {
  row.testing = true
  try {
    const res = await request.post(`/broker/accounts/${row.id}/test`)
    console.log('API响应:', res)
    console.log('API数据:', res.data)
    testResult.value = { success: res.success, message: res.message, data: res.data }
    row.connectionStatus = res.success ? 'connected' : 'failed'
    showTestResult.value = true
  } catch (error) {
    console.error('连接测试错误:', error)
    testResult.value = { success: false, message: error.message || '连接测试失败', data: null }
    row.connectionStatus = 'failed'
    showTestResult.value = true
  } finally {
    row.testing = false
  }
}

// 编辑券商账户
const editBrokerAccount = async (row) => {
  editingBroker.value = row
  
  // 先重置表单
  Object.assign(brokerForm, {
    broker_type: row.broker_type,
    tiger_id: '',
    account: '',
    license: '',
    private_key_pk1: '',
    private_key_pk8: '',
    env: 'PROD',
    is_default: row.is_default
  })
  
  showAddBrokerDialog.value = true
  
  // 从API获取完整配置
  try {
    const res = await request.get(`/broker/accounts/${row.id}`)
    if (res.success && res.data) {
      const data = res.data
      const config = data.config || {}
      
      // 根据券商类型填充配置
      if (data.broker_type === 'tiger') {
        Object.assign(brokerForm, {
          tiger_id: config.tiger_id || '',
          account: config.account || '',
          license: config.license || '',
          private_key_pk1: config.private_key_pk1 || '',
          private_key_pk8: config.private_key_pk8 || '',
          env: config.env || 'PROD'
        })
      }
    }
  } catch (error) {
    console.error('获取账户详情失败:', error)
    ElMessage.error('获取账户详情失败')
  }
}

// 设置默认券商
const setDefaultBroker = async (row) => {
  try {
    await ElMessageBox.confirm(`确定将 ${row.broker_name} 设为默认账户吗？`, '确认设置', { type: 'warning' })
    const res = await request.post(`/broker/accounts/${row.id}/default`)
    if (res.success) {
      ElMessage.success('默认账户设置成功')
      fetchBrokerAccounts()
    }
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('设置失败')
  }
}

// 删除券商账户
const deleteBrokerAccount = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除 ${row.broker_name} 账户吗？`, '确认删除', { type: 'danger' })
    const res = await request.delete(`/broker/accounts/${row.id}`)
    if (res.success) {
      ElMessage.success('删除成功')
      fetchBrokerAccounts()
    }
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('删除失败')
  }
}

// 保存券商账户
const saveBrokerAccount = async () => {
  const valid = await brokerFormRef.value.validate().catch(() => false)
  if (!valid) return

  brokerSaving.value = true
  try {
    let res
    if (brokerForm.broker_type === 'longbridge') {
      res = await request.post('/broker/longbridge/config', {
        is_default: brokerForm.is_default
      })
    } else {
      res = await request.post('/broker/tiger/config', {
        tiger_id: brokerForm.tiger_id,
        account: brokerForm.account,
        license: brokerForm.license,
        private_key_pk1: brokerForm.private_key_pk1,
        private_key_pk8: brokerForm.private_key_pk8,
        env: brokerForm.env,
        is_default: brokerForm.is_default
      })
    }

    if (res.success) {
      ElMessage.success(editingBroker.value ? '更新成功' : '添加成功')
      showAddBrokerDialog.value = false
      fetchBrokerAccounts()
      resetBrokerForm()
    }
  } catch (error) {
    ElMessage.error(error.message || '保存失败')
  } finally {
    brokerSaving.value = false
  }
}

const resetBrokerForm = () => {
  editingBroker.value = null
  Object.assign(brokerForm, {
    broker_type: 'longbridge',
    tiger_id: '',
    account: '',
    license: '',
    private_key_pk1: '',
    private_key_pk8: '',
    env: 'PROD',
    is_default: false
  })
  brokerFormRef.value?.resetFields()
}

// 工具函数
const getBrokerTypeLabel = (type) => ({ longbridge: '长桥', tiger: '老虎', interactive_brokers: '盈透' }[type] || type)
const getBrokerTypeTag = (type) => ({ longbridge: 'primary', tiger: 'success', interactive_brokers: 'warning' }[type] || '')
const getConnectionStatusLabel = (status) => ({ connected: '已连接', failed: '失败', unknown: '未知', testing: '测试中' }[status] || status)
const getConnectionStatusType = (status) => ({ connected: 'success', failed: 'danger', unknown: 'info', testing: 'warning' }[status] || 'info')
const maskAccountId = (accountId) => !accountId || accountId.length <= 4 ? '****' : accountId.slice(0, 2) + '****' + accountId.slice(-2)
const formatDate = (date) => !date ? '-' : new Date(date).toLocaleString('zh-CN')
const formatMoney = (value, currency = 'USD') => {
  if (value === null || value === undefined || value === '') return '-'
  // 强制转换为数字，避免字符串拼接
  const numValue = Number(value)
  if (isNaN(numValue)) return '-'
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: currency || 'USD' }).format(numValue)
}

// 生命周期
onMounted(() => {
  fetchConfig()
  fetchBrokerAccounts()
})
</script>

<style scoped lang="scss">
.config-management {
  padding: 24px;
  min-height: calc(100vh - 70px);
  background: #f5f7fa;
}

.page-header {
  margin-bottom: 24px;
  h1 {
    font-size: 24px;
    font-weight: 600;
    color: #1a1f2e;
    margin-bottom: 8px;
  }
  p {
    font-size: 14px;
    color: #666;
  }
}

.broker-section {
  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    padding: 20px;
    background: #fff;
    border-radius: 8px;
  }
}

.stats-row {
  display: flex;
  gap: 40px;
}

.default-badge {
  margin-left: 8px;
  padding: 2px 8px;
  background: #e6a23c;
  color: white;
  border-radius: 4px;
  font-size: 12px;
}

.broker-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.broker-icon {
  color: #409eff;
}

.broker-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.broker-name {
  font-weight: 500;
}

.account-id {
  font-family: monospace;
  color: #606266;
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

.config-card {
  margin-bottom: 24px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
  border-radius: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 16px;
  font-weight: 600;
}

.message-alert {
  margin-bottom: 20px;
}

.config-form {
  padding: 20px 0;
  .el-form-item {
    margin-bottom: 20px;
  }
  .unit {
    margin-left: 12px;
    color: #666;
  }
  .slider-value {
    margin-left: 12px;
    font-size: 14px;
    color: #666;
  }
}

.test-result {
  padding: 20px;
}

:deep(.el-statistic__content) {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
}

:deep(.el-statistic__title) {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}
</style>

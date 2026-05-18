<template>
  <div class="stocks-page">
    <div class="page-header">
      <h2>A股股票池</h2>
      <div class="header-actions">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索股票代码或名称"
          :prefix-icon="Search"
          clearable
          style="width: 200px"
          @input="handleSearch"
        />
        <el-button type="primary" :icon="Plus" @click="showAddDialog = true">
          添加股票
        </el-button>
        <el-button :icon="Refresh" @click="refreshData" :loading="loading">
          刷新
        </el-button>
      </div>
    </div>

    <!-- 分组快捷切换 -->
    <div class="group-tabs">
      <div
        v-for="group in groups"
        :key="group.id"
        class="group-tab"
        :class="{ active: currentGroupId === group.id }"
        :style="{ borderColor: group.color, color: currentGroupId === group.id ? '#fff' : group.color, backgroundColor: currentGroupId === group.id ? group.color : 'transparent' }"
        @click="handleGroupChange(group.id)"
      >
        {{ group.name }}
        <span class="count">({{ group.count || 0 }})</span>
      </div>
      <el-button link :icon="Setting" @click="showGroupManager = true" class="manage-btn">
        管理分组
      </el-button>
    </div>

    <!-- 统计卡片 -->
    <div class="stocks-stats">
      <div class="stat-item total">
        <div class="icon-wrapper">
          <el-icon size="24"><Collection /></el-icon>
        </div>
        <div class="stat-content">
          <span class="label">A股总数</span>
          <span class="value">{{ stats.total }}</span>
        </div>
      </div>
      <div class="stat-item stocks">
        <div class="icon-wrapper">
          <el-icon size="24"><OfficeBuilding /></el-icon>
        </div>
        <div class="stat-content">
          <span class="label">股票</span>
          <span class="value">{{ stats.stocks }}</span>
        </div>
      </div>
      <div class="stat-item etfs">
        <div class="icon-wrapper">
          <el-icon size="24"><DataLine /></el-icon>
        </div>
        <div class="stat-content">
          <span class="label">ETF</span>
          <span class="value">{{ stats.etfs }}</span>
        </div>
      </div>
    </div>

    <!-- 券商账户选择 -->
    <div class="broker-bar">
      <span class="label">当前券商账户：</span>
      <el-select v-model="currentBrokerId" placeholder="选择券商账户" style="width: 200px" @change="handleBrokerChange">
        <el-option
          v-for="account in brokerAccounts"
          :key="account.id"
          :label="account.broker_name + (account.is_default ? ' (默认)' : '')"
          :value="account.id"
        />
      </el-select>
      <el-button link type="primary" @click="setAsDefaultBroker" :disabled="!currentBrokerId">
        设为默认
      </el-button>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-radio-group v-model="filterType" size="default" @change="handleFilterChange">
        <el-radio-button value="all">全部类型</el-radio-button>
        <el-radio-button value="stock">股票</el-radio-button>
        <el-radio-button value="etf">ETF</el-radio-button>
      </el-radio-group>
      <el-button v-if="selectedStocks.length > 0" type="primary" size="small" @click="batchSetGroup">
        批量设置分组 ({{ selectedStocks.length }})
      </el-button>
    </div>

    <!-- 数据表格 -->
    <div class="table-card">
      <el-table
        :data="filteredStocks"
        style="width: 100%"
        :header-cell-style="{ background: '#f5f7fa', color: '#303133', fontWeight: 600 }"
        v-loading="loading"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        
        <el-table-column prop="symbol" label="代码" width="100">
          <template #default="{ row }">
            <span class="symbol">{{ row.symbol }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="name" label="名称" min-width="120">
          <template #default="{ row }">
            <span class="name">{{ row.name }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="group_name" label="分组" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.group_name" size="small" :color="row.group_color" effect="dark">
              {{ row.group_name }}
            </el-tag>
            <span v-else class="no-group">未分组</span>
          </template>
        </el-table-column>

        <el-table-column prop="type" label="类型" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.type === 'etf' ? 'warning' : 'info'">
              {{ row.type === 'etf' ? 'ETF' : '股票' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="price" label="当前价" width="100">
          <template #default="{ row }">
            <span class="price" v-if="row.price != null">
              ¥{{ formatNumber(row.price) }}
            </span>
            <span class="no-data" v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column prop="change_percent" label="涨跌幅" width="100">
          <template #default="{ row }">
            <span 
              class="change" 
              :class="getChangeClass(row.change_percent)"
              v-if="row.change_percent != null"
            >
              {{ row.change_percent >= 0 ? '+' : '' }}{{ row.change_percent.toFixed(2) }}%
            </span>
            <span class="no-data" v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column prop="volume" label="成交量" width="100">
          <template #default="{ row }">
            <span class="volume" v-if="row.volume != null">
              {{ formatVolume(row.volume) }}
            </span>
            <span class="no-data" v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column prop="market_cap" label="市值" width="100">
          <template #default="{ row }">
            <span class="market-cap" v-if="row.market_cap != null">
              {{ formatMarketCap(row.market_cap) }}
            </span>
            <span class="no-data" v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewDetail(row)">
              详情
            </el-button>
            <el-button type="danger" link size="small" @click="removeStock(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
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
    </div>

    <!-- 添加股票对话框 -->
    <el-dialog v-model="showAddDialog" title="添加股票" width="500px">
      <el-form :model="addForm" label-width="100px">
        <el-form-item label="股票代码">
          <el-input v-model="addForm.symbol" placeholder="输入股票代码，如000001.SZ">
            <template #append>
              <el-button :icon="Search" @click="searchStockInfo">查询</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="股票名称">
          <el-input v-model="addForm.name" placeholder="股票名称" disabled />
        </el-form-item>
        <el-form-item label="分组">
          <el-select v-model="addForm.group_id" placeholder="选择分组">
            <el-option
              v-for="group in groups"
              :key="group.id"
              :label="group.name"
              :value="group.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="券商账户">
          <el-select v-model="addForm.broker_account_id" placeholder="选择券商账户">
            <el-option
              v-for="account in brokerAccounts"
              :key="account.id"
              :label="account.broker_name"
              :value="account.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmAddStock" :loading="adding">
          添加
        </el-button>
      </template>
    </el-dialog>

    <!-- 分组管理对话框 -->
    <el-dialog v-model="showGroupManager" title="分组管理" width="600px">
      <el-table :data="groups" style="width: 100%">
        <el-table-column prop="name" label="分组名称" />
        <el-table-column prop="color" label="颜色">
          <template #default="{ row }">
            <div class="color-preview" :style="{ backgroundColor: row.color }"></div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button v-if="!row.is_default" type="danger" link @click="deleteGroup(row.id)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-group">
        <el-input v-model="newGroupName" placeholder="新分组名称" style="width: 200px" />
        <el-color-picker v-model="newGroupColor" />
        <el-button type="primary" @click="createGroup">创建分组</el-button>
      </div>
    </el-dialog>

    <!-- 批量设置分组对话框 -->
    <el-dialog v-model="showBatchGroupDialog" title="批量设置分组" width="400px">
      <el-form label-width="80px">
        <el-form-item label="选择分组">
          <el-select v-model="batchGroupId" placeholder="选择分组">
            <el-option
              v-for="group in groups"
              :key="group.id"
              :label="group.name"
              :value="group.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showBatchGroupDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmBatchSetGroup">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Search, Refresh, Collection, OfficeBuilding, DataLine, Plus, Setting } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  addStockToPool,
  createStockGroup,
  deleteStockGroup,
  getStockGroups,
  getStockPool,
  removeStockFromPool,
  searchStock,
  updateStockGroupAssignment
} from '../api/market.js'
import { getBrokerAccounts, getDefaultBrokerAccount } from '../api/trade.js'

const loading = ref(false)
const adding = ref(false)
const searchKeyword = ref('')
const filterType = ref('all')
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const stocks = ref([])
const stats = ref({
  total: 0,
  stocks: 0,
  etfs: 0
})
const selectedStocks = ref([])
const groups = ref([])
const currentGroupId = ref(null)
const brokerAccounts = ref([])
const currentBrokerId = ref(null)

// 对话框控制
const showAddDialog = ref(false)
const showGroupManager = ref(false)
const showBatchGroupDialog = ref(false)

// 添加表单
const addForm = ref({
  symbol: '',
  name: '',
  group_id: null,
  broker_account_id: null
})

// 新分组
const newGroupName = ref('')
const newGroupColor = ref('#667eea')
const batchGroupId = ref(null)

// 过滤后的股票列表
const filteredStocks = computed(() => {
  let result = stocks.value
  if (filterType.value !== 'all') {
    result = result.filter(s => s.type === filterType.value)
  }
  // 添加分组名称
  result = result.map(s => {
    const group = groups.value.find(g => g.id === s.group_id)
    return {
      ...s,
      group_name: group?.name || '',
      group_color: group?.color || ''
    }
  })
  return result
})

// 获取分组列表
const fetchGroups = async () => {
  try {
    const response = await getStockGroups('CN')
    if (response.success) {
      groups.value = response.data || []
      // 计算每个分组的股票数量
      groups.value.forEach(group => {
        group.count = stocks.value.filter(s => s.group_id === group.id).length
      })
      // 默认选中"全部"分组
      const allGroup = groups.value.find(g => g.name === '全部')
      if (allGroup && !currentGroupId.value) {
        currentGroupId.value = allGroup.id
      }
    }
  } catch (error) {
    console.error('获取分组失败:', error)
  }
}

// 获取券商账户列表
const fetchBrokerAccounts = async () => {
  try {
    const response = await getBrokerAccounts()
    if (response.success) {
      brokerAccounts.value = response.data || []
      // 获取默认账户
      const defaultAccount = brokerAccounts.value.find(a => a.is_default)
      if (defaultAccount) {
        currentBrokerId.value = defaultAccount.id
      }
    }
  } catch (error) {
    console.error('获取券商账户失败:', error)
  }
}

// 获取A股股票池数据
const fetchStockPool = async () => {
  loading.value = true
  try {
    const response = await getStockPool({
      market: 'CN',
      search: searchKeyword.value,
      group_id: currentGroupId.value || '',
      page: currentPage.value,
      page_size: pageSize.value
    })

    if (response.success) {
      stocks.value = response.stocks || []
      total.value = response.total || 0
      stats.value = {
        total: response.stats?.total || 0,
        stocks: response.stats?.stocks || 0,
        etfs: response.stats?.etfs || 0
      }
      // 更新分组计数
      fetchGroups()
    }
  } catch (error) {
    console.error('获取A股股票池失败:', error)
    ElMessage.error('获取A股股票池数据失败')
  } finally {
    loading.value = false
  }
}

// 搜索股票信息
const searchStockInfo = async () => {
  if (!addForm.value.symbol) {
    ElMessage.warning('请输入股票代码')
    return
  }
  try {
    const response = await searchStock({
      keyword: addForm.value.symbol,
      market: 'CN',
      broker_account_id: currentBrokerId.value
    })
    if (response.success && response.data && response.data.length > 0) {
      const stock = response.data[0]
      addForm.value.name = stock.name
      addForm.value.symbol = stock.symbol
    } else {
      ElMessage.warning('未找到该股票')
    }
  } catch (error) {
    console.error('搜索股票失败:', error)
    ElMessage.error('搜索股票失败')
  }
}

// 确认添加股票
const confirmAddStock = async () => {
  if (!addForm.value.symbol) {
    ElMessage.warning('请输入股票代码')
    return
  }
  adding.value = true
  try {
    const response = await addStockToPool({
      symbol: addForm.value.symbol,
      name: addForm.value.name,
      market: 'CN',
      type: 'stock',
      group_id: addForm.value.group_id,
      broker_account_id: addForm.value.broker_account_id || currentBrokerId.value
    })
    if (response.success) {
      ElMessage.success('添加成功')
      showAddDialog.value = false
      addForm.value = { symbol: '', name: '', group_id: null, broker_account_id: null }
      fetchStockPool()
    }
  } catch (error) {
    console.error('添加股票失败:', error)
    ElMessage.error('添加股票失败')
  } finally {
    adding.value = false
  }
}

// 删除股票
const removeStock = async (row) => {
  try {
    await ElMessageBox.confirm('确定从股票池中删除该股票吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    const response = await removeStockFromPool(row.symbol, 'CN')
    if (response.success) {
      ElMessage.success('删除成功')
      fetchStockPool()
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除股票失败:', error)
      ElMessage.error('删除股票失败')
    }
  }
}

// 创建分组
const createGroup = async () => {
  if (!newGroupName.value) {
    ElMessage.warning('请输入分组名称')
    return
  }
  try {
    const response = await createStockGroup({
      market: 'CN',
      name: newGroupName.value,
      color: newGroupColor.value
    })
    if (response.success) {
      ElMessage.success('创建成功')
      newGroupName.value = ''
      fetchGroups()
    }
  } catch (error) {
    console.error('创建分组失败:', error)
    ElMessage.error('创建分组失败')
  }
}

// 删除分组
const deleteGroup = async (groupId) => {
  try {
    await ElMessageBox.confirm('确定删除该分组吗？分组内的股票将变为未分组状态', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    const response = await deleteStockGroup(groupId)
    if (response.success) {
      ElMessage.success('删除成功')
      fetchGroups()
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除分组失败:', error)
      ElMessage.error('删除分组失败')
    }
  }
}

// 批量设置分组
const batchSetGroup = () => {
  if (selectedStocks.value.length === 0) {
    ElMessage.warning('请先选择股票')
    return
  }
  batchGroupId.value = null
  showBatchGroupDialog.value = true
}

// 确认批量设置分组
const confirmBatchSetGroup = async () => {
  if (!batchGroupId.value) {
    ElMessage.warning('请选择分组')
    return
  }
  try {
    const response = await updateStockGroupAssignment({
      symbols: selectedStocks.value.map(s => s.symbol),
      group_id: batchGroupId.value,
      market: 'CN'
    })
    if (response.success) {
      ElMessage.success('设置成功')
      showBatchGroupDialog.value = false
      selectedStocks.value = []
      fetchStockPool()
    }
  } catch (error) {
    console.error('批量设置分组失败:', error)
    ElMessage.error('批量设置分组失败')
  }
}

// 分组切换
const handleGroupChange = (groupId) => {
  currentGroupId.value = groupId
  currentPage.value = 1
  fetchStockPool()
}

// 刷新数据
const refreshData = async () => {
  await fetchStockPool()
}

// 搜索
const handleSearch = () => {
  currentPage.value = 1
  fetchStockPool()
}

// 筛选变化
const handleFilterChange = () => {
  currentPage.value = 1
}

// 分页变化
const handleSizeChange = (val) => {
  pageSize.value = val
  fetchStockPool()
}

const handleCurrentChange = (val) => {
  currentPage.value = val
  fetchStockPool()
}

// 选择变化
const handleSelectionChange = (val) => {
  selectedStocks.value = val
}

// 查看详情
const viewDetail = (row) => {
  ElMessage.info(`查看 ${row.symbol} 详情`)
}

// 格式化数字
const formatNumber = (num) => {
  if (num === null || num === undefined) return '-'
  return num.toFixed(2)
}

// 格式化成交量
const formatVolume = (volume) => {
  if (volume === null || volume === undefined) return '-'
  if (volume >= 100000000) {
    return (volume / 100000000).toFixed(2) + '亿'
  } else if (volume >= 10000) {
    return (volume / 10000).toFixed(2) + '万'
  }
  return volume.toString()
}

// 格式化市值
const formatMarketCap = (cap) => {
  if (cap === null || cap === undefined) return '-'
  if (cap >= 1000000000000) {
    return (cap / 1000000000000).toFixed(2) + '万亿'
  } else if (cap >= 100000000) {
    return (cap / 100000000).toFixed(2) + '亿'
  } else if (cap >= 10000) {
    return (cap / 10000).toFixed(2) + '万'
  }
  return cap.toString()
}

// 获取涨跌幅样式
const getChangeClass = (value) => {
  if (value === null || value === undefined) return ''
  return value >= 0 ? 'up' : 'down'
}

// 初始化
onMounted(async () => {
  await fetchBrokerAccounts()
  await fetchGroups()
  await fetchStockPool()
})
</script>

<style scoped lang="scss">
.stocks-page {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;

    h2 {
      font-size: 24px;
      font-weight: 600;
      color: #303133;
      margin: 0;
    }

    .header-actions {
      display: flex;
      gap: 12px;
    }
  }

  .group-tabs {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
    flex-wrap: wrap;
    align-items: center;

    .group-tab {
      padding: 8px 16px;
      border-radius: 20px;
      border: 2px solid;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
      transition: all 0.3s ease;

      &:hover {
        opacity: 0.8;
      }

      &.active {
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
      }

      .count {
        font-size: 12px;
        opacity: 0.8;
      }
    }

    .manage-btn {
      margin-left: auto;
    }
  }

  .stocks-stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-bottom: 20px;

    .stat-item {
      background: #fff;
      padding: 20px;
      border-radius: 12px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
      display: flex;
      align-items: center;
      gap: 16px;
      transition: all 0.3s ease;

      &:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
      }

      .icon-wrapper {
        width: 56px;
        height: 56px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
      }

      &.total .icon-wrapper {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      }

      &.stocks .icon-wrapper {
        background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
      }

      &.etfs .icon-wrapper {
        background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
      }

      .stat-content {
        flex: 1;

        .label {
          display: block;
          font-size: 14px;
          color: #909399;
          margin-bottom: 4px;
        }

        .value {
          display: block;
          font-size: 28px;
          font-weight: 700;
          color: #303133;
        }
      }
    }
  }

  .broker-bar {
    margin-bottom: 16px;
    padding: 12px 16px;
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
    display: flex;
    align-items: center;
    gap: 12px;

    .label {
      font-size: 14px;
      color: #606266;
    }
  }

  .filter-bar {
    margin-bottom: 16px;
    padding: 12px 16px;
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .table-card {
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
    padding: 20px;

    .symbol {
      font-weight: 600;
      color: #303133;
    }

    .name {
      color: #606266;
    }

    .price {
      font-weight: 600;
      color: #303133;
    }

    .change {
      font-weight: 500;
      
      &.up {
        color: #f56c6c;
      }
      
      &.down {
        color: #67c23a;
      }
    }

    .volume,
    .market-cap {
      color: #606266;
    }

    .no-data {
      color: #c0c4cc;
    }

    .no-group {
      color: #909399;
      font-size: 12px;
    }

    .pagination {
      margin-top: 20px;
      display: flex;
      justify-content: flex-end;
    }
  }

  .color-preview {
    width: 24px;
    height: 24px;
    border-radius: 4px;
  }

  .add-group {
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid #ebeef5;
    display: flex;
    gap: 12px;
    align-items: center;
  }
}
</style>

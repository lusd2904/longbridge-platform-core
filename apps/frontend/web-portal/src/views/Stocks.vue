<template>
  <div class="stocks-page">
    <div class="page-header">
      <h2>股票池</h2>
      <div class="header-actions">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索股票代码或名称"
          :prefix-icon="Search"
          clearable
          style="width: 280px"
          @input="handleSearch"
        />
        <el-button type="primary" :icon="Refresh" @click="refreshData" :loading="loading">
          刷新数据
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stocks-stats">
      <div class="stat-item total">
        <div class="icon-wrapper">
          <el-icon size="24"><Collection /></el-icon>
        </div>
        <div class="stat-content">
          <span class="label">股票总数</span>
          <span class="value">{{ stats.total }}</span>
        </div>
      </div>
      <div class="stat-item us">
        <div class="icon-wrapper">
          <el-icon size="24"><Money /></el-icon>
        </div>
        <div class="stat-content">
          <span class="label">美股</span>
          <span class="value">{{ stats.us }}</span>
        </div>
      </div>
      <div class="stat-item cn">
        <div class="icon-wrapper">
          <el-icon size="24"><TrendCharts /></el-icon>
        </div>
        <div class="stat-content">
          <span class="label">A股</span>
          <span class="value">{{ stats.cn }}</span>
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

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-radio-group v-model="filterMarket" size="default" @change="handleFilterChange">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="US">美股</el-radio-button>
        <el-radio-button value="CN">A股</el-radio-button>
      </el-radio-group>
      
      <el-radio-group v-model="filterType" size="default" @change="handleFilterChange" style="margin-left: 16px">
        <el-radio-button value="all">全部类型</el-radio-button>
        <el-radio-button value="stock">股票</el-radio-button>
        <el-radio-button value="etf">ETF</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 数据表格 -->
    <div class="table-card">
      <el-table
        :data="stocks"
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

        <el-table-column prop="name" label="名称" min-width="150">
          <template #default="{ row }">
            <span class="name">{{ row.name }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="market" label="市场" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.market === 'US' ? 'primary' : 'success'">
              {{ row.market }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="type" label="类型" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.type === 'etf' ? 'warning' : 'info'">
              {{ row.type === 'etf' ? 'ETF' : '股票' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="price" label="当前价" width="120">
          <template #default="{ row }">
            <span class="price" v-if="row.price != null">
              {{ row.market === 'CN' ? '¥' : '$' }}{{ formatNumber(row.price) }}
            </span>
            <span class="no-data" v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column prop="change_percent" label="涨跌幅" width="120">
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

        <el-table-column prop="change" label="涨跌额" width="120">
          <template #default="{ row }">
            <span 
              class="change" 
              :class="getChangeClass(row.change)"
              v-if="row.change != null"
            >
              {{ row.change >= 0 ? '+' : '' }}{{ row.market === 'CN' ? '¥' : '$' }}{{ formatNumber(row.change) }}
            </span>
            <span class="no-data" v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column prop="volume" label="成交量" width="120">
          <template #default="{ row }">
            <span class="volume" v-if="row.volume != null">
              {{ formatVolume(row.volume) }}
            </span>
            <span class="no-data" v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column prop="market_cap" label="市值" width="120">
          <template #default="{ row }">
            <span class="market-cap" v-if="row.market_cap != null">
              {{ formatMarketCap(row.market_cap) }}
            </span>
            <span class="no-data" v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column prop="pe" label="PE" width="80">
          <template #default="{ row }">
            <span class="pe" v-if="row.pe != null">{{ row.pe.toFixed(2) }}</span>
            <span class="no-data" v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column prop="pb" label="PB" width="80">
          <template #default="{ row }">
            <span class="pb" v-if="row.pb != null">{{ row.pb.toFixed(2) }}</span>
            <span class="no-data" v-else>-</span>
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Search, Refresh, Collection, Money, TrendCharts, OfficeBuilding, DataLine } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import request from '../utils/request'

const loading = ref(false)
const searchKeyword = ref('')
const filterMarket = ref('all')
const filterType = ref('all')
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const stocks = ref([])
const stats = ref({
  total: 0,
  us: 0,
  cn: 0,
  stocks: 0,
  etfs: 0
})
const selectedStocks = ref([])
const columnFilters = ref({
  symbol: '',
  name: '',
  market: '',
  type: '',
});

const filteredAndSortedStocks = computed(() => {
  if (!stocks.value) return [];

  let result = [...stocks.value];

  // Apply column filters
  if (columnFilters.value.symbol) {
    const filter = columnFilters.value.symbol.toLowerCase();
    result = result.filter(stock => 
      stock.symbol && stock.symbol.toLowerCase().includes(filter)
    );
  }
  if (columnFilters.value.name) {
    const filter = columnFilters.value.name.toLowerCase();
    result = result.filter(stock => 
      stock.name && stock.name.toLowerCase().includes(filter)
    );
  }
  if (columnFilters.value.market && columnFilters.value.market !== 'all') {
    result = result.filter(stock => stock.market === columnFilters.value.market);
  }
  if (columnFilters.value.type && columnFilters.value.type !== 'all') {
    result = result.filter(stock => stock.type === columnFilters.value.type);
  }

  // Sort by market_cap descending (largest first)
  result.sort((a, b) => {
    const capA = a.market_cap ?? 0;
    const capB = b.market_cap ?? 0;
    return capB - capA;
  });

  return result;
});

// 获取股票实时行情
const fetchStockQuotes = async (symbols) => {
  if (!symbols || symbols.length === 0) return
  
  try {
    const response = await request.post('/stock_quotes', {
      symbols: symbols
    })
    
    if (response.success && response.data) {
      // 更新股票数据
      const quotesData = response.data
      stocks.value = stocks.value.map(stock => {
        const quote = quotesData.find(q => q.symbol === stock.symbol)
        if (quote) {
          return { ...stock, ...quote }
        }
        return stock
      })
    }
  } catch (error) {
    console.error('获取行情失败:', error)
  }
}

// 获取股票池数据
const fetchStockPool = async () => {
  loading.value = true
  try {
    console.log('开始获取股票池数据...')
    console.log('参数:', {
      market: filterMarket.value === 'all' ? 'all' : filterMarket.value,
      search: searchKeyword.value,
      page: currentPage.value,
      page_size: pageSize.value
    })
    
    const response = await request.get('/stock_pool', {
      params: {
        market: filterMarket.value === 'all' ? 'all' : filterMarket.value,
        search: searchKeyword.value,
        page: currentPage.value,
        page_size: pageSize.value
      }
    })

    console.log('API响应:', response)
    
    if (response.success) {
      console.log('股票数据:', response.stocks)
      stocks.value = response.stocks || []
      total.value = response.total || 0
      // 使用后端返回的统计数据
      if (response.stats) {
        stats.value = response.stats
      } else {
        // 计算统计数据（备用）
        const usCount = stocks.value.filter(s => s.market === 'US').length
        const cnCount = stocks.value.filter(s => s.market === 'CN').length
        stats.value = {
          total: total.value,
          us: usCount,
          cn: cnCount,
          stocks: stocks.value.filter(s => s.type === 'stock').length,
          etfs: stocks.value.filter(s => s.type === 'etf').length
        }
      }
      console.log('更新后的stocks:', stocks.value)
      console.log('更新后的stats:', stats.value)
      
      // 获取当前页股票的实时行情
      const symbols = stocks.value.map(s => s.symbol)
      if (symbols.length > 0) {
        await fetchStockQuotes(symbols)
      }
    } else {
      console.error('API返回失败:', response.error)
    }
  } catch (error) {
    console.error('获取股票池失败:', error)
    ElMessage.error('获取股票池数据失败')
  } finally {
    loading.value = false
  }
}

// 批量更新股票数据
const updateStockData = async (symbols, market) => {
  if (!symbols || symbols.length === 0) return

  try {
    const response = await request.post('/stock_pool/update', {
      symbols: symbols,
      market: market
    })

    if (response.success && response.data) {
      // 更新本地数据
      const updatedData = response.data
      stocks.value = stocks.value.map(stock => {
        const updated = updatedData.find(u => u.symbol === stock.symbol)
        if (updated) {
          return { ...stock, ...updated }
        }
        return stock
      })

      ElMessage.success(`成功更新 ${response.updated || updatedData.length} 只股票数据`)
    }
  } catch (error) {
    console.error('更新股票数据失败:', error)
    ElMessage.error('更新股票数据失败')
  }
}

// 刷新数据
const refreshData = async () => {
  // 重新获取股票池数据
  await fetchStockPool()
}

// 更新单只股票
const updateSingleStock = async (row) => {
  await updateStockData([row.symbol], row.market)
}

// 搜索
const handleSearch = () => {
  currentPage.value = 1
  fetchStockPool()
}

// 筛选变化
const handleFilterChange = () => {
  currentPage.value = 1
  fetchStockPool()
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
    return (cap / 1000000000000).toFixed(2) + 'T'
  } else if (cap >= 1000000000) {
    return (cap / 1000000000).toFixed(2) + 'B'
  } else if (cap >= 1000000) {
    return (cap / 1000000).toFixed(2) + 'M'
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
  await fetchStockPool()
})
</script>

<style scoped lang="scss">
.stocks-page {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;

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

  .stocks-stats {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 16px;
    margin-bottom: 24px;

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

      &.us .icon-wrapper {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
      }

      &.cn .icon-wrapper {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
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

  .filter-bar {
    margin-bottom: 20px;
    padding: 16px;
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
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
        color: #f56c6c;  // 红涨
      }
      
      &.down {
        color: #67c23a;  // 绿跌
      }
    }

    .volume,
    .market-cap,
    .pe,
    .pb {
      color: #606266;
    }

    .no-data {
      color: #c0c4cc;
    }

    .pagination {
      margin-top: 20px;
      display: flex;
      justify-content: flex-end;
    }
  }
}
</style>

<!--
  移动端优化表格组件
  在小屏幕上以卡片形式展示数据
-->
<template>
  <div class="mobile-table">
    <!-- 桌面端：普通表格 -->
    <el-table
      v-if="!isMobile"
      :data="data"
      v-bind="$attrs"
      style="width: 100%"
    >
      <slot />
    </el-table>
    
    <!-- 移动端：卡片式布局 -->
    <div v-else class="mobile-cards">
      <div 
        v-for="(row, index) in data" 
        :key="index"
        class="mobile-card"
        @click="$emit('row-click', row)"
      >
        <div class="card-header">
          <slot name="mobile-header" :row="row" :index="index">
            <span class="card-title">{{ getTitle(row) }}</span>
            <span class="card-subtitle" v-if="getSubtitle(row)">
              {{ getSubtitle(row) }}
            </span>
          </slot>
        </div>
        
        <div class="card-body">
          <div 
            v-for="column in mobileColumns" 
            :key="column.prop"
            class="card-row"
          >
            <span class="card-label">{{ column.label }}:</span>
            <span class="card-value">
              <slot :name="`mobile-${column.prop}`" :row="row" :value="row[column.prop]">
                {{ formatValue(row[column.prop], column) }}
              </slot>
            </span>
          </div>
        </div>
        
        <div class="card-actions" v-if="$slots['mobile-actions']">
          <slot name="mobile-actions" :row="row" :index="index" />
        </div>
      </div>
      
      <!-- 空状态 -->
      <el-empty v-if="data.length === 0" :description="emptyText" />
    </div>
    
    <!-- 分页 -->
    <div class="pagination-wrapper" v-if="showPagination">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="pageSizes"
        :total="total"
        :layout="isMobile ? 'prev, pager, next' : 'total, sizes, prev, pager, next'"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  },
  columns: {
    type: Array,
    default: () => []
  },
  titleProp: {
    type: String,
    default: ''
  },
  subtitleProp: {
    type: String,
    default: ''
  },
  emptyText: {
    type: String,
    default: '暂无数据'
  },
  showPagination: {
    type: Boolean,
    default: false
  },
  total: {
    type: Number,
    default: 0
  },
  pageSizes: {
    type: Array,
    default: () => [10, 20, 50, 100]
  }
})

const emit = defineEmits(['row-click', 'size-change', 'current-change', 'update:pageSize', 'update:currentPage'])

// 分页状态
const currentPage = computed({
  get: () => props.currentPage || 1,
  set: (val) => emit('update:currentPage', val)
})

const pageSize = computed({
  get: () => props.pageSize || 10,
  set: (val) => emit('update:pageSize', val)
})

// 检测移动端
const isMobile = ref(false)

const checkMobile = () => {
  isMobile.value = window.innerWidth < 576
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

// 移动端显示的列（排除操作列）
const mobileColumns = computed(() => {
  return props.columns.filter(col => !col.type || col.type !== 'action')
})

// 获取标题
const getTitle = (row) => {
  if (props.titleProp) {
    return row[props.titleProp]
  }
  // 默认使用第一列
  if (props.columns.length > 0) {
    return row[props.columns[0].prop]
  }
  return ''
}

// 获取副标题
const getSubtitle = (row) => {
  if (props.subtitleProp) {
    return row[props.subtitleProp]
  }
  return null
}

// 格式化值
const formatValue = (value, column) => {
  if (column.formatter) {
    return column.formatter(value)
  }
  if (value === null || value === undefined) {
    return '-'
  }
  return value
}

// 分页事件
const handleSizeChange = (val) => {
  emit('size-change', val)
}

const handleCurrentChange = (val) => {
  emit('current-change', val)
}
</script>

<style scoped>
.mobile-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mobile-card {
  background: #fff;
  border-radius: 8px;
  padding: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  border: 1px solid #ebeef5;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid #ebeef5;
}

.card-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.card-subtitle {
  font-size: 12px;
  color: #909399;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.card-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.card-label {
  color: #606266;
  flex-shrink: 0;
}

.card-value {
  color: #303133;
  font-weight: 500;
  text-align: right;
  word-break: break-all;
}

.card-actions {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #ebeef5;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.pagination-wrapper {
  margin-top: 15px;
  display: flex;
  justify-content: center;
}
</style>

<template>
  <el-breadcrumb separator="/">
    <el-breadcrumb-item @click="setPage('dashboard')">首页</el-breadcrumb-item>
    <el-breadcrumb-item v-if="currentTitle">
      {{ currentTitle }}
    </el-breadcrumb-item>
  </el-breadcrumb>
</template>

<script setup>
import { computed } from 'vue'
import { usePageStore } from '../../stores/pageStore.js'

const { currentPage, setPage, pageTitles } = usePageStore()

const currentTitle = computed(() => {
  return pageTitles[currentPage.value]
})
</script>

<style scoped>
:deep(.el-breadcrumb__item) {
  font-size: 14px;
}

:deep(.el-breadcrumb__inner) {
  color: var(--text-secondary);
  cursor: pointer;
}

:deep(.el-breadcrumb__inner.is-link:hover) {
  color: var(--accent);
}

:deep(.el-breadcrumb__item:last-child .el-breadcrumb__inner) {
  color: var(--text-primary);
  font-weight: 600;
}
</style>

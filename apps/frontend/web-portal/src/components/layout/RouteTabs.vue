<template>
  <div v-if="tabsEnabled && tabs.length" class="route-tabs-shell">
    <div class="route-tabs-scroll">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="route-tab"
        :class="{ active: activeKey === tab.key }"
        @click="openTab(tab)"
      >
        <el-icon size="14">
          <component :is="iconMap[tab.icon] || Menu" />
        </el-icon>
        <span class="tab-title">{{ tab.title }}</span>
        <el-icon
          v-if="tab.closable"
          size="14"
          class="tab-close"
          @click.stop="closeTab(tab.key)"
        >
          <Close />
        </el-icon>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Bell,
  Close,
  Coin,
  Compass,
  Collection,
  Cpu,
  DataLine,
  Histogram,
  List,
  Menu,
  Odometer,
  Setting,
  Star,
  Timer,
  TrendCharts,
  User,
  UserFilled,
  Warning,
  Wallet
} from '@element-plus/icons-vue'
import { useWorkbenchTabs } from '../../composables/useWorkbenchTabs.js'

const route = useRoute()
const router = useRouter()
const { tabsEnabled, tabs, syncCurrentRoute, removeTab } = useWorkbenchTabs()

const iconMap = {
  Bell,
  Coin,
  Compass,
  Collection,
  Cpu,
  DataLine,
  Histogram,
  List,
  Menu,
  Odometer,
  Setting,
  Star,
  Timer,
  TrendCharts,
  User,
  UserFilled,
  Warning,
  Wallet
}

const activeKey = computed(() => route.fullPath)

const openTab = (tab) => {
  router.push(tab.fullPath)
}

const closeTab = (tabKey) => {
  removeTab(tabKey, route, router)
}

onMounted(() => {
  syncCurrentRoute(route)
})

watch(
  () => route.fullPath,
  () => syncCurrentRoute(route),
  { immediate: true }
)
</script>

<style scoped lang="scss">
.route-tabs-shell {
  margin: 8px 12px 0;
  padding: 6px 8px;
  border-radius: 10px;
  border: 1px solid var(--border-soft);
  background: var(--chrome-surface);
  box-shadow: var(--chrome-shadow), var(--chrome-inset);
  backdrop-filter: var(--chrome-backdrop);
}

.route-tabs-scroll {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  scrollbar-width: none;
}

.route-tabs-scroll::-webkit-scrollbar {
  display: none;
}

.route-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  padding: 6px 9px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: var(--surface-soft);
  color: var(--text-secondary);
  cursor: pointer;
  transition: transform 0.2s ease, background 0.2s ease, border-color 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    border-color: var(--border-soft);
  }

  &.active {
    background: color-mix(in srgb, var(--accent) 18%, var(--surface-soft) 82%);
    border-color: color-mix(in srgb, var(--accent) 32%, transparent);
    color: var(--text-emphasis);
  }
}

.tab-title {
  max-width: 140px;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tab-close {
  margin-left: 2px;
  border-radius: 999px;
}

@media (max-width: 960px) {
  .route-tabs-shell {
    display: none;
  }
}
</style>

<template>
  <div v-if="isCompactLayout" class="mobile-shell">
    <button
      type="button"
      class="mobile-shortcut"
      :class="{ active: drawerVisible }"
      @click="drawerVisible = true"
    >
      <el-icon :size="18"><Grid /></el-icon>
      <span>全部功能</span>
    </button>

    <div class="mobile-nav">
      <button
        v-for="item in mobileTabItems"
        :key="item.routeName || item.path"
        type="button"
        class="mobile-nav-item"
        :class="{ active: isActive(item) }"
        @click="handleClick(item)"
      >
        <el-icon :size="20">
          <component :is="item.icon" />
        </el-icon>
        <span class="nav-text">{{ item.title }}</span>
      </button>
    </div>

    <el-drawer
      v-model="drawerVisible"
      direction="btt"
      size="88%"
      :with-header="false"
      :append-to-body="true"
      :modal="true"
    >
      <div class="mobile-drawer">
        <div class="drawer-handle"></div>

        <div class="drawer-hero">
          <div class="drawer-copy">
            <strong>导航</strong>
            <span>{{ displayName }} · {{ currentSubsystemTitle }}</span>
          </div>

          <button type="button" class="drawer-close" @click="drawerVisible = false">
            <el-icon :size="18"><Close /></el-icon>
          </button>
        </div>

        <div class="drawer-primary-grid">
          <button
            v-for="item in mobileTabItems"
            :key="`primary-${item.routeName || item.path}`"
            type="button"
            class="drawer-primary-item"
            :class="{ active: isActive(item) }"
            @click="handleClick(item)"
          >
            <el-icon :size="18">
              <component :is="item.icon" />
            </el-icon>
            <div>
              <strong>{{ item.title }}</strong>
            </div>
          </button>
        </div>

        <div class="drawer-groups">
          <section
            v-for="subsystem in groupedMenuTree"
            :key="subsystem.code"
            class="drawer-section"
            :class="{ active: subsystem.code === activeSubsystemCode }"
          >
            <div class="section-head">
              <div class="section-icon">
                <el-icon :size="18">
                  <component :is="subsystem.icon" />
                </el-icon>
              </div>
              <div class="section-copy">
                <strong>{{ subsystem.title }}</strong>
              </div>
            </div>

            <div class="section-grid">
              <button
                v-for="item in subsystem.items"
                :key="item.targetKey"
                type="button"
                class="section-link"
                :class="{ active: isActive(item) }"
                @click="handleClick(item)"
              >
                <el-icon :size="16">
                  <component :is="item.icon" />
                </el-icon>
                <span>{{ item.title }}</span>
              </button>
            </div>
          </section>
        </div>

        <button type="button" class="drawer-logout" @click="handleLogout">
          <el-icon :size="18"><Close /></el-icon>
          <span>退出登录</span>
        </button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Bell,
  Close,
  Collection,
  Cpu,
  Grid,
  Histogram,
  HomeFilled,
  Menu,
  Odometer,
  Setting,
  Timer,
  TrendCharts,
  User,
  Wallet
} from '@element-plus/icons-vue'
import { useAdaptiveLayout } from '../../composables/useAdaptiveLayout.js'
import {
  getActiveSubsystem,
  getCurrentUser,
  getMenus,
  getSubsystems,
  logout
} from '../../utils/auth.js'

const route = useRoute()
const router = useRouter()
const drawerVisible = ref(false)
const sessionVersion = ref(0)
const { isCompactLayout } = useAdaptiveLayout()

const ICON_MAP = {
  Bell,
  Collection,
  Cpu,
  Grid,
  Histogram,
  HomeFilled,
  Menu,
  Odometer,
  Setting,
  Timer,
  TrendCharts,
  User,
  Wallet
}

const MOBILE_TAB_CONFIG = [
  {
    key: 'dashboard',
    routeNames: ['Dashboard'],
    fallback: { routeName: 'Dashboard', path: '/dashboard', title: '首页', icon: HomeFilled }
  },
  {
    key: 'market',
    routeNames: ['MarketData', 'StockPool', 'Recommendations', 'MarketSentiment', 'FinanceNews'],
    fallback: { routeName: 'MarketData', path: '/market', title: '行情', icon: Histogram }
  },
  {
    key: 'trade',
    routeNames: ['Trading', 'Positions', 'Orders'],
    fallback: { routeName: 'Trading', path: '/trading', title: '交易', icon: Wallet }
  },
  {
    key: 'strategy',
    routeNames: ['AIAnalysis', 'Strategy', 'Backtest'],
    fallback: { routeName: 'AIAnalysis', path: '/ai-analysis', title: '策略', icon: Cpu }
  },
  {
    key: 'profile',
    routeNames: ['Profile', 'Notifications', 'BrokerManagement', 'Settings'],
    fallback: { routeName: 'Profile', path: '/profile', title: '我的', icon: User }
  }
]

const normalizedMenus = computed(() => {
  sessionVersion.value
  return getMenus()
    .filter((menu) => !menu?.hidden)
    .map((menu, index) => ({
      routeName: menu?.routeName || '',
      path: menu?.path || '',
      title: menu?.title || '菜单',
      subsystemCode: String(menu?.subsystemCode || menu?.subsystem || 'workspace'),
      icon: ICON_MAP[menu?.icon] || Menu,
      targetKey: menu?.routeName || menu?.path || `menu:${index}`
    }))
})

const currentUser = computed(() => {
  sessionVersion.value
  return getCurrentUser() || {}
})

const displayName = computed(() => currentUser.value.nickname || currentUser.value.username || '平台用户')
const activeSubsystemCode = computed(() => {
  sessionVersion.value
  return String(getActiveSubsystem() || route.meta?.subsystem || 'workspace')
})

const subsystemMeta = computed(() => {
  sessionVersion.value
  const visibleSubsystemCodes = new Set(normalizedMenus.value.map((item) => item.subsystemCode))
  const source = getSubsystems().filter((item) => visibleSubsystemCodes.has(String(item?.code || '')))
  const map = new Map()
  source.forEach((item, index) => {
    map.set(String(item?.code || `subsystem:${index}`), {
      code: String(item?.code || `subsystem:${index}`),
      title: item?.title || '功能分区',
      icon: ICON_MAP[item?.icon] || Menu,
      sortIndex: Number(item?.sortIndex ?? index)
    })
  })
  return map
})

const currentSubsystemTitle = computed(() => (
  subsystemMeta.value.get(activeSubsystemCode.value)?.title || '功能总览'
))

const groupedMenuTree = computed(() => {
  const sections = new Map()

  normalizedMenus.value.forEach((item, index) => {
    const meta = subsystemMeta.value.get(item.subsystemCode) || {
      code: item.subsystemCode,
      title: item.subsystemCode === 'workspace' ? '工作台' : item.subsystemCode,
      icon: Menu,
      sortIndex: index
    }

    if (!sections.has(meta.code)) {
      sections.set(meta.code, {
        ...meta,
        items: []
      })
    }

    sections.get(meta.code).items.push({
      ...item,
      sortIndex: index
    })
  })

  return Array.from(sections.values())
    .map((section) => ({
      ...section,
      items: section.items.sort((a, b) => a.sortIndex - b.sortIndex)
    }))
    .sort((a, b) => a.sortIndex - b.sortIndex)
})

const resolveMenuByRouteName = (routeNames = []) => {
  for (const routeName of routeNames) {
    const matched = normalizedMenus.value.find((item) => item.routeName === routeName)
    if (matched) {
      return matched
    }
  }
  return null
}

const mobileTabItems = computed(() => MOBILE_TAB_CONFIG
  .map((tab) => {
    const matched = resolveMenuByRouteName(tab.routeNames)
    if (!matched) {
      return null
    }

    return {
      ...matched,
      title: matched.title,
      icon: matched.icon,
      clusterRoutes: tab.routeNames
    }
  })
  .filter(Boolean))

const refreshSessionMenus = () => {
  sessionVersion.value += 1
}

const isActive = (item) => {
  if (!item) {
    return false
  }

  if (item.routeName && String(route.name || '') === item.routeName) {
    return true
  }

  if (Array.isArray(item.clusterRoutes) && item.clusterRoutes.includes(String(route.name || ''))) {
    return true
  }

  return Boolean(item.path) && (route.path === item.path || route.path.startsWith(`${item.path}/`))
}

const resolveTarget = (item) => {
  if (item?.routeName) {
    return { name: item.routeName }
  }
  if (item?.path) {
    return { path: item.path }
  }
  return null
}

const handleClick = async (item) => {
  const target = resolveTarget(item)
  if (!target) {
    return
  }

  drawerVisible.value = false
  await router.push(target)
}

const openDrawer = () => {
  drawerVisible.value = true
}

const handleLogout = async () => {
  try {
    await logout()
    ElMessage.success('退出登录成功')
  } catch {
    ElMessage.success('已退出登录')
  } finally {
    drawerVisible.value = false
    await router.push('/login')
  }
}

watch(
  () => route.fullPath,
  () => {
    drawerVisible.value = false
  }
)

onMounted(() => {
  window.addEventListener('platform-session-updated', refreshSessionMenus)
  window.addEventListener('platform-mobile-drawer-open', openDrawer)
})

onUnmounted(() => {
  window.removeEventListener('platform-session-updated', refreshSessionMenus)
  window.removeEventListener('platform-mobile-drawer-open', openDrawer)
})
</script>

<style scoped lang="scss">
.mobile-shell {
  display: contents;
}

.mobile-shortcut {
  position: fixed;
  right: 12px;
  bottom: calc(68px + env(safe-area-inset-bottom, 0px));
  z-index: 1300;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 0 10px;
  border: 1px solid color-mix(in srgb, var(--accent-strong) 18%, transparent);
  border-radius: 999px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.16), rgba(255, 255, 255, 0.06)),
    color-mix(in srgb, var(--surface-strong) 94%, black 6%);
  color: var(--text-emphasis);
  box-shadow: var(--chrome-shadow), var(--chrome-inset);
  backdrop-filter: blur(28px) saturate(145%);
  cursor: pointer;
}

.mobile-shortcut.active {
  color: var(--accent);
}

.mobile-shortcut span {
  font-size: 12px;
  font-weight: 600;
}

.mobile-nav {
  position: fixed;
  left: 8px;
  right: 8px;
  bottom: 8px;
  z-index: 1300;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(0, 1fr));
  gap: 5px;
  padding: 7px;
  border-radius: 18px;
  border: 1px solid color-mix(in srgb, var(--accent-strong) 16%, transparent);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.14), rgba(255, 255, 255, 0.05)),
    color-mix(in srgb, var(--surface-strong) 92%, black 8%);
  box-shadow: var(--chrome-shadow), var(--chrome-inset);
  backdrop-filter: blur(28px) saturate(150%);
}

.mobile-nav-item {
  display: flex;
  min-width: 0;
  min-height: 44px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 5px 4px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: transform 0.22s ease, background 0.22s ease, color 0.22s ease;
}

.mobile-nav-item:hover,
.mobile-nav-item:active {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}

.mobile-nav-item.active {
  color: var(--text-emphasis);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 18%, transparent), transparent 82%),
    color-mix(in srgb, var(--surface-soft) 68%, transparent);
  transform: translateY(-1px);
}

.nav-text {
  overflow: hidden;
  max-width: 100%;
  font-size: 10px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mobile-drawer {
  display: flex;
  height: 100%;
  flex-direction: column;
  gap: 10px;
  padding: 10px 8px calc(12px + env(safe-area-inset-bottom, 0px));
  color: var(--text-primary);
}

:deep(.el-drawer.btt) {
  border-radius: 18px 18px 0 0;
  background: transparent;
  box-shadow: none;
}

:deep(.el-drawer__body) {
  padding: 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.03)),
    color-mix(in srgb, var(--surface-strong) 94%, black 6%);
}

.drawer-handle {
  width: 42px;
  height: 4px;
  margin: 0 auto;
  border-radius: 999px;
  background: color-mix(in srgb, var(--text-muted) 42%, transparent);
}

.drawer-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.drawer-copy {
  display: grid;
  gap: 6px;
}

.drawer-copy strong {
  font-size: 17px;
  line-height: 1.1;
  color: var(--text-emphasis);
}

.drawer-copy span {
  color: var(--text-muted);
  font-size: 11px;
}

.drawer-close {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 10px;
  background: var(--surface-soft);
  color: var(--text-emphasis);
  cursor: pointer;
}

.drawer-primary-grid {
  display: grid;
  gap: 8px;
}

.drawer-primary-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent 58%),
    color-mix(in srgb, var(--surface-soft) 72%, var(--surface-emphasis) 28%);
  color: var(--text-emphasis);
  cursor: pointer;
  text-align: left;
}

.drawer-primary-item.active {
  border-color: color-mix(in srgb, var(--accent) 28%, transparent);
  box-shadow: 0 18px 40px rgba(4, 10, 18, 0.14);
}

.drawer-primary-item strong {
  display: block;
}

.drawer-primary-item strong {
  font-size: 14px;
}

.drawer-groups {
  display: grid;
  flex: 1;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
  -webkit-overflow-scrolling: touch;
}

.drawer-logout {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: auto;
  width: 100%;
  padding: 9px 12px;
  border: 1px solid color-mix(in srgb, var(--danger) 18%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--danger) 10%, transparent);
  color: var(--text-emphasis);
  cursor: pointer;
}

.drawer-section {
  padding: 10px;
  border: 1px solid color-mix(in srgb, var(--border-soft) 88%, transparent);
  border-radius: 12px;
  background:
    radial-gradient(circle at top right, color-mix(in srgb, var(--accent) 8%, transparent), transparent 32%),
    color-mix(in srgb, var(--surface-strong) 92%, black 8%);
}

.drawer-section.active {
  border-color: color-mix(in srgb, var(--accent) 26%, transparent);
  box-shadow: 0 18px 40px rgba(4, 10, 18, 0.16);
}

.section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.section-icon {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  color: var(--text-emphasis);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 28%, transparent), transparent 88%),
    color-mix(in srgb, var(--surface-soft) 60%, var(--surface-emphasis) 40%);
}

.section-copy {
  display: grid;
  gap: 3px;
}

.section-copy strong {
  color: var(--text-emphasis);
  font-size: 13px;
}

.section-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
}

.section-link {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 7px;
  padding: 8px 9px;
  border: 0;
  border-radius: 9px;
  background: color-mix(in srgb, var(--surface-soft) 70%, var(--surface-emphasis) 30%);
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
}

.section-link span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.section-link.active {
  color: var(--text-emphasis);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 16%, transparent), transparent 80%),
    color-mix(in srgb, var(--surface-soft) 68%, var(--surface-emphasis) 32%);
}

.mobile-nav-item.active .nav-text {
  font-weight: 700;
}

@supports (padding-bottom: max(0px)) {
  .mobile-nav {
    padding-bottom: max(10px, env(safe-area-inset-bottom));
  }
}

@media (max-width: 1180px) {
  .mobile-nav {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .mobile-shortcut {
    right: 10px;
    bottom: calc(62px + env(safe-area-inset-bottom, 0px));
    padding-inline: 9px;
  }

  .mobile-shortcut span {
    display: none;
  }

  .mobile-nav {
    left: 8px;
    right: 8px;
    bottom: 8px;
    gap: 4px;
    padding-inline: 6px;
  }

  .mobile-nav-item {
    min-height: 42px;
    padding-inline: 3px;
  }

  .nav-text {
    font-size: 9px;
  }

  .section-grid {
    grid-template-columns: 1fr;
  }

  .drawer-copy strong {
    font-size: 16px;
  }
}

@media (min-width: 1181px) {
  .mobile-shortcut,
  .mobile-nav {
    display: none;
  }
}
</style>

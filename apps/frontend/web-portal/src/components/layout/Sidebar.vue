<template>
  <aside class="sidebar" :class="{ collapsed: isCollapsed }">
    <div class="sidebar-shell">
      <button type="button" class="logo" @click="goDashboard">
        <div class="logo-icon">
          <el-icon size="28"><TrendCharts /></el-icon>
        </div>
        <div class="logo-copy" v-show="!isCollapsed">
          <strong>{{ systemName }}</strong>
        </div>
      </button>

      <nav class="menu">
        <div
          v-for="subsystem in menuTree"
          :key="subsystem.code"
          class="subsystem-block"
        >
          <button
            type="button"
            class="subsystem-item"
            :class="{ expanded: isExpanded(subsystem.code), active: isSubsystemActive(subsystem) }"
            @click="handleSubsystemClick(subsystem)"
            @mouseenter="handleSubsystemPrefetch(subsystem)"
          >
            <div class="subsystem-main">
              <div class="subsystem-icon">
                <el-icon size="18">
                  <component :is="subsystem.icon" />
                </el-icon>
              </div>
              <span v-show="!isCollapsed" class="subsystem-title">{{ subsystem.title }}</span>
            </div>
            <el-icon v-show="!isCollapsed && subsystem.groups.length" class="subsystem-arrow" size="14">
              <ArrowDown v-if="isExpanded(subsystem.code)" />
              <ArrowRight v-else />
            </el-icon>
          </button>

          <div
            v-if="!isCollapsed && isExpanded(subsystem.code) && subsystem.groups.length"
            class="submenu-list"
          >
            <section
              v-for="group in subsystem.groups"
              :key="`${subsystem.code}:${group.code}`"
              class="group-block"
            >
              <div v-if="subsystem.groups.length > 1" class="group-title">
                {{ group.title }}
              </div>
              <button
                v-for="item in group.items"
                :key="item.targetKey"
                type="button"
                class="submenu-item"
                :class="{ active: isRouteActive(item) }"
                @click="handleMenuClick(item)"
                @mouseenter="handleMenuPrefetch(item)"
              >
                <el-icon size="16">
                  <component :is="item.icon" />
                </el-icon>
                <span class="menu-text">{{ item.title }}</span>
              </button>
            </section>
          </div>
        </div>
      </nav>

      <div class="sidebar-foot">
        <button type="button" class="collapse-btn" @click="toggleCollapse">
          <el-icon size="18">
            <Fold v-if="!isCollapsed" />
            <Expand v-else />
          </el-icon>
          <span v-show="!isCollapsed">{{ isCollapsed ? '展开导航' : '收起导航' }}</span>
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getMenus, getSubsystems, getActiveSubsystem } from '../../utils/auth.js'
import { getStoredSystemName } from '../../utils/api.js'
import { prefetchRouteByName, prefetchRoutesOnIdle } from '../../utils/routePrefetch.js'
import {
  ArrowDown,
  ArrowRight,
  Bell,
  Coin,
  Collection,
  Cpu,
  DataLine,
  Expand,
  Fold,
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

const route = useRoute()
const router = useRouter()

const isCollapsed = ref(false)
const sessionVersion = ref(0)
const expandedSubsystems = ref([])
const systemName = ref(getStoredSystemName())
const currentRouteName = computed(() => String(route.name || ''))
const currentRoutePath = computed(() => route.path)

const ICON_MAP = {
  Bell,
  Coin,
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

const GROUP_TITLE_MAP = {
  overview: '总览',
  trading: '交易',
  stocks: '股票池',
  analysis: '研究',
  strategy: '策略',
  risk: '风控',
  market: '市场',
  user: '账户',
  system: '系统'
}

const fallbackSubsystems = [
  {
    code: 'workspace',
    title: '仪表盘',
    routeName: 'Dashboard',
    path: '/dashboard',
    icon: 'Odometer'
  }
]

const syncSidebarWidth = () => {
  const width = isCollapsed.value ? '72px' : '248px'
  document.documentElement.style.setProperty('--sidebar-width', width)
}

const menuTree = computed(() => {
  sessionVersion.value
  const rawMenus = getMenus()
  const rawSubsystems = getSubsystems()
  const activeSubsystemCode = getActiveSubsystem()
  const visibleSubsystemCodes = new Set([activeSubsystemCode])
  const subsystems = rawSubsystems.length
    ? rawSubsystems.filter((item) => visibleSubsystemCodes.has(String(item?.code || '')))
    : fallbackSubsystems

  return subsystems.map((subsystem, subsystemIndex) => {
    const relatedMenus = rawMenus
      .filter((menu) => String(menu?.subsystemCode || 'workspace') === subsystem.code)
      .filter((menu) => !menu?.hidden)

    const groupMap = new Map()
    relatedMenus.forEach((menu, index) => {
      const groupCode = String(menu?.group || menu?.menuGroup || 'general').trim() || 'general'
      if (!groupMap.has(groupCode)) {
        groupMap.set(groupCode, {
          code: groupCode,
          title: menu?.groupTitle || GROUP_TITLE_MAP[groupCode] || groupCode,
          sortIndex: Number(menu?.sortIndex ?? index),
          items: []
        })
      }

      const group = groupMap.get(groupCode)
      group.items.push({
        routeName: menu?.routeName || '',
        path: menu?.path || '',
        targetKey: menu?.routeName || menu?.path || `${subsystem.code}:${groupCode}:${index}`,
        title: menu?.title || '菜单',
        icon: ICON_MAP[menu?.icon] || Menu,
        sortIndex: Number(menu?.sortIndex ?? index)
      })
      group.sortIndex = Math.min(group.sortIndex, Number(menu?.sortIndex ?? index))
    })

    const groups = Array.from(groupMap.values())
      .map((group) => ({
        ...group,
        items: group.items.sort((a, b) => a.sortIndex - b.sortIndex)
      }))
      .sort((a, b) => a.sortIndex - b.sortIndex)

    return {
      ...subsystem,
      icon: ICON_MAP[subsystem.icon] || Menu,
      sortIndex: Number(subsystem.sortIndex ?? subsystemIndex),
      groups,
      menuCount: relatedMenus.length,
      routeName: subsystem.routeName || relatedMenus[0]?.routeName || '',
      path: subsystem.path || relatedMenus[0]?.path || ''
    }
  })
    .filter((item) => item.groups.length || item.path || item.routeName)
    .sort((a, b) => a.sortIndex - b.sortIndex)
})

const isRouteActive = (item) => {
  if (!item) {
    return false
  }
  return currentRouteName.value === item.routeName || currentRoutePath.value === item.path
}

const isSubsystemActive = (subsystem) => {
  return subsystem.groups.some((group) => group.items.some((item) => isRouteActive(item)))
}

const ensureExpandedContains = (codes = []) => {
  const next = new Set(expandedSubsystems.value)
  codes.filter(Boolean).forEach((code) => next.add(code))
  expandedSubsystems.value = Array.from(next)
}

const syncExpandedSubsystems = () => {
  const activeCodes = menuTree.value.filter((item) => isSubsystemActive(item)).map((item) => item.code)
  if (!expandedSubsystems.value.length) {
    expandedSubsystems.value = activeCodes.length
      ? activeCodes
      : menuTree.value.slice(0, 1).map((item) => item.code)
    return
  }
  ensureExpandedContains(activeCodes)
}

const isExpanded = (code) => expandedSubsystems.value.includes(code)

const resolveTarget = (item) => {
  if (item?.routeName) {
    return { name: item.routeName }
  }
  if (item?.path) {
    return { path: item.path }
  }
  return null
}

const handleMenuClick = (item) => {
  const target = resolveTarget(item)
  if (target) {
    router.push(target)
  }
}

const handleSubsystemClick = (subsystem) => {
  if (!subsystem?.code) {
    return
  }

  if (isCollapsed.value) {
    const target = resolveTarget(subsystem)
    if (target) {
      router.push(target)
    }
    return
  }

  if (isExpanded(subsystem.code)) {
    expandedSubsystems.value = expandedSubsystems.value.filter((item) => item !== subsystem.code)
  } else {
    ensureExpandedContains([subsystem.code])
  }
}

const goDashboard = () => {
  router.push({ name: 'Dashboard' })
}

const handleSubsystemPrefetch = (subsystem) => {
  const routeNames = subsystem.groups.flatMap((group) => group.items.map((item) => item.routeName)).filter(Boolean)
  prefetchRoutesOnIdle(router, routeNames)
}

const handleMenuPrefetch = (item) => {
  if (item?.routeName) {
    prefetchRouteByName(router, item.routeName)
  }
}

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
  localStorage.setItem('sidebarCollapsed', String(isCollapsed.value))
  syncSidebarWidth()
}

const refreshSessionMenus = () => {
  sessionVersion.value += 1
  syncExpandedSubsystems()
}

const handleSystemNameUpdated = (event) => {
  systemName.value = String(event?.detail?.systemName || getStoredSystemName()).trim() || getStoredSystemName()
}

watch(
  () => route.fullPath,
  () => syncExpandedSubsystems(),
  { immediate: true }
)

onMounted(() => {
  isCollapsed.value = localStorage.getItem('sidebarCollapsed') === 'true'
  systemName.value = getStoredSystemName()
  syncSidebarWidth()
  syncExpandedSubsystems()
  window.addEventListener('platform-session-updated', refreshSessionMenus)
  window.addEventListener('platform-system-name-updated', handleSystemNameUpdated)
})

onUnmounted(() => {
  window.removeEventListener('platform-session-updated', refreshSessionMenus)
  window.removeEventListener('platform-system-name-updated', handleSystemNameUpdated)
})
</script>

<style scoped lang="scss">
.sidebar {
  position: relative;
  z-index: 100;
  width: var(--sidebar-width, 248px);
  padding: 0;
  z-index: 1200;
  transition: width 0.28s ease, transform 0.28s ease;

  &.collapsed {
    .logo,
    .collapse-btn,
    .subsystem-item,
    .submenu-item {
      justify-content: center;
    }

    .logo {
      padding-inline: 10px;
    }

    .logo-icon {
      margin-inline: auto;
    }

    .subsystem-item {
      padding-inline: 10px;
    }

    .submenu-list,
    .subsystem-arrow {
      display: none;
    }

    .sidebar-foot {
      padding-inline: 8px;
    }
  }
}

.sidebar-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  border-radius: 0;
  background: var(--panel-surface);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-right: 1px solid var(--border-soft);
  overflow: hidden;
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.05);
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 16px 20px;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  border-bottom: 1px solid var(--border-soft);
}

.logo-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: #06121d;
  background:
    radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.68), transparent 28%),
    linear-gradient(135deg, var(--accent), var(--accent-strong));
  box-shadow: 0 14px 28px color-mix(in srgb, var(--accent-strong) 18%, transparent);
}

.logo-copy {
  display: grid;
  min-width: 0;
}

.logo-copy strong {
  font-size: 15px;
  color: var(--text-emphasis);
  line-height: 1.1;
}

.menu {
  flex: 1;
  padding: 8px 6px 10px;
  overflow-y: auto;
}

.subsystem-block + .subsystem-block {
  margin-top: 4px;
}

.subsystem-item,
.submenu-item,
.collapse-btn {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 7px 8px;
  border: 0;
  border-radius: 8px;
  color: var(--text-secondary);
  background: transparent;
  cursor: pointer;
  transition:
    background 0.2s ease,
    color 0.2s ease,
    transform 0.2s ease,
    box-shadow 0.2s ease;
}

.subsystem-item.active {
  color: var(--text-emphasis);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

.subsystem-main {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  flex: 1;
}

.subsystem-icon {
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: color-mix(in srgb, var(--text-emphasis) 90%, transparent);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.03), transparent),
    color-mix(in srgb, var(--surface-soft) 58%, var(--surface-emphasis) 42%);
}

.subsystem-title,
.menu-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.subsystem-title {
  color: var(--text-emphasis);
  font-size: 15px;
  font-weight: 500;
}

.subsystem-arrow {
  color: var(--text-muted);
}

.submenu-list {
  display: grid;
  gap: 4px;
  margin-top: 3px;
  margin-left: 12px;
  padding: 3px 0 3px 10px;
  border-left: 1px solid color-mix(in srgb, var(--accent-strong) 9%, transparent);
}

.group-block {
  display: grid;
  gap: 4px;
}

.group-title {
  display: none;
  padding: 2px 4px;
  color: var(--text-muted);
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.submenu-item {
  padding: 7px 8px;
  border-radius: 7px;
  color: var(--text-secondary);
  font-size: 13px;
}

.subsystem-item:hover,
.submenu-item:hover,
.submenu-item.active,
.collapse-btn:hover {
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--accent) 10%, transparent),
    color-mix(in srgb, var(--surface-soft) 72%, transparent)
  );
  color: var(--text-emphasis);
  box-shadow: 0 12px 22px rgba(4, 10, 18, 0.14);
}

.subsystem-item.active {
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 14%, transparent), transparent 82%),
    color-mix(in srgb, var(--surface-soft) 68%, transparent);
}

.subsystem-item.active .subsystem-icon {
  background:
    radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.12), transparent 34%),
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 24%, transparent), color-mix(in srgb, var(--surface-soft) 54%, transparent));
}

.submenu-item.active {
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 16%, transparent), transparent 78%),
    color-mix(in srgb, var(--surface-soft) 62%, transparent);
}

.sidebar-foot {
  padding: 8px 6px 10px;
}

.collapse-btn {
  justify-content: center;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent 34%),
    color-mix(in srgb, var(--surface-soft) 56%, var(--surface-emphasis) 44%);
  color: var(--text-emphasis);
}

.collapse-btn span {
  font-weight: 600;
}

@media (max-width: 1180px) {
  .sidebar {
    display: none;
  }
}
</style>

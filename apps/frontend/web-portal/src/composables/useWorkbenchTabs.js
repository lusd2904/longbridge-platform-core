import { computed, ref } from 'vue'

const TABS_ENABLED_KEY = 'workbench_tabs_enabled'
const TABS_STORAGE_KEY = 'workbench_tabs'

function readBoolean(key, fallback = true) {
  if (typeof window === 'undefined') {
    return fallback
  }
  const raw = window.localStorage.getItem(key)
  if (raw === null) {
    return fallback
  }
  return raw === 'true'
}

function readTabs() {
  if (typeof window === 'undefined') {
    return []
  }

  try {
    const raw = window.localStorage.getItem(TABS_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed)
      ? parsed.filter((item) => item?.routeName && item.routeName !== 'WorkspaceNavigator' && item.fullPath !== '/workspace')
      : []
  } catch {
    return []
  }
}

const tabsEnabled = ref(readBoolean(TABS_ENABLED_KEY, false))
const tabs = ref(readTabs())

function persistState() {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(TABS_ENABLED_KEY, String(tabsEnabled.value))
  window.localStorage.setItem(TABS_STORAGE_KEY, JSON.stringify(tabs.value))
}

function buildTabFromRoute(route) {
  if (!route?.name || route.meta?.public) {
    return null
  }

  const routeName = String(route.name)
  const fullPath = route.fullPath || route.path || '/'
  const rawTitle = route.meta?.title || routeName
  const dynamicTitle = routeName === 'SymbolDetail' && route.params?.symbol
    ? `${String(route.params.symbol).toUpperCase()} 详情`
    : rawTitle

  return {
    key: fullPath,
    fullPath,
    routeName,
    title: dynamicTitle,
    icon: route.meta?.icon || 'Menu',
    closable: routeName !== 'Dashboard'
  }
}

function syncCurrentRoute(route) {
  const tab = buildTabFromRoute(route)
  if (!tab) {
    return
  }

  if (!tabsEnabled.value) {
    tabs.value = [{ ...tab, closable: false }]
    persistState()
    return
  }

  const index = tabs.value.findIndex((item) => item.key === tab.key)
  if (index >= 0) {
    tabs.value[index] = { ...tabs.value[index], ...tab }
  } else {
    tabs.value.push(tab)
  }
  persistState()
}

function removeTab(tabKey, currentRoute, router) {
  const index = tabs.value.findIndex((item) => item.key === tabKey)
  if (index < 0 || !tabs.value[index].closable) {
    return
  }

  const closingCurrent = currentRoute?.fullPath === tabs.value[index].fullPath
  tabs.value.splice(index, 1)

  if (!tabs.value.length) {
    const fallback = buildTabFromRoute(currentRoute) || {
      key: '/dashboard',
      fullPath: '/dashboard',
      routeName: 'Dashboard',
      title: '仪表盘',
      icon: 'Odometer',
      closable: false
    }
    tabs.value = [fallback]
  }

  persistState()

  if (closingCurrent && router) {
    const nextTab = tabs.value[index] || tabs.value[index - 1] || tabs.value[0]
    router.push(nextTab?.fullPath || '/dashboard')
  }
}

function setTabsEnabled(enabled, currentRoute) {
  tabsEnabled.value = Boolean(enabled)
  syncCurrentRoute(currentRoute)
  persistState()
}

const cachedViewNames = computed(() => {
  if (!tabsEnabled.value) {
    return []
  }
  return Array.from(new Set(tabs.value.map((item) => item.routeName).filter(Boolean)))
})

export function useWorkbenchTabs() {
  return {
    tabsEnabled,
    tabs,
    cachedViewNames,
    syncCurrentRoute,
    removeTab,
    setTabsEnabled
  }
}

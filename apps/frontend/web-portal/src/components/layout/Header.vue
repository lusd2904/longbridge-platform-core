<template>
  <header class="header" :class="{ compact: isCompactLayout, phone: isPhoneLayout }">
    <div class="header-right">
      <div class="market-status-container" :class="{ compact: isCompactLayout }">
        <div v-for="item in marketStatusEntries" :key="item.key" class="market-status">
          <span class="status-label">{{ item.label }}</span>
          <span class="status-dot" :class="item.status.status"></span>
          <span class="status-text">{{ item.status.status_text }}</span>
        </div>
      </div>

      <!-- Return to Portal Button -->
      <button
        type="button"
        class="notification"
        title="返回导航大厅"
        @click="router.push('/portal')"
      >
        <el-icon size="20"><Menu /></el-icon>
      </button>

      <!-- Subsystem Switcher -->
      <el-dropdown class="subsystem-dropdown" trigger="click" @command="(path) => router.push(path)">
        <button type="button" class="theme-switcher subsystem-switcher-btn" title="切换子系统">
          <el-icon :size="16"><Grid /></el-icon>
          <span class="theme-switcher__label">系统</span>
          <el-icon><ArrowDown /></el-icon>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="sys in subsystems" :key="sys.path" :command="sys.path">
              <el-icon :color="sys.color"><component :is="sys.icon" /></el-icon>
              {{ sys.name }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      
      <!-- Theme Switcher -->
      <ThemeSwitcher />
      
      <button
        type="button"
        class="notification"
        :aria-label="notificationButtonLabel"
        :title="notificationButtonLabel"
        @click="goToNotifications"
      >
        <el-badge :value="notificationCount" :max="99" :hidden="!notificationCount" class="notification-badge">
          <el-icon size="20"><Bell /></el-icon>
        </el-badge>
        <span class="notification-label">通知</span>
      </button>

      <div class="user-info">
        <el-dropdown>
          <div class="user-dropdown">
            <el-avatar :size="38" :src="currentUser.avatar || undefined">
              {{ userInitial }}
            </el-avatar>
            <div class="user-copy">
              <strong>{{ displayName }}</strong>
              <span>{{ roleLabel }}</span>
            </div>
            <el-icon><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="router.push('/profile')">个人中心</el-dropdown-item>
              <el-dropdown-item @click="router.push('/broker-management')">券商连接</el-dropdown-item>
              <el-dropdown-item v-if="access.canManageTasks" @click="router.push('/scheduler-center')">任务中心</el-dropdown-item>
              <el-dropdown-item v-if="isAdmin()" @click="router.push('/settings')">系统设置</el-dropdown-item>
              <el-dropdown-item @click="toggleTabsMode">
                {{ tabsEnabled ? '关闭多标签模式' : '开启多标签模式' }}
              </el-dropdown-item>
              <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
  </header>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown, Bell, Menu, Grid, Cpu, Histogram, TrendCharts, Wallet, DataLine, List, Star, Setting } from '@element-plus/icons-vue'
import ThemeSwitcher from './ThemeSwitcher.vue'
import { getMarketStatus } from '../../api/market.js'
import { getAccess, getCurrentUser, isAdmin, logout } from '../../utils/auth.js'
import { useWorkbenchTabs } from '../../composables/useWorkbenchTabs.js'
import { useAdaptiveLayout } from '../../composables/useAdaptiveLayout.js'

const router = useRouter()
const route = useRoute()
const sessionVersion = ref(0)
const liveNotificationCount = ref(null)
const { isCompactLayout, isPhoneLayout } = useAdaptiveLayout()
const MARKET_LABELS = {
  US: '美股',
  HK: '港股',
  CN: 'A股'
}
const MARKET_STATUS_ORDER = ['US', 'HK', 'CN']

const subsystems = [
  { name: 'AI 研判工作台', path: '/ai-analysis', icon: 'Cpu', color: '#60a5fa' },
  { name: '实时市场行情', path: '/market', icon: 'Histogram', color: '#34d399' },
  { name: '量化策略中心', path: '/strategy', icon: 'TrendCharts', color: '#a78bfa' },
  { name: '核心交易台', path: '/trading', icon: 'Wallet', color: '#fbbf24' },
  { name: '全局股票池', path: '/stock-pool', icon: 'DataLine', color: '#60a5fa' },
  { name: '风控与资产', path: '/positions', icon: 'List', color: '#34d399' },
  { name: '智能推荐系统', path: '/recommendations', icon: 'Star', color: '#a78bfa' },
  { name: '平台系统设置', path: '/settings', icon: 'Setting', color: '#fbbf24' }
]

function createPendingMarketStatus() {
  return {
    status: 'closed',
    status_text: '加载中',
    current_time: '--:--'
  }
}

function createMarketStatusMap() {
  return MARKET_STATUS_ORDER.reduce((result, key) => {
    result[key] = createPendingMarketStatus()
    return result
  }, {})
}

const marketStatus = ref(createMarketStatusMap())
const currentUser = computed(() => {
  sessionVersion.value
  return getCurrentUser() || {}
})
const access = computed(() => {
  sessionVersion.value
  return getAccess() || {}
})
const displayName = computed(() => currentUser.value.nickname || currentUser.value.username || '用户')
const userInitial = computed(() => displayName.value.slice(0, 1).toUpperCase())
const roleLabel = computed(() => {
  const roleCode = currentUser.value.roleCode || currentUser.value.role
  return {
    admin: '管理员',
    user: '普通用户',
    trader: '交易用户',
    analyst: '普通用户',
    viewer: '普通用户'
  }[roleCode] || '平台用户'
})
const sessionNotificationCount = computed(() => {
  const count = Number(access.value.notificationCount ?? access.value.pendingNotificationCount ?? 0)
  return count > 0 ? count : 0
})
const notificationCount = computed(() => {
  if (Number.isFinite(liveNotificationCount.value)) {
    return Math.max(0, Number(liveNotificationCount.value) || 0)
  }
  return sessionNotificationCount.value
})
const notificationButtonLabel = computed(() => (
  notificationCount.value > 0
    ? `通知中心，${notificationCount.value} 条未读消息`
    : '通知中心'
))
const { tabsEnabled, setTabsEnabled } = useWorkbenchTabs()
const marketStatusEntries = computed(() => {
  return MARKET_STATUS_ORDER.map((key) => ({
    key,
    label: MARKET_LABELS[key] || key,
    status: marketStatus.value?.[key] || createPendingMarketStatus()
  }))
})

const fetchMarketStatus = async () => {
  try {
    const res = await getMarketStatus()
    if (res?.success && res?.data) {
      marketStatus.value = {
        ...createMarketStatusMap(),
        ...res.data
      }
    }
  } catch (error) {
    console.error('获取市场状态失败:', error)
  }
}

let refreshTimer = null
let initialStatusTimer = null
const refreshSessionView = () => {
  liveNotificationCount.value = null
  sessionVersion.value += 1
}

const syncNotificationCount = (event) => {
  const nextCount = Number(event?.detail?.unreadCount)
  if (!Number.isFinite(nextCount)) {
    return
  }
  liveNotificationCount.value = Math.max(0, nextCount)
}

const goToNotifications = () => {
  if (route.name === 'Notifications') {
    return
  }
  router.push({ name: 'Notifications' })
}

onMounted(() => {
  initialStatusTimer = window.setTimeout(fetchMarketStatus, 800)
  refreshTimer = window.setInterval(fetchMarketStatus, 30000)
  window.addEventListener('platform-session-updated', refreshSessionView)
  window.addEventListener('platform-notifications-updated', syncNotificationCount)
})

onUnmounted(() => {
  if (initialStatusTimer) {
    window.clearTimeout(initialStatusTimer)
  }
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
  }
  window.removeEventListener('platform-session-updated', refreshSessionView)
  window.removeEventListener('platform-notifications-updated', syncNotificationCount)
})

const handleLogout = async () => {
  try {
    await logout()
    localStorage.removeItem('remember_username')
    ElMessage.success('退出登录成功')
    router.push('/login')
  } catch (error) {
    console.error('退出登录失败:', error)
    localStorage.removeItem('remember_username')
    ElMessage.success('已退出登录')
    router.push('/login')
  }
}

const toggleTabsMode = () => {
  setTabsEnabled(!tabsEnabled.value, router.currentRoute.value)
  ElMessage.success(tabsEnabled.value ? '多标签模式已开启' : '多标签模式已关闭')
}

</script>

<style scoped lang="scss">
.header {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin: 0;
  padding: 12px 20px;
  border-radius: 0;
  border: none;
  border-bottom: 1px solid var(--border-soft);
  background: var(--panel-surface);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.05);
}

.header-right,
.market-status-container,
.market-status,
.user-dropdown {
  display: flex;
  align-items: center;
}

.header-right {
  flex: 1 1 auto;
  margin-left: auto;
  gap: 10px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.user-copy span,
.status-label {
  color: var(--text-secondary);
  font-size: 12px;
}

.user-copy strong,
.status-text {
  color: var(--text-emphasis);
}

.market-status-container {
  gap: 8px;
  flex: 1 1 340px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.market-status {
  gap: 7px;
  padding: 7px 10px;
  border-radius: 12px;
  background: var(--surface-soft);
  white-space: nowrap;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;

  &.open {
    background: var(--success);
    box-shadow: 0 0 14px color-mix(in srgb, var(--success) 45%, transparent);
  }

  &.pre {
    background: var(--warning);
    box-shadow: 0 0 14px color-mix(in srgb, var(--warning) 45%, transparent);
  }

  &.post {
    background: var(--info);
    box-shadow: 0 0 14px color-mix(in srgb, var(--info) 45%, transparent);
  }

  &.break {
    background: color-mix(in srgb, var(--warning) 80%, transparent);
    box-shadow: 0 0 14px color-mix(in srgb, var(--warning) 45%, transparent);
  }

  &.night {
    background: var(--accent);
    box-shadow: 0 0 14px color-mix(in srgb, var(--accent) 45%, transparent);
  }

  &.closed {
    background: color-mix(in srgb, var(--text-secondary) 42%, transparent);
  }
}

.notification,
.user-dropdown {
  padding: 7px 10px;
  border-radius: 12px;
  background: var(--surface-soft);
}

.notification {
  border: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-emphasis);
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;

  &:hover,
  &:focus-visible {
    background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 22%, transparent);
    transform: translateY(-1px);
    outline: none;
  }
}

.notification-label {
  color: var(--text-emphasis);
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}

.notification-badge {
  display: inline-flex;
}

:deep(.theme-switcher__label) {
  color: var(--text-emphasis);
}

.user-dropdown {
  gap: 8px;
  color: var(--text-primary);
}

.user-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

@media (max-width: 1200px) {
  .header-right {
    flex-wrap: wrap;
  }

  .header-right {
    width: 100%;
  }

  .market-status-container {
    width: 100%;
    justify-content: flex-start;
    order: 10;
  }
}

@media (max-width: 1180px) {
  .header {
    margin: 8px 10px 0;
    padding: 8px 10px;
  }

  .header-right,
  .market-status-container {
    width: 100%;
  }

  .market-status-container {
    flex-wrap: nowrap;
    overflow-x: auto;
    padding-bottom: 2px;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }

  .market-status {
    flex: 0 0 auto;
    min-width: 116px;
  }

  .user-copy {
    display: none;
  }

  .notification {
    flex: 0 0 auto;
  }

  .user-info {
    flex: 1 1 180px;
  }

  .user-dropdown {
    width: 100%;
    justify-content: space-between;
  }

}

@media (max-width: 640px) {
  .header {
    gap: 8px;
    margin-inline: 8px;
    padding: 8px 10px;
  }

  .market-status {
    min-width: 0;
    padding: 9px 12px;
  }

  .status-label,
  .status-text {
    font-size: 11px;
  }

  .notification-label {
    display: none;
  }

}
</style>

<template>
  <div class="notifications-page">
    <div v-if="!isPhoneLayout" class="page-header">
      <div>
        <h2>消息通知</h2>
      </div>
      <div class="header-actions">
        <el-button type="primary" link :loading="loading" @click="loadNotifications">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
        <el-button type="primary" link :disabled="markAllReadDisabled" @click="markAllRead">
          <el-icon><Check /></el-icon> 全部已读
        </el-button>
        <el-button type="danger" link :disabled="clearAllDisabled" @click="clearAll">
          <el-icon><Delete /></el-icon> 清空
        </el-button>
      </div>
    </div>

    <section v-else class="mobile-notice-command">
      <div class="mobile-notice-copy">
        <strong>消息中心</strong>
      </div>
      <div class="mobile-notice-summary">
        <article class="mobile-notice-card">
          <span>未读数量</span>
          <strong>{{ unreadCount }}</strong>
        </article>
        <article class="mobile-notice-card">
          <span>当前筛选</span>
          <strong>{{ activeType ? getTypeLabel(activeType) : '全部消息' }}</strong>
        </article>
      </div>
      <div class="mobile-notice-actions">
        <el-button type="primary" @click="loadNotifications" :loading="loading">刷新</el-button>
        <el-button :disabled="markAllReadDisabled" @click="markAllRead">全部已读</el-button>
        <el-button type="danger" plain :disabled="clearAllDisabled" @click="clearAll">清空</el-button>
      </div>
    </section>

    <div class="notification-tabs" :class="{ mobile: isPhoneLayout }">
      <el-radio-group v-model="activeType" size="large">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="trade">交易</el-radio-button>
        <el-radio-button value="risk">风控</el-radio-button>
        <el-radio-button value="system">系统</el-radio-button>
      </el-radio-group>
    </div>

    <section v-if="!isPhoneLayout" class="notification-summary">
      <article v-for="item in notificationSummary" :key="item.label" class="summary-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </section>

    <el-card class="notifications-list glass-card" v-loading="loading">
      <div v-if="filteredNotifications.length === 0" class="empty-state">
        <el-empty description="暂无消息">
        </el-empty>
      </div>
      <div v-else>
        <div
          v-for="notification in filteredNotifications"
          :key="notification.id"
          class="notification-item"
          :class="{ unread: !notification.read }"
          @click="handleNotification(notification)"
        >
          <div class="notification-icon" :style="{ background: getTypeColor(notification.type) }">
            <el-icon size="20" color="white">
              <component :is="getTypeIcon(notification.type)" />
            </el-icon>
          </div>
          <div class="notification-content">
            <div class="notification-header">
              <div class="notification-title-wrap">
                <span class="notification-title">{{ notification.title }}</span>
                <el-tag size="small" effect="plain" :type="getTypeTagType(notification.type)">
                  {{ getTypeLabel(notification.type) }}
                </el-tag>
                <span v-if="!notification.read" class="unread-dot">未读</span>
              </div>
              <span class="notification-time">{{ formatTime(notification.time) }}</span>
            </div>
            <div class="notification-message">{{ notification.message }}</div>
            <div class="notification-meta" v-if="notification.symbol">
              <span>{{ notification.symbol }}</span>
            </div>
          </div>
          <div class="notification-actions">
            <el-button
              v-if="!notification.read"
              type="primary"
              link
              size="small"
              @click.stop="markRead(notification)"
            >
              标记已读
            </el-button>
            <el-button type="danger" link size="small" @click.stop="removeNotification(notification)">
              删除
            </el-button>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Delete, Wallet, Warning, Bell, Refresh } from '@element-plus/icons-vue'
import {
  clearNotifications,
  deleteNotificationItem,
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead
} from '../api/risk.js'
import { useAdaptiveLayout } from '../composables/useAdaptiveLayout.js'
import { getSession, setActiveSubsystem, setSession } from '../utils/auth.js'

const router = useRouter()
const { isPhoneLayout } = useAdaptiveLayout()
const loading = ref(false)
const activeType = ref('')
const notifications = ref([])

const emitUnreadCount = (count) => {
  if (typeof window === 'undefined') {
    return
  }
  window.dispatchEvent(new CustomEvent('platform-notifications-updated', {
    detail: {
      unreadCount: Math.max(0, Number(count) || 0)
    }
  }))
}

const syncSessionNotificationCount = (count) => {
  const session = getSession()
  if (!session) {
    emitUnreadCount(count)
    return
  }

  const nextCount = Math.max(0, Number(count) || 0)
  const currentCount = Number(
    session?.access?.notificationCount ??
    session?.access?.pendingNotificationCount ??
    0
  )

  if (currentCount === nextCount) {
    emitUnreadCount(nextCount)
    return
  }

  setSession({
    ...session,
    access: {
      ...(session.access || {}),
      notificationCount: nextCount,
      pendingNotificationCount: nextCount
    }
  })
  emitUnreadCount(nextCount)
}

const ensureNotificationShellContext = () => {
  setActiveSubsystem('platform')
}

const normalizeNotification = (item = {}) => ({
  ...item,
  id: item.id || item.notificationKey || item.notification_key || `${item.type || 'notice'}-${item.time || item.created_at || Date.now()}`,
  notificationKey: item.notificationKey || item.notification_key || item.id || '',
  title: item.title || item.subject || '系统通知',
  message: item.message || item.content || item.description || '',
  type: String(item.type || 'system').toLowerCase(),
  time: item.time || item.created_at || item.createdAt || item.timestamp || '',
  read: Boolean(item.read ?? item.isRead ?? item.is_read),
  route: item.route || item.path || '',
  symbol: item.symbol || item.code || ''
})

const unwrapNotificationPayload = (payload) => {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.items)) return payload.items
  if (Array.isArray(payload?.list)) return payload.list
  return []
}

const filteredNotifications = computed(() => {
  if (!activeType.value) {
    return notifications.value
  }
  return notifications.value.filter((item) => item.type === activeType.value)
})
const unreadCount = computed(() => notifications.value.filter((item) => !item.read).length)
const latestNotificationTime = computed(() => filteredNotifications.value[0]?.time || notifications.value[0]?.time || '')
const hasNotifications = computed(() => filteredNotifications.value.length > 0)
const markAllReadDisabled = computed(() => loading.value || !filteredNotifications.value.some((item) => !item.read))
const clearAllDisabled = computed(() => loading.value || !hasNotifications.value)
const notificationSummary = computed(() => [
  {
    label: '当前筛选',
    value: activeType.value ? getTypeLabel(activeType.value) : '全部消息',
    note: `${filteredNotifications.value.length} 条消息正在当前视图中展示`
  },
  {
    label: '未读数量',
    value: String(unreadCount.value),
    note: unreadCount.value ? '建议优先处理未读提醒' : '当前没有待处理的未读消息'
  },
  {
    label: '最新一条',
    value: latestNotificationTime.value ? formatTime(latestNotificationTime.value) : '--',
    note: latestNotificationTime.value ? '时间线会按最新事件自动靠前' : '等待新的平台消息进入'
  }
])

const getTypeColor = (type) => ({
  trade: 'linear-gradient(135deg, #4f8cff, #2dd4bf)',
  risk: 'linear-gradient(135deg, #ff7b72, #ffb36b)',
  system: 'linear-gradient(135deg, #718096, #94a3b8)'
}[type] || 'linear-gradient(135deg, #718096, #94a3b8)')

const getTypeLabel = (type) => ({
  trade: '交易',
  risk: '风控',
  system: '系统'
}[type] || '通知')

const getTypeTagType = (type) => ({
  trade: 'primary',
  risk: 'warning',
  system: 'info'
}[type] || 'info')

const getTypeIcon = (type) => ({
  trade: Wallet,
  risk: Warning,
  system: Bell
}[type] || Bell)

const loadNotifications = async () => {
  loading.value = true
  try {
    const res = await getNotifications({
      type: activeType.value,
      limit: 60
    })
    notifications.value = unwrapNotificationPayload(res?.data)
      .map((item) => normalizeNotification(item))
      .sort((a, b) => new Date(b.time || 0).getTime() - new Date(a.time || 0).getTime())
    syncSessionNotificationCount(unreadCount.value)
  } catch (error) {
    console.error('加载通知失败:', error)
    ElMessage.error('加载通知失败')
  } finally {
    loading.value = false
  }
}

const markRead = async (notification) => {
  try {
    if (!notification.notificationKey) {
      notification.read = true
      syncSessionNotificationCount(unreadCount.value)
      return
    }
    await markNotificationRead({ notification_key: notification.notificationKey })
    notification.read = true
    syncSessionNotificationCount(unreadCount.value)
    ElMessage.success('已标记为已读')
  } catch (error) {
    ElMessage.error('标记失败')
  }
}

const markAllRead = async () => {
  if (markAllReadDisabled.value) return
  try {
    await markAllNotificationsRead({ type: activeType.value })
    notifications.value = notifications.value.map((item) => (
      activeType.value && item.type !== activeType.value
        ? item
        : { ...item, read: true }
    ))
    syncSessionNotificationCount(unreadCount.value)
    ElMessage.success('全部已读')
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

const removeNotification = async (notification) => {
  try {
    if (notification.notificationKey) {
      await deleteNotificationItem({ notification_key: notification.notificationKey })
      notifications.value = notifications.value.filter((item) => item.notificationKey !== notification.notificationKey)
    } else {
      notifications.value = notifications.value.filter((item) => item.id !== notification.id)
    }
    syncSessionNotificationCount(unreadCount.value)
    ElMessage.success('已删除')
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

const clearAll = async () => {
  if (clearAllDisabled.value) return
  try {
    await clearNotifications({ type: activeType.value })
    notifications.value = activeType.value
      ? notifications.value.filter((item) => item.type !== activeType.value)
      : []
    syncSessionNotificationCount(unreadCount.value)
    ElMessage.success('已清空')
  } catch (error) {
    ElMessage.error('清空失败')
  }
}

const handleNotification = async (notification) => {
  if (!notification.read) {
    await markRead(notification)
  }
  if (notification.route) {
    router.push(notification.route)
  }
}

const formatTime = (time) => {
  if (!time) return '--'
  const current = new Date()
  const target = new Date(time)
  const diff = current.getTime() - target.getTime()
  if (diff < 60 * 1000) return '刚刚'
  if (diff < 60 * 60 * 1000) return `${Math.floor(diff / (60 * 1000))} 分钟前`
  if (diff < 24 * 60 * 60 * 1000) return `${Math.floor(diff / (60 * 60 * 1000))} 小时前`
  return target.toLocaleString('zh-CN')
}

watch(activeType, loadNotifications)
watch(unreadCount, (count) => {
  syncSessionNotificationCount(count)
})

onMounted(() => {
  ensureNotificationShellContext()
  loadNotifications()
})
</script>

<style scoped lang="scss">
.notifications-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.mobile-notice-command {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 26px;
  border: 1px solid var(--border-soft);
  background:
    radial-gradient(circle at top right, color-mix(in srgb, var(--accent) 14%, transparent), transparent 42%),
    var(--surface-panel);
  box-shadow: var(--shadow-soft);
}

.mobile-notice-copy {
  display: grid;
  gap: 6px;
}

.mobile-notice-copy strong {
  color: var(--text-primary);
  font-size: 24px;
}

.mobile-notice-copy p,
.mobile-notice-card small {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.6;
}

.mobile-notice-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.mobile-notice-card {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 18px;
  border: 1px solid var(--border-soft);
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
}

.mobile-notice-card span {
  color: var(--text-muted);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.mobile-notice-card strong {
  color: var(--text-primary);
  font-size: 18px;
}

.mobile-notice-actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;

  h2 {
    margin: 0;
    color: var(--text-primary);
  }

  p {
    margin: 6px 0 0;
    color: var(--text-secondary);
    line-height: 1.6;
  }
}

.header-actions {
  display: flex;
  gap: 8px;
}

.notification-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.summary-card {
  padding: 16px 18px;
  border-radius: 20px;
  border: 1px solid var(--border-soft);
  background: var(--surface-panel);
  box-shadow: var(--shadow-soft);

  span {
    color: var(--text-muted);
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  strong {
    display: block;
    margin-top: 10px;
    color: var(--text-primary);
    font-size: 24px;
  }

  p {
    margin: 8px 0 0;
    color: var(--text-secondary);
    line-height: 1.6;
  }
}

.notifications-list {
  border: 1px solid var(--border-soft);
  background: var(--surface-panel);
}

.notification-tabs {
  :deep(.el-radio-button__inner) {
    border-radius: 999px;
  }
}

.notification-tabs.mobile {
  position: sticky;
  top: 0;
  z-index: 8;
  padding-top: 2px;
  background: linear-gradient(180deg, var(--shell-surface), transparent);
}

.notification-tabs.mobile :deep(.el-radio-group) {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  width: 100%;
}

.notification-tabs.mobile :deep(.el-radio-button) {
  width: 100%;
}

.notification-tabs.mobile :deep(.el-radio-button__inner) {
  width: 100%;
}

.notification-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px;
  border-bottom: 1px solid var(--border-soft);
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: rgba(255, 255, 255, 0.05);
    transform: translateY(-1px);
  }

  &.unread {
    background: color-mix(in srgb, var(--accent) 10%, transparent);

    .notification-title {
      font-weight: 700;
    }
  }
}

.notification-icon {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.18);
}

.notification-content {
  flex: 1;
  min-width: 0;
}

.notification-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 6px;
}

.notification-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.notification-title {
  color: var(--text-primary);
}

.unread-dot {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  color: var(--accent-strong);
  font-size: 11px;
}

.notification-time,
.notification-meta {
  color: var(--text-secondary);
  font-size: 12px;
}

.notification-message {
  color: var(--text-secondary);
  line-height: 1.6;
}

.notification-actions {
  display: flex;
  gap: 8px;
}

.empty-state {
  padding: 72px 0;
}

.empty-copy {
  display: grid;
  gap: 8px;
  justify-items: center;
  text-align: center;

  strong {
    color: var(--text-primary);
  }

  span {
    max-width: 360px;
    color: var(--text-secondary);
    line-height: 1.7;
  }
}

@media (max-width: 980px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .notification-summary {
    grid-template-columns: 1fr;
  }

  .notification-item {
    align-items: flex-start;
  }

  .notification-actions {
    flex-direction: column;
    align-items: flex-end;
  }

  .mobile-notice-summary,
  .mobile-notice-actions {
    grid-template-columns: 1fr;
  }
}
</style>

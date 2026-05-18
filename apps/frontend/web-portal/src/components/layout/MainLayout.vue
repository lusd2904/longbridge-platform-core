<template>
  <div class="layout" :class="{ compact: isCompactLayout }">
    <div class="shell-grid" aria-hidden="true"></div>
    <Sidebar v-if="!isCompactLayout" />
    <div class="main-content" :class="{ compact: isCompactLayout }">
      <Header v-if="!isCompactLayout" />
      <RouteTabs v-if="!isCompactLayout" />
      <div v-else class="mobile-header">
        <div class="mobile-header-shell">
          <div class="mobile-header-actions">
            <button type="button" class="mobile-header-button" @click="openMobileCommand">
              <el-icon :size="18"><Menu /></el-icon>
            </button>
            <ThemeSwitcher compact />
            <button type="button" class="mobile-header-button" @click="router.push({ name: 'Notifications' })">
              <el-icon :size="18"><Bell /></el-icon>
            </button>
            <button type="button" class="mobile-header-profile" @click="router.push({ name: 'Profile' })">
              <span>{{ currentUserName.slice(0, 1).toUpperCase() }}</span>
            </button>
          </div>
        </div>
      </div>
      <main class="content" :class="{ compact: isCompactLayout, phone: isPhoneLayout }">
        <router-view v-slot="{ Component, route }">
          <Suspense>
            <template #default>
              <keep-alive :include="cacheInclude">
                <component
                  :is="Component"
                  :key="tabsEnabled ? route.fullPath : (route.name || route.fullPath)"
                />
              </keep-alive>
            </template>
            <template #fallback>
              <RouteSkeleton />
            </template>
          </Suspense>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, Suspense } from 'vue'
import { Bell, Menu } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import Header from './Header.vue'
import RouteTabs from './RouteTabs.vue'
import Sidebar from './Sidebar.vue'
import ThemeSwitcher from './ThemeSwitcher.vue'
import RouteSkeleton from '../common/RouteSkeleton.vue'
import { useWorkbenchTabs } from '../../composables/useWorkbenchTabs.js'
import { useAdaptiveLayout } from '../../composables/useAdaptiveLayout.js'
import { getCurrentUser } from '../../utils/auth.js'

const { tabsEnabled, cachedViewNames } = useWorkbenchTabs()
const cacheInclude = computed(() => (tabsEnabled.value ? cachedViewNames.value : []))
const { isCompactLayout, isPhoneLayout } = useAdaptiveLayout()
const router = useRouter()

const currentUser = computed(() => getCurrentUser() || {})
const currentUserName = computed(() => currentUser.value.nickname || currentUser.value.username || 'U')

const openMobileCommand = () => {
  window.dispatchEvent(new CustomEvent('platform-mobile-drawer-open'))
}
</script>

<style scoped lang="scss">
.layout {
  position: relative;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  overflow-x: clip;
  overflow-y: visible;
}

.shell-grid {
  position: absolute;
  pointer-events: none;
}

.shell-grid {
  inset: 0;
  z-index: 0;
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    linear-gradient(180deg, rgba(255, 255, 255, 0.028) 1px, transparent 1px);
  background-size: 88px 88px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.18), transparent 72%);
  opacity: 0.12;
}

.main-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 100vh;
  min-height: 100dvh;
  height: auto;
  margin-left: var(--sidebar-width, 260px);
  transition: margin-left 0.28s ease;
  overflow: visible;
}

.main-content.compact {
  margin-left: 0;
}

.mobile-header {
  position: sticky;
  top: 0;
  z-index: 90;
  padding: calc(6px + env(safe-area-inset-top, 0px)) 8px 4px;
  background: linear-gradient(180deg, rgba(3, 10, 20, 0.78), rgba(3, 10, 20, 0));
  backdrop-filter: blur(12px);
}

.mobile-header-shell {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid color-mix(in srgb, var(--accent) 12%, var(--border-soft));
  border-radius: 10px;
  background:
    radial-gradient(circle at top right, color-mix(in srgb, var(--accent) 12%, transparent), transparent 30%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0.03)),
    color-mix(in srgb, var(--surface-strong) 90%, black 10%);
  box-shadow: var(--chrome-shadow), var(--chrome-inset);
}

.mobile-header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mobile-header-button,
.mobile-header-profile {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface-soft) 84%, transparent);
  color: var(--text-emphasis);
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.mobile-header-button:hover,
.mobile-header-profile:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--accent) 24%, transparent);
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
}

.mobile-header-profile span {
  font-size: 14px;
  font-weight: 700;
}

.content {
  position: relative;
  flex: 1 0 auto;
  min-height: 0;
  padding: 8px 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-x: clip;
  overflow-y: visible;
  overscroll-behavior-y: auto;
  -webkit-overflow-scrolling: touch;
  isolation: isolate;
}

.content::before {
  content: none;
  position: absolute;
  inset: 0 8px 10px;
  border-radius: 10px;
  background: var(--shell-surface);
  border: 1px solid var(--workspace-shell-border);
  box-shadow: var(--shadow-strong), var(--shell-inset);
  backdrop-filter: var(--shell-backdrop);
  pointer-events: none;
}

.content > * {
  position: relative;
  z-index: 1;
}

@media (max-width: 960px) {
  .content {
    min-height: 0;
    padding: 5px 8px calc(66px + env(safe-area-inset-bottom, 0px));
  }

  .content::before {
    inset: 0 6px calc(58px + env(safe-area-inset-bottom, 0px));
    border-radius: 10px;
  }
}

@media (max-width: 1180px) {
  .content.compact {
    min-height: 0;
    padding: 5px 8px calc(68px + env(safe-area-inset-bottom, 0px));
  }

  .content.compact::before {
    inset: 0 6px calc(58px + env(safe-area-inset-bottom, 0px));
    border-radius: 10px;
  }
}

@media (max-width: 768px) {
  .mobile-header {
    padding-inline: 8px;
  }

  .content.phone {
    min-height: 0;
    padding: 4px 6px calc(66px + env(safe-area-inset-bottom, 0px));
    gap: 7px;
  }

  .content.phone::before {
    inset: 0 5px calc(56px + env(safe-area-inset-bottom, 0px));
    border-radius: 9px;
  }

  .mobile-header-shell {
    padding: 7px 9px;
    border-radius: 10px;
  }

}
</style>

<template>
  <router-view />
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTheme } from './composables/useTheme.js'
import { getSession, getToken, setSession } from './utils/auth.js'
import { getPlatformBootstrap } from './api/platform.js'

const { applyTheme } = useTheme()
const router = useRouter()
const route = useRoute()

const shouldSurfaceSystemToast = () => {
  if (typeof window === 'undefined') {
    return true
  }
  return window.location.pathname !== '/login'
}

const handlePwaUpdate = async (event) => {
  const updateSW = event?.detail?.updateSW
  if (!updateSW) {
    return
  }

  try {
    await ElMessageBox.confirm('检测到新版本，是否立即刷新应用？', '应用更新', {
      confirmButtonText: '立即刷新',
      cancelButtonText: '稍后',
      type: 'info'
    })
    await updateSW(true)
  } catch {
    // 用户稍后处理即可
  }
}

const handleOfflineReady = () => {
  if (!shouldSurfaceSystemToast()) {
    return
  }
  ElMessage.success('离线缓存已就绪，常用页面支持更快打开')
}

const handlePwaError = () => {
  if (!shouldSurfaceSystemToast()) {
    return
  }
  ElMessage.warning('PWA 注册失败，已自动回退到普通网页模式')
}

const handleNativeExitHint = () => {
  ElMessage.info('再按一次返回键退出应用')
}

const normalizeHomePath = (value) => {
  const candidate = String(value || '').trim()
  if (!candidate || candidate === '/workspace') {
    return '/portal'
  }
  return candidate
}

const refreshPlatformBootstrap = async () => {
  if (!getToken()) {
    return
  }

  try {
    const res = await getPlatformBootstrap()
    if (!res?.data) {
      return
    }
    setSession(res.data)
    const readyPath = router.currentRoute.value.path
    const homePath = normalizeHomePath(res.data?.navigation?.homePath)
    if (readyPath === '/' || readyPath === '/workspace' || readyPath === '/portal') {
      router.replace(homePath).catch(() => {})
    }
  } catch {
    // Keep the current cached session when the bootstrap refresh is temporarily unavailable.
  }
}

onMounted(() => {
  applyTheme()

  router.isReady().then(() => {
    const currentPath = router.currentRoute.value.path
    const existingSession = getSession()

    if (existingSession && (currentPath === '/' || currentPath === '/workspace' || currentPath === '/portal')) {
      const homePath = normalizeHomePath(existingSession?.navigation?.homePath)
      router.replace(homePath).catch(() => {})
    }

    refreshPlatformBootstrap()
  })

  window.addEventListener('pwa-update-ready', handlePwaUpdate)
  window.addEventListener('pwa-offline-ready', handleOfflineReady)
  window.addEventListener('pwa-register-error', handlePwaError)
  window.addEventListener('native-exit-hint', handleNativeExitHint)
})

onUnmounted(() => {
  window.removeEventListener('pwa-update-ready', handlePwaUpdate)
  window.removeEventListener('pwa-offline-ready', handleOfflineReady)
  window.removeEventListener('pwa-register-error', handlePwaError)
  window.removeEventListener('native-exit-hint', handleNativeExitHint)
})
</script>

<style>
:root {
  --font-cjk:
    'PingFang SC',
    'Hiragino Sans GB',
    'Noto Sans CJK SC',
    'Microsoft YaHei',
    'Source Han Sans SC';
  --font-heading:
    'Inter',
    var(--font-cjk),
    -apple-system,
    BlinkMacSystemFont,
    'SF Pro Display',
    'Segoe UI',
    'Helvetica Neue',
    Arial,
    sans-serif;
  --font-body:
    'Inter',
    var(--font-cjk),
    -apple-system,
    BlinkMacSystemFont,
    'SF Pro Text',
    'Segoe UI',
    'Helvetica Neue',
    Arial,
    sans-serif;
  --el-font-family: var(--font-body);
  --sidebar-width: 260px;
  --radius-strong: 28px;
  --radius-soft: 20px;
  --page-grid:
    linear-gradient(135deg, rgba(255, 255, 255, 0.035), transparent 32%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent 48%);
  --panel-highlight: linear-gradient(180deg, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0.05));
  --panel-surface: var(--panel-highlight), var(--overlay-bg);
  --chrome-surface: linear-gradient(180deg, rgba(255, 255, 255, 0.13), rgba(255, 255, 255, 0.05)), var(--overlay-bg);
  --shell-surface: linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02)), var(--workspace-shell-bg);
  --panel-backdrop: blur(24px) saturate(145%);
  --chrome-backdrop: blur(28px) saturate(150%);
  --shell-backdrop: none;
  --panel-inset: inset 0 1px 0 color-mix(in srgb, var(--accent-strong) 8%, transparent);
  --chrome-inset: inset 0 1px 0 color-mix(in srgb, var(--accent-strong) 9%, transparent);
  --shell-inset: inset 0 1px 0 color-mix(in srgb, var(--accent-strong) 5%, transparent);
  --chrome-shadow: 0 12px 30px rgba(2, 10, 24, 0.24);
  --sidebar-shadow: 0 18px 44px rgba(3, 10, 24, 0.36);
  --button-primary-solid-bg: #164a72;
  --button-primary-solid-bg-hover: #1b628d;
  --button-primary-bg: linear-gradient(135deg, #164a72 0%, #0e5f83 100%);
  --button-primary-bg-hover: linear-gradient(135deg, #1b628d 0%, #15739b 100%);
  --button-primary-text: #f9fdff;
  --button-primary-border: color-mix(in srgb, var(--accent) 34%, transparent);
  --button-primary-shadow: 0 16px 36px color-mix(in srgb, var(--accent-strong) 24%, transparent);
  --button-secondary-bg: color-mix(in srgb, var(--surface-soft) 84%, var(--surface-strong) 16%);
  --button-secondary-bg-hover: color-mix(in srgb, var(--surface-soft) 90%, var(--surface-strong) 10%);
  --button-secondary-text: var(--text-primary);
  --button-secondary-border: var(--border-soft);
  --button-link-color: color-mix(in srgb, var(--accent) 74%, var(--text-primary) 12%);
  --table-divider: color-mix(in srgb, var(--border-soft) 46%, transparent);
  --table-frame: color-mix(in srgb, var(--border-soft) 62%, transparent);
  --surface-panel: var(--panel-surface);
  --info: color-mix(in srgb, var(--accent-strong) 72%, white 16%);
  --safe-area-top: env(safe-area-inset-top, 0px);
  --safe-area-right: env(safe-area-inset-right, 0px);
  --safe-area-bottom: env(safe-area-inset-bottom, 0px);
  --safe-area-left: env(safe-area-inset-left, 0px);
}

:root,
:root,
:root[data-theme='tremor-light'] {
  --page-bg: #f8fafc;
  --page-bg-size: auto;
  --surface-strong: #ffffff;
  --surface-soft: #ffffff;
  --surface-muted: #f1f5f9;
  --surface-emphasis: #e2e8f0;
  --overlay-bg: rgba(255, 255, 255, 0.8);
  --loading-mask: rgba(255, 255, 255, 0.9);
  --border-soft: #e2e8f0;
  --border-strong: #cbd5e1;
  --panel-stroke: #e2e8f0;
  --shadow-strong: 0 1px 2px 0 rgba(0, 0, 0, 0.05), 0 1px 3px 0 rgba(0, 0, 0, 0.1);
  --text-primary: #0f172a;
  --text-secondary: #334155;
  --text-muted: #64748b;
  --text-emphasis: #000000;
  --accent: #2563eb;
  --accent-strong: #1d4ed8;
  --success: #10b981;
  --danger: #ef4444;
  --warning: #f59e0b;
  --chart-axis: #94a3b8;
  --chart-grid: #e2e8f0;
  --table-header-bg: #ffffff;
  --table-row-hover: #f1f5f9;
  --workspace-shell-bg: #f8fafc;
  --workspace-shell-border: #e2e8f0;
  --panel-surface: #ffffff;
  --chrome-surface: #ffffff;
  --shell-surface: #f8fafc;
  --shell-backdrop: none;

  /* Element Plus Mappings */
  --el-color-primary: var(--accent);
  --el-bg-color: var(--page-bg);
  --el-bg-color-overlay: var(--surface-strong);
  --el-bg-color-page: var(--page-bg);
  --el-border-color: var(--border-soft);
  --el-border-color-light: var(--border-soft);
  --el-border-color-lighter: var(--border-soft);
  --el-fill-color: var(--surface-muted);
  --el-fill-color-blank: var(--surface-strong);
  --el-fill-color-light: var(--surface-muted);
  --el-text-color-primary: var(--text-primary);
  --el-text-color-regular: var(--text-secondary);
  --el-text-color-secondary: var(--text-muted);
  --el-border-radius-base: 8px;
  --el-border-radius-small: 6px;
  --el-border-radius-round: 20px;
}

:root {
  --border-soft: color-mix(in srgb, var(--accent-strong) 10%, transparent);
  --border-strong: color-mix(in srgb, var(--accent-strong) 16%, transparent);
  --panel-stroke: color-mix(in srgb, var(--accent-strong) 7%, transparent);
  --panel-edge: color-mix(in srgb, var(--accent-strong) 11%, transparent);
  --control-border: color-mix(in srgb, var(--accent-strong) 13%, transparent);
  --control-border-hover: color-mix(in srgb, var(--accent-strong) 22%, transparent);
  --table-divider: color-mix(in srgb, var(--accent-strong) 7%, transparent);
  --table-frame: color-mix(in srgb, var(--accent-strong) 11%, transparent);
  --button-secondary-border: color-mix(in srgb, var(--accent-strong) 12%, transparent);
  --el-color-primary: var(--accent-strong);
  --el-color-success: var(--success);
  --el-color-warning: var(--warning);
  --el-color-danger: var(--danger);
  --el-text-color-primary: var(--text-primary);
  --el-text-color-regular: color-mix(in srgb, var(--text-primary) 78%, var(--text-secondary) 22%);
  --el-text-color-secondary: var(--text-secondary);
  --el-text-color-placeholder: color-mix(in srgb, var(--text-secondary) 82%, transparent);
  --el-border-color: var(--control-border);
  --el-border-color-light: var(--panel-edge);
  --el-border-color-lighter: color-mix(in srgb, var(--panel-edge) 76%, transparent);
  --el-fill-color-blank: var(--surface-muted);
  --el-fill-color-light: var(--surface-soft);
  --el-fill-color-lighter: var(--surface-muted);
  --el-fill-color-dark: color-mix(in srgb, var(--surface-emphasis) 92%, transparent);
  --el-fill-color: color-mix(in srgb, var(--surface-soft) 72%, var(--surface-muted) 28%);
  --el-fill-color-darker: color-mix(in srgb, var(--surface-emphasis) 88%, transparent);
  --el-bg-color: transparent;
  --el-bg-color-page: transparent;
  --el-bg-color-overlay: var(--surface-strong);
  --el-color-white: var(--text-emphasis);
  --el-box-shadow-light: var(--shadow-strong);
  --el-mask-color: var(--loading-mask);
  --el-mask-color-extra-light: color-mix(in srgb, var(--loading-mask) 68%, transparent);
  --el-overlay-color-light: color-mix(in srgb, var(--loading-mask) 92%, transparent);
  --el-overlay-color-lighter: var(--loading-mask);
  --el-disabled-bg-color: var(--surface-muted);
  --el-disabled-text-color: color-mix(in srgb, var(--text-secondary) 74%, transparent);
  --el-border-radius-base: 10px;
  --el-border-radius-small: 8px;
  --el-border-radius-round: 999px;
}

:root,
:root[data-theme] {
  --el-color-info: var(--text-secondary) !important;
  --el-color-primary: var(--accent-strong) !important;
  --el-color-success: var(--success) !important;
  --el-color-warning: var(--warning) !important;
  --el-color-danger: var(--danger) !important;
  --el-text-color-primary: var(--text-primary) !important;
  --el-text-color-regular: color-mix(in srgb, var(--text-primary) 78%, var(--text-secondary) 22%) !important;
  --el-text-color-secondary: var(--text-secondary) !important;
  --el-text-color-placeholder: color-mix(in srgb, var(--text-secondary) 82%, transparent) !important;
  --el-disabled-text-color: color-mix(in srgb, var(--text-secondary) 74%, transparent) !important;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html,
body,
#app {
  min-height: 100%;
}

html {
  height: 100%;
  overflow-x: hidden;
  overflow-x: hidden;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}

body {
  margin: 0;
  font-family: var(--font-body);
  color: var(--text-primary);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-strong) 72%, black 28%), color-mix(in srgb, var(--surface-emphasis) 76%, black 24%)),
    var(--page-bg);
  background-attachment: scroll;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior-y: auto;
  touch-action: pan-y pinch-zoom;
  -webkit-overflow-scrolling: touch;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

input,
button,
textarea,
select {
  font: inherit;
}

body::before,
body::after {
  content: none;
  position: fixed;
  inset: auto;
  width: 28vw;
  height: 28vw;
  border-radius: 999px;
  filter: blur(80px);
  opacity: 0.34;
  pointer-events: none;
  z-index: 0;
}

body::before {
  top: -10vw;
  right: -6vw;
  background: var(--glow-a);
}

body::after {
  left: -10vw;
  bottom: -14vw;
  background: var(--glow-b);
}

h1,
h2,
h3,
h4,
h5,
h6 {
  font-family: var(--font-heading);
  letter-spacing: 0;
}

a {
  color: inherit;
  text-decoration: none;
}

::selection {
  background: color-mix(in srgb, var(--accent-strong) 30%, transparent);
  color: var(--text-emphasis);
}

#app {
  position: relative;
  z-index: 1;
  min-height: 100%;
  height: auto;
}

.native-platform body,
body.native-platform {
  -webkit-tap-highlight-color: transparent;
}

input,
select,
textarea {
  font-size: 16px;
}

@media (max-width: 1180px) {
  body {
    background-attachment: scroll, scroll;
  }

  body::before,
  body::after {
    width: 52vw;
    height: 52vw;
    opacity: 0.28;
  }

  .page-header {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 14px;
  }

  .page-header > *,
  .header-actions > *,
  .card-actions > * {
    min-width: 0;
  }

  .header-actions,
  .card-actions {
    display: flex;
    flex-wrap: wrap;
    width: 100%;
    gap: 10px;
  }

  .header-actions .el-input,
  .header-actions .el-input-number,
  .header-actions .el-select,
  .header-actions .el-date-editor,
  .header-actions .el-button,
  .header-actions .el-button-group,
  .card-actions .el-input,
  .card-actions .el-input-number,
  .card-actions .el-select,
  .card-actions .el-date-editor,
  .card-actions .el-button,
  .card-actions .el-button-group {
    width: 100% !important;
  }

  .el-dialog {
    width: min(92vw, 560px) !important;
    margin: max(16px, var(--safe-area-top)) auto !important;
  }

  .el-table,
  .el-tabs__header,
  .el-scrollbar__wrap,
  .el-table__body-wrapper,
  .el-table__header-wrapper {
    -webkit-overflow-scrolling: touch;
  }

  .el-table__body-wrapper,
  .el-table__header-wrapper,
  .el-scrollbar__wrap {
    overflow-x: auto !important;
  }

  .el-drawer {
    max-width: calc(100vw - 16px);
  }

  .el-pagination {
    justify-content: center;
    gap: 8px;
    flex-wrap: wrap;
  }
}

@media (max-width: 640px) {
  .page-header {
    gap: 12px;
  }

  .page-header .el-card__body,
  .page-header .el-card__header {
    padding-inline: 14px;
  }

  .el-card__body {
    padding: 16px;
  }

  .el-message-box {
    width: calc(100vw - 24px) !important;
  }
}

body.native-keyboard-open .mobile-nav {
  opacity: 0;
  pointer-events: none;
  transform: translateY(calc(100% + 24px));
}

.el-button {
  --el-button-text-color: var(--button-secondary-text);
  --el-button-bg-color: var(--button-secondary-bg);
  --el-button-border-color: var(--button-secondary-border);
  --el-button-hover-text-color: var(--button-secondary-text);
  --el-button-hover-bg-color: var(--button-secondary-bg-hover);
  --el-button-hover-border-color: var(--control-border-hover);
  --el-button-active-text-color: var(--button-secondary-text);
  --el-button-active-bg-color: var(--button-secondary-bg-hover);
  --el-button-active-border-color: var(--control-border-hover);
  --el-button-disabled-text-color: color-mix(in srgb, var(--text-secondary) 80%, transparent);
  --el-button-disabled-bg-color: color-mix(in srgb, var(--surface-soft) 74%, var(--surface-strong) 26%);
  --el-button-disabled-border-color: color-mix(in srgb, var(--button-secondary-border) 74%, transparent);
  border-radius: 10px;
  font-weight: 700;
}

.el-button--primary:not(.is-link):not(.is-text) {
  --el-button-text-color: var(--button-primary-text);
  --el-button-bg-color: var(--button-primary-solid-bg);
  --el-button-border-color: var(--button-primary-border);
  --el-button-hover-text-color: var(--button-primary-text);
  --el-button-hover-bg-color: var(--button-primary-solid-bg-hover);
  --el-button-hover-border-color: var(--button-primary-border);
  --el-button-active-text-color: var(--button-primary-text);
  --el-button-active-bg-color: var(--button-primary-solid-bg-hover);
  --el-button-active-border-color: var(--button-primary-border);
  --el-button-disabled-text-color: color-mix(in srgb, var(--button-primary-text) 72%, transparent);
  --el-button-disabled-bg-color: color-mix(in srgb, var(--button-primary-solid-bg) 72%, var(--surface-strong) 28%);
  --el-button-disabled-border-color: color-mix(in srgb, var(--button-primary-border) 72%, transparent);
  color: var(--button-primary-text) !important;
  border: 1px solid var(--button-primary-border) !important;
  background-color: var(--button-primary-solid-bg) !important;
  background-image: var(--button-primary-bg) !important;
  box-shadow: var(--button-primary-shadow);
}

.el-button--primary:not(.is-link):not(.is-text):hover,
.el-button--primary:not(.is-link):not(.is-text):focus-visible,
.el-button--primary:not(.is-link):not(.is-text):active {
  color: var(--button-primary-text) !important;
  border-color: var(--button-primary-border) !important;
  background-color: var(--button-primary-solid-bg-hover) !important;
  background-image: var(--button-primary-bg-hover) !important;
}

.el-button.is-text:not(.is-link),
.el-button:not([class*="el-button--"]):not(.is-link):not(.is-text),
.el-button.is-plain:not(.is-link):not(.is-text),
.el-button--default:not(.is-link):not(.is-text) {
  color: var(--button-secondary-text) !important;
  border-color: var(--button-secondary-border) !important;
  background: var(--button-secondary-bg) !important;
}

.el-button.is-text:not(.is-link):hover,
.el-button:not([class*="el-button--"]):not(.is-link):not(.is-text):hover,
.el-button:not([class*="el-button--"]):not(.is-link):not(.is-text):focus-visible,
.el-button.is-plain:not(.is-link):not(.is-text):hover,
.el-button.is-plain:not(.is-link):not(.is-text):focus-visible,
.el-button--default:not(.is-link):not(.is-text):hover,
.el-button--default:not(.is-link):not(.is-text):focus-visible {
  color: var(--button-secondary-text) !important;
  border-color: var(--control-border-hover) !important;
  background: var(--button-secondary-bg-hover) !important;
}

.el-button--primary.is-link,
.el-link.el-link--primary {
  color: var(--button-link-color) !important;
}

.el-button--success.is-link,
.el-link.el-link--success {
  color: var(--success) !important;
}

.el-button--warning.is-link,
.el-link.el-link--warning {
  color: var(--warning) !important;
}

.el-button--danger.is-link,
.el-link.el-link--danger {
  color: var(--danger) !important;
}

.el-button--info.is-link,
.el-link.el-link--info {
  color: var(--text-secondary) !important;
}

.el-button--success:not(.is-link):not(.is-text) {
  color: #052016 !important;
  background-color: #86efac !important;
  background-image: linear-gradient(135deg, color-mix(in srgb, var(--success) 86%, white 14%), color-mix(in srgb, var(--success) 72%, var(--accent) 12%)) !important;
  border-color: color-mix(in srgb, var(--success) 48%, transparent) !important;
}

.el-button--warning:not(.is-link):not(.is-text) {
  color: #241704 !important;
  background-color: #ffd67d !important;
  background-image: linear-gradient(135deg, color-mix(in srgb, var(--warning) 88%, white 12%), color-mix(in srgb, var(--warning) 72%, var(--accent) 10%)) !important;
  border-color: color-mix(in srgb, var(--warning) 48%, transparent) !important;
}

.el-button--danger:not(.is-link):not(.is-text) {
  color: #2a0608 !important;
  background-color: #ff9f9f !important;
  background-image: linear-gradient(135deg, color-mix(in srgb, var(--danger) 88%, white 12%), color-mix(in srgb, var(--danger) 76%, var(--warning) 8%)) !important;
  border-color: color-mix(in srgb, var(--danger) 48%, transparent) !important;
}

.el-input-group__append .el-button,
.el-input-group__prepend .el-button {
  --el-button-text-color: var(--text-primary);
  --el-button-bg-color: rgba(20, 38, 64, 0.96);
  --el-button-border-color: var(--control-border);
  --el-button-hover-text-color: var(--text-primary);
  --el-button-hover-bg-color: rgba(26, 47, 78, 0.98);
  --el-button-hover-border-color: var(--control-border-hover);
  --el-button-active-text-color: var(--text-primary);
  --el-button-active-bg-color: rgba(26, 47, 78, 0.98);
  --el-button-active-border-color: var(--control-border-hover);
  color: var(--text-primary) !important;
  background-color: rgba(20, 38, 64, 0.96) !important;
  background-image: none !important;
  border-color: var(--control-border) !important;
}

.el-button.is-plain.is-disabled,
.el-button.is-disabled,
.el-button.is-disabled span {
  color: color-mix(in srgb, var(--text-secondary) 78%, transparent) !important;
}

.el-button.is-disabled:not(.is-link):not(.is-text),
.el-button.is-disabled.is-plain:not(.is-link):not(.is-text) {
  border-color: color-mix(in srgb, var(--button-secondary-border) 74%, transparent) !important;
  background: color-mix(in srgb, var(--surface-soft) 74%, var(--surface-strong) 26%) !important;
  opacity: 0.82;
}

.el-card,
.el-table,
.el-dialog,
.el-tabs--border-card,
.el-drawer,
.el-message-box,
.el-dropdown-menu,
.el-select-dropdown,
.el-picker-panel,
.el-date-range-picker,
.el-popover.el-popper,
.el-notification,
.el-message {
  background: transparent !important;
  color: var(--text-primary);
}

.el-dropdown__popper.el-popper,
.el-select__popper.el-popper,
.el-picker__popper.el-popper,
.el-tooltip__popper.el-popper,
.el-popover.el-popper,
.el-cascader__dropdown.el-popper {
  padding: 0 !important;
  overflow: hidden;
  border-radius: 12px !important;
  border: 1px solid var(--panel-edge) !important;
  background: var(--panel-surface) !important;
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.el-dropdown__popper.el-popper > .el-popper__arrow:before,
.el-select__popper.el-popper > .el-popper__arrow:before,
.el-picker__popper.el-popper > .el-popper__arrow:before,
.el-tooltip__popper.el-popper > .el-popper__arrow:before,
.el-popover.el-popper > .el-popper__arrow:before,
.el-cascader__dropdown.el-popper > .el-popper__arrow:before {
  background: color-mix(in srgb, var(--surface-emphasis) 96%, transparent) !important;
  border-color: var(--panel-edge) !important;
}

.el-card,
.el-dialog,
.el-dialog__body,
.el-drawer,
.el-message-box,
.el-dropdown-menu,
.el-select-dropdown,
.el-picker-panel,
.el-date-range-picker,
.el-popover.el-popper,
.el-notification,
.el-message {
  border-radius: 10px !important;
  border: 1px solid var(--panel-edge) !important;
  background: var(--panel-surface) !important;
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.el-dropdown-menu,
.el-select-dropdown,
.el-picker-panel,
.el-date-range-picker,
.el-popover.el-popper,
.el-tooltip__popper.el-popper {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
}

.el-dropdown__list,
.el-select-dropdown__list,
.el-cascader-menu,
.el-picker-panel__content,
.el-date-range-picker__content {
  background: transparent !important;
}

.el-card__header,
.el-card__body,
.el-dialog__header,
.el-dialog__body,
.el-dialog__footer {
  color: var(--text-primary);
  border-color: var(--panel-stroke) !important;
}

.el-input__wrapper,
.el-select__wrapper,
.el-textarea__inner,
.el-input-number,
.el-input-number__decrease,
.el-input-number__increase,
.el-radio-button__inner,
.el-tabs--border-card,
.el-pagination button,
.el-pager li,
.el-date-editor,
.el-date-editor .el-range-input {
  background: var(--surface-soft) !important;
  box-shadow: inset 0 0 0 1px var(--control-border) !important;
  color: var(--text-primary) !important;
}

.el-pagination .btn-prev,
.el-pagination .btn-next,
.el-pagination .el-pager li,
.el-pagination button:disabled {
  border-color: var(--control-border) !important;
}

.el-input__inner,
.el-textarea__inner,
.el-input__inner::placeholder,
.el-textarea__inner::placeholder,
.el-input-number__input {
  color: var(--text-primary) !important;
  -webkit-text-fill-color: var(--text-primary) !important;
}

.el-input__wrapper.is-focus,
.el-select__wrapper.is-focused {
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--accent) 40%, transparent),
    0 12px 32px color-mix(in srgb, var(--accent-strong) 18%, transparent) !important;
}

.el-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-border-color: var(--table-frame);
  --el-table-header-bg-color: var(--table-header-bg);
  --el-table-row-hover-bg-color: var(--table-row-hover);
  --el-table-text-color: var(--text-primary);
  --el-table-header-text-color: var(--text-secondary);
  --el-fill-color-lighter: var(--surface-soft);
  color: var(--text-primary) !important;
}

.el-table td.el-table__cell,
.el-table th.el-table__cell {
  border-bottom-color: var(--table-divider) !important;
}

.el-table th.el-table__cell,
.el-table tr,
.el-table td.el-table__cell,
.el-table__body-wrapper,
.el-table__header-wrapper {
  background: transparent !important;
}

.el-table th.el-table__cell {
  background: var(--table-header-bg) !important;
}

.el-table__inner-wrapper::before {
  background-color: var(--table-frame) !important;
}

.el-table--border::before,
.el-table--border::after,
.el-table--group::after,
.el-table__border-left-patch {
  background-color: var(--table-frame) !important;
}

.el-descriptions {
  --el-descriptions-table-border: var(--panel-stroke);
  color: var(--text-primary) !important;
}

.el-descriptions__body,
.el-descriptions__table,
.el-descriptions__cell {
  border-color: var(--panel-stroke) !important;
  background: transparent !important;
  color: var(--text-primary) !important;
}

.el-descriptions__label.el-descriptions__cell,
.el-descriptions__label {
  background: color-mix(in srgb, var(--surface-soft) 90%, var(--surface-emphasis) 10%) !important;
  color: var(--text-secondary) !important;
  font-weight: 700;
}

.el-descriptions__content.el-descriptions__cell,
.el-descriptions__content {
  background: color-mix(in srgb, var(--surface-muted) 88%, transparent) !important;
  color: var(--text-primary) !important;
}

.el-result {
  --el-result-title-font-size: 18px;
  --el-result-subtitle-font-size: 13px;
}

.el-result__title,
.el-result__title p,
.el-result__subtitle,
.el-result__subtitle p {
  color: var(--text-primary) !important;
}

.el-result__subtitle {
  color: var(--text-secondary) !important;
}

.el-dialog :where(p, span, small, strong, label, div),
.el-message-box :where(p, span, small, strong, label, div) {
  color: inherit;
}

.el-descriptions__label,
.el-descriptions__content,
.el-dialog__title,
.el-drawer__title,
.el-message-box__title,
.el-message-box__content,
.el-dropdown-menu__item,
.el-select-dropdown__item,
.el-checkbox__label,
.el-radio__label,
.el-form-item__label,
.el-empty__description p {
  color: var(--text-primary) !important;
}

.el-timeline {
  --el-timeline-node-color: color-mix(in srgb, var(--text-secondary) 46%, var(--panel-edge));
  color: var(--text-primary) !important;
}

.el-timeline-item {
  padding-bottom: 14px !important;
}

.el-timeline-item__content {
  color: var(--text-primary) !important;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
}

.el-timeline-item__timestamp {
  color: var(--text-secondary) !important;
  font-size: 12px;
  line-height: 1.35 !important;
}

.el-timeline-item__tail {
  border-left-color: color-mix(in srgb, var(--text-secondary) 48%, transparent) !important;
}

.el-timeline-item__node {
  box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 12%, transparent);
}

.el-text,
.el-statistic__head,
.el-step__description,
.el-upload__tip,
.el-form-item__error,
.el-checkbox__label,
.el-radio__label,
.el-input__count,
.el-select-dropdown__empty,
.el-table__empty-text,
.el-empty__description {
  color: var(--text-secondary) !important;
}

.el-statistic__content,
.el-step__title,
.el-collapse-item__header,
.el-collapse-item__content,
.el-tabs__item {
  color: var(--text-primary) !important;
}

.el-dropdown-menu__item:hover,
.el-select-dropdown__item.hover,
.el-select-dropdown__item:hover {
  background: var(--surface-soft) !important;
}

.el-select-dropdown__item.selected {
  color: var(--accent) !important;
}

.el-dialog__headerbtn .el-dialog__close,
.el-message-box__headerbtn .el-message-box__close {
  color: var(--text-secondary) !important;
}

.el-dialog__headerbtn:hover .el-dialog__close,
.el-message-box__headerbtn:hover .el-message-box__close {
  color: var(--text-primary) !important;
}

.el-overlay,
.el-overlay-dialog {
  background: transparent !important;
}

.el-loading-mask {
  background: var(--loading-mask) !important;
  backdrop-filter: blur(18px);
}

.el-skeleton__item {
  background:
    linear-gradient(
      90deg,
      color-mix(in srgb, var(--surface-muted) 88%, transparent),
      color-mix(in srgb, var(--surface-soft) 90%, var(--accent-strong) 4%),
      color-mix(in srgb, var(--surface-muted) 88%, transparent)
    ) !important;
  background-size: 220% 100% !important;
}

.el-divider {
  border-color: var(--panel-stroke) !important;
}

.el-progress-bar__outer {
  background: var(--surface-muted) !important;
}

.el-tag {
  border-radius: 999px;
  border-color: transparent !important;
}

.el-tag--primary {
  background: color-mix(in srgb, var(--accent-strong) 26%, transparent) !important;
  color: color-mix(in srgb, var(--text-primary) 86%, var(--accent) 14%) !important;
}

.el-tag--success {
  background: color-mix(in srgb, var(--success) 18%, transparent) !important;
  color: var(--success) !important;
}

.el-tag--danger {
  background: color-mix(in srgb, var(--danger) 18%, transparent) !important;
  color: var(--danger) !important;
}

.el-tag--warning {
  background: color-mix(in srgb, var(--warning) 18%, transparent) !important;
  color: var(--warning) !important;
}

.el-tag--info {
  background: color-mix(in srgb, var(--text-secondary) 18%, transparent) !important;
  color: var(--text-secondary) !important;
}

.page-header h2,
.card-header,
.symbol,
.price,
.value {
  color: var(--text-primary);
}
</style>

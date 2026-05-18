import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  getActiveView,
  getCurrentUser,
  getMenusByView,
  getViews,
  setActiveView
} from '../../utils/auth.js'

export function usePlatformShell() {
  const sessionVersion = ref(0)

  const refresh = () => {
    sessionVersion.value += 1
  }

  onMounted(() => {
    window.addEventListener('platform-session-updated', refresh)
  })

  onUnmounted(() => {
    window.removeEventListener('platform-session-updated', refresh)
  })

  const availableViews = computed(() => {
    sessionVersion.value
    return getViews()
  })

  const activeViewCode = computed(() => {
    sessionVersion.value
    return getActiveView()
  })

  const activeView = computed(() => {
    return availableViews.value.find((item) => item.code === activeViewCode.value) || availableViews.value[0] || null
  })

  const visibleMenus = computed(() => {
    sessionVersion.value
    return getMenusByView(activeViewCode.value)
  })

  const currentUser = computed(() => {
    sessionVersion.value
    return getCurrentUser() || {}
  })

  const switchView = (viewCode) => {
    return setActiveView(viewCode)
  }

  return {
    availableViews,
    activeViewCode,
    activeView,
    visibleMenus,
    currentUser,
    switchView,
    refresh
  }
}

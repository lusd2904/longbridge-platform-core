import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Capacitor } from '@capacitor/core'

const COMPACT_BREAKPOINT = 1180
const NATIVE_COMPACT_BREAKPOINT = 1280
const PHONE_BREAKPOINT = 768

function getViewportWidth() {
  if (typeof window === 'undefined') {
    return COMPACT_BREAKPOINT
  }
  return window.innerWidth || document.documentElement.clientWidth || COMPACT_BREAKPOINT
}

function getViewportHeight() {
  if (typeof window === 'undefined') {
    return 0
  }
  return window.innerHeight || document.documentElement.clientHeight || 0
}

function detectTouchCapability() {
  if (typeof window === 'undefined') {
    return false
  }

  return Boolean(
    window.matchMedia?.('(pointer: coarse)')?.matches ||
    navigator.maxTouchPoints > 0 ||
    'ontouchstart' in window
  )
}

export function useAdaptiveLayout() {
  const viewportWidth = ref(getViewportWidth())
  const viewportHeight = ref(getViewportHeight())
  const touchCapable = ref(detectTouchCapability())

  const nativePlatform = Capacitor.isNativePlatform() ? Capacitor.getPlatform() : 'web'
  const isNativeApp = nativePlatform === 'android' || nativePlatform === 'ios'

  const syncViewport = () => {
    viewportWidth.value = getViewportWidth()
    viewportHeight.value = getViewportHeight()
    touchCapable.value = detectTouchCapability()
  }

  const isCompactLayout = computed(() => false)
  const isPhoneLayout = computed(() => false)

  onMounted(() => {
    syncViewport()
    window.addEventListener('resize', syncViewport, { passive: true })
    window.addEventListener('orientationchange', syncViewport, { passive: true })
  })

  onUnmounted(() => {
    window.removeEventListener('resize', syncViewport)
    window.removeEventListener('orientationchange', syncViewport)
  })

  return {
    isCompactLayout,
    isNativeApp,
    isPhoneLayout,
    nativePlatform,
    touchCapable,
    viewportHeight,
    viewportWidth
  }
}

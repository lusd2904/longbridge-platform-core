import { Capacitor } from '@capacitor/core'
import { App as CapacitorApp } from '@capacitor/app'
import { Keyboard, KeyboardResize } from '@capacitor/keyboard'
import { StatusBar, Style } from '@capacitor/status-bar'

const EXIT_GUARD_WINDOW_MS = 1800
let lastExitAttemptAt = 0

function setKeyboardState(isOpen) {
  document.body.classList.toggle('native-keyboard-open', Boolean(isOpen))
}

async function configureStatusBar() {
  try {
    await StatusBar.setStyle({ style: Style.Light })
    await StatusBar.setBackgroundColor({ color: '#08101d' })
    await StatusBar.setOverlaysWebView({ overlay: false })
  } catch (error) {
    console.warn('StatusBar 初始化失败', error)
  }
}

async function configureKeyboard(platform) {
  if (platform === 'ios') {
    try {
      await Keyboard.setResizeMode({ mode: KeyboardResize.Body })
    } catch (error) {
      console.warn('Keyboard resize 初始化失败', error)
    }
  }

  if (platform === 'ios') {
    try {
      await Keyboard.setAccessoryBarVisible({ isVisible: false })
    } catch {
      // iOS 某些上下文不支持时忽略即可
    }
  }
}

export async function setupNativeRuntime(router) {
  if (!Capacitor.isNativePlatform()) {
    return
  }

  const platform = Capacitor.getPlatform()
  document.documentElement.classList.add('native-platform', `platform-${platform}`)
  document.body.classList.add('native-platform', `platform-${platform}`)

  await Promise.allSettled([
    configureStatusBar(),
    configureKeyboard(platform)
  ])

  const handles = await Promise.all([
    Keyboard.addListener('keyboardDidShow', () => setKeyboardState(true)),
    Keyboard.addListener('keyboardDidHide', () => setKeyboardState(false)),
    CapacitorApp.addListener('backButton', ({ canGoBack }) => {
      const currentPath = router.currentRoute.value.path
      if (currentPath !== '/dashboard' && currentPath !== '/login' && canGoBack) {
        router.back()
        return
      }

      const now = Date.now()
      if ((now - lastExitAttemptAt) <= EXIT_GUARD_WINDOW_MS) {
        CapacitorApp.exitApp()
        return
      }

      lastExitAttemptAt = now
      window.dispatchEvent(new CustomEvent('native-exit-hint'))
    })
  ])

  if (platform === 'ios') {
    document.body.classList.add('platform-ios')
  }

  if (platform === 'android') {
    document.body.classList.add('platform-android')
  }

  return () => {
    handles.forEach((handle) => handle.remove())
  }
}

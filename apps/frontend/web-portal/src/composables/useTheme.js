import { computed, ref } from 'vue'

const STORAGE_KEY = 'longbridge-active-theme'

const themeOptions = [
  {
    id: 'liquid-night',
    mode: 'dark',
    label: '默认',
    description: '深色交易界面',
    preview: 'linear-gradient(135deg, #7af1ff 0%, #4f9bff 48%, #102a60 100%)'
  },
  {
    id: 'neon-grid',
    mode: 'dark',
    label: '霓虹',
    description: '高对比行情界面',
    preview: 'linear-gradient(135deg, #93ff5c 0%, #15d1ff 54%, #0b1121 100%)'
  },
  {
    id: 'vulcan-forge',
    mode: 'dark',
    label: '熔岩',
    description: '暖色风险界面',
    preview: 'linear-gradient(135deg, #ffcc6b 0%, #ff5b4d 48%, #1a1210 100%)'
  },
  {
    id: 'emerald-core',
    mode: 'dark',
    label: '翡翠',
    description: '绿色资金界面',
    preview: 'linear-gradient(135deg, #38f0b3 0%, #0fa77e 52%, #081b17 100%)'
  },
  {
    id: 'cobalt-strike',
    mode: 'dark',
    label: '钴蓝',
    description: '蓝色研究界面',
    preview: 'linear-gradient(135deg, #71b8ff 0%, #1b5cff 52%, #0b1526 100%)'
  },
  {
    id: 'obsidian-crown',
    mode: 'dark',
    label: '鎏金',
    description: '金色管理界面',
    preview: 'linear-gradient(135deg, #f6d077 0%, #b8882a 48%, #17181c 100%)'
  },
  {
    id: 'solar-tide',
    mode: 'dark',
    label: '日潮',
    description: '暖光复盘界面',
    preview: 'linear-gradient(135deg, #ffd784 0%, #ff9f6b 44%, #9576ff 100%)'
  }
]

const isValidTheme = (themeId) => themeOptions.some((theme) => theme.id === themeId)

const resolveTheme = () => {
  if (typeof window === 'undefined') {
    return themeOptions[0].id
  }

  const storedTheme = window.localStorage.getItem(STORAGE_KEY)
  return isValidTheme(storedTheme) ? storedTheme : themeOptions[0].id
}

const activeTheme = ref(resolveTheme())

const applyTheme = (themeId = activeTheme.value) => {
  if (typeof document === 'undefined') {
    return
  }

  const currentTheme = themeOptions.find((theme) => theme.id === themeId) || themeOptions[0]
  const nextTheme = currentTheme.id
  document.documentElement.dataset.theme = nextTheme
  document.documentElement.style.colorScheme = currentTheme.mode === 'light' ? 'light' : 'dark'
}

const setTheme = (themeId) => {
  if (!isValidTheme(themeId)) {
    return
  }

  activeTheme.value = themeId
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, themeId)
  }
  applyTheme(themeId)
}

const themeMeta = computed(() => {
  return themeOptions.find((theme) => theme.id === activeTheme.value) || themeOptions[0]
})

if (typeof window !== 'undefined') {
  applyTheme(activeTheme.value)
}

export const getThemeValue = (variableName, fallback = '') => {
  if (typeof window === 'undefined') {
    return fallback
  }

  const value = getComputedStyle(document.documentElement).getPropertyValue(variableName).trim()
  return value || fallback
}

export function useTheme() {
  return {
    themes: themeOptions,
    activeTheme,
    themeMeta,
    applyTheme,
    setTheme
  }
}

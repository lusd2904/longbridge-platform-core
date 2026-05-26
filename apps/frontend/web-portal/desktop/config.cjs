const path = require('node:path')

const DESKTOP_APP_NAME = '量化交易终端'
const DEFAULT_DESKTOP_PORT = 4168
const DEFAULT_API_BASE_URL = 'http://127.0.0.1:3100'
const SERVICE_PORT_ENV = {
  user: ['REF_USER_CENTER_PORT', '8101'],
  market: ['REF_MARKET_SERVICE_PORT', '8102'],
  analysis: ['REF_ANALYSIS_SERVICE_PORT', '8103'],
  strategy: ['REF_STRATEGY_SERVICE_PORT', '8104'],
  trade: ['REF_TRADE_SERVICE_PORT', '8105'],
  sentiment: ['REF_SENTIMENT_SERVICE_PORT', '8106'],
  scheduler: ['REF_SCHEDULER_SERVICE_PORT', '8107'],
  risk: ['REF_RISK_SERVICE_PORT', '8108'],
  gateway: ['REF_GATEWAY_PORT', '5101']
}

function normalizeBaseUrl(rawValue, fallback = DEFAULT_API_BASE_URL) {
  const value = String(rawValue || fallback || '').trim()
  if (!value) {
    return ''
  }
  try {
    const url = new URL(/^https?:\/\//i.test(value) ? value : `http://${value}`)
    url.pathname = url.pathname.replace(/\/+$/, '') || '/'
    url.search = ''
    url.hash = ''
    return url.toString().replace(/\/$/, '')
  } catch {
    return fallback
  }
}

function readDesktopApiBase(env = process.env) {
  return normalizeBaseUrl(
    env.REFV2_DESKTOP_API_BASE
      || env.VITE_DESKTOP_API_BASE_URL
      || env.VITE_NATIVE_API_BASE_URL
      || DEFAULT_API_BASE_URL
  )
}

function readConfiguredDesktopApiBase(env = process.env) {
  return normalizeBaseUrl(
    env.REFV2_DESKTOP_API_BASE
      || env.VITE_DESKTOP_API_BASE_URL
      || env.VITE_NATIVE_API_BASE_URL
      || '',
    ''
  )
}

function readDesktopPort(env = process.env) {
  const port = Number(env.REFV2_DESKTOP_PORT || DEFAULT_DESKTOP_PORT)
  return Number.isInteger(port) && port > 0 ? port : DEFAULT_DESKTOP_PORT
}

function buildServiceTargets(env = process.env) {
  return Object.fromEntries(
    Object.entries(SERVICE_PORT_ENV).map(([serviceName, [envKey, fallbackPort]]) => [
      serviceName,
      normalizeBaseUrl(`http://127.0.0.1:${env[envKey] || fallbackPort}`)
    ])
  )
}

function buildWindowOptions({ dirname = __dirname, apiBaseUrl = DEFAULT_API_BASE_URL, icon } = {}) {
  return {
    width: 1560,
    height: 980,
    minWidth: 1280,
    minHeight: 820,
    title: DESKTOP_APP_NAME,
    backgroundColor: '#08101d',
    icon,
    titleBarStyle: 'hiddenInset',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      additionalArguments: [`--refv2-api-base=${apiBaseUrl}`]
    }
  }
}

function buildMenuTemplate() {
  return [
    {
      label: '应用',
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        { role: 'services' },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'hideOthers' },
        { role: 'unhide' },
        { type: 'separator' },
        { role: 'quit' }
      ]
    },
    {
      label: '窗口',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'togglefullscreen' },
        { type: 'separator' },
        { role: 'minimize' },
        { role: 'zoom' }
      ]
    }
  ]
}

module.exports = {
  DEFAULT_API_BASE_URL,
  DEFAULT_DESKTOP_PORT,
  DESKTOP_APP_NAME,
  SERVICE_PORT_ENV,
  buildMenuTemplate,
  buildServiceTargets,
  buildWindowOptions,
  normalizeBaseUrl,
  readConfiguredDesktopApiBase,
  readDesktopApiBase,
  readDesktopPort
}

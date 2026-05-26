const path = require('node:path')
const fs = require('node:fs')
const { app, BrowserWindow, Menu, nativeTheme, shell } = require('electron')
const {
  buildMenuTemplate,
  buildServiceTargets,
  buildWindowOptions,
  normalizeBaseUrl,
  readConfiguredDesktopApiBase,
  readDesktopPort
} = require('./config.cjs')

const APP_PORT = readDesktopPort()
const API_BASE_URL = readConfiguredDesktopApiBase() || normalizeBaseUrl(`http://127.0.0.1:${APP_PORT}`)
const IS_SMOKE = process.env.REFV2_ELECTRON_SMOKE === '1'

let mainWindow = null
let desktopServer = null
const DESKTOP_ICON = path.join(__dirname, '..', 'build', 'icon.png')

async function ensureDesktopServer() {
  if (desktopServer) {
    return desktopServer
  }

  const { startDesktopServer } = await import('./static-server.mjs')
  desktopServer = await startDesktopServer(APP_PORT, {
    apiBaseUrl: API_BASE_URL,
    serviceTargets: buildServiceTargets()
  })
  return desktopServer
}

async function createMainWindow() {
  const server = await ensureDesktopServer()

  nativeTheme.themeSource = 'dark'
  const icon = fs.existsSync(DESKTOP_ICON) ? DESKTOP_ICON : undefined

  if (process.platform === 'darwin' && icon && app.dock?.setIcon) {
    app.dock.setIcon(icon)
  }

  mainWindow = new BrowserWindow(buildWindowOptions({ dirname: __dirname, apiBaseUrl: API_BASE_URL, icon }))

  Menu.setApplicationMenu(Menu.buildFromTemplate(buildMenuTemplate()))

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.webContents.on('did-finish-load', () => {
    console.log(`desktop_loaded:${mainWindow.webContents.getURL()}`)
    if (IS_SMOKE) {
      mainWindow.webContents.executeJavaScript(
        `JSON.stringify({
          desktop: Boolean(window.__REFV2_DESKTOP__),
          apiBaseUrl: window.__REFV2_DESKTOP_API_BASE__,
          platform: window.refactorDesktop && window.refactorDesktop.platform,
          os: window.refactorDesktop && window.refactorDesktop.os
        })`
      ).then((payload) => {
        console.log(`desktop_context:${payload}`)
      }).catch((error) => {
        console.error(`desktop_context_error:${error?.message || error}`)
      }).finally(() => setTimeout(() => {
        app.quit()
      }, 800))
    }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  await mainWindow.loadURL(`http://127.0.0.1:${server.port}`)
}

app.whenReady().then(async () => {
  await createMainWindow()

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createMainWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', async () => {
  if (desktopServer) {
    try {
      await desktopServer.close()
    } catch {
      // ignore close failures during shutdown
    }
    desktopServer = null
  }
})

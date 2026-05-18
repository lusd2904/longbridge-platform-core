const path = require('node:path')
const fs = require('node:fs')
const { app, BrowserWindow, Menu, nativeTheme, shell } = require('electron')

const APP_PORT = Number(process.env.REFV2_DESKTOP_PORT || 4168)
const API_BASE_URL = process.env.REFV2_DESKTOP_API_BASE
  || process.env.VITE_DESKTOP_API_BASE_URL
  || process.env.VITE_NATIVE_API_BASE_URL
  || 'http://127.0.0.1:3100'
const IS_SMOKE = process.env.REFV2_ELECTRON_SMOKE === '1'

let mainWindow = null
let desktopServer = null
const DESKTOP_ICON = path.join(__dirname, '..', 'build', 'icon.png')

async function ensureDesktopServer() {
  if (desktopServer) {
    return desktopServer
  }

  const { startDesktopServer } = await import('./static-server.mjs')
  desktopServer = await startDesktopServer(APP_PORT)
  return desktopServer
}

async function createMainWindow() {
  const server = await ensureDesktopServer()

  nativeTheme.themeSource = 'dark'
  const icon = fs.existsSync(DESKTOP_ICON) ? DESKTOP_ICON : undefined

  if (process.platform === 'darwin' && icon && app.dock?.setIcon) {
    app.dock.setIcon(icon)
  }

  mainWindow = new BrowserWindow({
    width: 1560,
    height: 980,
    minWidth: 1280,
    minHeight: 820,
    title: 'Refactor V2',
    backgroundColor: '#08101d',
    icon,
    titleBarStyle: 'hiddenInset',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      additionalArguments: [`--refv2-api-base=${API_BASE_URL}`]
    }
  })

  Menu.setApplicationMenu(Menu.buildFromTemplate([
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
  ]))

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.webContents.on('did-finish-load', () => {
    console.log(`desktop_loaded:${mainWindow.webContents.getURL()}`)
    if (IS_SMOKE) {
      setTimeout(() => {
        app.quit()
      }, 2500)
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

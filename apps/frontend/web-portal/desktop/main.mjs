import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { startDesktopServer } from './static-server.mjs'

const require = createRequire(import.meta.url)
const { app, BrowserWindow, Menu, nativeTheme, shell } = require('electron')

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const APP_PORT = Number(process.env.REFV2_DESKTOP_PORT || 4168)
const API_BASE_URL = process.env.REFV2_DESKTOP_API_BASE || 'http://127.0.0.1:3100'
const IS_SMOKE = process.env.REFV2_ELECTRON_SMOKE === '1'

let mainWindow = null
let desktopServer = null

async function createMainWindow() {
  if (!desktopServer) {
    desktopServer = await startDesktopServer(APP_PORT)
  }

  nativeTheme.themeSource = 'dark'

  mainWindow = new BrowserWindow({
    width: 1560,
    height: 980,
    minWidth: 1280,
    minHeight: 820,
    title: 'Refactor V2',
    backgroundColor: '#08101d',
    titleBarStyle: 'hiddenInset',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      additionalArguments: [`--refv2-api-base=${API_BASE_URL}`]
    }
  })

  const menu = Menu.buildFromTemplate([
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
  ])
  Menu.setApplicationMenu(menu)

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

  await mainWindow.loadURL(`http://127.0.0.1:${desktopServer.port}`)
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

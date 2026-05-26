const { contextBridge } = require('electron')
const { buildPreloadContext } = require('./preload-context.cjs')

const preloadContext = buildPreloadContext(process.argv)

contextBridge.exposeInMainWorld('__REFV2_DESKTOP__', preloadContext.__REFV2_DESKTOP__)
contextBridge.exposeInMainWorld('__REFV2_DESKTOP_API_BASE__', preloadContext.__REFV2_DESKTOP_API_BASE__)
contextBridge.exposeInMainWorld('refactorDesktop', preloadContext.refactorDesktop)

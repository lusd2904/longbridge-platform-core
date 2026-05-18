const { contextBridge } = require('electron')

const apiArg = process.argv.find((item) => String(item || '').startsWith('--refv2-api-base='))
const apiBaseUrl = apiArg ? apiArg.replace('--refv2-api-base=', '') : 'http://127.0.0.1:3100'

contextBridge.exposeInMainWorld('__REFV2_DESKTOP__', true)
contextBridge.exposeInMainWorld('__REFV2_DESKTOP_API_BASE__', apiBaseUrl)
contextBridge.exposeInMainWorld('refactorDesktop', {
  platform: 'macos',
  apiBaseUrl
})

function parseDesktopApiBase(argv = process.argv) {
  const apiArg = argv.find((item) => String(item || '').startsWith('--refv2-api-base='))
  return apiArg ? apiArg.replace('--refv2-api-base=', '') : 'http://127.0.0.1:3100'
}

function buildPreloadContext(argv = process.argv) {
  const apiBaseUrl = parseDesktopApiBase(argv)
  return {
    __REFV2_DESKTOP__: true,
    __REFV2_DESKTOP_API_BASE__: apiBaseUrl,
    refactorDesktop: {
      platform: 'desktop',
      os: process.platform,
      apiBaseUrl
    }
  }
}

module.exports = {
  buildPreloadContext,
  parseDesktopApiBase
}

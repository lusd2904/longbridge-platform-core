import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const projectRoot = path.resolve(__dirname, '..')
const appName = '量化交易终端'

function resolveAppRoot() {
  const distRoot = path.resolve(projectRoot, 'desktop-dist')
  const candidateDirs = [
    path.join(distRoot, 'mac'),
    path.join(distRoot, 'mac-arm64'),
    path.join(distRoot, 'mac-universal'),
    ...(
      fs.existsSync(distRoot)
        ? fs.readdirSync(distRoot)
          .filter((entry) => entry.startsWith('mac'))
          .map((entry) => path.join(distRoot, entry))
        : []
    )
  ]
  for (const dir of candidateDirs) {
    const appRoot = path.join(dir, `${appName}.app`)
    if (fs.existsSync(appRoot)) {
      return appRoot
    }
  }
  return path.join(distRoot, 'mac', `${appName}.app`)
}

const appRoot = resolveAppRoot()
const requiredPaths = [
  appRoot,
  path.join(appRoot, 'Contents', 'Info.plist'),
  path.join(appRoot, 'Contents', 'MacOS', appName),
  path.join(appRoot, 'Contents', 'Resources', 'app.asar')
]

const missing = requiredPaths.filter((item) => !fs.existsSync(item))
if (missing.length) {
  console.error(`desktop_package_missing:${missing.join(',')}`)
  process.exit(1)
}

console.log(`desktop_package_verified:${appRoot}`)

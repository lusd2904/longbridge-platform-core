import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const projectRoot = path.resolve(__dirname, '..')
const runtimeDir = path.resolve(projectRoot, '../../runtime/mobile')
const lockDir = path.join(runtimeDir, 'cap-sync.lock')
const lockMetaFile = path.join(lockDir, 'owner.json')

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function acquireLock() {
  await fs.mkdir(runtimeDir, { recursive: true })

  const startedAt = Date.now()
  while (Date.now() - startedAt < 120000) {
    try {
      await fs.mkdir(lockDir)
      await fs.writeFile(lockMetaFile, JSON.stringify({
        pid: process.pid,
        startedAt: new Date().toISOString()
      }, null, 2))
      return
    } catch (error) {
      if (error?.code !== 'EEXIST') {
        throw error
      }
      await sleep(350)
    }
  }

  throw new Error('Timed out waiting for Capacitor sync lock')
}

async function releaseLock() {
  await fs.rm(lockDir, { recursive: true, force: true })
}

async function runCapSync() {
  await acquireLock()

  try {
    await new Promise((resolve, reject) => {
      const child = spawn('npx', ['cap', 'sync'], {
        cwd: projectRoot,
        stdio: 'inherit',
        shell: process.platform === 'win32'
      })

      child.on('exit', (code) => {
        if (code === 0) {
          resolve()
          return
        }
        reject(new Error(`cap sync exited with code ${code}`))
      })

      child.on('error', reject)
    })
  } finally {
    await releaseLock()
  }
}

runCapSync().catch((error) => {
  console.error(error?.stack || error?.message || String(error))
  process.exitCode = 1
})

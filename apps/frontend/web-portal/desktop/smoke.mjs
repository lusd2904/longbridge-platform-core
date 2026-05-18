import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const projectRoot = path.resolve(__dirname, '..')
const electronBin = path.resolve(projectRoot, 'node_modules', '.bin', 'electron')

async function runSmoke() {
  await new Promise((resolve, reject) => {
    const childEnv = {
      ...process.env,
      REFV2_ELECTRON_SMOKE: '1'
    }
    delete childEnv.ELECTRON_RUN_AS_NODE

    const child = spawn(electronBin, ['./desktop/main.cjs'], {
      cwd: projectRoot,
      env: childEnv,
      stdio: ['ignore', 'pipe', 'pipe']
    })

    let output = ''
    let settled = false

    const complete = (error) => {
      if (settled) {
        return
      }
      settled = true
      if (error) {
        reject(error)
        return
      }
      resolve(output)
    }

    child.stdout.on('data', (chunk) => {
      output += chunk.toString()
    })
    child.stderr.on('data', (chunk) => {
      output += chunk.toString()
    })

    child.on('error', complete)
    child.on('exit', (code) => {
      if (code !== 0) {
        complete(new Error(`Electron smoke failed with code ${code}\n${output}`))
        return
      }
      if (!output.includes('desktop_loaded:')) {
        complete(new Error(`Electron smoke missing load marker\n${output}`))
        return
      }
      complete()
    })
  })

  console.log('desktop_smoke_passed')
}

runSmoke().catch((error) => {
  console.error(error?.stack || error?.message || String(error))
  process.exit(1)
})

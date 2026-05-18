import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const projectRoot = path.resolve(__dirname, '..')
const distDir = path.resolve(projectRoot, 'dist')

const MIME_TYPES = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp'
}

function resolveMimeType(filePath = '') {
  return MIME_TYPES[path.extname(filePath).toLowerCase()] || 'application/octet-stream'
}

async function readFileWithFallback(requestPath = '/') {
  const normalizedPath = decodeURIComponent(String(requestPath || '/').split('?')[0]).replace(/^\/+/, '')
  const targetPath = normalizedPath ? path.join(distDir, normalizedPath) : path.join(distDir, 'index.html')

  try {
    const stat = await fs.stat(targetPath)
    if (stat.isDirectory()) {
      const indexPath = path.join(targetPath, 'index.html')
      return {
        filePath: indexPath,
        content: await fs.readFile(indexPath)
      }
    }
    return {
      filePath: targetPath,
      content: await fs.readFile(targetPath)
    }
  } catch {
    const indexPath = path.join(distDir, 'index.html')
    return {
      filePath: indexPath,
      content: await fs.readFile(indexPath)
    }
  }
}

export async function startDesktopServer(port = 4168) {
  const server = http.createServer(async (request, response) => {
    try {
      const { filePath, content } = await readFileWithFallback(request.url || '/')
      response.writeHead(200, {
        'Content-Type': resolveMimeType(filePath),
        'Cache-Control': filePath.endsWith('index.html') ? 'no-cache' : 'public, max-age=31536000, immutable'
      })
      response.end(content)
    } catch (error) {
      response.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' })
      response.end(`Desktop server error: ${error?.message || error}`)
    }
  })

  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(port, '127.0.0.1', () => {
      server.off('error', reject)
      resolve()
    })
  })

  return {
    port,
    close: () => new Promise((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error)
          return
        }
        resolve()
      })
    })
  }
}

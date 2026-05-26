import fs from 'node:fs/promises'
import http from 'node:http'
import { createRequire } from 'node:module'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const require = createRequire(import.meta.url)
const { buildServiceTargets } = require('./config.cjs')
const projectRoot = path.resolve(__dirname, '..')
const distDir = path.resolve(projectRoot, 'dist')
const DEFAULT_API_BASE_URL = 'http://127.0.0.1:3100'

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

function normalizeBaseUrl(rawValue = '') {
  const value = String(rawValue || '').trim()
  if (!value) {
    return ''
  }
  try {
    const url = new URL(/^https?:\/\//i.test(value) ? value : `http://${value}`)
    url.pathname = url.pathname.replace(/\/+$/, '') || '/'
    url.search = ''
    url.hash = ''
    return url.toString().replace(/\/$/, '')
  } catch {
    return ''
  }
}

function resolveMimeType(filePath = '') {
  return MIME_TYPES[path.extname(filePath).toLowerCase()] || 'application/octet-stream'
}

function resolveServiceTarget(requestPath = '', options = {}) {
  const parsedRequest = new URL(String(requestPath || '/'), 'http://127.0.0.1')
  const match = parsedRequest.pathname.match(/^\/svc\/([^/?#]+)(?=\/|$)/)
  if (!match) {
    return null
  }

  const serviceName = match[1]
  const serviceTargets = options.serviceTargets || buildServiceTargets()
  const targetBase = normalizeBaseUrl(serviceTargets[serviceName])
    || normalizeBaseUrl(options.apiBaseUrl)
    || DEFAULT_API_BASE_URL
  const targetUrl = new URL(targetBase)
  targetUrl.pathname = `${targetUrl.pathname.replace(/\/$/, '')}${parsedRequest.pathname.replace(/^\/svc\/[^/?#]+/, '') || '/'}`
  targetUrl.search = parsedRequest.search
  return {
    serviceName,
    targetBase,
    targetUrl
  }
}

function pipeProxyRequest(request, response, target) {
  const targetUrl = target.targetUrl
  const headers = { ...request.headers, host: targetUrl.host }
  const proxy = http.request(
    targetUrl,
    {
      method: request.method,
      headers,
      timeout: 30_000
    },
    (proxyResponse) => {
      response.writeHead(proxyResponse.statusCode || 502, proxyResponse.headers)
      proxyResponse.pipe(response)
    }
  )

  proxy.on('timeout', () => {
    proxy.destroy(new Error(`desktop proxy timeout for ${target.serviceName}`))
  })
  proxy.on('error', (error) => {
    if (!response.headersSent) {
      response.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
    }
    response.end(JSON.stringify({
      success: false,
      error: `Desktop proxy error: ${error?.message || error}`,
      service: target.serviceName
    }))
  })

  request.pipe(proxy)
}

function pipeProxyWebSocket(request, socket, head, target) {
  const targetUrl = new URL(target.targetUrl)
  targetUrl.protocol = targetUrl.protocol === 'https:' ? 'wss:' : 'ws:'
  const proxyRequest = http.request(targetUrl, {
    method: 'GET',
    headers: {
      ...request.headers,
      host: targetUrl.host
    }
  })

  proxyRequest.on('upgrade', (proxyResponse, proxySocket, proxyHead) => {
    socket.write([
      'HTTP/1.1 101 Switching Protocols',
      'Upgrade: websocket',
      'Connection: Upgrade',
      ...Object.entries(proxyResponse.headers).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`),
      '',
      ''
    ].join('\r\n'))
    if (proxyHead?.length) {
      socket.write(proxyHead)
    }
    if (head?.length) {
      proxySocket.write(head)
    }
    proxySocket.pipe(socket)
    socket.pipe(proxySocket)
  })

  proxyRequest.on('error', () => {
    socket.destroy()
  })
  proxyRequest.end()
}

function writeWebSocketTextFrame(socket, payload) {
  const body = Buffer.from(String(payload))
  const header = body.length < 126
    ? Buffer.from([0x81, body.length])
    : Buffer.from([0x81, 126, body.length >> 8, body.length & 0xff])
  socket.write(Buffer.concat([header, body]))
}

function writeWebSocketCloseFrame(socket) {
  socket.write(Buffer.from([0x88, 0x00]), () => {
    socket.destroy()
  })
}

function installDesktopMetaSocket(server) {
  server.on('upgrade', (request, socket, head) => {
    if (request.url === '/__desktop_meta_ws__') {
      const socketKey = request.headers['sec-websocket-key']
      if (!socketKey) {
        socket.destroy()
        return
      }
      const acceptKey = crypto
        .createHash('sha1')
        .update(`${socketKey}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
        .digest('base64')
      socket.write([
        'HTTP/1.1 101 Switching Protocols',
        'Upgrade: websocket',
        'Connection: Upgrade',
        `Sec-WebSocket-Accept: ${acceptKey}`,
        '',
        ''
      ].join('\r\n'))
      writeWebSocketTextFrame(socket, JSON.stringify({
        type: 'desktop-meta',
        payload: {
          desktop: true,
          servedBy: 'refactor-v2-desktop'
        }
      }))
      writeWebSocketCloseFrame(socket)
      return
    }

    const serviceTarget = resolveServiceTarget(request.url || '/', server.__refv2DesktopOptions || {})
    if (serviceTarget) {
      pipeProxyWebSocket(request, socket, head, serviceTarget)
      return
    }

    socket.destroy()
  })
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

export async function startDesktopServer(port = 4168, options = {}) {
  const server = http.createServer(async (request, response) => {
    try {
      const requestPath = request.url || '/'
      const serviceTarget = resolveServiceTarget(requestPath, options)
      if (serviceTarget) {
        pipeProxyRequest(request, response, serviceTarget)
        return
      }

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
  server.__refv2DesktopOptions = options
  installDesktopMetaSocket(server)

  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(port, '127.0.0.1', () => {
      server.off('error', reject)
      resolve()
    })
  })

  const address = server.address()
  const boundPort = typeof address === 'object' && address ? address.port : port

  return {
    port: boundPort,
    serviceTargets: options.serviceTargets || buildServiceTargets(),
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

export const desktopServerInternals = {
  normalizeBaseUrl,
  resolveMimeType,
  resolveServiceTarget
}

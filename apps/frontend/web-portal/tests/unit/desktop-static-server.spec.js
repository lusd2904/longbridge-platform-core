import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { WebSocket } from 'ws'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import {
  desktopServerInternals,
  startDesktopServer
} from '../../desktop/static-server.mjs'

let tempRoot
let distDir
let desktopServer
let apiServer
let upstreamWsPath = ''

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      server.off('error', reject)
      resolve(server.address().port)
    })
  })
}

describe('desktop static server', () => {
  beforeAll(async () => {
    tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'refv2-desktop-static-'))
    distDir = path.join(tempRoot, 'dist')
    await fs.mkdir(path.join(distDir, 'assets'), { recursive: true })
    await fs.writeFile(path.join(distDir, 'index.html'), '<main id="app">desktop shell</main>')
    await fs.writeFile(path.join(distDir, 'assets', 'fixture.js'), 'window.fixture = true')

    apiServer = http.createServer((request, response) => {
      if (request.url === '/api/v1/market/ping') {
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify({ success: true, service: 'market-service' }))
        return
      }
      response.writeHead(404)
      response.end()
    })
    apiServer.on('upgrade', (request, socket) => {
      upstreamWsPath = request.url || ''
      const socketKey = request.headers['sec-websocket-key']
      const acceptKey = socketKey
        ? awaitWebSocketAcceptKey(socketKey)
        : ''
      socket.write([
        'HTTP/1.1 101 Switching Protocols',
        'Upgrade: websocket',
        'Connection: Upgrade',
        `Sec-WebSocket-Accept: ${acceptKey}`,
        '',
        ''
      ].join('\r\n'))
      writeWebSocketTextFrame(socket, JSON.stringify({
        type: 'market-stream-ready',
        path: upstreamWsPath
      }))
      socket.write(Buffer.from([0x88, 0x00]), () => socket.destroy())
    })
    const apiPort = await listen(apiServer)
    desktopServer = await startDesktopServer(0, {
      distDir,
      serviceTargets: {
        market: `http://127.0.0.1:${apiPort}`
      }
    })
  })

  afterAll(async () => {
    if (desktopServer) {
      await desktopServer.close()
    }
    if (apiServer) {
      await new Promise((resolve) => apiServer.close(resolve))
    }
    if (tempRoot) {
      await fs.rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('serves SPA fallback for unknown desktop routes', async () => {
    const response = await fetch(`http://127.0.0.1:${desktopServer.port}/dashboard`)
    const body = await response.text()

    expect(response.status).toBe(200)
    expect(response.headers.get('content-type')).toContain('text/html')
    expect(body).toContain('desktop shell')
  })

  it('serves static assets with stable content type', async () => {
    const response = await fetch(`http://127.0.0.1:${desktopServer.port}/assets/fixture.js`)

    expect(response.status).toBe(200)
    expect(response.headers.get('content-type')).toContain('text/javascript')
  })

  it('proxies /svc routes to the matching local service target', async () => {
    const response = await fetch(`http://127.0.0.1:${desktopServer.port}/svc/market/api/v1/market/ping`)
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload).toEqual({ success: true, service: 'market-service' })
  })

  it('exposes a desktop WebSocket probe for packaged smoke checks', async () => {
    const payload = await new Promise((resolve, reject) => {
      const socket = new WebSocket(`ws://127.0.0.1:${desktopServer.port}/__desktop_meta_ws__`)
      socket.on('message', (message) => {
        resolve(JSON.parse(String(message)))
      })
      socket.on('error', reject)
    })

    expect(payload).toEqual({
      type: 'desktop-meta',
      payload: {
        desktop: true,
        servedBy: 'refactor-v2-desktop'
      }
    })
  })

  it('proxies /svc WebSocket upgrades without changing the target protocol', async () => {
    const payload = await new Promise((resolve, reject) => {
      const socket = new WebSocket(`ws://127.0.0.1:${desktopServer.port}/svc/market/api/v1/market/stream?symbols=AAPL.US`)
      socket.on('message', (message) => {
        resolve(JSON.parse(String(message)))
      })
      socket.on('error', reject)
    })

    expect(payload).toEqual({
      type: 'market-stream-ready',
      path: '/api/v1/market/stream?symbols=AAPL.US'
    })
    expect(upstreamWsPath).toBe('/api/v1/market/stream?symbols=AAPL.US')
  })

  it('resolves service targets using Web portal service path semantics', () => {
    const target = desktopServerInternals.resolveServiceTarget('/svc/trade/api/v1/trade/orders?limit=5', {
      serviceTargets: {
        trade: 'http://127.0.0.1:8105'
      }
    })

    expect(target.serviceName).toBe('trade')
    expect(target.targetUrl.toString()).toBe('http://127.0.0.1:8105/api/v1/trade/orders?limit=5')
  })
})

function awaitWebSocketAcceptKey(socketKey) {
  return crypto
    .createHash('sha1')
    .update(`${socketKey}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
    .digest('base64')
}

function writeWebSocketTextFrame(socket, payload) {
  const body = Buffer.from(String(payload))
  socket.write(Buffer.concat([
    Buffer.from([0x81, body.length]),
    body
  ]))
}

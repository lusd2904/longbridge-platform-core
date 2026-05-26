import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import { WebSocket } from 'ws'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import {
  desktopServerInternals,
  startDesktopServer
} from '../../desktop/static-server.mjs'

const projectRoot = path.resolve(import.meta.dirname, '../..')
const distDir = path.resolve(projectRoot, 'dist')
let desktopServer
let apiServer

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
    const apiPort = await listen(apiServer)
    desktopServer = await startDesktopServer(0, {
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

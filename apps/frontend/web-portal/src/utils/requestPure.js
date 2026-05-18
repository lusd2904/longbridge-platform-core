import { getTokenLocal, setTokenLocal, clearAuth } from './authPure.js'
import { Capacitor, CapacitorHttp } from '@capacitor/core'

const API_BASE_URL_KEY = 'platform_api_base_url'
const SESSION_KEY = 'platform_bootstrap'
const TOKEN_REFRESH_WINDOW_MS = 12 * 60 * 1000
const USER_REFRESH_PATH = '/svc/user/api/v1/auth/refresh'
let refreshPromise = null
const pendingGetRequests = new Map()
const RETRYABLE_METHODS = new Set(['GET'])

function isDesktopContainer() {
  if (typeof window === 'undefined') {
    return false
  }
  return Boolean(window.__REFV2_DESKTOP__ || window.__REFV2_DESKTOP_API_BASE__)
}

function readEnvBase(...keys) {
  for (const key of keys) {
    const value = normalizeBaseUrl(import.meta.env[key] || '')
    if (value) {
      return value
    }
  }
  return ''
}

function normalizeBaseUrl(rawUrl = '') {
  const value = String(rawUrl || '').trim()
  if (!value) {
    return ''
  }
  if (/^https?:\/\//i.test(value)) {
    return value.replace(/\/+$/, '')
  }
  return `https://${value.replace(/\/+$/, '')}`
}

function resolveNativeBaseUrl() {
  const explicitNativeBase = readEnvBase('VITE_NATIVE_API_BASE_URL')
  if (explicitNativeBase) {
    return explicitNativeBase
  }

  const platform = Capacitor.getPlatform()
  if (platform === 'android') {
    const androidBase = readEnvBase('VITE_ANDROID_API_BASE_URL')
    return androidBase || 'http://10.0.2.2:3100'
  }

  if (platform === 'ios') {
    const iosBase = readEnvBase('VITE_IOS_API_BASE_URL')
    return iosBase || 'http://127.0.0.1:3100'
  }

  return ''
}

function resolveDesktopBaseUrl() {
  if (!isDesktopContainer()) {
    return ''
  }

  const explicitDesktopBase = readEnvBase('VITE_DESKTOP_API_BASE_URL', 'VITE_NATIVE_API_BASE_URL')
  if (explicitDesktopBase) {
    return explicitDesktopBase
  }

  return normalizeBaseUrl(window.__REFV2_DESKTOP_API_BASE__ || 'http://127.0.0.1:3100')
}

function resolveBaseUrl() {
  if (typeof window !== 'undefined') {
    const stored = normalizeBaseUrl(window.localStorage.getItem(API_BASE_URL_KEY) || '')
    if (stored) {
      return stored
    }
  }

  const envBase = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL || '')
  if (envBase) {
    return envBase
  }

  if (Capacitor.isNativePlatform()) {
    return resolveNativeBaseUrl()
  }

  const desktopBase = resolveDesktopBaseUrl()
  if (desktopBase) {
    return desktopBase
  }

  if (typeof window !== 'undefined') {
    return window.location.origin
  }

  return ''
}

function buildBaseUrl(path = '') {
  const baseURL = resolveBaseUrl()
  if (/^https?:\/\//i.test(path)) {
    return path
  }
  const normalizedPath = String(path || '').startsWith('/')
    ? String(path || '')
    : `/${String(path || '')}`

  if (!baseURL) {
    return normalizedPath
  }

  return `${baseURL}${normalizedPath}`
}

function isNativeHttpAvailable() {
  return Capacitor.isNativePlatform() && Capacitor.isPluginAvailable('CapacitorHttp')
}

function headersToObject(headersLike = {}) {
  const headers = new Headers(headersLike)
  const result = {}
  headers.forEach((value, key) => {
    result[key] = value
  })
  return result
}

function parseNativeBody(body, headers = {}) {
  if (body === undefined || body === null || body === '') {
    return undefined
  }

  if (typeof body !== 'string') {
    return body
  }

  const contentType = String(headers['content-type'] || headers['Content-Type'] || '').toLowerCase()
  if (contentType.includes('application/json')) {
    try {
      return JSON.parse(body)
    } catch {
      return body
    }
  }

  return body
}

function buildQueryString(paramsOrConfig = {}) {
  const params = (
    paramsOrConfig &&
    typeof paramsOrConfig === 'object' &&
    !Array.isArray(paramsOrConfig) &&
    Object.prototype.hasOwnProperty.call(paramsOrConfig, 'params')
  )
    ? paramsOrConfig.params || {}
    : paramsOrConfig || {}

  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }

    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== undefined && item !== null && item !== '') {
          searchParams.append(key, String(item))
        }
      })
      return
    }

    searchParams.append(key, String(value))
  })

  return searchParams.toString()
}

function decodeJwtPayload(token = '') {
  try {
    const parts = String(token || '').split('.')
    if (parts.length !== 3) {
      return null
    }
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')
    return JSON.parse(atob(padded))
  } catch {
    return null
  }
}

function isTokenExpiringSoon(token = '') {
  const payload = decodeJwtPayload(token)
  const expiresAt = Number(payload?.exp || 0) * 1000
  if (!expiresAt) {
    return false
  }
  return (expiresAt - Date.now()) <= TOKEN_REFRESH_WINDOW_MS
}

function clearSessionState() {
  clearAuth()
  localStorage.removeItem(SESSION_KEY)
  localStorage.removeItem('user')
}

async function refreshAccessToken() {
  if (refreshPromise) {
    return refreshPromise
  }

  const currentToken = getTokenLocal()
  if (!currentToken) {
    return ''
  }

  refreshPromise = sendRequest(USER_REFRESH_PATH, {
    method: 'POST',
    headers: new Headers({
      Authorization: `Bearer ${currentToken}`
    })
  })
    .then(async (response) => {
      const data = await consumeResponse(response, { skipAuthReset: true })
      const nextToken = data?.data?.token || ''
      if (nextToken) {
        setTokenLocal(nextToken)
      }
      return nextToken
    })
    .catch((error) => {
      clearSessionState()
      throw error
    })
    .finally(() => {
      refreshPromise = null
    })

  return refreshPromise
}

async function getValidToken() {
  const token = getTokenLocal()
  if (!token) {
    return ''
  }

  if (!isTokenExpiringSoon(token)) {
    return token
  }

  try {
    return await refreshAccessToken()
  } catch {
    return token
  }
}

async function defaultHeaders(extra = {}, options = {}) {
  const headers = new Headers(extra)
  if (!options.skipAuth) {
    const token = await getValidToken()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
  }
  return headers
}

async function handleResponse(response, options = {}) {
  if (response.status === 401 && !options.skipAuthReset) {
    clearSessionState()
  }
  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const message = data?.detail || data?.message || data?.error || `Request failed with status ${response.status}`
    const err = new Error(message)
    err.response = response
    err.data = data
    throw err
  }
  return data
}

async function handleNativeResponse(response, options = {}) {
  const status = Number(response?.status || 0)
  const data = response?.data

  if (status === 401 && !options.skipAuthReset) {
    clearSessionState()
  }

  if (status < 200 || status >= 300) {
    const message = data?.detail || data?.message || data?.error || `Request failed with status ${status}`
    const err = new Error(message)
    err.response = {
      status,
      headers: response?.headers || {},
      data,
      url: response?.url || ''
    }
    err.data = data
    throw err
  }

  return data
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function isRetryableError(error) {
  const status = Number(error?.response?.status || 0)
  const message = String(error?.message || '')
  const bodyError = String(error?.data?.error || '')
  if (status >= 500) {
    return true
  }
  if (message.includes('Failed to fetch')) {
    return true
  }
  if (bodyError.toLowerCase().includes('timed out')) {
    return true
  }
  return false
}

async function sendRequest(url, init = {}) {
  const requestUrl = buildBaseUrl(url)
  if (!isNativeHttpAvailable()) {
    return fetch(requestUrl, init)
  }

  const plainHeaders = headersToObject(init.headers || {})
  const nativeResponse = await CapacitorHttp.request({
    url: requestUrl,
    method: String(init.method || 'GET').toUpperCase(),
    headers: plainHeaders,
    data: parseNativeBody(init.body, plainHeaders)
  })

  return {
    __native: true,
    ...nativeResponse
  }
}

function getResponseStatus(response) {
  return Number(response?.status || 0)
}

async function consumeResponse(response, options = {}) {
  if (response?.__native) {
    return handleNativeResponse(response, options)
  }
  return handleResponse(response, options)
}

async function doRequest(url, init = {}, options = {}) {
  const requestHeaders = await defaultHeaders(init.headers || {}, { skipAuth: options.skipAuth })
  const method = String(init.method || 'GET').toUpperCase()
  const retryLimit = Number(options.retryCount ?? (RETRYABLE_METHODS.has(method) ? 1 : 0))

  let attempt = 0
  while (attempt <= retryLimit) {
    try {
      const response = await sendRequest(url, {
        ...init,
        headers: requestHeaders
      })

      if (getResponseStatus(response) === 401 && !options.skipAuth && !options.skipRetry && getTokenLocal()) {
        try {
          const nextToken = await refreshAccessToken()
          if (nextToken) {
            const retryHeaders = new Headers(init.headers || {})
            retryHeaders.set('Authorization', `Bearer ${nextToken}`)
            const retried = await sendRequest(url, {
              ...init,
              headers: retryHeaders
            })
            return consumeResponse(retried)
          }
        } catch {
          return consumeResponse(response)
        }
      }

      return consumeResponse(response)
    } catch (error) {
      if (attempt >= retryLimit || !isRetryableError(error)) {
        throw error
      }
      await sleep(250 * (attempt + 1))
      attempt += 1
    }
  }

  throw new Error('Request retry exhausted')
}

export const request = {
  async get(url, params = {}) {
    const query = buildQueryString(params)
    const fullUrl = query ? `${url}?${query}` : url
    const tokenKey = getTokenLocal() || ''
    const requestKey = `${fullUrl}|${tokenKey}`
    if (pendingGetRequests.has(requestKey)) {
      return pendingGetRequests.get(requestKey)
    }

    const pendingRequest = doRequest(fullUrl, { method: 'GET' })
      .finally(() => {
        pendingGetRequests.delete(requestKey)
      })
    pendingGetRequests.set(requestKey, pendingRequest)
    return pendingRequest
  },
  async post(url, data) {
    return doRequest(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
  },
  async put(url, data) {
    return doRequest(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
  },
  async delete(url) {
    return doRequest(url, { method: 'DELETE' })
  }
}

// Backward compatible default export.
export default request;

// Helper functions for token management.
export function setAuthToken(token) {
  setTokenLocal(token)
}

export function logout() {
  clearSessionState()
}

export function getApiBaseUrl() {
  const baseUrl = resolveBaseUrl()
  if (typeof window !== 'undefined' && !baseUrl) {
    return window.location.origin
  }
  return baseUrl
}

export function setApiBaseUrl(url) {
  const normalized = normalizeBaseUrl(url)
  if (typeof window === 'undefined') {
    return normalized
  }
  if (!normalized) {
    window.localStorage.removeItem(API_BASE_URL_KEY)
    return ''
  }
  window.localStorage.setItem(API_BASE_URL_KEY, normalized)
  return normalized
}

export function isNativeClient() {
  return Capacitor.isNativePlatform()
}

export function isDesktopClient() {
  return isDesktopContainer()
}

export async function ensureFreshToken() {
  return getValidToken()
}

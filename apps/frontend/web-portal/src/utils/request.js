import axios from 'axios'
import { ElMessage } from 'element-plus'
import { getToken, clearAuth } from './auth.js'
import router from '../router/index.js'

const normalizeLegacyPath = (path = '') => {
  const rawPath = String(path || '')
  if (!rawPath || /^https?:\/\//i.test(rawPath) || rawPath.startsWith('/svc/')) {
    return rawPath
  }

  if (rawPath.startsWith('/api/v1/')) {
    return `/svc/user${rawPath}`
  }

  if (rawPath === '/users' || rawPath.startsWith('/users/')) {
    return `/svc/user/api/v1/admin${rawPath}`
  }

  if (rawPath === '/broker/accounts') {
    return '/svc/trade/api/v1/trade/accounts'
  }

  if (rawPath.startsWith('/broker/accounts/')) {
    return `/svc/trade/api/v1/trade/brokers/accounts${rawPath.slice('/broker/accounts'.length)}`
  }

  if (rawPath === '/broker/longbridge/config') {
    return '/svc/trade/api/v1/trade/brokers/longbridge'
  }

  if (rawPath === '/broker/tiger/config') {
    return '/svc/trade/api/v1/trade/brokers/tiger'
  }

  if (rawPath === '/stock_pool') {
    return '/svc/market/api/v1/market/stock-pool'
  }

  if (rawPath === '/stock_pool/update') {
    return '/svc/market/api/v1/market/stock-pool/sync-universe'
  }

  if (rawPath === '/stock_quotes') {
    return '/svc/market/api/v1/market/quote-snapshots'
  }

  return rawPath
}

const request = axios.create({
  baseURL: '',
  headers: {
    'Content-Type': 'application/json'
  }
})

request.interceptors.request.use(
  (config) => {
    config.url = normalizeLegacyPath(config.url)
    // 添加token到请求头
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

request.interceptors.response.use(
  (response) => {
    const { data } = response
    
    // 处理业务错误
    if (!data.success && data.error) {
      ElMessage.error(data.error)
      return Promise.reject(new Error(data.error))
    }
    
    return data
  },
  (error) => {
    const { response } = error
    
    if (response) {
      const { status, data } = response
      
      // 401 未登录或token过期
      if (status === 401) {
        ElMessage.error('登录已过期，请重新登录')
        clearAuth()
        // 使用路由跳转而不是window.location.href
        router.push('/login')
        return Promise.reject(new Error('登录已过期'))
      }
      
      // 403 无权限
      if (status === 403) {
        ElMessage.error('无权限访问')
        return Promise.reject(new Error('无权限访问'))
      }
      
      // 其他错误
      const errorMsg = data?.error || `请求失败 (${status})`
      ElMessage.error(errorMsg)
      return Promise.reject(new Error(errorMsg))
    }
    
    ElMessage.error(error.message || '网络错误')
    return Promise.reject(error)
  }
)

export default request

import { request } from './requestPure.js'
import {
  buildFinanceBriefingSummary,
  buildMarketScanSummary,
  looksLikePromptArtifact,
  sanitizeNarrativeText
} from './contentSanitizer.js'

const brokerLabelMap = {
  longbridge: '长桥证券',
  tiger: '老虎证券',
  interactive_brokers: '盈透证券'
}

const orderStatusMap = {
  filled: 'filled',
  partialfilled: 'partial',
  partial: 'partial',
  new: 'pending',
  submitted: 'submitted',
  waittonew: 'pending',
  waittocancel: 'pending',
  pendingcancel: 'pending',
  waittoreplace: 'pending',
  pendingreplace: 'pending',
  pending: 'pending',
  cancelled: 'cancelled',
  canceled: 'cancelled',
  rejected: 'rejected',
  expired: 'expired',
  removed: 'cancelled',
  '已成交': 'filled',
  '部分成交': 'partial',
  '已提交待报': 'submitted',
  '已提交': 'submitted',
  '待提交': 'pending',
  '待成交': 'pending',
  '待撤单': 'pending',
  '撤单中': 'pending',
  '已撤单': 'cancelled',
  '已拒绝': 'rejected',
  '已过期': 'expired'
}

function normalizeBrokerAccountId(account = {}) {
  const candidate = account.id ?? account.accountId ?? account.account_id ?? null
  if (candidate === null || candidate === undefined || candidate === '') {
    return null
  }

  const numericId = Number(candidate)
  if (Number.isInteger(numericId) && numericId > 0) {
    return numericId
  }

  return null
}

function normalizeAccount(account = {}) {
  const brokerType = account.broker_type || account.brokerType || ''
  const brokerName = account.broker_name || account.brokerName || brokerLabelMap[brokerType] || brokerType || '账户'
  const accountId = account.account_id || account.accountId || ''
  const normalizedId = normalizeBrokerAccountId(account)
  const isDefault = Boolean(account.is_default ?? account.isDefault)
  const isActive = Boolean(account.is_active ?? account.isActive ?? true)
  const name = account.name || account.display_name || `${brokerName} - ${accountId || account.id || '--'}`

  return {
    ...account,
    id: normalizedId,
    broker_type: brokerType,
    brokerType,
    broker_name: brokerName,
    brokerName,
    account_id: accountId,
    accountId,
    is_default: isDefault,
    isDefault,
    is_active: isActive,
    isActive,
    name
  }
}

function normalizePosition(position = {}) {
  const quantity = Number(position.quantity || 0)
  const avgPrice = Number(position.avgPrice ?? position.avg_price ?? position.average_cost ?? position.cost_price ?? 0)
  const currentPrice = Number(position.currentPrice ?? position.current_price ?? position.market_price ?? 0)
  const marketValue = Number(position.marketValue ?? position.market_value ?? (quantity * currentPrice))
  const pnl = Number(position.pnl ?? position.unrealized_pnl ?? 0)
  const pnlPercent = Number(
    position.pnlPercent ??
    position.pnl_percent ??
    position.pnl_ratio ??
    (avgPrice > 0 ? ((currentPrice - avgPrice) / avgPrice) * 100 : 0)
  )
  const change = Number(position.change ?? (currentPrice - avgPrice))
  const changePercent = Number(position.changePercent ?? position.change_percent ?? pnlPercent)
  const weight = Number(position.weight ?? 0)

  return {
    ...position,
    symbol: position.symbol || '',
    name: position.name || position.symbol_name || position.symbol || '',
    quantity,
    avgPrice,
    avg_price: avgPrice,
    currentPrice,
    current_price: currentPrice,
    marketValue,
    market_value: marketValue,
    pnl,
    pnlPercent,
    pnl_ratio: pnlPercent,
    change,
    changePercent,
    weight,
    holdDays: Number(position.holdDays ?? position.hold_days ?? 0),
    accountId: position.accountId ?? position.account_id ?? null
  }
}

const firstPositiveNumber = (...values) => {
  for (const value of values) {
    if (value === null || value === undefined || value === '') {
      continue
    }
    const number = Number(value)
    if (Number.isFinite(number) && number > 0) {
      return number
    }
  }
  return null
}

export function resolveOrderDisplayPrice(order = {}) {
  return firstPositiveNumber(
    order.price,
    order.submittedPrice,
    order.submitted_price,
    order.requestPrice,
    order.request_price,
    order.referencePrice,
    order.reference_price,
    order.limitPrice,
    order.limit_price,
    order.orderPrice,
    order.order_price,
    order.triggerPrice,
    order.trigger_price,
    order.filledPrice,
    order.filled_price,
    order.avgPrice,
    order.avg_price
  )
}

export function isMarketOrder(order = {}) {
  const value = String(order.orderType || order.order_type || '').trim().toLowerCase()
  return ['market', 'mo', 'marketorder'].includes(value)
}

export function normalizeOrder(order = {}) {
  const rawAction = (order.action || order.side || '').toString().trim()
  const action = ['buy', 'BUY', '买入'].includes(rawAction) ? 'buy' : ['sell', 'SELL', '卖出'].includes(rawAction) ? 'sell' : rawAction.toLowerCase()
  const rawStatus = (order.status || '').toString().trim()
  const statusKey = rawStatus.toLowerCase()
  const status = orderStatusMap[rawStatus] || orderStatusMap[statusKey] || statusKey || 'unknown'
  const orderTypeRaw = (order.orderType || order.order_type || '').toString().toLowerCase()
  const price = resolveOrderDisplayPrice(order)

  return {
    ...order,
    orderId: order.orderId || order.order_id || '',
    symbol: order.symbol || '',
    name: order.name || order.symbol_name || order.symbol || '',
    action,
    orderType: orderTypeRaw,
    quantity: Number(order.quantity || 0),
    filledQuantity: Number(order.filledQuantity ?? order.filled_quantity ?? 0),
    filledAmount: Number(order.filledAmount ?? order.filled_amount ?? 0),
    price,
    hasPrice: price !== null,
    referencePrice: firstPositiveNumber(order.referencePrice, order.reference_price),
    requestPrice: firstPositiveNumber(order.requestPrice, order.request_price),
    status,
    createTime: order.createTime || order.create_time || null,
    updateTime: order.updateTime || order.update_time || null,
    accountId: order.accountId ?? order.account_id ?? null,
    accountName: order.accountName ?? order.account_name ?? ''
  }
}

function normalizeMarketSummary(summary = {}) {
  const benchmarks = Array.isArray(summary?.benchmarks)
    ? summary.benchmarks.map((item) => ({
      ...item,
      price: Number(item?.price || 0),
      changePercent: Number(item?.changePercent ?? item?.change_percent ?? 0),
      tone: item?.tone || (Number(item?.changePercent ?? item?.change_percent ?? 0) > 0 ? 'up' : Number(item?.changePercent ?? item?.change_percent ?? 0) < 0 ? 'down' : 'flat')
    }))
    : []

  return {
    ...summary,
    market: summary?.market || 'US',
    regime: summary?.regime || 'balanced',
    riskTemperature: summary?.risk_temperature || summary?.riskTemperature || '中性',
    summary: sanitizeNarrativeText(summary?.summary, '暂无市场扫描数据'),
    benchmarks
  }
}

function normalizeAnalysisLayer(layer = {}, fallback = {}) {
  return {
    id: layer?.id || fallback.id || 'layer',
    name: layer?.name || fallback.name || '扫描层',
    summary: layer?.summary || fallback.summary || '',
    fullText: layer?.fullText || layer?.full_text || fallback.fullText || '',
    signal: layer?.signal || fallback.signal || 'warning',
    decision: layer?.decision || fallback.decision || '观望',
    modelId: layer?.modelId || layer?.model_id || fallback.modelId || '',
    modelAlias: layer?.modelAlias || layer?.model_alias || fallback.modelAlias || '',
    modelLatency: layer?.modelLatency || layer?.model_latency || fallback.modelLatency || '',
    modelQuality: layer?.modelQuality || layer?.model_quality || fallback.modelQuality || '',
    reasoningEffort: layer?.reasoningEffort || layer?.reasoning_effort || fallback.reasoningEffort || '',
    highlights: (Array.isArray(layer?.highlights) ? layer.highlights : []).filter(Boolean)
  }
}

function normalizeAnalysisResult(result = {}) {
  const errorMessage = result?.error || result?.reason || ''
  const finalDecision = result?.finalDecision || result?.final_decision || (errorMessage ? '分析失败' : '观望')
  const finalSignal = result?.finalSignal || result?.final_signal || (errorMessage ? 'danger' : 'warning')
  const marketSummary = normalizeMarketSummary(result?.marketSummary || result?.market_summary || {})
  const scanLayers = Array.isArray(result?.scanLayers) && result.scanLayers.length
    ? result.scanLayers.map((layer) => normalizeAnalysisLayer(layer))
    : errorMessage
      ? [
        normalizeAnalysisLayer({
          id: 'status',
          name: '扫描状态',
          summary: errorMessage,
          fullText: errorMessage,
          signal: finalSignal,
          decision: finalDecision,
          highlights: [result?.indicatorSource ? `指标来源 ${result.indicatorSource}` : '']
        })
      ]
    : [
      normalizeAnalysisLayer({
        id: 'pulse',
        name: '市场脉冲层',
        summary: result?.gemma || '',
        fullText: result?.gemmaFullText || result?.gemma || '',
        signal: result?.gemmaSignal || finalSignal,
        decision: result?.gemmaDecision || finalDecision,
        highlights: [result?.gemmaTrend, result?.gemmaIndicators, result?.gemmaLevels]
      }),
      normalizeAnalysisLayer({
        id: 'risk',
        name: '风险筛查层',
        summary: result?.llama || '',
        fullText: result?.llamaFullText || result?.llama || '',
        signal: result?.llamaSignal || finalSignal,
        decision: result?.llamaDecision || finalDecision,
        highlights: [result?.llamaSentiment, result?.llamaRisk, result?.llamaMarket]
      }),
      normalizeAnalysisLayer({
        id: 'final',
        name: '决策终审层',
        summary: result?.deepseek || '',
        fullText: result?.deepseekFullText || result?.deepseek || '',
        signal: result?.deepseekSignal || finalSignal,
        decision: result?.deepseekDecision || finalDecision,
        highlights: [result?.deepseekStrategy, result?.deepseekTarget, result?.deepseekStopLoss]
      })
    ]

  const technicalScore = Number(result?.deepseekTechnical ?? 0)
  const fundamentalScore = Number(result?.deepseekFundamental ?? 0)
  const capitalScore = Number(result?.deepseekCapital ?? 0)
  const marketScore = Number(result?.deepseekMarketScore ?? 0)
  const confidence = Number(result?.deepseekConfidence ?? result?.confidence ?? 0)

  const averageScore = [technicalScore, fundamentalScore, capitalScore, marketScore]
    .filter((score) => score > 0)
    .reduce((sum, score, _, arr) => sum + score / arr.length, 0)

  return {
    ...result,
    symbol: result?.symbol || '',
    name: result?.name || result?.symbol || '',
    price: Number(result?.price || 0),
    prevClose: Number(result?.prevClose ?? result?.prev_close ?? 0),
    changePercent: Number(result?.changePercent ?? result?.change_percent ?? 0),
    volume: Number(result?.volume || 0),
    error: result?.error || '',
    finalDecision,
    finalSignal,
    reason: result?.reason || result?.error || '',
    analysisTime: result?.analysisTime || result?.timestamp || null,
    confidence,
    score: confidence || Math.round(averageScore * 10) || 0,
    technicalScore,
    fundamentalScore,
    capitalScore,
    marketScore,
    indicators: result?.indicators || {},
    marketSummary,
    scanLayers,
    modelPlan: result?.modelPlan || result?.model_plan || {},
    indicatorSource: result?.indicatorSource || result?.indicator_source || '',
    degraded: Boolean(result?.degraded)
  }
}

function normalizePlatformMarketScan(scan = {}) {
  const technicalScore = Number(scan?.technicalScore ?? scan?.technical_score ?? 0)
  const breadthRatio = Number(scan?.breadthRatio ?? scan?.breadth_ratio ?? 0)
  const regime = technicalScore >= 60 && breadthRatio >= 50
    ? 'risk_on'
    : technicalScore <= 40 && breadthRatio <= 45
      ? 'risk_off'
      : 'balanced'

  return normalizeMarketSummary({
    market: scan?.market || 'US',
    regime,
    riskTemperature: scan?.status || '中性',
    summary: sanitizeNarrativeText(scan?.summary, buildMarketScanSummary(scan)),
    benchmarks: scan?.benchmarks || []
  })
}

function normalizeMarketInsight(insight = {}) {
  const benchmarks = Array.isArray(insight?.benchmarks)
    ? insight.benchmarks.map((item) => ({
      ...item,
      price: Number(item?.price || 0),
      changePercent: Number(item?.changePercent ?? item?.change_percent ?? 0),
      volume: Number(item?.volume || 0)
    }))
    : []

  return {
    ...insight,
    market: insight?.market || 'US',
    summary: sanitizeNarrativeText(
      insight?.summary,
      buildFinanceBriefingSummary({
        market: insight?.market,
        briefingType: 'market-insight',
        payload: { benchmarks, marketScore: insight?.marketScore }
      })
    ),
    benchmarks
  }
}

function normalizeFinanceBriefing(item = {}) {
  return {
    ...item,
    headline: sanitizeNarrativeText(item?.headline, item?.payload?.symbol || item?.market || '财经快讯'),
    summary: sanitizeNarrativeText(item?.summary, buildFinanceBriefingSummary(item))
  }
}

function normalizeRecommendationPayload(payload = {}) {
  const items = Array.isArray(payload?.items)
    ? payload.items.map((item) => {
      const rawReasons = Array.isArray(item?.reasons) ? item.reasons.filter(Boolean) : []
      const rawRisks = Array.isArray(item?.risks) ? item.risks.filter(Boolean) : []
      const reasonText = rawReasons.join(' ')
      const riskText = rawRisks.join(' ')
      const hasDirtyReasons = looksLikePromptArtifact(reasonText) || /核心催化|主要风险|综合评分|置信度|\blist\b/i.test(reasonText)
      const hasDirtyRisks = looksLikePromptArtifact(riskText) || /主要风险|综合评分|置信度|\blist\b/i.test(riskText)
      const reasons = hasDirtyReasons
        ? []
        : rawReasons.map((entry) => sanitizeNarrativeText(entry)).filter(Boolean)
      const risks = hasDirtyRisks
        ? []
        : rawRisks.map((entry) => sanitizeNarrativeText(entry)).filter(Boolean)

      return {
        ...item,
        thesis: sanitizeNarrativeText(item?.thesis, 'AI 推荐摘要当前不可用。'),
        reasons,
        risks
      }
    })
    : []

  return {
    ...payload,
    summary: sanitizeNarrativeText(payload?.summary, '暂无组合摘要。'),
    items
  }
}

const SERVICE_PREFIX = {
  user: '/svc/user',
  market: '/svc/market',
  analysis: '/svc/analysis',
  strategy: '/svc/strategy',
  trade: '/svc/trade',
  risk: '/svc/risk',
  scheduler: '/svc/scheduler',
  gateway: '/svc/gateway'
}

const buildServicePath = (service, path) => `${SERVICE_PREFIX[service]}${path}`
const serviceGet = (service, path, params = {}) => request.get(buildServicePath(service, path), params)
const servicePost = (service, path, data = {}) => request.post(buildServicePath(service, path), data)
const servicePut = (service, path, data = {}) => request.put(buildServicePath(service, path), data)
const serviceDelete = (service, path) => request.delete(buildServicePath(service, path))
const successPayload = (data = {}, extra = {}) => ({ success: true, data, ...extra })
const SYSTEM_NAME_STORAGE_KEY = 'platform_system_name'
const SYSTEM_NAME_EVENT = 'platform-system-name-updated'
const DEFAULT_SYSTEM_NAME = 'LongbridgeTrade'

const normalizeSystemName = (value) => String(value || '').trim()

export const getStoredSystemName = () => {
  if (typeof window === 'undefined') {
    return DEFAULT_SYSTEM_NAME
  }
  return normalizeSystemName(window.localStorage.getItem(SYSTEM_NAME_STORAGE_KEY)) || DEFAULT_SYSTEM_NAME
}

export const syncSystemName = (value) => {
  const nextName = normalizeSystemName(value) || DEFAULT_SYSTEM_NAME
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(SYSTEM_NAME_STORAGE_KEY, nextName)
    window.dispatchEvent(new CustomEvent(SYSTEM_NAME_EVENT, {
      detail: { systemName: nextName }
    }))
  }
  return nextName
}

const extractRequestStatus = (error) => Number(error?.response?.status || 0)

const resolveBusinessErrorMessage = (error, fallback = '请求失败') => {
  const rawBodyError = String(error?.data?.error || '').trim()
  const rawMessage = String(error?.message || '').trim()
  const status = extractRequestStatus(error)
  const normalizedBody = rawBodyError.toLowerCase()
  const normalizedMessage = rawMessage.toLowerCase()
  const isAiGatewayTimeout = (
    status === 504 ||
    normalizedBody.includes('504') ||
    normalizedBody.includes('gateway timeout') ||
    normalizedBody.includes('timed out') ||
    normalizedBody.includes('sub2api') ||
    normalizedMessage.includes('504') ||
    normalizedMessage.includes('gateway timeout')
  )

  if (isAiGatewayTimeout) {
    return 'AI 研判服务响应超时，已保留当前页面数据，请稍后重试。'
  }

  if (rawBodyError) {
    return rawBodyError
  }

  if (status >= 500) {
    return `${fallback}，服务暂时不可用`
  }

  if (rawMessage && !rawMessage.startsWith('Request failed with status')) {
    return rawMessage
  }

  return fallback
}

const HEALTH_TARGETS = [
  ['gateway', 'gateway'],
  ['user-center', 'user_center'],
  ['market-service', 'market_service'],
  ['analysis-service', 'analysis_service'],
  ['strategy-service', 'strategy_service'],
  ['trade-service', 'trade_service'],
  ['scheduler-service', 'scheduler_service'],
  ['risk-service', 'risk_service']
]

function normalizeHealthStatus(status = 'unknown') {
  const rawStatus = String(status || 'unknown').trim().toLowerCase()
  if (rawStatus === 'ok' || rawStatus === 'healthy') return 'healthy'
  if (rawStatus === 'degraded') return 'degraded'
  if (rawStatus === 'error' || rawStatus === 'unhealthy') return 'unhealthy'
  if (rawStatus === 'disabled') return 'disabled'
  return 'unknown'
}

function normalizeHealthServiceEntry(serviceKey, alias, payload = {}) {
  const resolvedStatus = normalizeHealthStatus(payload?.status || payload?.data?.status || 'unknown')
  return {
    status: resolvedStatus,
    status_text: payload?.status_text || (resolvedStatus === 'healthy' ? '运行正常' : resolvedStatus === 'degraded' ? '部分受限' : resolvedStatus === 'unhealthy' ? '异常' : resolvedStatus === 'disabled' ? '未启用' : '待确认'),
    service: payload?.service || serviceKey,
    version: payload?.version || '',
    port: payload?.port || payload?.data?.port || null,
    phase: payload?.phase || '',
    checked_at: payload?.checked_at || '',
    alert_count: Array.isArray(payload?.alerts) ? payload.alerts.length : 0,
    deps: payload?.deps || {},
    details: payload
  }
}

function buildHealthSummary(services = {}, environment = 'development', phase = '') {
  let healthyCount = 0
  let degradedCount = 0
  let unhealthyCount = 0
  let alertCount = 0

  Object.values(services).forEach((service) => {
    const status = normalizeHealthStatus(service?.status)
    if (status === 'healthy') healthyCount += 1
    else if (status === 'degraded') degradedCount += 1
    else if (status !== 'disabled') unhealthyCount += 1
    alertCount += Number(service?.alert_count || 0)
  })

  const overallStatus = unhealthyCount
    ? 'unhealthy'
    : degradedCount
      ? 'degraded'
      : healthyCount
        ? 'healthy'
        : 'unknown'

  return successPayload({
    status: overallStatus,
    services,
    environment,
    phase,
    summary: {
      total: Object.keys(services).length,
      healthy: healthyCount,
      degraded: degradedCount,
      unhealthy: unhealthyCount,
      alerts: alertCount
    }
  })
}

async function getGatewayObservabilityHealth() {
  const res = await serviceGet('gateway', '/api/v1/system/observability')
  const payload = res?.data || {}
  const deps = payload?.deps && typeof payload.deps === 'object' ? payload.deps : {}
  const services = {
    gateway: normalizeHealthServiceEntry('gateway', 'gateway', {
      service: payload?.service || 'api-gateway',
      status: payload?.status || 'unknown',
      alerts: payload?.alerts || [],
      checked_at: new Date().toISOString()
    })
  }

  HEALTH_TARGETS.slice(1).forEach(([serviceKey, alias]) => {
    const entry = deps[serviceKey] || {}
    services[alias] = normalizeHealthServiceEntry(serviceKey, alias, {
      service: entry?.service || serviceKey,
      version: entry?.version || '',
      port: entry?.observed?.port || null,
      phase: entry?.phase || '',
      checked_at: payload?.checked_at || new Date().toISOString(),
      status: entry?.status || 'unknown',
      status_text: entry?.status_text || '',
      deps: {},
      alerts: Array.isArray(payload?.alerts)
        ? payload.alerts.filter((item) => item?.service === serviceKey)
        : []
    })
  })

  return buildHealthSummary(
    services,
    payload?.environment || 'development',
    payload?.phase || ''
  )
}

function parseDecimalValue(value, fallback = 0) {
  if (value === null || value === undefined || value === '') {
    return fallback
  }

  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : fallback
  }

  if (typeof value === 'string') {
    const numeric = Number(value)
    return Number.isFinite(numeric) ? numeric : fallback
  }

  if (typeof value === 'object') {
    return parseDecimalValue(
      value.real ?? value.value ?? value.price ?? value.amount ?? value.decimal,
      fallback
    )
  }

  return fallback
}

function normalizeQuotePayload(row = {}) {
  const price = parseDecimalValue(row.last_done ?? row.last_price ?? row.price, 0)
  const prevClose = parseDecimalValue(row.prev_close ?? row.prevClose, 0)
  const changePercent = parseDecimalValue(
    row.change_rate ?? row.changePercent ?? row.change_percent,
    prevClose ? ((price - prevClose) / prevClose) * 100 : 0
  )
  const name = row.name_cn || row.name_en || row.name_hk || row.name || row.symbol_name || row.company_name || ''

  return {
    ...row,
    symbol: row.symbol || '',
    ...(name ? { name } : {}),
    price,
    last_price: price,
    prevClose,
    prev_close: prevClose,
    changePercent,
    change_percent: changePercent,
    change: parseDecimalValue(row.change, prevClose ? price - prevClose : 0),
    volume: Number(row.volume || 0),
    high: parseDecimalValue(row.high, 0),
    low: parseDecimalValue(row.low, 0),
    open: parseDecimalValue(row.open, 0),
    currency: row.currency || ''
  }
}

function normalizeQuoteSnapshotRow(row = {}) {
  const price = parseDecimalValue(row?.price ?? row?.last_price ?? row?.lastPrice, 0)
  const prevClose = parseDecimalValue(row?.prevClose ?? row?.prev_close, 0)
  const changePercentRaw = row?.changePercent ?? row?.change_percent
  const volumeRaw = row?.volume
  const snapshotAt = row?.snapshotAt || row?.snapshot_at || row?.quoteSnapshotAt || row?.quote_snapshot_at || null
  const normalized = {
    ...row,
    symbol: row?.symbol || '',
    market: row?.market || '',
    price,
    last_price: price,
    lastPrice: price,
    prevClose,
    prev_close: prevClose,
    change: parseDecimalValue(row?.change, prevClose ? price - prevClose : 0),
    changePercent: parseDecimalValue(changePercentRaw, 0),
    change_percent: parseDecimalValue(changePercentRaw, 0),
    volume: volumeRaw === null || volumeRaw === undefined || volumeRaw === '' ? null : Number(volumeRaw),
    high: parseDecimalValue(row?.high, 0),
    low: parseDecimalValue(row?.low, 0),
    open: parseDecimalValue(row?.open, 0),
    turnover: parseDecimalValue(row?.turnover, 0),
    quoteSource: row?.quoteSource || row?.quote_source || row?.source || '',
    quote_source: row?.quoteSource || row?.quote_source || row?.source || '',
    quoteSnapshotAt: snapshotAt,
    quote_snapshot_at: snapshotAt,
    quoteReady: row?.quoteReady ?? row?.quote_ready ?? Boolean(price || prevClose || snapshotAt)
  }
  return normalized
}

function normalizeStockPoolRow(row = {}) {
  const price = parseDecimalValue(row?.price ?? row?.current_price, 0)
  const prevClose = parseDecimalValue(row?.prevClose ?? row?.prev_close, 0)
  const changePercentRaw = row?.changePercent ?? row?.change_percent
  const volumeRaw = row?.volume
  const high = parseDecimalValue(row?.high, 0)
  const low = parseDecimalValue(row?.low, 0)
  const open = parseDecimalValue(row?.open, 0)
  const quoteSnapshotAt = row?.quoteSnapshotAt || row?.quote_snapshot_at || null
  const hasQuoteBase = Boolean(price || prevClose || high || low || open || quoteSnapshotAt)
  const isWatchlisted = Boolean(
    row?.isWatchlisted ??
    row?.is_watchlisted ??
    row?.is_watchlist ??
    row?.inWatchlist ??
    row?.in_watchlist ??
    row?.watchlisted
  )
  return {
    ...row,
    symbol: row?.symbol || '',
    name: row?.name || row?.company_name || row?.etf_name || row?.symbol || '',
    market: row?.market || '',
    sector: row?.sector || row?.category || '',
    type: row?.type || 'stock',
    price,
    prevClose,
    prev_close: prevClose,
    change: parseDecimalValue(row?.change, prevClose ? price - prevClose : 0),
    changePercent: parseDecimalValue(changePercentRaw, 0),
    change_percent: parseDecimalValue(changePercentRaw, 0),
    volume: volumeRaw === null || volumeRaw === undefined || volumeRaw === '' ? null : Number(volumeRaw),
    high,
    low,
    open,
    turnover: parseDecimalValue(row?.turnover, 0),
    quoteReady: row?.quoteReady ?? row?.quote_ready ?? hasQuoteBase,
    quoteSource: row?.quoteSource || row?.quote_source || '',
    quote_source: row?.quoteSource || row?.quote_source || '',
    quoteSnapshotAt,
    quote_snapshot_at: quoteSnapshotAt,
    marketCap: Number(row?.marketCap ?? row?.market_cap ?? 0),
    market_cap: Number(row?.marketCap ?? row?.market_cap ?? 0),
    pe: row?.pe === null || row?.pe === undefined ? (row?.pe_ratio === null || row?.pe_ratio === undefined ? null : Number(row.pe_ratio)) : Number(row.pe),
    isWatchlisted,
    is_watchlisted: isWatchlisted
  }
}

function normalizeStockPoolQueryParams(params = {}) {
  const columnFilters = params?.columnFilters && typeof params.columnFilters === 'object'
    ? params.columnFilters
    : {}
  const merged = {
    ...params,
    ...columnFilters
  }

  delete merged.columnFilters

  return Object.fromEntries(
    Object.entries(merged)
      .map(([key, value]) => {
        if (typeof value === 'string') {
          return [key, value.trim()]
        }
        return [key, value]
      })
      .filter(([, value]) => {
        if (value === undefined || value === null || value === '') {
          return false
        }
        if (Array.isArray(value)) {
          return value.length > 0
        }
        return true
      })
  )
}

function isMissingEndpointError(error) {
  const status = Number(error?.response?.status || 0)
  return status === 404 || status === 405 || status === 501
}

function aggregatePositions(positions = []) {
  const items = Array.isArray(positions) ? positions : []
  const totals = items.reduce((acc, item) => {
    const quantity = Number(item.quantity || 0)
    const avgPrice = Number(item.avgPrice ?? item.avg_price ?? item.average_cost ?? 0)
    const currentPrice = Number(item.currentPrice ?? item.current_price ?? item.market_price ?? 0)
    const marketValue = Number(item.marketValue ?? item.market_value ?? currentPrice * quantity)
    const pnl = Number(item.pnl ?? item.unrealized_pnl ?? (currentPrice - avgPrice) * quantity)
    acc.marketValue += marketValue
    acc.cost += avgPrice * quantity
    acc.pnl += pnl
    return acc
  }, { marketValue: 0, cost: 0, pnl: 0 })

  return {
    marketValue: totals.marketValue,
    pnl: totals.pnl,
    pnlRatio: totals.cost > 0 ? (totals.pnl / totals.cost) * 100 : 0
  }
}

async function resolveTradeAccountId(accountId = null) {
  if (accountId) {
    return Number(accountId)
  }
  try {
    const res = await serviceGet('trade', '/api/v1/trade/accounts/default')
    return Number(res?.data?.id || res?.data?.accountId || 0) || null
  } catch {
    return null
  }
}

async function loadTradeState(accountId = null, { status = '', limit = 30, realtime = false } = {}) {
  const resolvedAccountId = await resolveTradeAccountId(accountId)
  if (!resolvedAccountId) {
    return null
  }
  const res = await serviceGet('trade', `/api/v1/trade/accounts/${encodeURIComponent(resolvedAccountId)}/state`, {
    ...(status ? { status } : {}),
    ...(realtime ? { realtime: true } : {}),
    limit
  })
  return res?.data || null
}

async function loadTradeSnapshotState(accountId = null) {
  const resolvedAccountId = await resolveTradeAccountId(accountId)
  if (!resolvedAccountId) {
    return null
  }
  const res = await serviceGet('trade', `/api/v1/trade/accounts/${encodeURIComponent(resolvedAccountId)}/snapshot/state`)
  return res?.data || null
}

function normalizeTradeState(state = {}) {
  if (!state || typeof state !== 'object') {
    return null
  }

  const positions = Array.isArray(state.positions) ? state.positions.map(normalizePosition) : []
  const orders = Array.isArray(state.orders) ? state.orders.map(normalizeOrder) : []

  return {
    ...state,
    account: state.account ? normalizeAccount(state.account) : state.account,
    positions,
    orders,
    positionCount: Number(state.positionCount ?? positions.length),
    orderCount: Number(state.orderCount ?? orders.length)
  }
}

export async function getTradeSnapshotState(accountId = null) {
  const state = await loadTradeSnapshotState(accountId)
  return successPayload(normalizeTradeState(state || {}) || null)
}

export async function getTradeAccountState(accountId = null, options = {}) {
  const state = await loadTradeState(accountId, options)
  return successPayload(normalizeTradeState(state || {}) || null)
}

function buildLegacyDashboardSummary(state = {}) {
  const accountInfo = state?.accountInfo || {}
  const aggregate = aggregatePositions(state?.positions || [])
  const cash = Number(accountInfo.cash || 0)
  const marketValue = Number((accountInfo.market_value ?? accountInfo.marketValue ?? aggregate.marketValue) || 0)
  const totalAssets = Number((accountInfo.total_equity ?? accountInfo.totalAssets ?? (cash + marketValue)) || 0)
  const pnl = Number(aggregate.pnl || 0)
  const pnlRatio = Number(aggregate.pnlRatio || 0)
  return {
    account_id: state?.account?.account_id || '',
    currency: accountInfo.currency || 'USD',
    total_assets: totalAssets,
    daily_pnl: pnl,
    today_pnl: pnl,
    today_pnl_percent: pnlRatio,
    pnl_ratio: pnlRatio,
    cash,
    market_value: marketValue,
    buying_power: Number(accountInfo.buying_power || cash),
    maintenance_margin: Number(accountInfo.maintenance_margin || 0),
    source: state?.dataSource || state?.source || 'live',
    snapshot_at: state?.snapshotAt || null
  }
}

const MARKET_STATUS_TIMEZONES = {
  US: 'America/New_York',
  HK: 'Asia/Hong_Kong',
  CN: 'Asia/Shanghai'
}

const MARKET_STATUS_FALLBACK_SESSIONS = {
  US: [
    { status: 'pre', statusText: '盘前交易', start: 4 * 60, end: 9 * 60 + 30 },
    { status: 'open', statusText: '交易中', start: 9 * 60 + 30, end: 16 * 60 },
    { status: 'post', statusText: '盘后交易', start: 16 * 60, end: 20 * 60 }
  ],
  HK: [
    { status: 'open', statusText: '交易中', start: 9 * 60 + 30, end: 12 * 60 },
    { status: 'break', statusText: '午间休市', start: 12 * 60, end: 13 * 60 },
    { status: 'open', statusText: '交易中', start: 13 * 60, end: 16 * 60 }
  ],
  CN: [
    { status: 'open', statusText: '交易中', start: 9 * 60 + 30, end: 11 * 60 + 30 },
    { status: 'break', statusText: '午间休市', start: 11 * 60 + 30, end: 13 * 60 },
    { status: 'open', statusText: '交易中', start: 13 * 60, end: 15 * 60 }
  ]
}

function getMarketTimeParts(timeZone = 'UTC') {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone,
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
  const partMap = Object.fromEntries(formatter.formatToParts(new Date()).map((part) => [part.type, part.value]))
  const hour = Number(partMap.hour || 0)
  const minute = Number(partMap.minute || 0)

  return {
    weekday: String(partMap.weekday || ''),
    minutes: hour * 60 + minute,
    timeLabel: `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
  }
}

function parseSessionMinutes(value, timeZone = 'UTC') {
  if (value === null || value === undefined || value === '') {
    return null
  }

  if (typeof value === 'number' && Number.isFinite(value)) {
    return value >= 0 && value < 24 * 60 ? value : null
  }

  const raw = String(value).trim()
  const clockMatch = raw.match(/(\d{1,2}):(\d{2})(?::\d{2})?$/)
  if (clockMatch) {
    return Number(clockMatch[1]) * 60 + Number(clockMatch[2])
  }

  const dateValue = new Date(raw)
  if (Number.isNaN(dateValue.getTime())) {
    return null
  }

  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
  const partMap = Object.fromEntries(formatter.formatToParts(dateValue).map((part) => [part.type, part.value]))
  return Number(partMap.hour || 0) * 60 + Number(partMap.minute || 0)
}

function normalizeSessionCode(value = '') {
  const normalized = String(value || '').trim().toLowerCase().replace(/[\s_-]+/g, '')

  if (!normalized) {
    return ''
  }

  if (normalized.includes('intraday') || normalized.includes('regular') || normalized.includes('normal')) {
    return 'open'
  }
  if (normalized.includes('pre')) {
    return 'pre'
  }
  if (normalized.includes('post') || normalized.includes('afterhours')) {
    return 'post'
  }
  if (normalized.includes('night') || normalized.includes('overnight')) {
    return 'night'
  }
  if (normalized.includes('break') || normalized.includes('lunch') || normalized.includes('midday')) {
    return 'break'
  }

  return ''
}

function normalizeSessionLabel(status = '') {
  if (status === 'open') return '交易中'
  if (status === 'pre') return '盘前交易'
  if (status === 'post') return '盘后交易'
  if (status === 'night') return '夜盘交易'
  if (status === 'break') return '午间休市'
  return '已休市'
}

function extractSessionRows(raw = {}) {
  const directSessions = raw?.trade_sessions ?? raw?.tradeSessions ?? raw?.sessions
  return Array.isArray(directSessions) ? directSessions : []
}

function buildResolvedMarketSessions(raw = {}, marketKey = '') {
  const timeZone = MARKET_STATUS_TIMEZONES[marketKey] || 'UTC'
  const resolvedSessions = extractSessionRows(raw)
    .map((session) => {
      const status = normalizeSessionCode(
        session?.trade_session ??
        session?.tradeSession ??
        session?.session ??
        session?.session_name ??
        session?.name ??
        session?.type
      )
      const start = parseSessionMinutes(
        session?.start_time ??
        session?.startTime ??
        session?.begin_time ??
        session?.beginTime ??
        session?.open_time ??
        session?.openTime,
        timeZone
      )
      const end = parseSessionMinutes(
        session?.end_time ??
        session?.endTime ??
        session?.close_time ??
        session?.closeTime ??
        session?.finish_time ??
        session?.finishTime,
        timeZone
      )

      if (!status || start === null || end === null || start === end) {
        return null
      }

      return {
        status,
        statusText: normalizeSessionLabel(status),
        start,
        end
      }
    })
    .filter(Boolean)
    .sort((left, right) => left.start - right.start)

  return resolvedSessions.length ? resolvedSessions : (MARKET_STATUS_FALLBACK_SESSIONS[marketKey] || [])
}

function buildMarketStatusCard(raw = {}, marketKey = '') {
  const timeZone = MARKET_STATUS_TIMEZONES[marketKey] || 'UTC'
  const { weekday, minutes, timeLabel } = getMarketTimeParts(timeZone)
  const sessions = buildResolvedMarketSessions(raw, marketKey)
  const isWeekend = weekday === 'Sat' || weekday === 'Sun'
  const activeSession = !isWeekend
    ? sessions.find((session) => minutes >= session.start && minutes < session.end) || null
    : null

  return {
    status: activeSession?.status || 'closed',
    status_text: activeSession?.statusText || '已休市',
    current_time: timeLabel,
    sessions: sessions.map((session) => ({
      session: session.status,
      start: session.start,
      end: session.end
    }))
  }
}

function collectTradingSessionItems(payload) {
  if (Array.isArray(payload)) {
    return payload
  }

  if (!payload || typeof payload !== 'object') {
    return []
  }

  if (Array.isArray(payload.items)) {
    return payload.items
  }

  return Object.entries(payload)
    .map(([key, value]) => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return null
      }

      const marketKey = extractMarketCode(key)
      if (!marketKey) {
        return null
      }

      return {
        market: marketKey,
        ...value
      }
    })
    .filter(Boolean)
}

function extractMarketCode(rawMarket) {
  if (typeof rawMarket === 'string') {
    const normalized = rawMarket.replace(/^Market\./i, '').toUpperCase()
    return normalized || ''
  }

  if (!rawMarket || typeof rawMarket !== 'object') {
    return ''
  }

  const preferredMarkets = ['US', 'HK', 'CN', 'SG']
  for (const key of preferredMarkets) {
    const value = rawMarket[key]
    if (typeof value === 'string' && value.toUpperCase().endsWith(`.${key}`)) {
      return key
    }
  }

  for (const [key, value] of Object.entries(rawMarket)) {
    if (typeof value === 'string') {
      const normalized = value.replace(/^Market\./i, '').toUpperCase()
      if (preferredMarkets.includes(normalized) && key.toUpperCase() === normalized) {
        return normalized
      }
    }
  }

  return ''
}

export const loginPure = (data) => servicePost('user', '/api/v1/auth/login', data)
export const logoutPure = () => servicePost('user', '/api/v1/auth/logout', {})
export const refreshTokenPure = () => servicePost('user', '/api/v1/auth/refresh', {})
export const getUserInfoPure = () => serviceGet('user', '/api/v1/auth/info')
export const getUserInfo = () => serviceGet('user', '/api/v1/auth/info')
export const updateUserInfo = (data) => servicePut('user', '/api/v1/users/profile', data)
export const changePassword = (data) => servicePut('user', '/api/v1/auth/password', data)
export const getConfig = () => serviceGet('user', '/api/v1/config')
export const updateConfig = (data) => servicePut('user', '/api/v1/config', data)
export const updateUserInfoPure = (data) => servicePut('user', '/api/v1/users/profile', data)
export const getPlatformBootstrap = () => serviceGet('user', '/api/v1/users/bootstrap')

export const getApiHealth = async () => {
  try {
    return await getGatewayObservabilityHealth()
  } catch (gatewayError) {
    console.warn('Failed to load gateway observability, falling back to direct health probes:', gatewayError)
  }

  const healthTargets = [
    ['gateway', 'gateway'],
    ['user', 'user_center'],
    ['market', 'market_service'],
    ['analysis', 'analysis_service'],
    ['strategy', 'strategy_service'],
    ['trade', 'trade_service'],
    ['scheduler', 'scheduler_service'],
    ['risk', 'risk_service']
  ]

  const results = await Promise.allSettled(
    healthTargets.map(async ([service]) => ({ service, payload: await serviceGet(service, '/health') }))
  )

  const services = {}
  let environment = 'development'
  let phase = ''

  results.forEach((result, index) => {
    const [serviceKey, alias] = healthTargets[index]

    if (result.status === 'fulfilled') {
      const payload = result.value?.payload || {}
      if (!phase && payload?.phase) {
        phase = payload.phase
      }

      if (payload?.environment) {
        environment = payload.environment
      }

      services[alias] = normalizeHealthServiceEntry(serviceKey, alias, payload)
      return
    }

    services[alias] = {
      status: 'unhealthy',
      status_text: '检查失败',
      service: serviceKey,
      port: null,
      phase: '',
      details: {
        error: result.reason?.message || String(result.reason || 'health check failed')
      }
    }
  })

  return buildHealthSummary(services, environment, phase)
}

export const getPlatformRoles = () => serviceGet('user', '/api/v1/platform/roles')
export const getPlatformMenus = () => serviceGet('user', '/api/v1/platform/menus')
export const createPlatformRole = (data = {}) => servicePost('user', '/api/v1/platform/roles', data)
export const updatePlatformRole = (roleCode, data = {}) => servicePut('user', `/api/v1/platform/roles/${encodeURIComponent(roleCode)}`, data)

export const getPlatformTasks = () => serviceGet('scheduler', '/api/v1/scheduler/tasks')
export const updatePlatformTask = (taskKey, data = {}) => servicePut('scheduler', `/api/v1/scheduler/tasks/${encodeURIComponent(taskKey)}`, data)
export const runPlatformTask = (taskKey, data = {}) => servicePost('scheduler', `/api/v1/scheduler/tasks/${encodeURIComponent(taskKey)}/run`, data)
export const getAgentRuns = (params = {}) => serviceGet('analysis', '/api/v1/analysis/agent/runs', params)
export const getAgentRun = (runId) => serviceGet('analysis', `/api/v1/analysis/agent/runs/${encodeURIComponent(runId)}`)
export const reviewAgentRun = (runId, data = {}) => servicePost('analysis', `/api/v1/analysis/agent/runs/${encodeURIComponent(runId)}/override`, data)
export const getSystemSettings = async () => {
  const res = await serviceGet('user', '/api/v1/config')
  syncSystemName(res?.data?.system_name)
  return res
}
export const updateSystemSettings = async (data = {}) => {
  const res = await servicePut('user', '/api/v1/config', data)
  syncSystemName(res?.data?.system_name ?? data?.settings?.system_name ?? data?.system_name)
  return res
}
export const getSystemLogs = (params = {}) => serviceGet('user', '/api/v1/system/logs', params)
export const getFinanceBriefings = async (params = {}) => {
  const res = await serviceGet('analysis', '/api/v1/analysis/finance-briefings', params)
  const items = Array.isArray(res?.data) ? res.data : []
  return {
    ...res,
    data: items.map(normalizeFinanceBriefing),
    meta: res?.meta && typeof res.meta === 'object' ? res.meta : {}
  }
}

export const getMarketScans = async () => {
  const res = await serviceGet('market', '/api/v1/market/scans')
  const items = Array.isArray(res?.data) ? res.data : []
  return {
    ...res,
    data: items.map((item) => ({
      ...item,
      summary: sanitizeNarrativeText(item?.summary, buildMarketScanSummary(item)),
      insights: item?.insights
        ? {
            ...item.insights,
            fullText: sanitizeNarrativeText(item?.insights?.fullText, buildMarketScanSummary(item)),
            technicalObservation: sanitizeNarrativeText(item?.insights?.technicalObservation),
            riskHint: sanitizeNarrativeText(item?.insights?.riskHint),
            rhythm: sanitizeNarrativeText(item?.insights?.rhythm)
          }
        : item?.insights,
      marketSummary: normalizePlatformMarketScan(item)
    }))
  }
}

export const getPlatformMarketScans = getMarketScans
export const getSymbolOverview = (symbol) => serviceGet('market', `/api/v1/market/symbols/${encodeURIComponent(symbol)}/overview`)

export const getUsers = (params = {}) => serviceGet('user', '/api/v1/admin/users', params)
export const createUser = (data = {}) => servicePost('user', '/api/v1/admin/users', data)
export const updateUser = (userId, data = {}) => servicePut('user', `/api/v1/admin/users/${encodeURIComponent(userId)}`, data)
export const deleteUser = (userId) => serviceDelete('user', `/api/v1/admin/users/${encodeURIComponent(userId)}`)
export const resetUserPassword = (userId, data = {}) => servicePut('user', `/api/v1/admin/users/${encodeURIComponent(userId)}/password`, data)

export const getDashboardSummary = async (accountId, options = {}) => {
  const { realtime = false } = options
  const resolvedAccountId = await resolveTradeAccountId(accountId)
  if (!resolvedAccountId) {
    return successPayload({})
  }

  try {
    const res = await serviceGet('trade', `/api/v1/trade/accounts/${encodeURIComponent(resolvedAccountId)}/summary`, {
      ...(realtime ? { realtime: true } : {})
    })
    const payload = res?.data || {}
    return {
      ...res,
      data: {
        ...payload,
        meta: payload?.meta && typeof payload.meta === 'object' ? payload.meta : {}
      }
    }
  } catch {
    // 新 summary 接口不可用时继续走前端兼容回退。
  }

  try {
    if (!realtime) {
      const snapshotState = await loadTradeSnapshotState(resolvedAccountId)
      if (snapshotState) {
        const summary = buildLegacyDashboardSummary(snapshotState || {})
        return successPayload({
          ...summary,
          meta: snapshotState?.meta && typeof snapshotState.meta === 'object'
            ? {
                ...snapshotState.meta,
                readModel: 'trade-dashboard-summary',
                defaultMode: 'database',
                sources: {
                  ...(snapshotState.meta.sources || {}),
                  summary: 'trade-dashboard-summary'
                }
              }
            : {}
        })
      }
    }
  } catch {
    // 快照不可用时回退实时状态。
  }
  const state = await loadTradeState(resolvedAccountId, { limit: 1 })
  const summary = buildLegacyDashboardSummary(state || {})
  return successPayload({
    ...summary,
    ...(realtime ? { source: 'realtime' } : {}),
    meta: state?.meta && typeof state.meta === 'object'
      ? {
          ...state.meta,
          readModel: 'trade-dashboard-summary',
          defaultMode: realtime ? 'realtime' : 'database',
          sources: {
            ...(state.meta.sources || {}),
            summary: 'trade-dashboard-summary'
          }
        }
      : {}
  })
}

export const getAssetTrend = (params = {}) => serviceGet('user', '/api/v1/users/asset-trend', params)
export const getDashboardMarketInsights = async () => {
  if (getDashboardMarketInsights.cache && Date.now() < getDashboardMarketInsights.expiresAt) {
    return getDashboardMarketInsights.cache
  }
  if (getDashboardMarketInsights.pending) {
    return getDashboardMarketInsights.pending
  }
  getDashboardMarketInsights.pending = (async () => {
    const res = await serviceGet('market', '/api/v1/market/insights')
    const items = Array.isArray(res?.data) ? res.data : []
    const payload = {
      ...res,
      data: items.map(normalizeMarketInsight),
      meta: res?.meta && typeof res.meta === 'object' ? res.meta : {}
    }
    getDashboardMarketInsights.cache = payload
    getDashboardMarketInsights.expiresAt = Date.now() + 30_000
    return payload
  })().finally(() => {
    getDashboardMarketInsights.pending = null
  })
  return getDashboardMarketInsights.pending
}
getDashboardMarketInsights.cache = null
getDashboardMarketInsights.expiresAt = 0
getDashboardMarketInsights.pending = null

const marketInsightCache = new Map()
const marketInsightPending = new Map()
const marketInsightCacheKey = (prefix, params = {}) => `${prefix}:${JSON.stringify(params || {})}`

export const getMarketInsightHistory = async (params = {}) => {
  const key = marketInsightCacheKey('history', params)
  const cached = marketInsightCache.get(key)
  if (cached && Date.now() < cached.expiresAt) {
    return cached.payload
  }
  if (marketInsightPending.has(key)) {
    return marketInsightPending.get(key)
  }
  const pending = (async () => {
    const res = await serviceGet('market', '/api/v1/market/insights/history', params)
    const items = Array.isArray(res?.data) ? res.data : []
    const payload = { ...res, data: items.map(normalizeMarketInsight) }
    marketInsightCache.set(key, {
      payload,
      expiresAt: Date.now() + 30_000
    })
    return payload
  })().finally(() => {
    marketInsightPending.delete(key)
  })
  marketInsightPending.set(key, pending)
  return pending
}
export const getMarketInsightsAtTime = async (params = {}) => {
  const key = marketInsightCacheKey('at-time', params)
  const cached = marketInsightCache.get(key)
  if (cached && Date.now() < cached.expiresAt) {
    return cached.payload
  }
  if (marketInsightPending.has(key)) {
    return marketInsightPending.get(key)
  }
  const pending = (async () => {
    const res = await serviceGet('market', '/api/v1/market/insights', params)
    const items = Array.isArray(res?.data) ? res.data : []
    const payload = {
      ...res,
      data: items.map(normalizeMarketInsight),
      meta: res?.meta && typeof res.meta === 'object' ? res.meta : {}
    }
    marketInsightCache.set(key, {
      payload,
      expiresAt: Date.now() + 30_000
    })
    return payload
  })().finally(() => {
    marketInsightPending.delete(key)
  })
  marketInsightPending.set(key, pending)
  return pending
}
export const getPositionDistribution = async () => successPayload([])
export const getMarketOverview = () => getMarketScans()

export const getAccounts = async () => {
  const res = await serviceGet('trade', '/api/v1/trade/accounts')
  const data = Array.isArray(res?.data) ? res.data : []
  return { ...res, data: data.map(normalizeAccount) }
}

export const getBrokerAccounts = getAccounts

export const getBrokerAccountDetail = async (accountId) => {
  const res = await serviceGet('trade', `/api/v1/trade/brokers/accounts/${encodeURIComponent(accountId)}`)
  return {
    ...res,
    data: res?.data ? normalizeAccount(res.data) : null
  }
}

export const testBrokerAccountConnection = (accountId) => {
  return servicePost('trade', `/api/v1/trade/brokers/accounts/${encodeURIComponent(accountId)}/test`)
}

export const setDefaultBrokerAccount = (accountId) => {
  return servicePost('trade', `/api/v1/trade/brokers/accounts/${encodeURIComponent(accountId)}/default`)
}

export const deleteBrokerAccount = (accountId) => {
  return serviceDelete('trade', `/api/v1/trade/brokers/accounts/${encodeURIComponent(accountId)}`)
}

export const saveLongbridgeBrokerConfig = (data = {}) => {
  return servicePost('trade', '/api/v1/trade/brokers/longbridge', data)
}

export const saveTigerBrokerConfig = (data = {}) => {
  return servicePost('trade', '/api/v1/trade/brokers/tiger', data)
}

export const getPositions = async (accountId, options = {}) => {
  const { realtime = true } = options
  const resolvedAccountId = await resolveTradeAccountId(accountId)
  if (!resolvedAccountId) {
    return successPayload([])
  }
  if (!realtime) {
    const state = await loadTradeSnapshotState(resolvedAccountId)
    const items = Array.isArray(state?.positions) ? state.positions : []
    return successPayload(items.map(normalizePosition))
  }
  const res = await serviceGet('trade', `/api/v1/trade/accounts/${encodeURIComponent(resolvedAccountId)}/positions`)
  const items = Array.isArray(res?.data) ? res.data : []
  return {
    ...res,
    data: items.map(normalizePosition),
    meta: res?.meta && typeof res.meta === 'object' ? res.meta : {}
  }
}

export const getPositionsSnapshot = async (accountId) => {
  const state = await loadTradeSnapshotState(accountId)
  const items = Array.isArray(state?.positions) ? state.positions : []
  const stateMeta = state?.meta && typeof state.meta === 'object' ? state.meta : {}
  return {
    success: true,
    data: items.map(normalizePosition),
    meta: {
      readModel: 'trade-positions',
      defaultMode: 'database',
      dataSource: state?.dataSource || 'snapshot',
      snapshotAt: stateMeta?.positionSnapshotAt || state?.snapshotAt || '',
      sources: {
        positions: stateMeta?.sources?.positions || 'position_snapshots',
        account: stateMeta?.sources?.account || 'account_asset_snapshots'
      },
      positionCount: Number(state?.positionCount ?? items.length),
      realtimeOverlay: ['quotes']
    }
  }
}

export const getDefaultBrokerAccount = async () => {
  try {
    const res = await serviceGet('trade', '/api/v1/trade/accounts/default')
    if (res?.data) {
      return normalizeAccount(res.data)
    }
  } catch {
    // 忽略并回退到账户列表。
  }

  const res = await getBrokerAccounts()
  if (Array.isArray(res?.data) && res.data.length) {
    return res.data.find((item) => item.isDefault || item.is_default) || res.data[0]
  }
  return null
}

export const getTodayPnL = async () => {
  const res = await getDashboardSummary()
  return successPayload({
    today_pnl: Number(res?.data?.today_pnl || 0),
    today_pnl_percent: Number(res?.data?.today_pnl_percent || 0)
  })
}

let marketStatusCache = null
let marketStatusExpiresAt = 0
let marketStatusPromise = null

export const getMarketStatus = async () => {
  const buildDefaultStatusMap = () => ({
    US: buildMarketStatusCard({}, 'US'),
    HK: buildMarketStatusCard({}, 'HK'),
    CN: buildMarketStatusCard({}, 'CN')
  })

  const now = Date.now()
  if (marketStatusCache && now < marketStatusExpiresAt) {
    return successPayload(marketStatusCache)
  }
  if (marketStatusPromise) {
    return marketStatusPromise
  }

  marketStatusPromise = (async () => {
    try {
      const res = await serviceGet('market', '/api/v1/market/longbridge/trading-session')
      const payload = res?.data?.payload ?? res?.data?.data?.payload ?? res?.data?.data ?? res?.data
      const items = collectTradingSessionItems(payload)
      const statusMap = {}

      items.forEach((item) => {
        const marketSource = item?.market ?? item?.market_code ?? item?.marketCode ?? item?.region
        const marketKey = extractMarketCode(marketSource)
        if (marketKey) {
          statusMap[marketKey] = buildMarketStatusCard(item, marketKey)
        }
      })

      marketStatusCache = {
        ...buildDefaultStatusMap(),
        ...statusMap
      }
      marketStatusExpiresAt = Date.now() + 60_000
      return successPayload(marketStatusCache)
    } catch (error) {
      console.warn('获取市场状态失败:', error)
      marketStatusCache = marketStatusCache || buildDefaultStatusMap()
      marketStatusExpiresAt = Date.now() + 15_000
      return successPayload(marketStatusCache)
    } finally {
      marketStatusPromise = null
    }
  })()
  return marketStatusPromise
}

export const getStockPool = async (params = {}) => {
  const res = await serviceGet('market', '/api/v1/market/stock-pool', normalizeStockPoolQueryParams(params))
  const items = Array.isArray(res?.data) ? res.data : Array.isArray(res?.stocks) ? res.stocks : []
  const normalizedStats = res?.stats || {}
  const filteredTotal = Number(normalizedStats?.filtered_total ?? res?.total ?? items.length)
  return {
    ...res,
    data: items.map(normalizeStockPoolRow),
    total: filteredTotal,
    filteredTotal,
    stats: {
      ...normalizedStats,
      filtered_total: filteredTotal
    },
    meta: res?.meta && typeof res.meta === 'object' ? res.meta : {}
  }
}

export const getStockGroups = (params = {}) => serviceGet('market', '/api/v1/market/stock-groups', params)
export const addStockToPool = (data) => servicePost('market', '/api/v1/market/stock-pool', data)
const WATCHLIST_SESSION_MAP = {
  pre_market: 'before_open',
  before_open: 'before_open',
  open: 'before_open',
  after_market: 'after_close',
  post_market: 'after_close',
  after_close: 'after_close',
  close: 'after_close'
}

const normalizeWatchlistPayload = (data = {}) => {
  const scanBeforeOpen = data.scan_before_open ?? data.scanBeforeOpen ?? data.pre_market_enabled ?? data.preMarketEnabled
  const scanAfterClose = data.scan_after_close ?? data.scanAfterClose ?? data.after_market_enabled ?? data.afterMarketEnabled
  return {
    ...data,
    ...(data.asset_type && !data.type ? { type: data.asset_type } : {}),
    ...(scanBeforeOpen !== undefined ? { scan_before_open: Boolean(scanBeforeOpen) } : {}),
    ...(scanAfterClose !== undefined ? { scan_after_close: Boolean(scanAfterClose) } : {})
  }
}

const normalizeWatchlistSession = (session = '') => {
  const normalized = String(session || '').trim().toLowerCase()
  return WATCHLIST_SESSION_MAP[normalized] || normalized
}

export const getWatchlist = (params = {}) => serviceGet('market', '/api/v1/market/watchlist', params)
export const addWatchlistStock = (data = {}) => servicePost('market', '/api/v1/market/watchlist', normalizeWatchlistPayload(data))
export const updateWatchlist = (data = {}) => {
  const symbol = String(data?.symbol || '').trim()
  if (!symbol) {
    return Promise.reject(new Error('股票代码不能为空'))
  }
  return servicePut('market', `/api/v1/market/watchlist/${encodeURIComponent(symbol)}`, normalizeWatchlistPayload(data))
}
export const removeWatchlistStock = (symbol) => (
  serviceDelete('market', `/api/v1/market/watchlist/${encodeURIComponent(symbol)}`)
)
export const removeWatchlist = removeWatchlistStock
export const getWatchlistScanTargets = (sessionOrParams = {}) => {
  const payload = typeof sessionOrParams === 'string'
    ? { session: normalizeWatchlistSession(sessionOrParams) }
    : {
        ...sessionOrParams,
        session: normalizeWatchlistSession(sessionOrParams?.session || sessionOrParams?.trade_session || '')
      }
  return servicePost('market', '/api/v1/market/watchlist/scan-targets', payload)
}
export const removeStockFromPool = (symbol, market, type = 'stock') => serviceDelete('market', `/api/v1/market/stock-pool/${encodeURIComponent(symbol)}?market=${encodeURIComponent(market)}&type=${encodeURIComponent(type)}`)
export const searchStock = (params) => getStockPool(params)
export const updateStockGroupAssignment = (payload) => servicePut('market', '/api/v1/market/stock-pool/group', payload)
export const createStockGroup = (data) => servicePost('market', '/api/v1/market/stock-groups', data)
export const deleteStockGroup = (groupId) => serviceDelete('market', `/api/v1/market/stock-groups/${encodeURIComponent(groupId)}`)
export const updateStockBroker = (payload) => servicePut('market', '/api/v1/market/stock-pool/broker', payload)
export const syncMarketUniverse = (data = {}) => servicePost('market', '/api/v1/market/stock-pool/sync-universe', data)

export const analyzePositions = async ({ positions = [], accountId = null, forceRefresh = true } = {}) => {
  try {
    const res = await servicePost('analysis', '/api/v1/analysis/analyze-positions', {
      positions,
      ...(accountId ? { account_id: accountId } : {}),
      force_refresh: forceRefresh
    })
    const items = Array.isArray(res?.data) ? res.data : []
    return {
      ...res,
      marketSummary: normalizeMarketSummary(res?.marketSummary || res?.market_summary || {}),
      modelPlan: res?.modelPlan || res?.model_plan || {},
      data: items.map(normalizeAnalysisResult)
    }
  } catch (error) {
    const businessMessage = resolveBusinessErrorMessage(error, 'AI 研判失败')
    error.businessMessage = businessMessage
    throw error
  }
}

export const analyzeStock = async (symbol, options = {}) => {
  const res = await analyzePositions({
    positions: [{ symbol }],
    accountId: options.accountId || null,
    forceRefresh: options.forceRefresh ?? true
  })
  return { ...res, data: res?.data?.[0] || null }
}

export const getLatestTrendScans = async (params = {}) => {
  const query = {
    limit: params.limit || 10,
    ...(params.symbols && params.symbols.length ? { symbols: params.symbols } : {}),
    ...(params.market ? { market: params.market } : {})
  }
  const res = await serviceGet('analysis', '/api/v1/analysis/trend-scans', query)
  const items = Array.isArray(res?.data) ? res.data : []
  return {
    ...res,
    data: items.map(normalizeAnalysisResult),
    meta: res?.meta && typeof res.meta === 'object' ? res.meta : {}
  }
}

export const getAIModels = () => serviceGet('analysis', '/api/v1/analysis/models')
export const testAIConnection = (data = {}) => servicePost('analysis', '/api/v1/analysis/test-connection', data)
export const getRecommendations = async (params = {}) => {
  const res = await serviceGet('analysis', '/api/v1/analysis/recommendations', params)
  return {
    ...res,
    data: normalizeRecommendationPayload(res?.data || {}),
    meta: res?.meta && typeof res.meta === 'object' ? res.meta : {}
  }
}
export const refreshRecommendations = async (data = {}) => {
  const res = await servicePost('analysis', '/api/v1/analysis/recommendations/refresh', data)
  return {
    ...res,
    data: normalizeRecommendationPayload(res?.data || {}),
    meta: res?.meta && typeof res.meta === 'object' ? res.meta : {}
  }
}
export const getQuantStatus = () => serviceGet('strategy', '/api/v1/strategy/quant/status')
export const runQuantCycle = (data = {}) => servicePost('strategy', '/api/v1/strategy/quant/run', data)
export const getMarketHistory = async (params = {}) => {
  const res = await serviceGet('market', '/api/v1/market/history', params)
  return {
    ...res,
    meta: res?.meta && typeof res.meta === 'object' ? res.meta : {}
  }
}
export const getMarketHistoryCoverage = async (params = {}) => {
  try {
    return await request.get('/svc/market/api/v1/market/history/coverage', params)
  } catch (error) {
    const status = Number(error?.response?.status || 0)
    const message = String(error?.message || '').toLowerCase()
    const canFallback = status === 404 || status === 405 || message.includes('not found')
    if (!canFallback) {
      throw error
    }
    return serviceGet('market', '/api/v1/market/history/backfill-status', params)
  }
}
export const getMarketHistoryCompare = async (params = {}) => {
  const res = await serviceGet('market', '/api/v1/market/history/compare', params)
  return {
    ...res,
    meta: res?.meta && typeof res.meta === 'object' ? res.meta : {}
  }
}
export const getMarketHistoryBackfillStatus = () => serviceGet('market', '/api/v1/market/backfill/status')

export const getStockQuotes = async (symbols = []) => {
  const querySymbols = Array.isArray(symbols) ? symbols : [symbols]
  const res = await serviceGet('market', '/api/v1/market/longbridge/quotes', { symbols: querySymbols })
  const payload = res?.data?.payload ?? res?.data?.data?.payload ?? res?.data?.data ?? res?.data
  const items = Array.isArray(payload) ? payload : []
  return { ...res, data: items.map(normalizeQuotePayload) }
}

export const getMarketQuotes = (symbols = []) => getStockQuotes(symbols)

export const getQuoteSnapshots = async (symbols = [], params = {}) => {
  const querySymbols = Array.isArray(symbols) ? symbols.filter(Boolean) : [symbols].filter(Boolean)
  if (!querySymbols.length) {
    return successPayload([])
  }
  const res = await serviceGet('market', '/api/v1/market/quote-snapshots', {
    symbols: querySymbols,
    max_age_minutes: params.maxAgeMinutes || params.max_age_minutes || 20
  })
  const items = Array.isArray(res?.data) ? res.data : []
  return {
    ...res,
    data: items.map(normalizeQuoteSnapshotRow)
  }
}

export const getStockQuote = async (symbol, params = {}) => {
  const res = await getStockQuotes([symbol], params?.account_id || null)
  return successPayload(res?.data?.[0] || {})
}

function buildOrderSubmitPayload(data = {}, action = 'BUY') {
  return {
    symbol: String(data.symbol || '').trim().toUpperCase(),
    action,
    quantity: Number(data.quantity || 0),
    account_id: Number(data.account_id || 0),
    price: data.price === null || data.price === undefined ? null : Number(data.price),
    order_type: data.price ? 'LIMIT' : 'MARKET',
    time_in_force: 'DAY'
  }
}

export const buyStock = (data) => servicePost('trade', '/api/v1/trade/orders/submit', buildOrderSubmitPayload(data, 'BUY'))
export const sellStock = (data) => servicePost('trade', '/api/v1/trade/orders/submit', buildOrderSubmitPayload(data, 'SELL'))

export const getOrders = async (params = {}) => {
  const query = {
    ...(params.account_id ? { account_id: params.account_id } : {}),
    ...(params.status ? { status: params.status } : {}),
    limit: params.limit || 200,
    ...(params.realtime ? { realtime: true } : {})
  }
  const res = await serviceGet('trade', '/api/v1/trade/orders', query)
  const payload = res?.data && typeof res.data === 'object' ? res.data : {}
  const items = Array.isArray(payload?.list)
    ? payload.list
    : Array.isArray(res?.data)
      ? res.data
      : Array.isArray(res?.orders)
        ? res.orders
        : []
  return {
    ...res,
    data: {
      list: items.map(normalizeOrder),
      total: Number(payload?.count ?? res?.count ?? items.length),
      dataSource: payload?.dataSource || (params.realtime ? 'broker-live' : 'order-projection'),
      snapshotAt: payload?.snapshotAt || null,
      warnings: Array.isArray(payload?.warnings) ? payload.warnings : Array.isArray(res?.warnings) ? res.warnings : [],
      meta: payload?.meta && typeof payload.meta === 'object' ? payload.meta : {}
    }
  }
}

export const getProjectedOrders = async (params = {}) => {
  const query = {
    ...(params.account_id ? { account_id: params.account_id } : {}),
    ...(params.status ? { status: params.status } : {}),
    limit: params.limit || 200
  }
  const res = await serviceGet('trade', '/api/v1/trade/orders/projection', query)
  const payload = res?.data || {}
  const items = Array.isArray(payload?.list) ? payload.list : []
  return {
    ...res,
    data: {
      list: items.map(normalizeOrder),
      total: Number(payload?.count ?? items.length),
      dataSource: payload?.dataSource || 'order-projection',
      snapshotAt: payload?.snapshotAt || null,
      warnings: Array.isArray(payload?.warnings) ? payload.warnings : [],
      meta: payload?.meta && typeof payload.meta === 'object' ? payload.meta : {}
    }
  }
}

export const cancelOrder = (orderId, accountId) => servicePost('trade', '/api/v1/trade/orders/cancel', { order_id: orderId, account_id: accountId })
export const getTradeOutboxHealth = () => serviceGet('trade', '/health')
export const repairTradeOutbox = () => servicePost('trade', '/api/v1/trade/outbox/repair', {})
export const getTradeOutboxEvents = (params = {}) => serviceGet('trade', '/api/v1/trade/outbox/events', params)
export const getTradeOutboxSagas = (params = {}) => serviceGet('trade', '/api/v1/trade/outbox/sagas', params)
export const requeueTradeOutboxEvents = (eventIds = []) => servicePost('trade', '/api/v1/trade/outbox/requeue', { event_ids: eventIds })
export const purgeTradeDeadLetters = (eventIds = []) => servicePost('trade', '/api/v1/trade/outbox/dead-letter/purge', { event_ids: eventIds })
export const requeueTradeOutboxSagas = (sagaIds = []) => servicePost('trade', '/api/v1/trade/outbox/sagas/requeue', { saga_ids: sagaIds })
export const purgeTradeDeadLettersBySaga = (sagaIds = []) => servicePost('trade', '/api/v1/trade/outbox/sagas/dead-letter/purge', { saga_ids: sagaIds })

export const getStrategies = (params = {}) => serviceGet('strategy', '/api/v1/strategy/strategies', params)
export const getStrategyTemplates = () => serviceGet('strategy', '/api/v1/strategy/templates')
export const createStrategy = (data) => servicePost('strategy', '/api/v1/strategy/strategies', data)
export const updateStrategy = (id, data) => servicePut('strategy', `/api/v1/strategy/strategies/${encodeURIComponent(id)}`, data)
export const deleteStrategy = (id) => serviceDelete('strategy', `/api/v1/strategy/strategies/${encodeURIComponent(id)}`)
export const getStrategyMonitorSummary = () => serviceGet('strategy', '/api/v1/strategy/monitor/summary')
export const runStrategyMonitor = (data = {}) => servicePost('strategy', '/api/v1/strategy/monitor/run', data)
export const getStrategyAlerts = (params = {}) => serviceGet('strategy', '/api/v1/strategy/monitor/alerts', params)

export const getBacktestList = (params = {}) => serviceGet('strategy', '/api/v1/strategy/backtests', params)
export const runStrategyBacktest = async (data) => {
  try {
    return await servicePost('strategy', '/api/v1/strategy/backtests', data)
  } catch (error) {
    error.businessMessage = resolveBusinessErrorMessage(error, '回测失败')
    throw error
  }
}

export const getRiskOverview = (params = {}) => serviceGet('risk', '/api/v1/risk/overview', params)
export const getRiskOverviewSnapshot = (params = {}) => serviceGet('risk', '/api/v1/risk/overview/snapshot', params)
export const getRiskLimits = () => serviceGet('risk', '/api/v1/risk/limits')
export const updateRiskLimits = (data) => servicePut('risk', '/api/v1/risk/limits', data)
export const getRiskEvents = (params = {}) => serviceGet('risk', '/api/v1/risk/events', params)
export const getStopLossOrders = (params = {}) => serviceGet('risk', '/api/v1/risk/stoploss', params)
export const getTakeProfitOrders = (params = {}) => serviceGet('risk', '/api/v1/risk/takeprofit', params)
export const setStopLoss = (data) => servicePost('risk', '/api/v1/risk/stoploss', data)
export const setTakeProfit = (data) => servicePost('risk', '/api/v1/risk/takeprofit', data)
export const cancelStopLoss = (orderId) => servicePost('risk', '/api/v1/risk/stoploss/cancel', { order_id: orderId })
export const cancelTakeProfit = (orderId) => servicePost('risk', '/api/v1/risk/takeprofit/cancel', { order_id: orderId })

export const getNotifications = (params = {}) => serviceGet('risk', '/api/v1/notifications', params)
export const markNotificationRead = (payload = {}) => servicePost('risk', '/api/v1/notifications/read', payload)
export const markAllNotificationsRead = (payload = {}) => servicePost('risk', '/api/v1/notifications/read-all', payload)
export const deleteNotificationItem = (payload = {}) => servicePost('risk', '/api/v1/notifications/delete', payload)
export const clearNotifications = (payload = {}) => servicePost('risk', '/api/v1/notifications/clear', payload)

export const getLongbridgeAnnouncements = (symbol) => serviceGet('market', '/api/v1/market/longbridge/announcements', { symbol })
export const getLongbridgeDepth = (symbol) => serviceGet('market', '/api/v1/market/longbridge/depth', { symbol })
export const getLongbridgeNews = (symbol) => serviceGet('market', '/api/v1/market/longbridge/content/news', { symbol })
export const getLongbridgeTrades = (symbol, params = {}) => serviceGet('market', '/api/v1/market/longbridge/trades', {
  symbol,
  count: params.count || 18
})
export const getLongbridgeTopics = (symbol) => serviceGet('market', '/api/v1/market/longbridge/content/topics', { symbol })

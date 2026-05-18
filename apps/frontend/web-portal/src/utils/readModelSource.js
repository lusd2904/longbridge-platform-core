const SOURCE_LABEL_MAP = {
  account_asset_snapshots: '账户快照',
  'account_asset_snapshots.payload.recentOrders': '订单快照',
  position_snapshots: '持仓快照',
  trade_order_projections: '订单快照',
  recommendation_runs: '推荐批次',
  recommendation_items: '推荐明细',
  recommendation_snapshots: '推荐快照',
  quote_snapshots: '报价快照',
  finance_briefings: '财经快讯',
  daily_symbol_trend_ai_scans: '趋势扫描',
  historical_market_data: '历史行情',
  indicator_snapshots: '指标快照',
  market_insight_snapshots: '市场快照',
  market_universe: '股票池',
  risk_overview_snapshots: '风控快照',
  symbol_content_cache: '内容缓存',
  content_cache: '内容缓存',
  'content-cache': '内容缓存',
  'content-cache-empty': '内容缓存待补齐',
  'content-cache-fallback': '缓存回退',
  'longbridge-content': '内容回填',
  'order-stream': '订单推送',
  'live-backfill': '实时回填',
  live: '实时',
  quotes: '行情推送',
  depth: '盘口',
  trades: '成交明细',
  'quote / depth / trades': '行情推送',
  'quote/depth/trades': '行情推送',
  'protection-order-status': '保护单状态'
}

export const formatReadModelSourceLabel = (source = '', fallback = '') => {
  const raw = String(source || fallback || '').trim()
  if (!raw) {
    return ''
  }

  const normalized = raw.replace(/\s+/g, ' ')
  if (SOURCE_LABEL_MAP[normalized]) {
    return SOURCE_LABEL_MAP[normalized]
  }

  const compact = normalized.replace(/\s*\/\s*/g, '/')
  if (SOURCE_LABEL_MAP[compact]) {
    return SOURCE_LABEL_MAP[compact]
  }

  const snake = normalized.replace(/-/g, '_')
  if (SOURCE_LABEL_MAP[snake]) {
    return SOURCE_LABEL_MAP[snake]
  }

  return normalized
    .split(/\s*\/\s*/)
    .map((part) => SOURCE_LABEL_MAP[part] || part)
    .join(' / ')
}

export const formatReadModelSourceList = (sources = []) => (
  sources.map((source) => formatReadModelSourceLabel(source)).filter(Boolean).join(' / ')
)

export const formatQuoteCoverageLabel = (coverage = {}, options = {}) => {
  const readyCount = Number(coverage?.readyCount || 0)
  const totalCount = Number(coverage?.totalCount || 0)
  const prefix = options?.prefix || '快照'
  const emptyLabel = options?.emptyLabel || '等待快照'

  if (!totalCount || !readyCount) {
    return emptyLabel
  }
  return `${prefix} ${readyCount}/${totalCount}`
}

export const formatQuoteSnapshotTimeLabel = (snapshotAt, formatTime, options = {}) => {
  const prefix = options?.prefix || '快照'
  const emptyLabel = options?.emptyLabel || `等待${prefix}`
  if (!snapshotAt) {
    return emptyLabel
  }
  return `${prefix} ${typeof formatTime === 'function' ? formatTime(snapshotAt) : snapshotAt}`
}

export const formatQuoteCoverageMeta = (coverage = {}, formatTime, options = {}) => {
  const readyCount = Number(coverage?.readyCount || 0)
  const totalCount = Number(coverage?.totalCount || 0)
  const latestSnapshotAt = coverage?.latestSnapshotAt || ''
  const prefix = options?.prefix || '报价'
  const pendingText = options?.pendingText || '等待报价快照'

  if (!readyCount || !totalCount) {
    return pendingText
  }

  const timeText = latestSnapshotAt
    ? `，最新时间 ${typeof formatTime === 'function' ? formatTime(latestSnapshotAt) : latestSnapshotAt}`
    : ''
  return `${prefix} ${readyCount}/${totalCount}${timeText}`
}

export const formatQuoteStatusTag = ({ wsConnected = false, pendingCount = 0, readyCount = 0 } = {}) => {
  if (wsConnected && pendingCount > 0) {
    return { type: 'success', text: '行情补齐中' }
  }
  if (wsConnected) {
    return { type: 'success', text: '实时推送' }
  }
  if (readyCount > 0) {
    return { type: 'info', text: '报价快照' }
  }
  return { type: 'warning', text: '等待报价快照' }
}

export const formatContentCacheSourceLabel = (meta = {}) => {
  const source = String(meta?.dataSource || '').trim()
  const totalCount = Number(meta?.totalCount || 0)
  if (source === 'content-cache') return `内容缓存 ${totalCount} 条`
  if (source === 'content-cache-fallback') return '缓存回退'
  if (source === 'longbridge-content') return '内容已回填'
  return '等待内容缓存'
}

export const summarizeBriefingDataset = (items = []) => {
  const rows = Array.isArray(items) ? items : []
  const counts = rows.reduce((acc, item) => {
    const type = String(item?.briefingType || '').trim()
    if (type === 'market-insight' || type === 'market-ai-scan') {
      acc.scanCount += 1
    } else if (type === 'recommendation') {
      acc.recommendationCount += 1
    } else if (type === 'market-news' || type === 'announcements' || type === 'topics') {
      acc.contentCount += 1
    } else {
      acc.internalCount += 1
    }
    return acc
  }, {
    scanCount: 0,
    contentCount: 0,
    recommendationCount: 0,
    internalCount: 0
  })

  const snapshotAt = rows
    .map((item) => item?.generatedAt || '')
    .filter(Boolean)
    .sort((a, b) => String(b).localeCompare(String(a)))[0] || ''

  const parts = [
    counts.contentCount ? `内容 ${counts.contentCount} 条` : '',
    counts.scanCount ? `扫描 ${counts.scanCount} 条` : '',
    counts.recommendationCount ? `推荐 ${counts.recommendationCount} 条` : '',
    counts.internalCount ? `系统 ${counts.internalCount} 条` : ''
  ].filter(Boolean)

  return {
    ...counts,
    totalCount: rows.length,
    snapshotAt,
    sourceLabel: snapshotAt ? '资讯快照' : '等待资讯',
    sourceDetail: parts.length ? parts.join(' · ') : '等待后台任务刷新'
  }
}

export const buildAccountReadModelSummary = ({
  source = 'snapshot',
  snapshotAt = '',
  accountLabel = '',
  quotesConnected = false,
  orderStreamConnected = false,
  positionCount = 0,
  orderCount = 0
} = {}) => {
  const realtime = String(source || '').trim() === 'realtime'
  const statusText = realtime
    ? '实时账户态'
    : snapshotAt
      ? '账户快照'
      : '等待账户快照'

  const statusType = realtime ? 'success' : (snapshotAt ? 'info' : 'warning')
  const detail = realtime
    ? '账户资产、持仓价格和订单状态保持更新。'
    : '账户、持仓与订单使用最近快照。'

  const tags = [
    {
      type: snapshotAt ? 'info' : 'warning',
      text: snapshotAt ? '账户快照' : '等待快照'
    }
  ]

  if (accountLabel) {
    tags.push({ type: 'info', text: accountLabel })
  }
  if (positionCount > 0) {
    tags.push({
      type: quotesConnected ? 'success' : 'info',
      text: quotesConnected ? `持仓最新价 ${positionCount} 个` : `持仓快照 ${positionCount} 个`
    })
  }
  if (orderCount > 0) {
    tags.push({
      type: orderStreamConnected ? 'success' : 'info',
      text: orderStreamConnected ? `订单更新 ${orderCount} 条` : `订单 ${orderCount} 条`
    })
  }

  return {
    detail,
    statusText,
    statusType,
    updatedAt: snapshotAt || '',
    updatedPrefix: realtime ? '状态于' : '快照于',
    tags
  }
}

const pickReadModelSources = (meta = {}) => (
  meta?.sources && typeof meta.sources === 'object'
    ? meta.sources
    : {}
)

export const buildRecommendationReadModelSummary = (meta = {}, options = {}) => {
  const sources = pickReadModelSources(meta)
  const count = Number(meta?.count ?? options?.count ?? 0)
  const profile = options?.profileLabel || meta?.profile || 'growth'
  const quoteCoverageLabel = options?.quoteCoverageLabel || '报价快照待补齐'
  const snapshotAt = meta?.generatedAt || meta?.snapshotAt || ''
  const runLabel = formatReadModelSourceLabel(sources.runs || 'recommendation_runs')
  const itemLabel = formatReadModelSourceLabel(sources.items || 'recommendation_items')

  return {
    detail: '推荐列表按最近结果展示。',
    statusText: snapshotAt ? '推荐快照' : '等待推荐',
    statusType: snapshotAt ? 'info' : 'warning',
    updatedAt: snapshotAt,
    updatedPrefix: '生成于',
    tags: [
      { text: String(profile || '').trim() || 'growth', type: 'info' },
      { text: `${runLabel} / ${itemLabel}`, type: snapshotAt ? 'info' : 'warning' },
      { text: quoteCoverageLabel, type: String(quoteCoverageLabel).includes('待补齐') ? 'warning' : 'success' },
      { text: `${count} 条`, type: 'info' }
    ]
  }
}

export const buildFinanceBriefingReadModelSummary = (meta = {}, options = {}) => {
  const sources = pickReadModelSources(meta)
  const count = Number(meta?.count ?? options?.count ?? 0)
  const marketLabel = options?.marketLabel || meta?.market || '全部市场'
  const briefingLabel = formatReadModelSourceLabel(sources.briefings || 'finance_briefings')

  return {
    detail: '财经快讯、市场扫描与推荐关注已聚合展示。',
    statusText: meta?.snapshotAt ? '资讯快照' : '等待资讯',
    statusType: meta?.snapshotAt ? 'success' : 'warning',
    updatedAt: meta?.snapshotAt || '',
    updatedPrefix: '快照于',
    tags: [
      { text: briefingLabel, type: meta?.snapshotAt ? 'info' : 'warning' },
      { text: String(marketLabel || '').trim() || '全部市场', type: 'info' },
      { text: `${count} 条`, type: 'info' }
    ]
  }
}

export const buildTrendScanReadModelSummary = (meta = {}, options = {}) => {
  const sources = pickReadModelSources(meta)
  const count = Number(meta?.count ?? options?.count ?? 0)
  const symbolCount = Array.isArray(meta?.query?.symbols) ? meta.query.symbols.length : 0

  const scanLabel = formatReadModelSourceLabel(sources.scans || 'daily_symbol_trend_ai_scans')

  return {
    detail: '趋势扫描使用历史行情与指标快照。',
    statusText: meta?.snapshotAt ? '趋势扫描' : '等待扫描',
    statusType: meta?.snapshotAt ? 'warning' : 'warning',
    updatedAt: meta?.snapshotAt || '',
    updatedPrefix: '快照于',
    tags: [
      { text: scanLabel, type: meta?.snapshotAt ? 'info' : 'warning' },
      ...(symbolCount ? [{ text: `${symbolCount} 个标的`, type: 'info' }] : []),
      { text: `${count} 条`, type: 'info' }
    ]
  }
}

export const buildMarketInsightReadModelSummary = (meta = {}, options = {}) => {
  const sources = pickReadModelSources(meta)
  const count = Number(meta?.count ?? options?.count ?? 0)
  const quoteCoverageLabel = options?.quoteCoverageLabel || '报价快照待补齐'
  const label = options?.label || '市场动态'

  const insightLabel = formatReadModelSourceLabel(sources.insights || 'market_insight_snapshots')

  return {
    detail: `${label}使用最近市场快照。`,
    statusText: meta?.snapshotAt ? '市场快照' : '等待市场',
    statusType: meta?.snapshotAt ? 'info' : 'warning',
    updatedAt: meta?.snapshotAt || '',
    updatedPrefix: '快照于',
    tags: [
      { text: insightLabel, type: meta?.snapshotAt ? 'info' : 'warning' },
      { text: quoteCoverageLabel, type: String(quoteCoverageLabel).includes('待补齐') ? 'warning' : 'success' },
      { text: `${count} 条`, type: 'info' }
    ]
  }
}

export const buildStockPoolReadModelSummary = (meta = {}, options = {}) => {
  const sources = pickReadModelSources(meta)
  const count = Number(meta?.count ?? options?.count ?? 0)
  const total = Number(meta?.total ?? options?.total ?? count)
  const quoteCoverageLabel = options?.quoteCoverageLabel || '报价快照待补齐'
  const marketLabel = options?.marketLabel || meta?.market || '全部市场'
  const universeLabel = formatReadModelSourceLabel(sources.universe || 'market_universe')

  return {
    detail: '股票池按市场与最新报价展示。',
    statusText: total > 0 ? '股票池快照' : '等待股票池',
    statusType: total > 0 ? 'info' : 'warning',
    updatedAt: meta?.snapshotAt || '',
    updatedPrefix: '快照于',
    tags: [
      { text: universeLabel, type: total > 0 ? 'info' : 'warning' },
      { text: String(marketLabel || '').trim() || '全部市场', type: 'info' },
      { text: quoteCoverageLabel, type: String(quoteCoverageLabel).includes('待补齐') ? 'warning' : 'success' },
      { text: `${count}/${total || count} 条`, type: 'info' }
    ]
  }
}

export const buildHistoryReadModelSummary = (meta = {}, options = {}) => {
  const sources = pickReadModelSources(meta)
  const symbolCount = Array.isArray(meta?.query?.symbols) ? meta.query.symbols.length : Number(options?.symbolCount || 0)
  const timeframeLabel = options?.timeframeLabel || meta?.query?.timeframe || '日K'
  const limitLabel = options?.limitLabel || meta?.query?.limit || ''

  const historyLabel = formatReadModelSourceLabel(sources.history || 'historical_market_data')
  const indicatorLabel = formatReadModelSourceLabel(sources.indicators || 'indicator_snapshots')

  return {
    detail: '历史 K 线与指标按最新查询展示。',
    statusText: meta?.snapshotAt ? '历史快照' : '等待历史数据',
    statusType: meta?.snapshotAt ? 'info' : 'warning',
    updatedAt: meta?.snapshotAt || '',
    updatedPrefix: '快照于',
    tags: [
      ...(symbolCount ? [{ text: `${symbolCount} 个标的`, type: 'info' }] : []),
      { text: String(timeframeLabel || '').trim() || '日K', type: 'info' },
      ...(limitLabel ? [{ text: `${limitLabel} 根`, type: 'info' }] : []),
      { text: historyLabel, type: 'info' },
      { text: indicatorLabel, type: 'info' }
    ]
  }
}

export const buildSymbolOverviewReadModelSummary = (meta = {}, options = {}) => {
  const sources = pickReadModelSources(meta)
  const hasSnapshot = Boolean(meta?.snapshotAt || options?.fallbackUpdatedAt)
  const wsConnected = Boolean(options?.wsConnected)
  const overlayLabel = String(options?.overlayLabel || '').trim()
  const contentReady = Boolean(options?.contentReady)

  const historyLabel = formatReadModelSourceLabel(sources.history || 'historical_market_data')
  const indicatorLabel = formatReadModelSourceLabel(sources.indicators || 'indicator_snapshots')
  const quoteLabel = formatReadModelSourceLabel(sources.quote || 'quote_snapshots')
  const contentLabel = formatReadModelSourceLabel(sources.content || 'symbol_content_cache')
  const overlayText = formatReadModelSourceLabel(overlayLabel || '行情推送')

  return {
    detail: '标的详情展示基础资料、行情与指标。',
    statusText: wsConnected ? '行情在线' : (hasSnapshot ? '标的快照' : '等待标的'),
    statusType: wsConnected ? 'success' : (hasSnapshot ? 'info' : 'warning'),
    updatedAt: meta?.snapshotAt || options?.fallbackUpdatedAt || '',
    updatedPrefix: '更新于',
    tags: [
      { text: `历史 ${historyLabel}`, type: 'info' },
      { text: `指标 ${indicatorLabel}`, type: 'info' },
      { text: `报价 ${quoteLabel}`, type: options?.quoteReady ? 'info' : 'warning' },
      { text: `内容 ${contentLabel}`, type: contentReady ? 'info' : 'warning' },
      ...(overlayLabel ? [{ text: overlayText, type: wsConnected ? 'success' : 'info' }] : [])
    ]
  }
}

export const buildContentCacheReadModelSummary = (meta = {}, options = {}) => {
  const sourceLabel = formatReadModelSourceLabel(options?.sourceLabel || 'symbol_content_cache')
  const totalCount = Number(meta?.totalCount ?? options?.totalCount ?? 0)
  const refreshing = Boolean(options?.refreshing)
  const ready = totalCount > 0

  return {
    detail: ready
      ? '公告、资讯和讨论已同步。'
      : '公告、资讯和讨论待刷新。',
    statusText: formatContentCacheSourceLabel(meta),
    statusType: ready ? 'success' : 'warning',
    updatedAt: meta?.updatedAt || '',
    updatedPrefix: '快照于',
    tags: [
      ...(options?.symbol ? [{ text: String(options.symbol).trim().toUpperCase(), type: 'info' }] : []),
      { text: sourceLabel, type: ready ? 'info' : 'warning' },
      { text: ready ? `${totalCount} 条` : '等待内容', type: ready ? 'info' : 'warning' },
      ...(refreshing ? [{ text: '回源刷新中', type: 'warning' }] : [])
    ]
  }
}

export const buildTradingReadModelSummary = ({
  hasAccount = false,
  accountLabel = '',
  tradeMeta = {},
  orderMeta = {},
  hasLiveOverlay = false,
  hasRecentOrderStreamCoverage = false,
  quoteStreamConnected = false,
  positionQuotesConnected = false,
  streamSymbolCount = 0,
  positionSymbolCount = 0,
  recentOrderCount = 0
} = {}) => {
  if (!hasAccount) {
    return {
      detail: '未选择账户时先展示市场行情。',
      statusText: '等待账户接入',
      statusType: 'warning',
      updatedAt: '',
      updatedPrefix: '快照于',
      tags: [
        { type: 'warning', text: '未选择账户' },
        { type: 'info', text: '市场行情可用' }
      ]
    }
  }

  const tradeSources = pickReadModelSources(tradeMeta)
  const orderSources = pickReadModelSources(orderMeta)
  const accountLabelText = formatReadModelSourceLabel(tradeSources.account || 'account_asset_snapshots')
  const positionLabelText = formatReadModelSourceLabel(tradeSources.positions || 'position_snapshots')
  const orderLabelText = formatReadModelSourceLabel(orderSources.orders || 'trade_order_projections')
  const updatedAt = hasRecentOrderStreamCoverage
    ? (orderMeta?.snapshotAt || tradeMeta?.snapshotAt || '')
    : (tradeMeta?.snapshotAt || orderMeta?.snapshotAt || '')

  return {
    detail: '交易台展示账户、持仓、行情与订单。',
    statusText: hasLiveOverlay ? '交易在线' : (updatedAt ? '交易快照' : '等待交易数据'),
    statusType: hasLiveOverlay ? 'success' : (updatedAt ? 'info' : 'warning'),
    updatedAt,
    updatedPrefix: hasRecentOrderStreamCoverage ? '状态于' : '快照于',
    tags: [
      { type: tradeMeta?.snapshotAt ? 'info' : 'warning', text: tradeMeta?.snapshotAt ? `账户 ${accountLabelText}` : '等待账户快照' },
      { type: tradeMeta?.snapshotAt ? 'info' : 'warning', text: tradeMeta?.snapshotAt ? `持仓 ${positionLabelText}` : '等待持仓快照' },
      { type: orderMeta?.snapshotAt ? 'info' : 'warning', text: orderMeta?.snapshotAt ? `订单 ${orderLabelText}` : '等待订单' },
      ...(accountLabel ? [{ type: 'info', text: accountLabel }] : []),
      ...(streamSymbolCount
        ? [{ type: quoteStreamConnected ? 'success' : 'info', text: quoteStreamConnected ? '行情在线' : '等待行情' }]
        : positionSymbolCount
          ? [{ type: positionQuotesConnected ? 'success' : 'info', text: positionQuotesConnected ? `持仓最新价 ${positionSymbolCount} 个` : `等待最新价 ${positionSymbolCount} 个` }]
          : []),
      {
        type: hasRecentOrderStreamCoverage ? 'success' : 'info',
        text: hasRecentOrderStreamCoverage ? '订单更新中' : `${recentOrderCount} 条订单`
      },
      ...(Array.isArray(orderMeta?.warnings) && orderMeta.warnings.length ? [{ type: 'warning', text: '订单快照回退' }] : [])
    ]
  }
}

export const buildRiskReadModelSummary = ({
  overviewSource = 'snapshot',
  riskMeta = {},
  tradeMeta = {},
  quotesConnected = false,
  streamSymbolCount = 0,
  eventCount = 0
} = {}) => {
  const riskSources = pickReadModelSources(riskMeta)
  const tradeSources = pickReadModelSources(tradeMeta)
  const overlayLabel = Array.isArray(riskMeta?.realtimeOverlay) ? riskMeta.realtimeOverlay.join(' / ') : ''
  const overviewLabel = formatReadModelSourceLabel(riskSources.overview || 'risk_overview_snapshots')
  const positionLabel = formatReadModelSourceLabel(riskSources.positions || tradeSources.positions || 'position_snapshots')
  const overlayText = formatReadModelSourceLabel(overlayLabel)
  const updatedAt = riskMeta?.snapshotAt || riskMeta?.positionSnapshotAt || tradeMeta?.snapshotAt || ''
  const isRealtime = String(overviewSource || '').trim() === 'realtime'

  return {
    detail: isRealtime
      ? '风控总览保持更新。'
      : '风险评分、事件与保护单按最近快照展示。',
    statusText: isRealtime ? '实时总览' : (updatedAt ? '风险快照' : '等待风险'),
    statusType: isRealtime ? 'success' : (updatedAt ? 'info' : 'warning'),
    updatedAt,
    updatedPrefix: riskMeta?.snapshotAt ? '风控于' : '持仓于',
    tags: [
      {
        type: isRealtime ? 'success' : 'info',
        text: isRealtime ? '实时总览' : `总览 ${overviewLabel}`
      },
      {
        type: (riskMeta?.positionSnapshotAt || tradeMeta?.snapshotAt) ? 'info' : 'warning',
        text: (riskMeta?.positionSnapshotAt || tradeMeta?.snapshotAt)
          ? `持仓 ${positionLabel}`
          : '等待持仓快照'
      },
      ...(streamSymbolCount
        ? [{
            type: quotesConnected ? 'success' : 'info',
            text: quotesConnected ? `最新价 ${streamSymbolCount} 个` : `等待最新价 ${streamSymbolCount} 个`
          }]
        : []),
      ...(overlayLabel ? [{ type: isRealtime ? 'success' : 'info', text: overlayText }] : []),
      { type: 'info', text: `风险事件 ${eventCount} 条` }
    ]
  }
}

export const buildPositionReadModelSummary = ({
  meta = {},
  accountLabel = '',
  quotesConnected = false,
  streamSymbolCount = 0,
  positionCount = 0
} = {}) => {
  const sources = pickReadModelSources(meta)
  const overlays = new Set(Array.isArray(meta?.realtimeOverlay) ? meta.realtimeOverlay : [])
  if (quotesConnected && streamSymbolCount) {
    overlays.add('quotes')
  }
  const overlayLabel = Array.from(overlays).filter(Boolean).join(' / ')
  const positionLabel = formatReadModelSourceLabel(sources.positions || 'position_snapshots')
  const overlayText = formatReadModelSourceLabel(overlayLabel || '行情推送')
  const hasSnapshot = Boolean(meta?.snapshotAt)

  return {
    detail: positionCount
      ? '持仓明细展示最新价、浮盈亏和仓位占比。'
      : '持仓页等待账户快照；有持仓后会补齐最新价与浮盈亏。',
    statusText: quotesConnected && streamSymbolCount ? '最新价在线' : (hasSnapshot ? '持仓快照' : '等待持仓'),
    statusType: quotesConnected && streamSymbolCount ? 'success' : (hasSnapshot ? 'info' : 'warning'),
    updatedAt: meta?.snapshotAt || '',
    updatedPrefix: '更新于',
    tags: [
      {
        type: hasSnapshot ? 'info' : 'warning',
        text: hasSnapshot ? `持仓 ${positionLabel}` : '等待持仓快照'
      },
      ...(accountLabel ? [{ type: 'info', text: accountLabel }] : []),
      ...(streamSymbolCount
        ? [{
            type: quotesConnected ? 'success' : 'info',
            text: quotesConnected ? `最新价 ${streamSymbolCount} 个` : `等待最新价 ${streamSymbolCount} 个`
          }]
        : []),
      ...(overlayLabel ? [{ type: quotesConnected ? 'success' : 'info', text: overlayText }] : [])
    ]
  }
}

export const buildOrderProjectionReadModelSummary = ({
  meta = {},
  accountLabel = '',
  hasStreamCoverage = false,
  activeOrderCount = 0,
  filterLabel = ''
} = {}) => {
  const sources = pickReadModelSources(meta)
  const query = meta?.query && typeof meta.query === 'object' ? meta.query : {}
  const overlays = Array.isArray(meta?.realtimeOverlay) ? meta.realtimeOverlay : []
  const overlayLabel = overlays.includes('order-stream') ? '订单推送' : ''
  const snapshotAt = meta?.snapshotAt || ''
  const dataSource = String(meta?.dataSource || '').trim() || 'order-projection'
  const queryStatus = String(query.status || filterLabel || '').trim()

  const orderLabel = formatReadModelSourceLabel(sources.orders || 'trade_order_projections')

  return {
    detail: hasStreamCoverage
      ? '订单列表展示最新状态。'
      : '订单列表按最近快照展示。',
    statusText: hasStreamCoverage ? '订单更新中' : (snapshotAt ? '订单快照' : '等待订单'),
    statusType: hasStreamCoverage ? 'success' : (snapshotAt ? 'info' : 'warning'),
    updatedAt: snapshotAt,
    updatedPrefix: hasStreamCoverage ? '状态于' : '快照于',
    tags: [
      {
        type: snapshotAt ? 'info' : 'warning',
        text: dataSource === 'live-backfill' ? '最新订单' : `订单 ${orderLabel}`
      },
      ...(accountLabel ? [{ type: 'info', text: accountLabel }] : []),
      ...(queryStatus ? [{ type: 'warning', text: `筛选 ${queryStatus}` }] : []),
      { type: hasStreamCoverage ? 'success' : 'info', text: `当前 ${activeOrderCount} 条` },
      ...(overlayLabel ? [{ type: hasStreamCoverage ? 'success' : 'info', text: hasStreamCoverage ? `${overlayLabel}中` : `等待${overlayLabel}` }] : []),
      ...(Array.isArray(meta?.warnings) && meta.warnings.length ? [{ type: 'warning', text: '订单快照回退' }] : [])
    ]
  }
}

const PROMPT_ARTIFACT_PATTERNS = [
  /we need to produce/i,
  /must be within/i,
  /let'?s craft/i,
  /count characters/i,
  /position sizing/i,
  /market distribution/i,
  /including punctuation/i,
  /growth style/i,
  /use candidates list/i,
  /use given data/i,
  /use (the )?data/i,
  /provide title/i,
  /one-sentence conclusion/i,
  /risk提示/i,
  /recommendation summary/i,
  /推荐摘要[,，]\s*核心催化/i,
  /综合评分[,，]\s*置信度/i,
  /核心催化\s*\(list/i,
  /主要风险\s*\(list/i,
  /综合评分\s*\(0-?100\)/i,
  /置信度\s*\(0-?100\)/i
]

const GENERATED_PLACEHOLDER_PATTERNS = [
  /系统已生成(?:无模型降级)?摘要[。.!！]*/gi,
  /系统已生成(?:推荐|量化|市场扫描|组合)?摘要[。.!！]*/gi,
  /数据库中暂无新的市场扫描摘要[。.!！]*/gi,
  /AI\s*(?:推荐|组合)?摘要当前不可用[，,]?[^。.!！]*[。.!！]?/gi,
  /系统会综合[^。.!！]*生成推荐[。.!！]?/gi
]

const MARKET_LABEL_MAP = {
  US: '美股',
  CN: 'A股',
  HK: '港股'
}

const BRIEFING_TYPE_LABEL_MAP = {
  recommendation: '推荐跟踪',
  'market-ai-scan': '技术扫描',
  'market-insight': '市场动态',
  'market-news': '市场资讯',
  announcements: '公司公告',
  topics: '市场讨论',
  internal: '系统简报'
}

const toNumber = (value, fallback = 0) => {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

const formatSignedPercent = (value) => {
  const numeric = toNumber(value)
  return `${numeric >= 0 ? '+' : ''}${numeric.toFixed(2)}%`
}

const stripStructuredTags = (text = '') => {
  return String(text || '')
    .replace(/\[st\][^#\]]*#([^[]+)\[\/st\]/gi, '$1')
    .replace(/\[st\][^[]+\[\/st\]/gi, ' ')
}

const normalizeDisplayText = (text = '') => {
  return stripStructuredTags(text)
    .replace(/\*\*/g, '')
    .replace(/`+/g, '')
    .replace(/\r/g, '')
    .replace(/\u00a0/g, ' ')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

const stripGeneratedPlaceholders = (text = '') => {
  return GENERATED_PLACEHOLDER_PATTERNS
    .reduce((result, pattern) => result.replace(pattern, ''), normalizeDisplayText(text))
    .replace(/\s{2,}/g, ' ')
    .replace(/^[，,。.!！、\s]+|[，,。.!！、\s]+$/g, '')
    .trim()
}

export const looksLikePromptArtifact = (text = '') => {
  const source = normalizeDisplayText(text)
  if (!source) {
    return false
  }
  return PROMPT_ARTIFACT_PATTERNS.some((pattern) => pattern.test(source))
}

export const sanitizeNarrativeText = (text = '', fallback = '') => {
  const cleaned = stripGeneratedPlaceholders(text)
  const fallbackText = stripGeneratedPlaceholders(fallback)

  if (!cleaned) {
    return fallbackText
  }

  if (/^([*.,;:，。；：、\-\s]|标题)+$/i.test(cleaned)) {
    return fallbackText
  }

  if (looksLikePromptArtifact(cleaned)) {
    return fallbackText
  }

  return cleaned
}

export const buildMarketScanSummary = (scan = {}) => {
  const marketLabel = MARKET_LABEL_MAP[scan?.market] || scan?.market || '市场'
  const technicalScore = toNumber(scan?.technicalScore ?? scan?.technical_score)
  const breadthRatio = toNumber(scan?.breadthRatio ?? scan?.breadth_ratio)
  const status = String(scan?.status || '').trim()
  const statusText = status === 'risk_on'
    ? '偏强'
    : status === 'risk_off'
      ? '偏弱'
      : status === 'closed'
        ? '已休市'
        : '震荡'
  const benchmarkText = Array.isArray(scan?.benchmarks)
    ? scan.benchmarks
      .slice(0, 2)
      .map((item) => `${item?.name || item?.symbol || '基准'} ${formatSignedPercent(item?.changePercent)}`)
      .join('，')
    : ''

  return [
    `${marketLabel}当前处于${statusText}区间，技术分 ${technicalScore.toFixed(2)}。`,
    `市场广度 ${breadthRatio.toFixed(2)}%，建议结合主线强弱控制仓位节奏。`,
    benchmarkText ? `重点观察 ${benchmarkText}。` : ''
  ].join('')
}

export const buildFinanceBriefingSummary = (item = {}) => {
  if (item?.briefingType === 'market-ai-scan') {
    return buildMarketScanSummary({
      market: item?.market,
      technicalScore: item?.payload?.technicalScore,
      breadthRatio: item?.payload?.breadthRatio,
      benchmarks: item?.payload?.benchmarks
    })
  }

  if (item?.briefingType === 'recommendation') {
    const symbol = item?.payload?.symbol || item?.headline || '候选标的'
    const confidence = item?.payload?.confidence
    return `${symbol} 已同步最新推荐结论，可结合评分${confidence ? `和 ${confidence}% 置信度` : ''}做后续跟踪。`
  }

  if (item?.briefingType === 'market-insight') {
    return ''
  }

  const typeLabel = BRIEFING_TYPE_LABEL_MAP[item?.briefingType] || '资讯'
  return typeLabel
}

export const buildRecommendationOverview = (payload = {}) => {
  const rawItems = Array.isArray(payload?.items) ? payload.items : []
  const stats = payload?.stats || {}
  const symbols = rawItems.slice(0, 3).map((item) => item?.symbol).filter(Boolean)
  const marketMix = Object.entries(stats?.markets || {})
    .sort((a, b) => toNumber(b[1]) - toNumber(a[1]))
    .slice(0, 2)
    .map(([market, count]) => `${market} ${count}只`)
    .join('、')
  const profileLabel = payload?.profile_label || payload?.profile || '当前策略'

  return [
    `${profileLabel}当前共 ${stats?.total || rawItems.length || 0} 个候选。`,
    symbols.length ? `优先关注 ${symbols.join('、')}。` : '',
    marketMix ? `分布以 ${marketMix} 为主，建议分批布局并控制单票暴露。` : '建议结合风险等级与市场状态分批跟踪。'
  ].join('')
}

export const buildRecommendationItemThesis = (item = {}) => {
  const reasons = Array.isArray(item?.reasons) ? item.reasons.filter((entry) => !looksLikePromptArtifact(entry)) : []
  const pieces = [
    reasons.length ? `核心看点：${reasons.slice(0, 3).join('、')}` : '',
    item?.market ? `所属市场：${item.market}` : '',
    Number.isFinite(Number(item?.expectedReturn)) ? `预期收益 ${formatSignedPercent(item.expectedReturn)}` : ''
  ].filter(Boolean)

  return pieces.join('。')
}

export const buildRecommendationReasons = (item = {}) => {
  const market = item?.market ? `${item.market} 市场当前排序靠前` : ''
  const score = Number.isFinite(Number(item?.aiScore ?? item?.score))
    ? `量化分数 ${toNumber(item?.aiScore ?? item?.score).toFixed(2)}`
    : ''
  const expectedReturn = Number.isFinite(Number(item?.expectedReturn))
    ? `预期收益 ${formatSignedPercent(item.expectedReturn)}`
    : ''
  const assetHint = item?.assetType === 'etf' ? 'ETF 更适合分散配置' : '个股弹性更高，适合分批跟踪'

  return [market, score, expectedReturn || assetHint].filter(Boolean).slice(0, 3)
}

export const buildRecommendationRisks = (item = {}) => {
  const level = toNumber(item?.riskLevel)
  return [
    level >= 4 ? '波动级别偏高，建议控制单票仓位' : '建议保持单票仓位纪律',
    '追高前先确认量能与趋势延续性'
  ]
}

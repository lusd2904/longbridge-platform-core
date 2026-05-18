const pickDefined = (...values) => values.find((value) => value !== null && value !== undefined && value !== '')

export const getQuoteSnapshotAt = (item = {}) => (
  pickDefined(
    item?.quoteSnapshotAt,
    item?.quote_snapshot_at,
    item?.snapshotAt,
    item?.snapshot_at,
    item?.updatedAt
  ) || null
)

export const getQuoteSource = (item = {}) => (
  pickDefined(
    item?.quoteSource,
    item?.quote_source,
    item?.source
  ) || ''
)

export const isQuoteSnapshotReady = (item = {}) => {
  if (item?.quoteReady !== undefined && item?.quoteReady !== null) {
    return Boolean(item.quoteReady)
  }
  if (item?.quote_ready !== undefined && item?.quote_ready !== null) {
    return Boolean(item.quote_ready)
  }

  return Boolean(
    pickDefined(
      item?.price,
      item?.last_price,
      item?.lastPrice,
      item?.prevClose,
      item?.prev_close,
      item?.high,
      item?.low,
      item?.open,
      getQuoteSnapshotAt(item)
    )
  )
}

export const buildQuoteSnapshotMap = (items = []) => {
  return Object.fromEntries(
    (Array.isArray(items) ? items : [])
      .map((item) => [String(item?.symbol || '').trim().toUpperCase(), item])
      .filter(([symbol]) => Boolean(symbol))
  )
}

export const mergeQuoteSnapshot = (item = {}, quoteMap = {}) => {
  const base = { ...item }
  const symbol = String(base?.symbol || '').trim().toUpperCase()
  const snapshot = symbol ? quoteMap[symbol] || null : null
  const quoteSnapshotAt = getQuoteSnapshotAt(snapshot || base)
  const quoteSource = getQuoteSource(snapshot || base)

  if (!snapshot) {
    return {
      ...base,
      quoteSource,
      quote_source: quoteSource,
      quoteSnapshotAt,
      quote_snapshot_at: quoteSnapshotAt,
      quoteReady: isQuoteSnapshotReady(base)
    }
  }

  const price = pickDefined(snapshot?.price, snapshot?.last_price, snapshot?.lastPrice, base?.price)
  const changePercent = pickDefined(
    snapshot?.changePercent,
    snapshot?.change_percent,
    base?.changePercent,
    base?.change_percent
  )
  const volume = pickDefined(snapshot?.volume, base?.volume)

  return {
    ...base,
    price,
    changePercent,
    change_percent: changePercent,
    volume,
    quoteSource,
    quote_source: quoteSource,
    quoteSnapshotAt,
    quote_snapshot_at: quoteSnapshotAt,
    quoteReady: isQuoteSnapshotReady(snapshot) || isQuoteSnapshotReady(base)
  }
}

export const mergeQuoteSnapshots = (items = [], quoteMap = {}) => {
  return (Array.isArray(items) ? items : []).map((item) => mergeQuoteSnapshot(item, quoteMap))
}

export const summarizeQuoteSnapshotCoverage = (items = []) => {
  const rows = Array.isArray(items) ? items : []
  const latestSnapshotAt = rows
    .map((item) => getQuoteSnapshotAt(item))
    .filter(Boolean)
    .sort((a, b) => String(b).localeCompare(String(a)))[0] || ''

  const readyCount = rows.filter((item) => isQuoteSnapshotReady(item)).length
  return {
    readyCount,
    totalCount: rows.length,
    pendingCount: Math.max(rows.length - readyCount, 0),
    latestSnapshotAt
  }
}

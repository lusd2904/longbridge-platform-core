export const normalizeSuggestionKeyword = (value = '') => String(value || '').trim().toLowerCase()

const normalizeSuggestionSymbolBase = (value = '') => {
  return String(value || '')
    .trim()
    .toUpperCase()
    .split('.')
    .filter(Boolean)[0] || ''
}

export const buildSuggestionLabel = (target = {}) => {
  const symbol = String(target?.symbol || '').trim().toUpperCase()
  const name = String(target?.name || '').trim()
  return [symbol, name].filter(Boolean).join(' ').trim()
}

export const normalizeSuggestionEntry = (item = {}) => {
  const symbol = String(item?.symbol || '').trim().toUpperCase()
  const name = String(item?.name || item?.symbol || '').trim() || symbol
  const market = String(item?.market || '').trim().toUpperCase()
  const label = buildSuggestionLabel({ symbol, name })

  return {
    ...item,
    symbol,
    name,
    market,
    value: label,
    label
  }
}

export const filterLocalSuggestionMatches = (targets = [], keyword = '') => {
  const normalizedKeyword = normalizeSuggestionKeyword(keyword)
  const items = Array.isArray(targets) ? targets : []

  return items
    .filter((target) => {
      if (!normalizedKeyword) {
        return true
      }

      const symbol = String(target?.symbol || '').trim()
      const symbolBase = normalizeSuggestionSymbolBase(symbol)
      return [symbol, symbolBase, target?.name]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedKeyword))
    })
    .map((target) => normalizeSuggestionEntry(target))
}

const scoreSuggestion = (item = {}, keyword = '') => {
  const normalizedKeyword = normalizeSuggestionKeyword(keyword)
  const symbol = String(item?.symbol || '').trim().toUpperCase()
  const symbolBase = normalizeSuggestionSymbolBase(symbol)
  const name = String(item?.name || '').trim().toUpperCase()

  if (!normalizedKeyword) {
    return 0
  }

  const upperKeyword = normalizedKeyword.toUpperCase()
  if (symbolBase === upperKeyword || symbol === upperKeyword || symbol === `${upperKeyword}.US`) {
    return 0
  }
  if (symbol.startsWith(`${upperKeyword}.`)) {
    return 1
  }
  if (symbolBase.startsWith(upperKeyword) || symbol.startsWith(upperKeyword)) {
    return 2
  }
  if (name.startsWith(upperKeyword)) {
    return 3
  }
  if (symbolBase.includes(upperKeyword) || symbol.includes(upperKeyword)) {
    return 4
  }
  if (name.includes(upperKeyword)) {
    return 5
  }
  return 6
}

export const mergeSuggestionSources = (...sources) => {
  const merged = []
  const seen = new Set()

  sources.flat().forEach((item) => {
    const normalized = normalizeSuggestionEntry(item)
    if (!normalized.symbol || seen.has(normalized.symbol)) {
      return
    }
    seen.add(normalized.symbol)
    merged.push(normalized)
  })

  return merged
}

export const rankSuggestionMatches = (items = [], keyword = '') => {
  return [...(Array.isArray(items) ? items : [])].sort((left, right) => {
    const scoreDelta = scoreSuggestion(left, keyword) - scoreSuggestion(right, keyword)
    if (scoreDelta !== 0) {
      return scoreDelta
    }

    const leftSymbol = String(left?.symbol || '')
    const rightSymbol = String(right?.symbol || '')
    return leftSymbol.localeCompare(rightSymbol)
  })
}

export const collectRenderableSuggestionTexts = (values = []) => {
  return (Array.isArray(values) ? values : [])
    .map((value) => String(value || '').replace(/\s+/g, ' ').trim())
    .filter(Boolean)
}

export const hasExpectedSuggestion = (suggestionTexts = [], expectedSymbols = []) => {
  const normalizedSuggestions = collectRenderableSuggestionTexts(suggestionTexts).map((value) => value.toUpperCase())
  const normalizedExpected = (Array.isArray(expectedSymbols) ? expectedSymbols : [])
    .map((value) => String(value || '').trim().toUpperCase())
    .filter(Boolean)

  return normalizedExpected.some((expected) => {
    return normalizedSuggestions.some((suggestion) => suggestion.includes(expected))
  })
}

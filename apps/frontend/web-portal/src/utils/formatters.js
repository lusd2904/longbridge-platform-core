export function formatDecimal(value, digits = 2, fallback = '--') {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) {
    return fallback
  }
  return Number(value).toFixed(digits)
}

export function formatCurrency(value, options = {}) {
  const {
    currency = '$',
    digits = 2,
    fallback = `${currency}0.00`,
    signed = false,
    absolute = false
  } = options

  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) {
    return fallback
  }

  const amount = Number(value)
  const sign = signed ? (amount > 0 ? '+' : amount < 0 ? '-' : '') : ''
  const target = absolute ? Math.abs(amount) : signed ? Math.abs(amount) : amount

  return `${sign}${currency}${target.toFixed(digits).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`
}

export function formatOrderPrice(order = {}, options = {}) {
  const {
    fallback = '--',
    marketLabel = '市价',
    referencePrefix = '参考',
    currency = '$',
    digits = 2
  } = options
  const orderType = String(order?.orderType || order?.order_type || '').trim().toLowerCase()
  const candidates = [
    order?.price,
    order?.submittedPrice,
    order?.submitted_price,
    order?.requestPrice,
    order?.request_price,
    order?.referencePrice,
    order?.reference_price,
    order?.limitPrice,
    order?.limit_price
  ]

  for (const value of candidates) {
    if (value === null || value === undefined || value === '') {
      continue
    }
    const amount = Number(value)
    if (Number.isFinite(amount) && amount > 0) {
      const formatted = formatCurrency(amount, { currency, digits, fallback })
      return orderType === 'market' || orderType === 'mo' ? `${marketLabel} ${formatted}` : formatted
    }
  }

  if (orderType === 'market' || orderType === 'mo') {
    return marketLabel
  }
  return referencePrefix ? fallback : fallback
}

export function formatPercent(value, options = {}) {
  const {
    digits = 2,
    fallback = '--',
    signed = true
  } = options

  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) {
    return fallback
  }

  const amount = Number(value)
  const prefix = signed && amount > 0 ? '+' : ''
  return `${prefix}${amount.toFixed(digits)}%`
}

export function formatSignedNumber(value, digits = 2, fallback = '--') {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) {
    return fallback
  }
  const amount = Number(value)
  return `${amount > 0 ? '+' : ''}${amount.toFixed(digits)}`
}

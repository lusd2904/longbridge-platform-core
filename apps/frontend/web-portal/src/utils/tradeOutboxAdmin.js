const toArray = (value) => (Array.isArray(value) ? value : [])

export const supportsTradeOutboxAdminDetails = (summary = {}) => {
  return Boolean(summary?.eventStream && typeof summary.eventStream === 'object')
}

export const isTradeOutboxEndpointMissing = (error) => {
  const status = Number(error?.response?.status || error?.status || 0)
  if (status === 404) {
    return true
  }

  const payload = error?.data || error?.response?.data || {}
  const text = [
    error?.message,
    payload?.error,
    payload?.message
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()

  return text.includes('not found')
}

export const resolveTradeOutboxAdminPayload = ({
  healthResult,
  eventsResult,
  sagasResult
}) => {
  const summary = healthResult?.status === 'fulfilled' ? (healthResult.value || {}) : {}
  const eventsMissing = eventsResult?.status === 'rejected' && isTradeOutboxEndpointMissing(eventsResult.reason)
  const sagasMissing = sagasResult?.status === 'rejected' && isTradeOutboxEndpointMissing(sagasResult.reason)
  const missingNotes = []

  if (eventsMissing) {
    missingNotes.push('事件列表接口暂未开放')
  }

  if (sagasMissing) {
    missingNotes.push('Saga 聚合接口暂未开放')
  }

  const error = [
    healthResult?.status === 'rejected' ? healthResult.reason : null,
    eventsResult?.status === 'rejected' && !eventsMissing ? eventsResult.reason : null,
    sagasResult?.status === 'rejected' && !sagasMissing ? sagasResult.reason : null
  ].find(Boolean) || null

  const events = eventsResult?.status === 'fulfilled'
    ? toArray(eventsResult.value?.data)
    : []
  const sagas = sagasResult?.status === 'fulfilled'
    ? toArray(sagasResult.value?.data)
    : []

  let mode = 'full'
  if (eventsMissing && sagasMissing) {
    mode = 'health-only'
  } else if (eventsMissing || sagasMissing || error) {
    mode = 'partial'
  }

  return {
    mode,
    summary,
    events,
    sagas,
    error,
    message: missingNotes.join('，'),
    availability: {
      health: healthResult?.status === 'fulfilled',
      events: eventsResult?.status === 'fulfilled',
      sagas: sagasResult?.status === 'fulfilled'
    }
  }
}

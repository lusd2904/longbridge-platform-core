export function resolveViewBySubsystem(subsystemCode = '', currentViewCode = 'trading') {
  const normalizedCode = String(subsystemCode || '').trim()

  if (normalizedCode === 'analysis') {
    return 'research'
  }

  if (normalizedCode === 'platform') {
    return 'management'
  }

  if (normalizedCode === 'trading') {
    return 'trading'
  }

  return String(currentViewCode || '').trim() || 'trading'
}

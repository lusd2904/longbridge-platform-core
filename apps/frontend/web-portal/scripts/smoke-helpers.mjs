const normalizeTimeout = (value, fallback) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

export const withStepTimeout = async (task, options = {}) => {
  const label = options.label || 'smoke-step'
  const timeoutMs = normalizeTimeout(options.timeoutMs, 30000)

  let timer = null

  try {
    return await Promise.race([
      Promise.resolve(task),
      new Promise((_, reject) => {
        timer = setTimeout(() => {
          reject(new Error(`${label} timed out after ${timeoutMs}ms`))
        }, timeoutMs)
      })
    ])
  } finally {
    if (timer) {
      clearTimeout(timer)
    }
  }
}

export const createProgressReporter = (options = {}) => {
  const enabled = options.enabled !== false

  return (message) => {
    if (!enabled) {
      return
    }

    const timestamp = new Date().toISOString()
    console.log(`[smoke ${timestamp}] ${message}`)
  }
}

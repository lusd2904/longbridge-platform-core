const DEFAULT_LOCAL_BASE_URL = 'http://127.0.0.1:3100'

function formatBaseUrlError(message, { envVarName, example }) {
  return new Error(`${envVarName} ${message}. Example: ${example}`)
}

function normalizeBaseUrl(rawValue, options = {}) {
  const envVarName = options.envVarName || 'BASE_URL'
  const fallback = options.fallback || DEFAULT_LOCAL_BASE_URL
  const example = options.example || fallback

  const sourceValue = rawValue == null || String(rawValue).trim() === ''
    ? fallback
    : String(rawValue).trim()

  let normalized = sourceValue.replace(/^(https?):(?!\/\/)/i, '$1://')
  normalized = normalized.replace(/^(https?)\/\/+/i, '$1://')

  let parsed
  try {
    parsed = new URL(normalized)
  } catch {
    throw formatBaseUrlError(`must be a valid http(s) URL, received "${sourceValue}"`, {
      envVarName,
      example
    })
  }

  if (!/^https?:$/.test(parsed.protocol)) {
    throw formatBaseUrlError(`must use http:// or https://, received "${sourceValue}"`, {
      envVarName,
      example
    })
  }

  if (!parsed.hostname) {
    throw formatBaseUrlError(`must include a hostname, received "${sourceValue}"`, {
      envVarName,
      example
    })
  }

  parsed.pathname = parsed.pathname.replace(/\/+$/, '') || '/'
  return parsed.toString().replace(/\/$/, '')
}

function resolveBaseUrl(envVarName, options = {}) {
  return normalizeBaseUrl(process.env[envVarName], {
    envVarName,
    fallback: options.fallback || DEFAULT_LOCAL_BASE_URL,
    example: options.example || DEFAULT_LOCAL_BASE_URL
  })
}

module.exports = {
  DEFAULT_LOCAL_BASE_URL,
  normalizeBaseUrl,
  resolveBaseUrl
}

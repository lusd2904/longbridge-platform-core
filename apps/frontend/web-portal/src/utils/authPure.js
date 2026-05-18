// Pure auth utilities for token handling without any router dependencies.
// Store token in localStorage under the key 'auth_token'.

export function getTokenLocal() {
  return localStorage.getItem('auth_token') || ''
}

export function setTokenLocal(token) {
  if (typeof token === 'string') {
    localStorage.setItem('auth_token', token)
  }
}

export function clearAuthLocal() {
  localStorage.removeItem('auth_token')
}

// Export clearAuth as alias for compatibility with other modules.
export const clearAuth = clearAuthLocal

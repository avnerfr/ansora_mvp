// Cognito tokens are stored in cookies (set by /api/auth/callback)

export const getAuthToken = (): string | null => {
  if (typeof window === 'undefined') return null
  const match = document.cookie.match(/(?:^|; )cognito_access_token=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : null
}

export const isAuthenticated = (): boolean => {
  return getAuthToken() !== null
}

export const logout = (): void => {
  window.location.href = '/api/auth/logout'
}

export const getCurrentUser = (): any => {
  if (typeof window === 'undefined') return null
  const match = document.cookie.match(/(?:^|; )cognito_user=([^;]*)/)
  if (!match) return null
  try {
    return JSON.parse(decodeURIComponent(match[1]))
  } catch {
    return null
  }
}


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
  // Clear cookies first
  clearAllCognitoCookies()
  // Then redirect to logout endpoint
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

export const isAdmin = (): boolean => {
  const token = getAuthToken()
  if (!token) return false
  
  try {
    // Decode JWT payload (access token contains cognito:groups)
    const payload = JSON.parse(atob(token.split('.')[1]))
    const groups = payload['cognito:groups'] || []
    return groups.includes('Administrators')
  } catch {
    return false
  }
}

// Clear all Cognito-related cookies (useful for clearing obsolete tokens)
export const clearAllCognitoCookies = (): void => {
  if (typeof window === 'undefined') return
  
  const cookiesToDelete = [
    'cognito_access_token',
    'cognito_id_token',
    'cognito_refresh_token',
    'cognito_user',
    'oidc_nonce',
    'oidc_state',
  ]
  
  const hostname = window.location.hostname
  const baseDomain = hostname.split('.').slice(-2).join('.')
  
  cookiesToDelete.forEach(cookieName => {
    // Delete with different path and domain options to ensure it's cleared
    document.cookie = `${cookieName}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`
    document.cookie = `${cookieName}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; domain=${hostname};`
    if (baseDomain !== hostname) {
      document.cookie = `${cookieName}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; domain=.${baseDomain};`
    }
  })
}


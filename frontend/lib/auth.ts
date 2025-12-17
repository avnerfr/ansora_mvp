// Temporary simple JWT auth for development
// This allows the app to work while you resolve the Cognito package installation

export const getAuthToken = (): string | null => {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('auth_token')
}

export const setAuthToken = (token: string): void => {
  if (typeof window === 'undefined') return
  localStorage.setItem('auth_token', token)
}

export const removeAuthToken = (): void => {
  if (typeof window === 'undefined') return
  localStorage.removeItem('auth_token')
}

export const isAuthenticated = (): boolean => {
  const token = getAuthToken()
  console.log('isAuthenticated check - token exists:', !!token)

  if (!token) return false

  try {
    // Basic JWT expiration check
    const payload = JSON.parse(atob(token.split('.')[1]))
    const now = Math.floor(Date.now() / 1000)
    const isValid = payload.exp > now
    console.log('Token expiration check - valid:', isValid, 'exp:', payload.exp, 'now:', now)
    return isValid
  } catch (error) {
    console.log('Token parsing error:', error)
    return false
  }
}

export const login = async (email: string, password: string): Promise<any> => {
  // For now, this will work with your existing backend auth
  // You can implement Cognito later once the package is installed
  console.log('Login called with:', email, password)
  throw new Error('Authentication temporarily disabled - please use your existing auth system')
}

export const logout = (): void => {
  removeAuthToken()
  window.location.href = '/auth/login'
}

export const getCurrentUser = async () => {
  // Return basic user info for now
  return {
    email: 'user@example.com',
    username: 'user'
  }
}


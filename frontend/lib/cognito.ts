import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserSession
} from 'amazon-cognito-identity-js'

// Cognito configuration
const poolData = {
  UserPoolId: 'us-east-1_vpBoYyEss',
  ClientId: '2vhardprmlfa8rfe4rbm4rin3b'
}

const userPool = new CognitoUserPool(poolData)

// Get stored tokens
export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('cognito_access_token')
}

export function getIdToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('cognito_id_token')
}

export function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('cognito_refresh_token')
}

// Store tokens from Cognito session
function storeTokens(session: CognitoUserSession): void {
  if (typeof window === 'undefined') return

  const accessToken = session.getAccessToken().getJwtToken()
  const idToken = session.getIdToken().getJwtToken()
  const refreshToken = session.getRefreshToken().getToken()

  localStorage.setItem('cognito_access_token', accessToken)
  localStorage.setItem('cognito_id_token', idToken)
  localStorage.setItem('cognito_refresh_token', refreshToken)
}

// Login with username and password
export async function login(email: string, password: string): Promise<any> {
  return new Promise((resolve, reject) => {
    const authenticationDetails = new AuthenticationDetails({
      Username: email,
      Password: password,
    })

    const cognitoUser = new CognitoUser({
      Username: email,
      Pool: userPool,
    })

    cognitoUser.authenticateUser(authenticationDetails, {
      onSuccess: (session) => {
        storeTokens(session)
        resolve({
          accessToken: session.getAccessToken().getJwtToken(),
          idToken: session.getIdToken().getJwtToken(),
          refreshToken: session.getRefreshToken().getToken()
        })
      },
      onFailure: (err) => {
        reject(err)
      },
      newPasswordRequired: (userAttributes, requiredAttributes) => {
        // Handle new password required (e.g., first login)
        reject(new Error('New password required'))
      }
    })
  })
}

// Get current authenticated user
export function getCurrentUser(): any {
  const cognitoUser = userPool.getCurrentUser()
  return cognitoUser
}

// Get user info from stored tokens
export function getUserInfo(): any {
  const idToken = getIdToken()
  if (!idToken) return null

  try {
    const payload = JSON.parse(atob(idToken.split('.')[1]))
    return {
      sub: payload.sub,
      email: payload.email,
      email_verified: payload.email_verified,
      given_name: payload.given_name,
      family_name: payload.family_name,
      username: payload['cognito:username']
    }
  } catch (error) {
    console.error('Error parsing user info:', error)
    return null
  }
}

// Logout
export function logout(): void {
  if (typeof window === 'undefined') return

  const cognitoUser = userPool.getCurrentUser()
  if (cognitoUser) {
    cognitoUser.signOut()
  }

  // Clear stored tokens
  localStorage.removeItem('cognito_access_token')
  localStorage.removeItem('cognito_id_token')
  localStorage.removeItem('cognito_refresh_token')
  localStorage.removeItem('auth_token') // Clear legacy token too

  // Redirect to login page
  window.location.href = '/auth/login'
}

// Check if user is authenticated
export function isAuthenticated(): boolean {
  const accessToken = getAccessToken()
  if (!accessToken) return false

  try {
    // Decode JWT to check expiration
    const payload = JSON.parse(atob(accessToken.split('.')[1]))
    const now = Math.floor(Date.now() / 1000)
    return payload.exp > now
  } catch {
    return false
  }
}

// Register new user
export async function register(email: string, password: string): Promise<any> {
  return new Promise((resolve, reject) => {
    userPool.signUp(email, password, [], [], (err, result) => {
      if (err) {
        reject(err)
      } else {
        resolve(result)
      }
    })
  })
}

// Confirm registration with verification code
export async function confirmRegistration(email: string, code: string): Promise<any> {
  return new Promise((resolve, reject) => {
    const cognitoUser = new CognitoUser({
      Username: email,
      Pool: userPool,
    })

    cognitoUser.confirmRegistration(code, true, (err, result) => {
      if (err) {
        reject(err)
      } else {
        resolve(result)
      }
    })
  })
}

// Resend confirmation code
export async function resendConfirmationCode(email: string): Promise<any> {
  return new Promise((resolve, reject) => {
    const cognitoUser = new CognitoUser({
      Username: email,
      Pool: userPool,
    })

    cognitoUser.resendConfirmationCode((err, result) => {
      if (err) {
        reject(err)
      } else {
        resolve(result)
      }
    })
  })
}

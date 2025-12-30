import { Issuer } from 'openid-client'

let cachedClient: any | null = null
let cachedConfig: string | null = null

// Simple logger for server-side code
const logger = {
  error: (msg: string) => console.error(`[Cognito OIDC] ${msg}`),
  warn: (msg: string) => console.warn(`[Cognito OIDC] ${msg}`),
  info: (msg: string) => console.log(`[Cognito OIDC] ${msg}`),
}

/**
 * Server-only Cognito OIDC client initialization.
 *
 * IMPORTANT:
 * - Do NOT import this module from client components.
 * - Keep client_secret on the server only.
 *
 * Required env vars:
 * - COGNITO_USER_POOL_ID (e.g. us-east-1_vpBoYyEss)
 * - COGNITO_REGION (e.g. us-east-1)
 * - COGNITO_CLIENT_ID
 * - COGNITO_CLIENT_SECRET
 * - COGNITO_REDIRECT_URI (e.g. https://ansora-mvp.vercel.app/api/auth/callback)
 */
export async function getCognitoOidcClient(redirectUri?: string) {
  const region = process.env.COGNITO_REGION
  const userPoolId = process.env.COGNITO_USER_POOL_ID
  const clientId = process.env.COGNITO_CLIENT_ID
  const clientSecret = process.env.COGNITO_CLIENT_SECRET
  const envRedirectUri = process.env.COGNITO_REDIRECT_URI

  if (!region || !userPoolId || !clientId || !clientSecret) {
    throw new Error(
      'Missing Cognito env vars. Required: COGNITO_REGION, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, COGNITO_CLIENT_SECRET'
    )
  }

  // Use provided redirectUri or fallback to env var
  const finalRedirectUri = redirectUri || envRedirectUri
  if (!finalRedirectUri) {
    throw new Error('Redirect URI must be provided either as parameter or via COGNITO_REDIRECT_URI env var')
  }

  // Create a cache key based on config to invalidate when region/app changes
  const configKey = `${region}:${userPoolId}:${clientId}:${finalRedirectUri}`
  
  // If config changed, clear the cache
  if (cachedConfig !== configKey) {
    cachedClient = null
    cachedConfig = configKey
  }

  if (cachedClient) return cachedClient

  // Cognito OIDC discovery endpoint
  const issuerUrl = `https://cognito-idp.${region}.amazonaws.com/${userPoolId}`
  const issuer = await Issuer.discover(issuerUrl)

  cachedClient = new issuer.Client({
    client_id: clientId,
    client_secret: clientSecret,
    redirect_uris: [finalRedirectUri],
    response_types: ['code'],
  })

  return cachedClient
}

/**
 * Clear the cached OIDC client (useful when Cognito config changes)
 */
export function clearCognitoClientCache(): void {
  cachedClient = null
  cachedConfig = null
}

/**
 * Get Cognito logout URL
 * This will sign the user out from Cognito and redirect back to the app
 */
export function getCognitoLogoutUrl(logoutRedirectUri: string): string {
  const region = process.env.COGNITO_REGION
  const userPoolId = process.env.COGNITO_USER_POOL_ID
  const clientId = process.env.COGNITO_CLIENT_ID
  const cognitoDomain = process.env.COGNITO_DOMAIN // Optional: if custom domain is configured

  if (!region || !userPoolId || !clientId) {
    throw new Error('Missing Cognito env vars for logout')
  }

  // Construct Cognito domain
  // If COGNITO_DOMAIN is set, use it (for custom domains)
  // Otherwise, construct from user pool ID
  // User pool ID format: us-east-1_XXXXXXXXX
  // Default domain format: {userPoolIdWithoutUnderscore}.auth.{region}.amazoncognito.com
  let domain: string
  if (cognitoDomain) {
    // Clean domain - remove protocol and trailing slashes
    domain = cognitoDomain.trim()
    domain = domain.replace(/^https?:\/\//, '') // Remove protocol if present
    domain = domain.replace(/\/+$/, '') // Remove trailing slashes
  } else {
    // Remove underscore from user pool ID to get domain part
    // e.g., us-east-1_kOwOgLGdg -> us-east-1kOwOgLGdg
    const domainPart = userPoolId.replace('_', '').toLowerCase()
    domain = `${domainPart}.auth.${region}.amazoncognito.com`
  }
  
  // Ensure domain doesn't have protocol or slashes
  domain = domain.trim().replace(/^https?:\/\//, '').replace(/\/+$/, '')
  
  // Build logout URL - construct manually to avoid any URL parsing issues
  const encodedClientId = encodeURIComponent(clientId)
  const encodedLogoutUri = encodeURIComponent(logoutRedirectUri)
  const logoutUrlString = `https://${domain}/logout?client_id=${encodedClientId}&logout_uri=${encodedLogoutUri}`
  
  // Validate the URL by parsing it
  try {
    const testUrl = new URL(logoutUrlString)
    // Double-check for malformed URLs
    if (testUrl.href.includes('https://https://') || testUrl.pathname.startsWith('//')) {
      throw new Error(`Malformed URL detected: ${testUrl.href}`)
    }
    return testUrl.toString()
  } catch (error) {
    logger.error(`Failed to construct valid logout URL: ${error}`)
    throw new Error(`Invalid logout URL: ${logoutUrlString}`)
  }
}



import { Issuer } from 'openid-client'

let cachedClient: any | null = null

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
export async function getCognitoOidcClient() {
  if (cachedClient) return cachedClient

  const region = process.env.COGNITO_REGION
  const userPoolId = process.env.COGNITO_USER_POOL_ID
  const clientId = process.env.COGNITO_CLIENT_ID
  const clientSecret = process.env.COGNITO_CLIENT_SECRET
  const redirectUri = process.env.COGNITO_REDIRECT_URI

  if (!region || !userPoolId || !clientId || !clientSecret || !redirectUri) {
    throw new Error(
      'Missing Cognito env vars. Required: COGNITO_REGION, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, COGNITO_CLIENT_SECRET, COGNITO_REDIRECT_URI'
    )
  }

  // Cognito OIDC discovery endpoint
  const issuerUrl = `https://cognito-idp.${region}.amazonaws.com/${userPoolId}`
  const issuer = await Issuer.discover(issuerUrl)

  cachedClient = new issuer.Client({
    client_id: clientId,
    client_secret: clientSecret,
    redirect_uris: [redirectUri],
    response_types: ['code'],
  })

  return cachedClient
}



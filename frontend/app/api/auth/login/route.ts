import { NextResponse } from 'next/server'
import { getCognitoOidcClient } from '@/lib/cognito-oidc.server'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const client = await getCognitoOidcClient()
    const redirectUri = process.env.COGNITO_REDIRECT_URI
    
    if (!redirectUri) {
      console.error('COGNITO_REDIRECT_URI is not configured')
      return NextResponse.redirect(new URL('/auth/login?error=config_error', process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'))
    }
    
    const authUrl = client.authorizationUrl({
      redirect_uri: redirectUri,
      scope: 'email openid phone',
      response_type: 'code',
    })
    
    return NextResponse.redirect(authUrl)
  } catch (error) {
    console.error('Login error:', error)
    return NextResponse.redirect(new URL('/auth/login?error=init_failed', process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'))
  }
}

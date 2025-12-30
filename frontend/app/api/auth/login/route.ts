import { NextRequest, NextResponse } from 'next/server'
import { getCognitoOidcClient } from '@/lib/cognito-oidc.server'

export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  try {
    // Use root domain as redirect URI to match Cognito configuration
    // Cognito is configured to redirect to http://localhost:3000 (root)
    const redirectUri = request.nextUrl.origin
    
    // Get client with the dynamically constructed redirect URI
    const client = await getCognitoOidcClient(redirectUri)
    
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

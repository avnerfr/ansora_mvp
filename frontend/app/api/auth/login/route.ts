import { NextResponse } from 'next/server'
import { getCognitoOidcClient } from '@/lib/cognito-oidc.server'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const client = await getCognitoOidcClient()
    
    const authUrl = client.authorizationUrl({
      scope: 'email openid phone',
    })
    
    return NextResponse.redirect(authUrl)
  } catch (error) {
    console.error('Login error:', error)
    return NextResponse.redirect(new URL('/auth/login?error=init_failed', process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'))
  }
}

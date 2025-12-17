import { NextResponse } from 'next/server'
import { generators } from 'openid-client'
import { getCognitoOidcClient } from '@/lib/cognito-oidc.server'

export async function GET() {
  try {
    const client = await getCognitoOidcClient()
    
    const nonce = generators.nonce()
    const state = generators.state()
    
    const authUrl = client.authorizationUrl({
      scope: 'email openid phone',
      state: state,
      nonce: nonce,
    })
    
    const response = NextResponse.redirect(authUrl)
    
    // Store nonce and state in HTTP-only cookies for callback verification
    response.cookies.set('oidc_nonce', nonce, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 60 * 10, // 10 minutes
      path: '/',
    })
    response.cookies.set('oidc_state', state, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 60 * 10, // 10 minutes
      path: '/',
    })
    
    return response
  } catch (error) {
    console.error('Login error:', error)
    return NextResponse.redirect(new URL('/auth/login?error=init_failed', process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'))
  }
}


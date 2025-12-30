import { NextRequest, NextResponse } from 'next/server'
import { getCognitoOidcClient } from '@/lib/cognito-oidc.server'

export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  try {
    const code = request.nextUrl.searchParams.get('code')
    
    if (!code) {
      console.error('Missing authorization code')
      return NextResponse.redirect(new URL('/auth/login?error=missing_code', request.url))
    }
    
    // Use root domain as redirect URI to match Cognito configuration
    // Cognito redirects to http://localhost:3000 (root), not /api/auth/callback
    const redirectUri = request.nextUrl.origin
    
    const client = await getCognitoOidcClient(redirectUri)
    
    // Exchange code for tokens (skip state/nonce verification)
    const tokenSet = await client.callback(redirectUri, { code })
    
    // Get user info
    const userInfo = await client.userinfo(tokenSet.access_token!)
    
    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://ansora-mvp.vercel.app'
    
    // Check for redirect destination in cookie or default to home
    const redirectTo = request.cookies.get('redirect_after_login')?.value || '/'
    const response = NextResponse.redirect(new URL(redirectTo, baseUrl))
    
    // Clear the redirect cookie
    response.cookies.delete('redirect_after_login')
    
    // Store tokens in cookies
    if (tokenSet.access_token) {
      response.cookies.set('cognito_access_token', tokenSet.access_token, {
        httpOnly: false,
        secure: true,
        sameSite: 'lax',
        maxAge: tokenSet.expires_in || 3600,
        path: '/',
      })
    }
    
    if (tokenSet.id_token) {
      response.cookies.set('cognito_id_token', tokenSet.id_token, {
        httpOnly: true,
        secure: true,
        sameSite: 'lax',
        maxAge: tokenSet.expires_in || 3600,
        path: '/',
      })
    }
    
    if (tokenSet.refresh_token) {
      response.cookies.set('cognito_refresh_token', tokenSet.refresh_token, {
        httpOnly: true,
        secure: true,
        sameSite: 'lax',
        maxAge: 60 * 60 * 24 * 30,
        path: '/',
      })
    }
    
    response.cookies.set('cognito_user', JSON.stringify(userInfo), {
      httpOnly: false,
      secure: true,
      sameSite: 'lax',
      maxAge: tokenSet.expires_in || 3600,
      path: '/',
    })
    
    return response
  } catch (err) {
    console.error('Callback error:', err)
    return NextResponse.redirect(new URL('/auth/login?error=callback_failed', request.url))
  }
}

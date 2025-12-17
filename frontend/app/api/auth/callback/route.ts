import { NextRequest, NextResponse } from 'next/server'
import { getCognitoOidcClient } from '@/lib/cognito-oidc.server'

export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  try {
    const client = await getCognitoOidcClient()
    
    // Get nonce and state from cookies
    const nonce = request.cookies.get('oidc_nonce')?.value
    const state = request.cookies.get('oidc_state')?.value
    
    if (!nonce || !state) {
      console.error('Missing nonce or state cookies')
      return NextResponse.redirect(new URL('/auth/login?error=missing_state', request.url))
    }
    
    // Get callback params from URL
    const params = {
      code: request.nextUrl.searchParams.get('code'),
      state: request.nextUrl.searchParams.get('state'),
    }
    
    const redirectUri = process.env.COGNITO_REDIRECT_URI || 'https://ansora-mvp.vercel.app/api/auth/callback'
    
    // Exchange code for tokens
    const tokenSet = await client.callback(redirectUri, params, {
      nonce: nonce,
      state: state,
    })
    
    // Get user info
    const userInfo = await client.userinfo(tokenSet.access_token!)
    
    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://ansora-mvp.vercel.app'
    const response = NextResponse.redirect(new URL('/', baseUrl))
    
    // Store tokens in HTTP-only cookies
    if (tokenSet.access_token) {
      response.cookies.set('cognito_access_token', tokenSet.access_token, {
        httpOnly: false, // Allow client-side access for API calls
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        maxAge: tokenSet.expires_in || 3600,
        path: '/',
      })
    }
    
    if (tokenSet.id_token) {
      response.cookies.set('cognito_id_token', tokenSet.id_token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        maxAge: tokenSet.expires_in || 3600,
        path: '/',
      })
    }
    
    if (tokenSet.refresh_token) {
      response.cookies.set('cognito_refresh_token', tokenSet.refresh_token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        maxAge: 60 * 60 * 24 * 30, // 30 days
        path: '/',
      })
    }
    
    // Store user info
    response.cookies.set('cognito_user', JSON.stringify(userInfo), {
      httpOnly: false,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: tokenSet.expires_in || 3600,
      path: '/',
    })
    
    // Clear nonce and state cookies
    response.cookies.delete('oidc_nonce')
    response.cookies.delete('oidc_state')
    
    return response
  } catch (err) {
    console.error('Callback error:', err)
    return NextResponse.redirect(new URL('/auth/login?error=callback_failed', request.url))
  }
}


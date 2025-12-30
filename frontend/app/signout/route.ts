import { NextRequest, NextResponse } from 'next/server'

/**
 * Signout callback endpoint.
 * Cognito redirects here after logout, then we redirect to login page.
 */
export async function GET(request: NextRequest) {
  // Cognito redirects here after logout
  // Simply redirect to login page
  const origin = request.nextUrl.origin
  const loginUrl = new URL('/auth/login', origin)
  
  const response = NextResponse.redirect(loginUrl)
  
  // Clear any remaining cookies (in case Cognito didn't clear them)
  const cookieOptions = {
    expires: new Date(0),
    path: '/',
    httpOnly: false,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
  }
  
  const cookiesToDelete = [
    'cognito_access_token',
    'cognito_id_token',
    'cognito_refresh_token',
    'cognito_user',
    'oidc_nonce',
    'oidc_state',
    'redirect_after_login',
  ]
  
  cookiesToDelete.forEach(cookieName => {
    response.cookies.set(cookieName, '', { ...cookieOptions, expires: new Date(0) })
    response.cookies.delete(cookieName)
  })
  
  return response
}


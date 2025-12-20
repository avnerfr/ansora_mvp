import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'
  
  // Always redirect to login after clearing cookies
  // The redirect_after_login cookie (if set) will be used by the callback after login
  const redirectUrl = new URL('/auth/login', baseUrl)
  
  const response = NextResponse.redirect(redirectUrl)
  
  // Clear all auth cookies with explicit expiration in the past
  const cookieOptions = {
    expires: new Date(0), // Set to epoch time to delete
    path: '/',
    httpOnly: false,
    secure: true,
    sameSite: 'lax' as const,
  }
  
  // Clear all possible Cognito-related cookies
  const cookiesToDelete = [
    'cognito_access_token',
    'cognito_id_token',
    'cognito_refresh_token',
    'cognito_user',
    'oidc_nonce',
    'oidc_state',
    'cognito_access_token_us-east-1',
    'cognito_id_token_us-east-1',
    'cognito_refresh_token_us-east-1',
  ]
  
  cookiesToDelete.forEach(cookieName => {
    // Delete with different path options to ensure it's cleared
    response.cookies.set(cookieName, '', { ...cookieOptions, expires: new Date(0) })
    response.cookies.delete(cookieName)
  })
  
  return response
}


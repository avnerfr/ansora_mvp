import { NextRequest, NextResponse } from 'next/server'
import { clearCognitoClientCache, getCognitoLogoutUrl } from '@/lib/cognito-oidc.server'

export async function GET(request: NextRequest) {
  // Clear the cached OIDC client to force re-initialization with new config
  clearCognitoClientCache()
  
  // Get the origin from the request to construct proper redirect URL
  const origin = request.nextUrl.origin
  
  // Use signout URL that matches Cognito's allowed sign-out URLs
  // Cognito allows: http://localhost:3000/signout or https://ansora-mvp.vercel.app/signout
  const signoutUrl = new URL('/signout', origin).toString()
  
  // Cookie options for clearing
  const cookieOptions = {
    expires: new Date(0), // Set to epoch time to delete
    path: '/',
    httpOnly: false,
    secure: process.env.NODE_ENV === 'production', // Only secure in production
    sameSite: 'lax' as const,
  }
  
  // List of cookies to delete
  const cookiesToDelete = [
    'cognito_access_token',
    'cognito_id_token',
    'cognito_refresh_token',
    'cognito_user',
    'oidc_nonce',
    'oidc_state',
    'redirect_after_login',
    // Region-specific cookies (common regions)
    'cognito_access_token_us-east-1',
    'cognito_id_token_us-east-1',
    'cognito_refresh_token_us-east-1',
    'cognito_access_token_us-west-2',
    'cognito_id_token_us-west-2',
    'cognito_refresh_token_us-west-2',
    'cognito_access_token_eu-west-1',
    'cognito_id_token_eu-west-1',
    'cognito_refresh_token_eu-west-1',
  ]
  
  try {
    // Get Cognito logout URL - this will sign out from Cognito and redirect back to signout endpoint
    const cognitoLogoutUrlString = getCognitoLogoutUrl(signoutUrl)
    
    // Debug: log the constructed URL
    console.log('Cognito logout URL:', cognitoLogoutUrlString)
    
    // Parse and validate the URL before redirecting
    let logoutUrlObj: URL
    try {
      logoutUrlObj = new URL(cognitoLogoutUrlString)
    } catch (urlError) {
      console.error('Invalid logout URL format:', cognitoLogoutUrlString, urlError)
      throw new Error(`Invalid logout URL: ${cognitoLogoutUrlString}`)
    }
    
    // Validate the URL structure
    if (!logoutUrlObj.protocol || !logoutUrlObj.hostname) {
      throw new Error(`Invalid URL structure: ${logoutUrlObj.href}`)
    }
    
    // Check for common malformation issues
    if (logoutUrlObj.href.includes('https://https://') || 
        logoutUrlObj.href.includes('http://https://') ||
        logoutUrlObj.pathname.startsWith('//')) {
      throw new Error(`Malformed logout URL detected: ${logoutUrlObj.href}`)
    }
    
    // Create response that redirects to Cognito logout
    // Cognito will handle the logout and redirect back to our login page
    const response = NextResponse.redirect(logoutUrlObj)
    
    // Clear all local cookies before redirecting to Cognito
    cookiesToDelete.forEach(cookieName => {
      response.cookies.set(cookieName, '', { ...cookieOptions, expires: new Date(0) })
      response.cookies.delete(cookieName)
    })
    
    return response
  } catch (error) {
    // If Cognito logout URL construction fails, still clear cookies and redirect to login
    console.error('Error constructing Cognito logout URL:', error)
    
    const redirectUrl = new URL('/auth/login', origin)
    const response = NextResponse.redirect(redirectUrl)
    
    // Clear all cookies
    cookiesToDelete.forEach(cookieName => {
      response.cookies.set(cookieName, '', { ...cookieOptions, expires: new Date(0) })
      response.cookies.delete(cookieName)
    })
    
    return response
  }
}


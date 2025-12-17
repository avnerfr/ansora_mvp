import { NextResponse } from 'next/server'

export async function GET() {
  const clientId = process.env.COGNITO_CLIENT_ID || '2vhardprmlfa8rfe4rbm4rin3b'
  const logoutUri = process.env.COGNITO_LOGOUT_URI || 'https://ansora-mvp.vercel.app/'
  const cognitoDomain = process.env.COGNITO_DOMAIN || 'us-east-1vpboyyess.auth.us-east-1.amazoncognito.com'
  
  const logoutUrl = `https://${cognitoDomain}/logout?client_id=${clientId}&logout_uri=${encodeURIComponent(logoutUri)}`
  
  const response = NextResponse.redirect(logoutUrl)
  
  // Clear all auth cookies
  response.cookies.delete('cognito_access_token')
  response.cookies.delete('cognito_id_token')
  response.cookies.delete('cognito_refresh_token')
  response.cookies.delete('cognito_user')
  response.cookies.delete('oidc_nonce')
  response.cookies.delete('oidc_state')
  
  return response
}


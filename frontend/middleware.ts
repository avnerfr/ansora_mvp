import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value || 
                (typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null)
  
  const { pathname } = request.nextUrl

  // Public routes that don't require authentication
  const publicRoutes = ['/auth/login', '/auth/register', '/auth/forgot-password']
  const isPublicRoute = publicRoutes.some(route => pathname.startsWith(route))

  // If accessing a protected route without auth, redirect to login
  if (!isPublicRoute && !token && pathname !== '/') {
    // Note: We can't access localStorage in middleware, so we handle redirects in components
    return NextResponse.next()
  }

  // If authenticated user tries to access auth pages, redirect to home
  if (isPublicRoute && token) {
    return NextResponse.redirect(new URL('/', request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api (API routes)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!api|_next/static|_next/image|favicon.ico).*)',
  ],
}


'use client'

import { useEffect } from 'react'

export default function RegisterPage() {
  useEffect(() => {
    // Redirect to Cognito hosted UI for registration
    // Cognito handles both login and signup on the same hosted UI
    window.location.href = '/api/auth/login'
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
        <p className="mt-4 text-gray-600">Redirecting to registration...</p>
      </div>
    </div>
  )
}

import Link from 'next/link'
import { Button } from '@/components/Button'

export default function ForgotPasswordPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Forgot Password
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Password recovery feature is not yet implemented. Please contact
            support for assistance.
          </p>
        </div>
        <div className="text-center">
          <Link href="/auth/login">
            <Button variant="secondary">Back to Login</Button>
          </Link>
        </div>
      </div>
    </div>
  )
}


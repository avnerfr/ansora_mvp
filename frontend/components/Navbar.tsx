'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { logout } from '@/lib/auth'
import { Button } from './Button'

export const Navbar: React.FC = () => {
  const router = useRouter()

  const handleLogout = () => {
    logout()
  }

  return (
    <nav className="bg-white shadow-sm border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <Link href="/" className="flex items-center space-x-2">
              <img
                src="/ansora.png"
                alt="Ansora"
                className="h-10 w-auto"
              />
              <span className="text-lg font-semibold text-gray-900">
                Ansora
              </span>
            </Link>
          </div>
          <div className="flex items-center space-x-4">
            <Link
              href="/prompt-template"
              className="text-gray-700 hover:text-primary-600 px-3 py-2 rounded-md text-sm font-medium"
            >
              Prompt Template
            </Link>
            <Button variant="secondary" onClick={handleLogout}>
              Logout
            </Button>
          </div>
        </div>
      </div>
    </nav>
  )
}


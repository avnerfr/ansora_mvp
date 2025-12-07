'use client'

import { useEffect } from 'react'

export default function ChunkErrorHandler() {
  useEffect(() => {
    const handleError = (e: ErrorEvent) => {
      if (e.message && e.message.includes('ChunkLoadError')) {
        console.warn('ChunkLoadError detected, reloading page...')
        setTimeout(() => {
          window.location.reload()
        }, 1000)
      }
    }

    window.addEventListener('error', handleError)

    return () => {
      window.removeEventListener('error', handleError)
    }
  }, [])

  return null
}


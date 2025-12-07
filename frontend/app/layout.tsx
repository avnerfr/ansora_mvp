import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'
import ChunkErrorHandler from './chunk-error-handler'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Ansora - AI Marketing Assistant',
  description: 'AI-powered marketing material refinement with community insights',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <ChunkErrorHandler />
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}

'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Navbar } from '@/components/Navbar'
import { FileDropzone } from '@/components/FileDropzone'
import { TextArea } from '@/components/TextArea'
import { Button } from '@/components/Button'
import { ragAPI } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'

const USE_CASE_OPTIONS = [
  'Change & Risk Management',
  'Policy Sprawl & Ownership',
  'Visibility & Validation',
  'Hybrid & Cloud Complexity',
  'Operational Efficiency',

]

export default function HomePage() {
  const router = useRouter()
  const [selectedUseCases, setSelectedUseCases] = useState<string[]>([])
  const [contextText, setContextText] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [hasToken, setHasToken] = useState(false)
  const [assetType, setAssetType] = useState<string>('')
  const [icp, setIcp] = useState<string>('')
  const [isUploadingContextDocs, setIsUploadingContextDocs] = useState(false)

  // Check authentication only after component mounts
  useEffect(() => {
    const token = isAuthenticated()
    console.log('Auth check:', token)
    setHasToken(token)
    setAuthChecked(true)
    
    if (!token) {
      router.push('/auth/login')
    }
  }, [router])

  const handleContextFilesSelected = async (files: File[]) => {
    if (!files || files.length === 0) return

    setIsUploadingContextDocs(true)

    try {
      const response = await ragAPI.uploadContext(files)

      // Collect extracted text from the backend for each successfully processed file
      const extractedTexts: string[] = []
      response.forEach((item: any) => {
        if (item.status === 'success' && item.content_text) {
          extractedTexts.push(item.content_text)
        }
      })

      if (extractedTexts.length > 0) {
        const combined = extractedTexts.join('\n\n')
        setContextText((prev) =>
          prev && prev.trim().length > 0
            ? `${prev.trim()}\n\n${combined}`
            : combined
        )
      }
    } catch (error: any) {
      console.error('Upload error:', error)
      alert('Failed to upload files. Please try again.')
    } finally {
      setIsUploadingContextDocs(false)
    }
  }

  const handleProcess = async () => {
    // Validation
    if (!assetType.trim()) {
      alert('Please select or enter an asset type')
      return
    }

    if (!icp.trim()) {
      alert('Please select or enter an ICP')
      return
    }

    if (!contextText.trim()) {
      alert('Please provide your context')
      return
    }

    setIsProcessing(true)

    try {
      const response = await ragAPI.process(
        selectedUseCases.length > 0 ? selectedUseCases : [""],
        contextText,
        {
          assetType,
          icp,
        }
      )
      console.log('Response: ', response)
      // Open results in new tab
      const resultsUrl = `/results/${response.job_id}`
      window.open(resultsUrl, '_blank')
    } catch (error: any) {
      console.error('Processing error:', error)
      alert(
        error.response?.data?.detail ||
          'Failed to process your request. Please try again.'
      )
    } finally {
      setIsProcessing(false)
    }
  }

  if (!authChecked || !hasToken) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        <div className="space-y-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              Refine Your Marketing Materials
            </h1>
            <p className="mt-2 text-gray-600">
              Provide your context, select or enter use cases, and let AI generate
              a tailored marketing asset.
            </p>
          </div>

          {/* Section 1: Context */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <section className="bg-white rounded-lg shadow p-4 flex flex-col h-full">
              <h2 className="text-lg font-semibold text-gray-900 mb-3">
                1. Context
              </h2>
              <div className="flex-1 flex flex-col">
                <TextArea
                  label="Context"
                  rows={6}
                  value={contextText}
                  onChange={(e) => setContextText(e.target.value)}
                  placeholder="Describe the situation, pain points, or raw notes you want to turn into a marketing asset..."
                />
              </div>
            </section>

            <section className="bg-white rounded-lg shadow p-4 flex flex-col h-full">
              <h2 className="text-lg font-semibold text-gray-900 mb-3">
                Attach Context
              </h2>
              <div className="space-y-2 flex-1 flex flex-col">
                <p className="text-xs text-gray-500">
                  Upload .txt, .docx, or .pdf files and we&apos;ll append their text
                  after your context.
                </p>
                <div className="flex-1">
                  <FileDropzone
                    onFilesSelected={handleContextFilesSelected}
                    acceptedTypes={[
                      'text/plain',
                      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                      'application/pdf',
                    ]}
                  />
                </div>
                {isUploadingContextDocs && (
                  <p className="text-xs text-gray-500 mt-1">
                    Uploading and extracting text from your documents...
                  </p>
                )}
              </div>
            </section>
          </div>

          {/* Section 2: Asset Type, ICP */}
          <section className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              2. Generation Settings
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Asset Type */}
              <div>
                <label
                  htmlFor="assetType"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Asset Type
                </label>
                <input
                  id="assetType"
                  list="asset-type-options"
                  value={assetType}
                  onChange={(e) => setAssetType(e.target.value)}
                  placeholder="Select or type asset type..."
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 text-sm"
                />
                <datalist id="asset-type-options">
                  <option value="one-pager" />
                  <option value="email" />
                  <option value="landing page" />
                  <option value="blog" />
                </datalist>
              </div>

              {/* ICP */}
              <div>
                <label
                  htmlFor="icp"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  ICP / Role
                </label>
                <input
                  id="icp"
                  list="icp-options"
                  value={icp}
                  onChange={(e) => setIcp(e.target.value)}
                  placeholder="Select or type ICP..."
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 text-sm"
                />
                <datalist id="icp-options">
                  <option value="Network & Security Operations" />
                  <option value="Application & Service Delivery" />
                  <option value="CIO" />
                  <option value="CISO" />
                  <option value="Risk and Complience" />
                </datalist>
              </div>
            </div>
          </section>

          {/* Section 3: Use Cases (Multi-select with custom input) */}
          <section className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              3. Use Cases
            </h2>
            <p className="text-sm text-gray-600 mb-3">
              Add the specific use cases, scenarios, or problems this asset should speak to.
            </p>
            <input
              list="use-case-options"
              value={selectedUseCases.join(', ')}
              onChange={(e) =>
                setSelectedUseCases(
                  e.target.value
                    .split(',')
                    .map((item) => item.trim())
                    .filter(Boolean)
                )
              }
              placeholder="Select or type use cases (comma-separated)..."
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 text-sm"
            />
            <datalist id="use-case-options">
              {USE_CASE_OPTIONS.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
          </section>

          {/* Section 4: Process Button */}
          <section className="bg-white rounded-lg shadow p-6">
            <Button
              variant="primary"
              onClick={handleProcess}
              isLoading={isProcessing}
              className="w-full py-3 text-lg"
            >
              Process
            </Button>
          </section>
        </div>
      </main>
    </div>
  )
}


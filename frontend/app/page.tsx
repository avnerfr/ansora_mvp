'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Navbar } from '@/components/Navbar'
import { TextArea } from '@/components/TextArea'
import { Button } from '@/components/Button'
import { ragAPI } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'

const USE_CASE_OPTIONS = [
  'Afraid to push a network change without knowing what will break',
  'Security changes get stuck in CAB because no one can prove safety',
  'Cannot verify that network policies actually work as intended',
  'Rules accumulated over time that nobody understands or owns',
  'Afraid to remove access because the real dependencies are unknown',
  'Cloud and on-prem environments behave differently under the same policy',
  'Audits fail because policy intent cannot be proven',
]

export default function HomePage() {
  const router = useRouter()
  const [selectedOperationalPain, setSelectedOperationalPain] = useState<string>('')
  const [contextText, setContextText] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [hasToken, setHasToken] = useState(false)
  const [assetType, setAssetType] = useState<string>('')
  const [icp, setIcp] = useState<string>('')
  const [isUploadingContextDocs, setIsUploadingContextDocs] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

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

    setSelectedFiles(files)
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
      setSelectedFiles([])
    } finally {
      setIsUploadingContextDocs(false)
    }
  }

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const files = Array.from(e.target.files)
      handleContextFilesSelected(files)
    }
  }

  const handleBrowseClick = () => {
    fileInputRef.current?.click()
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

    setIsProcessing(true)

    try {
      const response = await ragAPI.process(
        selectedOperationalPain ? [selectedOperationalPain] : [""],
        contextText.trim() || "",
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
      <main className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        <div className="space-y-4">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">
              Ground your copy in real-world operational insights
            </h1>
            <p className="mt-1 text-sm text-slate-600">
              
            </p>
          </div>

          {/* Main Content: Context on left, Settings on right */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Left Column: Context */}
            <div className="lg:col-span-1 space-y-3">
              <section className="bg-gray-100 rounded-lg border border-slate-200 p-3">
                <h2 className="text-sm font-medium text-slate-900 mb-2">
                  Campaign Context (Optional)
                </h2>
                <TextArea
                  label=""
                  rows={8}
                  value={contextText}
                  onChange={(e) => setContextText(e.target.value)}
                  placeholder="Add specific notes, goals, or a unique scenario. If left blank, we’ll use global insights from the field..."
                />
              </section>

              <section className="bg-gray-200 rounded-lg border border-slate-200 p-3">
                <h2 className="text-sm font-medium text-slate-900 mb-2">
                  Reference Materials (Optional)
                </h2>
                <div className="space-y-2">
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".txt,.docx,.pdf"
                    onChange={handleFileInputChange}
                    className="hidden"
                  />
                  <button
                    type="button"
                    onClick={handleBrowseClick}
                    className="w-full px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 border border-slate-300 rounded-md hover:bg-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    BROWSE
                  </button>
                  <div className="min-h-[40px] p-2 text-xs border border-slate-200 rounded-md bg-slate-50">
                    {isUploadingContextDocs ? (
                      <p className="text-slate-500">Uploading and extracting text...</p>
                    ) : selectedFiles.length > 0 ? (
                      <div className="space-y-1">
                        {selectedFiles.map((file, index) => (
                          <p key={index} className="text-slate-700 truncate">
                            {file.name}
                          </p>
                        ))}
                      </div>
                    ) : (
                      <p className="text-slate-400">No files selected</p>
                    )}
                  </div>
                </div>
              </section>
            </div>

            {/* Right Column: Settings Group */}
            <div className="lg:col-span-2">
              <section className="bg-gray-200 rounded-lg border border-slate-100 p-3 space-y-3">
                <h2 className="text-sm font-medium text-slate-900 mb-2">
                  Settings
                </h2>
                
                {/* Asset Type */}
                <div>
                  <label
                    htmlFor="assetType"
                    className="block text-xs font-medium text-slate-700 mb-1"
                  >
                    Asset Type
                  </label>
                  <select
                    id="assetType"
                    value={assetType}
                    onChange={(e) => setAssetType(e.target.value)}
                    className="block w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-gray-100"
                  >
                    <option value="">Select</option>
                    <option value="one-pager">one-pager</option>
                    <option value="email">email</option>
                    <option value="landing page">landing page</option>
                    <option value="blog">blog</option>
                    <option value="linkedin post">linkedin post</option>
                    <option value="blog post">blog post</option>
                  </select>
                </div>

                {/* ICP */}
                <div>
                  <label
                    htmlFor="icp"
                    className="block text-xs font-medium text-slate-700 mb-1"
                  >
                    Target Audience
                  </label>
                  <select
                    id="icp"
                    value={icp}
                    onChange={(e) => setIcp(e.target.value)}
                    className="block w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-gray-100"
                  >
                    <option value="">Select</option>
                    <option value="Network & Security Operations">Network & Security Operations</option>
                    <option value="Application & Service Delivery">Application & Service Delivery</option>
                    <option value="CIO">CIO</option>
                    <option value="CISO">CISO</option>
                    <option value="Risk and Complience">Risk and Complience</option>
                  </select>
                </div>

                {/* Operational Pain */}
                <div>
                  <label
                    htmlFor="operationalPain"
                    className="block text-xs font-medium text-slate-700 mb-1"
                  >
                    Operational Pain Point
                  </label>
                  <select
                    id="operationalPain"
                    value={selectedOperationalPain}
                    onChange={(e) => setSelectedOperationalPain(e.target.value)}
                    className="block w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-gray-100"
                  >
                    <option value="">Select</option>
                    {USE_CASE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </div>
              </section>
            </div>
          </div>

          {/* Process Button */}
          <section className="bg-gray-100 rounded-lg border border-slate-200 p-3 flex justify-center">
            <Button
              variant="primary"
              onClick={handleProcess}
              isLoading={isProcessing}
              loadingText="Building Your Optimal Asset"
              className="w-fit py-2 text-sm"
            >
              CREATE ASSET
            </Button>
          </section>
        </div>
      </main>
    </div>
  )
}


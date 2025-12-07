'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Navbar } from '@/components/Navbar'
import { FileDropzone } from '@/components/FileDropzone'
import { TextArea } from '@/components/TextArea'
import { Button } from '@/components/Button'
import { documentsAPI, ragAPI } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'

const USE_CASE_OPTIONS = [
  'cybersecurity',
  'network security',
  'sysadmin',
  'Fortinet',
  'Cisco',
]

export default function HomePage() {
  const router = useRouter()
  const [selectedUseCases, setSelectedUseCases] = useState<string[]>([])
  const [contextText, setContextText] = useState('')
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<Record<string, string>>({})
  const [authChecked, setAuthChecked] = useState(false)
  const [hasToken, setHasToken] = useState(false)
  const [tone, setTone] = useState<string>('')
  const [assetType, setAssetType] = useState<string>('')
  const [icp, setIcp] = useState<string>('')

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

  // Fetch user's documents
  const { data: documents, refetch: refetchDocuments } = useQuery({
    queryKey: ['documents'],
    queryFn: documentsAPI.list,
    enabled: authChecked && hasToken,
  })

  const handleFilesSelected = async (files: File[]) => {
    setUploadStatus({})
    setIsProcessing(true)

    try {
      const response = await documentsAPI.upload(files)
      setUploadedFiles([...uploadedFiles, ...files])
      
      // Update upload status
      const statusMap: Record<string, string> = {}
      response.forEach((item: any) => {
        statusMap[item.filename] = item.status
      })
      setUploadStatus(statusMap)
      
      refetchDocuments()
    } catch (error: any) {
      console.error('Upload error:', error)
      alert('Failed to upload files. Please try again.')
    } finally {
      setIsProcessing(false)
    }
  }

  const handleProcess = async () => {
    // Validation
    if (!tone) {
      alert('Please select a tone')
      return
    }

    if (!assetType.trim()) {
      alert('Please select or enter an asset type')
      return
    }

    if (!icp.trim()) {
      alert('Please select or enter an ICP')
      return
    }

    if (selectedUseCases.length === 0) {
      alert('Please select or enter at least one use case')
      return
    }

    if (!contextText.trim()) {
      alert('Please provide your context')
      return
    }

    setIsProcessing(true)

    try {
      const response = await ragAPI.process(
        selectedUseCases,
        contextText,
        {
          tone,
          assetType,
          icp,
        }
      )
      console.log('Response: ', response)
      // Open results in new tab
      const resultsUrl = `/results/${response.job_id}`
      window.open(resultsUrl, '_blank')
      
      // Reset form
      setContextText('')
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

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
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

          {/* Section 1: Your Request and Upload Documents (Side by Side) */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Your Request - Takes 2 columns */}
            <section className="bg-white rounded-lg shadow p-6 lg:col-span-2">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">
                1. Context
              </h2>
              <TextArea
                label="Context"
                rows={10}
                value={contextText}
                onChange={(e) => setContextText(e.target.value)}
                placeholder="Describe the situation, pain points, or raw notes you want to turn into a marketing asset..."
              />
            </section>

            {/* Upload Documents - Takes 1 column */}
            <section className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">
                Upload Documents
              </h2>
              <p className="text-xs text-gray-500 mb-3">(Optional)</p>
              <FileDropzone onFilesSelected={handleFilesSelected} />
              
              {uploadedFiles.length > 0 && (
                <div className="mt-4 space-y-2">
                  <h3 className="text-sm font-medium text-gray-700">
                    Recently uploaded:
                  </h3>
                  {uploadedFiles.map((file, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-2 bg-gray-50 rounded"
                    >
                      <span className="text-sm text-gray-700 truncate">{file.name}</span>
                      <span className="text-xs text-gray-500 ml-2 whitespace-nowrap">
                        {formatFileSize(file.size)}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {documents && documents.length > 0 && (
                <div className="mt-4 space-y-2">
                  <h3 className="text-sm font-medium text-gray-700">
                    Your documents:
                  </h3>
                  {documents.map((doc: any) => (
                    <div
                      key={doc.id}
                      className="flex flex-col p-2 bg-gray-50 rounded"
                    >
                      <span className="text-sm text-gray-700 truncate">{doc.filename}</span>
                      <span className="text-xs text-gray-500 mt-1">
                        {formatFileSize(doc.file_size)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          {/* Section 2: Tone, Asset Type, ICP */}
          <section className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              2. Generation Settings
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Tone */}
              <div>
                <label
                  htmlFor="tone"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Tone
                </label>
                <select
                  id="tone"
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 text-sm"
                >
                  <option value="">Select tone...</option>
                  <option value="manager">Manager</option>
                  <option value="technical">Technical</option>
                </select>
              </div>

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


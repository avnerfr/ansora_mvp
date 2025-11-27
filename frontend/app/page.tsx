'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Navbar } from '@/components/Navbar'
import { MultiSelect } from '@/components/MultiSelect'
import { FileDropzone } from '@/components/FileDropzone'
import { TextArea } from '@/components/TextArea'
import { Button } from '@/components/Button'
import { documentsAPI, ragAPI } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'

const TOPIC_OPTIONS = [
  'cybersecurity',
  'network security',
  'marketing',
  'data analytics',
  'SaaS',
]

export default function HomePage() {
  const router = useRouter()
  const [selectedTopics, setSelectedTopics] = useState<string[]>([])
  const [marketingText, setMarketingText] = useState('')
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<Record<string, string>>({})
  const [authChecked, setAuthChecked] = useState(false)
  const [hasToken, setHasToken] = useState(false)

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
    if (selectedTopics.length === 0) {
      alert('Please select at least one topic')
      return
    }

    if (!marketingText.trim()) {
      alert('Please provide your request text')
      return
    }

    setIsProcessing(true)

    try {
      const response = await ragAPI.process(
        selectedTopics,
        marketingText
      )
      console.log('Response: ', response)
      // Open results in new tab
      const resultsUrl = `/results/${response.job_id}`
      window.open(resultsUrl, '_blank')
      
      // Reset form
      setMarketingText('')
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
              Provide your request, select topics, and let AI enhance your
              marketing content.
            </p>
          </div>

          {/* Section 1: Your Request and Upload Documents (Side by Side) */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Your Request - Takes 2 columns */}
            <section className="bg-white rounded-lg shadow p-6 lg:col-span-2">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">
                1. Your Request
              </h2>
              <TextArea
                label=""
                rows={10}
                value={marketingText}
                onChange={(e) => setMarketingText(e.target.value)}
                placeholder="Paste or write your marketing material here..."
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

          {/* Section 2: Topics (MultiSelect Dropdown) */}
          <section className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              2. Topics
            </h2>
            <MultiSelect
              options={TOPIC_OPTIONS}
              selected={selectedTopics}
              onChange={setSelectedTopics}
              label=""
              placeholder="Select topics..."
            />
          </section>

          {/* Section 3: Process Button */}
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


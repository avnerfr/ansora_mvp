'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Navbar } from '@/components/Navbar'
import { Button } from '@/components/Button'
import { isAdmin, isAuthenticated } from '@/lib/auth'
import { maintenanceAPI } from '@/lib/api'

type TabType = 'vectordb' | 'upsert' | 'modeltest' | 'prompts'

export default function MaintenancePage() {
  const router = useRouter()
  const [activeTab, setActiveTab] = useState<TabType>('vectordb')
  const [authChecked, setAuthChecked] = useState(false)

  // Vector DB state
  const [collections, setCollections] = useState<string[]>([])
  const [selectedCollection, setSelectedCollection] = useState('')
  const [recordCount, setRecordCount] = useState(10)
  const [records, setRecords] = useState<any[]>([])
  const [loadingCollections, setLoadingCollections] = useState(false)
  const [loadingRecords, setLoadingRecords] = useState(false)
  const [collectionStats, setCollectionStats] = useState<{total_points: number, doc_type_counts: Record<string, number>} | null>(null)
  const [loadingStats, setLoadingStats] = useState(false)
  const [selectedDocType, setSelectedDocType] = useState<string>('')
  
  // Query Collection state
  const [queryTerm, setQueryTerm] = useState<string>('')
  const [queryingCollection, setQueryingCollection] = useState(false)
  const [queryResults, setQueryResults] = useState<any[]>([])

  // Create Collection Dialog state
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [newCollectionName, setNewCollectionName] = useState('')
  const [newVectorSize, setNewVectorSize] = useState(1536)
  const [newDistance, setNewDistance] = useState('Cosine')
  const [creatingCollection, setCreatingCollection] = useState(false)
  const [createMessage, setCreateMessage] = useState('')
  
  // Delete Collection Dialog state
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [deletingCollection, setDeletingCollection] = useState(false)
  const [deleteMessage, setDeleteMessage] = useState('')

  // Upsert state
  const [upsertType, setUpsertType] = useState<'reddit' | 'podcast' | 'youtube'>('reddit')
  const [upsertCollection, setUpsertCollection] = useState('')
  const [podcastFormat, setPodcastFormat] = useState('default')
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [uploadMessage, setUploadMessage] = useState('')

  // Model Test state
  const [vendor, setVendor] = useState<string>('')
  const [availableModels, setAvailableModels] = useState<Array<{id: string, display_name?: string, cost: string, url?: string}>>([])
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [selectedModelUrl, setSelectedModelUrl] = useState<string>('')
  const [systemPrompt, setSystemPrompt] = useState<string>('')
  const [prompt, setPrompt] = useState<string>('')
  const [placeholders, setPlaceholders] = useState<Array<{key: string, text: string, file?: File}>>([{key: '', text: ''}])
  const [processing, setProcessing] = useState(false)
  const [answer, setAnswer] = useState<string>('')

  // Prompts state
  const [templateNames, setTemplateNames] = useState<string[]>([])
  const [selectedTemplateName, setSelectedTemplateName] = useState<string>('')
  const [editors, setEditors] = useState<string[]>([])
  const [selectedEditor, setSelectedEditor] = useState<string>('')
  const [versions, setVersions] = useState<Array<{edited_at_iso: number, edited_by_sub: string, edit_comment: string}>>([])
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [templateBody, setTemplateBody] = useState<string>('')
  const [editComment, setEditComment] = useState<string>('')
  const [loadingTemplate, setLoadingTemplate] = useState(false)
  const [updatingTemplate, setUpdatingTemplate] = useState(false)
  const [promptMessage, setPromptMessage] = useState<string>('')

  useEffect(() => {
    if (!isAuthenticated()) {
      // Store intended destination in cookie before redirecting
      if (typeof window !== 'undefined') {
        document.cookie = `redirect_after_login=/maintenance; path=/; max-age=300` // 5 minutes
      }
      router.push('/auth/login')
      return
    }
    if (!isAdmin()) {
      router.push('/')
      return
    }
    setAuthChecked(true)
    loadCollections()
  }, [router])

  const loadCollections = async () => {
    setLoadingCollections(true)
    try {
      const data = await maintenanceAPI.getCollections()
      setCollections(data.collections || [])
      if (data.collections?.length > 0) {
        setSelectedCollection(data.collections[0])
      }
    } catch (error) {
      console.error('Failed to load collections:', error)
    } finally {
      setLoadingCollections(false)
    }
  }

  const loadCollectionStats = async (collection: string) => {
    if (!collection) return
    setLoadingStats(true)
    setCollectionStats(null)
    setSelectedDocType('')
    try {
      const data = await maintenanceAPI.getCollectionStats(collection)
      setCollectionStats(data)
    } catch (error) {
      console.error('Failed to load collection stats:', error)
    } finally {
      setLoadingStats(false)
    }
  }

  useEffect(() => {
    if (selectedCollection) {
      loadCollectionStats(selectedCollection)
    }
  }, [selectedCollection])

  const fetchRecords = async () => {
    if (!selectedCollection) return
    setLoadingRecords(true)
    setRecords([])
    try {
      const data = await maintenanceAPI.getRecords(
        selectedCollection, 
        recordCount, 
        selectedDocType || undefined
      )
      setRecords(data.records || [])
    } catch (error) {
      console.error('Failed to fetch records:', error)
    } finally {
      setLoadingRecords(false)
    }
  }

  const queryCollection = async () => {
    if (!selectedCollection || !queryTerm.trim()) {
      return
    }
    setQueryingCollection(true)
    setQueryResults([])
    try {
      const data = await maintenanceAPI.queryCollection(
        selectedCollection, 
        queryTerm, 
        selectedDocType || undefined, 
        recordCount
      )
      setQueryResults(data.results || [])
    } catch (error) {
      console.error('Failed to query collection:', error)
      setQueryResults([])
    } finally {
      setQueryingCollection(false)
    }
  }

  const handleCreateCollection = async () => {
    if (!newCollectionName.trim()) {
      setCreateMessage('✗ Collection name is required')
      return
    }
    setCreatingCollection(true)
    setCreateMessage('')
    try {
      await maintenanceAPI.createCollection(newCollectionName, newVectorSize, newDistance)
      setCreateMessage(`✓ Collection '${newCollectionName}' created successfully`)
      setNewCollectionName('')
      setNewVectorSize(1536)
      setNewDistance('Cosine')
      // Reload collections list
      await loadCollections()
      // Select the newly created collection
      setSelectedCollection(newCollectionName)
      // Close dialog after a short delay
      setTimeout(() => {
        setShowCreateDialog(false)
        setCreateMessage('')
      }, 1500)
    } catch (error: any) {
      setCreateMessage(`✗ Error: ${error.response?.data?.detail || error.message || 'Failed to create collection'}`)
    } finally {
      setCreatingCollection(false)
    }
  }

  const handleDeleteCollection = async () => {
    if (!selectedCollection) return
    setDeletingCollection(true)
    setDeleteMessage('')
    try {
      await maintenanceAPI.deleteCollection(selectedCollection)
      setDeleteMessage(`✓ Collection '${selectedCollection}' deleted successfully`)
      // Clear selection and reload collections
      setSelectedCollection('')
      setCollectionStats(null)
      setRecords([])
      await loadCollections()
      // Close dialog after a short delay
      setTimeout(() => {
        setShowDeleteDialog(false)
        setDeleteMessage('')
      }, 1500)
    } catch (error: any) {
      setDeleteMessage(`✗ Error: ${error.response?.data?.detail || error.message || 'Failed to delete collection'}`)
    } finally {
      setDeletingCollection(false)
    }
  }

  const handleFilesDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const files = Array.from(e.dataTransfer.files)
    setUploadFiles(prev => [...prev, ...files])
  }, [])

  const handleFilesSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files)
      setUploadFiles(prev => [...prev, ...files])
    }
  }

  const removeFile = (index: number) => {
    setUploadFiles(prev => prev.filter((_, i) => i !== index))
  }

  const handleUpsert = async () => {
    if (uploadFiles.length === 0) return
    if (!upsertCollection) {
      setUploadMessage('✗ Please select a target collection')
      return
    }
    setUploading(true)
    setUploadMessage('')
    try {
      const result = await maintenanceAPI.upsertData(
        upsertType,
        uploadFiles,
        upsertCollection,
        upsertType === 'podcast' ? podcastFormat : undefined
      )
      setUploadMessage(`✓ Successfully upserted ${result.count} records to ${upsertCollection} at ${new Date().toLocaleString()}`)
      setUploadFiles([])
    } catch (error: any) {
      setUploadMessage(`✗ Error: ${error.message || 'Upload failed'}`)
    } finally {
      setUploading(false)
    }
  }

  // Model Test handlers
  const handleVendorChange = async (newVendor: string) => {
    setVendor(newVendor)
    setSelectedModel('')
    setSelectedModelUrl('')
    setAvailableModels([])
    if (newVendor) {
      try {
        const data = await maintenanceAPI.getModels(newVendor)
        setAvailableModels(data.models || [])
      } catch (error) {
        console.error('Failed to load models:', error)
      }
    }
  }

  const handleModelChange = (newModel: string) => {
    setSelectedModel(newModel)
    // Find the URL for the selected model
    const model = availableModels.find(m => m.id === newModel)
    setSelectedModelUrl(model?.url || '')
  }

  const addPlaceholder = () => {
    setPlaceholders([...placeholders, {key: '', text: ''}])
  }

  const removePlaceholder = (index: number) => {
    setPlaceholders(placeholders.filter((_, i) => i !== index))
  }

  const updatePlaceholder = (index: number, field: 'key' | 'text', value: string) => {
    const updated = [...placeholders]
    updated[index] = { ...updated[index], [field]: value }
    setPlaceholders(updated)
  }

  const handlePlaceholderFile = async (index: number, file: File) => {
    const text = await file.text()
    updatePlaceholder(index, 'text', text)
  }

  const handleProcess = async () => {
    if (!vendor || !selectedModel || !prompt) {
      return
    }
    
    setProcessing(true)
    try {
      // Build placeholders object (only include entries with keys)
      const placeholdersObj: Record<string, string> = {}
      placeholders.forEach(p => {
        if (p.key.trim()) {
          placeholdersObj[p.key.trim()] = p.text
        }
      })

      const result = await maintenanceAPI.testModel(
        vendor,
        selectedModel,
        systemPrompt || undefined,
        prompt,
        placeholdersObj
      )
      
      // Only update the answer, nothing else
      setAnswer(result.answer || '')
    } catch (error: any) {
      setAnswer(`Error: ${error.response?.data?.detail || error.message || 'Failed to process'}`)
    } finally {
      setProcessing(false)
    }
  }

  // Prompts handlers
  const loadTemplateNames = async () => {
    try {
      const data = await maintenanceAPI.getTemplateNames()
      setTemplateNames(data.template_names || [])
      if (data.template_names?.length > 0) {
        setSelectedTemplateName(data.template_names[0])
      }
    } catch (error) {
      console.error('Failed to load template names:', error)
    }
  }

  const loadEditors = async (templateName: string) => {
    if (!templateName) return
    try {
      const data = await maintenanceAPI.getEditors(templateName)
      setEditors(data.editors || [])
      setSelectedEditor('')
    } catch (error) {
      console.error('Failed to load editors:', error)
    }
  }

  const loadVersions = async (templateName: string, editedBy?: string) => {
    if (!templateName) return
    try {
      const data = await maintenanceAPI.getTemplateVersions(templateName, editedBy)
      setVersions(data.versions || [])
      if (data.versions?.length > 0) {
        setSelectedVersion(data.versions[0].edited_at_iso)
      } else {
        setSelectedVersion(null)
      }
    } catch (error) {
      console.error('Failed to load versions:', error)
    }
  }

  const loadTemplate = async (templateName: string, editedAtIso: number) => {
    if (!templateName || !editedAtIso) return
    setLoadingTemplate(true)
    try {
      const data = await maintenanceAPI.getTemplate(templateName, editedAtIso)
      setTemplateBody(data.template_body || '')
      setEditComment(data.edit_comment || '')
    } catch (error: any) {
      setPromptMessage(`✗ Error: ${error.response?.data?.detail || error.message || 'Failed to load template'}`)
    } finally {
      setLoadingTemplate(false)
    }
  }

  const handleUpdateTemplate = async () => {
    if (!selectedTemplateName || !templateBody) {
      setPromptMessage('✗ Template name and body are required')
      return
    }
    setUpdatingTemplate(true)
    setPromptMessage('')
    try {
      await maintenanceAPI.updateTemplate(selectedTemplateName, templateBody, editComment)
      setPromptMessage(`✓ Template '${selectedTemplateName}' updated successfully`)
      // Reload versions and select the new one
      await loadVersions(selectedTemplateName, selectedEditor || undefined)
    } catch (error: any) {
      setPromptMessage(`✗ Error: ${error.response?.data?.detail || error.message || 'Failed to update template'}`)
    } finally {
      setUpdatingTemplate(false)
    }
  }

  // Load template names when switching to prompts tab
  useEffect(() => {
    if (activeTab === 'prompts' && templateNames.length === 0) {
      loadTemplateNames()
    }
  }, [activeTab])

  // Load editors when template name changes
  useEffect(() => {
    if (selectedTemplateName) {
      loadEditors(selectedTemplateName)
      loadVersions(selectedTemplateName)
    }
  }, [selectedTemplateName])

  // Load versions when editor filter changes
  useEffect(() => {
    if (selectedTemplateName && selectedEditor) {
      loadVersions(selectedTemplateName, selectedEditor)
    }
  }, [selectedEditor])

  // Load template when version changes
  useEffect(() => {
    if (selectedTemplateName && selectedVersion) {
      loadTemplate(selectedTemplateName, selectedVersion)
    }
  }, [selectedVersion])

  if (!authChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Admin Maintenance</h1>
          <p className="text-gray-600">Manage Vector DB and data ingestion</p>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 mb-6">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('vectordb')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'vectordb'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Vector DB
            </button>
            <button
              onClick={() => setActiveTab('upsert')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'upsert'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Upsert Data
            </button>
            <button
              onClick={() => setActiveTab('modeltest')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'modeltest'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Model Test
            </button>
            <button
              onClick={() => setActiveTab('prompts')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'prompts'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Prompts
            </button>
          </nav>
        </div>

        {/* Vector DB Tab */}
        {activeTab === 'vectordb' && (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="space-y-6">
              {/* Collection Selector */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Select Collection
                </label>
                <div className="flex space-x-4">
                  <select
                    value={selectedCollection}
                    onChange={(e) => setSelectedCollection(e.target.value)}
                    disabled={loadingCollections}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                  >
                    {collections.length === 0 ? (
                      <option value="">No collections found</option>
                    ) : (
                      collections.map((col) => (
                        <option key={col} value={col}>{col}</option>
                      ))
                    )}
                  </select>
                  <Button 
                    onClick={() => setShowDeleteDialog(true)} 
                    variant="secondary"
                    disabled={!selectedCollection}
                    className="text-red-600 hover:text-red-700 border-red-300 hover:border-red-400"
                  >
                    Delete Collection
                  </Button>
                  <Button onClick={() => setShowCreateDialog(true)} variant="primary">
                    Create Collection
                  </Button>
                  <Button onClick={loadCollections} variant="secondary" isLoading={loadingCollections}>
                    Refresh
                  </Button>
                </div>
              </div>

              {/* Collection Stats */}
              {loadingStats && (
                <div className="text-sm text-gray-500">Loading collection stats...</div>
              )}
              {collectionStats && (
                <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <h4 className="text-sm font-medium text-gray-700 mb-3">
                    Collection Stats ({collectionStats.total_points} total points)
                  </h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {Object.entries(collectionStats.doc_type_counts).map(([docType, count]) => (
                      <div key={docType} className="bg-white rounded p-3 border border-gray-200">
                        <div className="text-xs text-gray-500 uppercase">{docType}</div>
                        <div className="text-lg font-semibold text-gray-900">{count}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Doc Type Filter */}
              {collectionStats && Object.keys(collectionStats.doc_type_counts).length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Filter by doc_type
                  </label>
                  <select
                    value={selectedDocType}
                    onChange={(e) => setSelectedDocType(e.target.value)}
                    className="w-64 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                  >
                    <option value="">All doc_types</option>
                    {Object.keys(collectionStats.doc_type_counts).map((docType) => (
                      <option key={docType} value={docType}>{docType}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Record Count */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Number of Records to Retrieve
                </label>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={recordCount}
                  onChange={(e) => setRecordCount(parseInt(e.target.value) || 10)}
                  className="w-32 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                />
              </div>

              {/* Fetch Button */}
              <Button onClick={fetchRecords} variant="primary" isLoading={loadingRecords}>
                Retrieve Records
              </Button>

              {/* Query Collection Section */}
              <div className="border-t border-gray-200 pt-6 mt-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">
                  Query Collection
                </h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Search Term
                    </label>
                    <input
                      type="text"
                      value={queryTerm}
                      onChange={(e) => setQueryTerm(e.target.value)}
                      placeholder="Enter search query..."
                      className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                      onKeyPress={(e) => {
                        if (e.key === 'Enter' && !queryingCollection) {
                          queryCollection()
                        }
                      }}
                    />
                  </div>
                  <Button 
                    onClick={queryCollection} 
                    variant="primary" 
                    isLoading={queryingCollection}
                    disabled={!selectedCollection || !queryTerm.trim()}
                  >
                    Query Collection
                  </Button>
                </div>

                {/* Query Results Display */}
                {queryResults.length > 0 && (
                  <div className="mt-6">
                    <h4 className="text-md font-medium text-gray-900 mb-4">
                      Query Results ({queryResults.length})
                    </h4>
                    <div className="space-y-4 max-h-96 overflow-y-auto">
                      {queryResults.map((result, index) => (
                        <div key={index} className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                          <div className="text-xs text-blue-600 font-semibold mb-2">
                            Score: {result.score?.toFixed(4)} | ID: {result.id}
                          </div>
                          <pre className="text-sm text-gray-700 whitespace-pre-wrap overflow-x-auto">
                            {JSON.stringify(result, null, 2)}
                          </pre>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {queryingCollection === false && queryResults.length === 0 && queryTerm && (
                  <div className="mt-4 text-sm text-gray-500">
                    No results found for "{queryTerm}"
                  </div>
                )}
              </div>

              {/* Records Display */}
              {records.length > 0 && (
                <div className="mt-6">
                  <h3 className="text-lg font-medium text-gray-900 mb-4">
                    Retrieved Records ({records.length})
                  </h3>
                  <div className="space-y-4 max-h-96 overflow-y-auto">
                    {records.map((record, index) => (
                      <div key={index} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                        <div className="text-xs text-gray-500 mb-2">ID: {record.id}</div>
                        <pre className="text-sm text-gray-700 whitespace-pre-wrap overflow-x-auto">
                          {JSON.stringify(record.metadata, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Upsert Data Tab */}
        {activeTab === 'upsert' && (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="space-y-6">
              {/* Collection Selector */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Target Collection
                </label>
                <select
                  value={upsertCollection}
                  onChange={(e) => setUpsertCollection(e.target.value)}
                  className="w-64 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                >
                  <option value="">Select a collection</option>
                  {collections.map((col) => (
                    <option key={col} value={col}>{col}</option>
                  ))}
                </select>
              </div>

              {/* Data Type Selector */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Data Type
                </label>
                <div className="flex space-x-4">
                  {(['reddit', 'podcast', 'youtube'] as const).map((type) => (
                    <button
                      key={type}
                      onClick={() => {
                        setUpsertType(type)
                        setUploadFiles([])
                        setUploadMessage('')
                      }}
                      className={`px-4 py-2 rounded-md text-sm font-medium ${
                        upsertType === type
                          ? 'bg-primary-600 text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {type === 'reddit' && 'Reddit Posts'}
                      {type === 'podcast' && 'Podcast Transcript'}
                      {type === 'youtube' && 'YouTube Transcript'}
                    </button>
                  ))}
                </div>
              </div>

              {/* Podcast Format (only for podcast) */}
              {upsertType === 'podcast' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Podcast Format
                  </label>
                  <select
                    value={podcastFormat}
                    onChange={(e) => setPodcastFormat(e.target.value)}
                    className="w-64 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                  >
                    <option value="default">Default</option>
                    <option value="spotify">Spotify</option>
                    <option value="apple">Apple Podcasts</option>
                    <option value="rss">RSS Feed</option>
                  </select>
                </div>
              )}

              {/* File Drop Zone */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {upsertType === 'reddit' ? 'Upload Comments Files' : 'Upload Files'}
                </label>
                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleFilesDrop}
                  className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-primary-400 transition-colors"
                >
                  <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <p className="mt-2 text-sm text-gray-600">
                    Drag and drop files here, or{' '}
                    <label className="text-primary-600 hover:text-primary-500 cursor-pointer">
                      browse
                      <input
                        type="file"
                        multiple
                        onChange={handleFilesSelect}
                        className="hidden"
                        accept={upsertType === 'reddit' ? '.json' : '.json,.csv,.txt'}
                      />
                    </label>
                  </p>
                  <p className="mt-1 text-xs text-gray-500">
                    {upsertType === 'reddit' ? 'JSON files only' : 'JSON, CSV, or TXT files'}
                  </p>
                </div>
              </div>

              {/* Selected Files */}
              {uploadFiles.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-700 mb-2">
                    Selected Files ({uploadFiles.length})
                  </h4>
                  <ul className="space-y-2">
                    {uploadFiles.map((file, index) => (
                      <li key={index} className="flex items-center justify-between bg-gray-50 px-3 py-2 rounded">
                        <span className="text-sm text-gray-700">{file.name}</span>
                        <button
                          onClick={() => removeFile(index)}
                          className="text-red-500 hover:text-red-700"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Upsert Button */}
              <Button
                onClick={handleUpsert}
                variant="primary"
                isLoading={uploading}
                disabled={uploadFiles.length === 0}
              >
                Upsert {upsertType === 'reddit' ? 'Reddit Posts' : upsertType === 'podcast' ? 'Podcast Transcript' : 'YouTube Transcript'}
              </Button>

              {/* Upload Message */}
              {uploadMessage && (
                <div className={`p-4 rounded-md ${
                  uploadMessage.startsWith('✓') ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                }`}>
                  {uploadMessage}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Create Collection Dialog */}
        {showCreateDialog && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-xl font-bold text-gray-900">Create New Collection</h2>
                <button
                  onClick={() => {
                    setShowCreateDialog(false)
                    setCreateMessage('')
                    setNewCollectionName('')
                    setNewVectorSize(1536)
                    setNewDistance('Cosine')
                  }}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="space-y-4">
                {/* Collection Name */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Collection Name *
                  </label>
                  <input
                    type="text"
                    value={newCollectionName}
                    onChange={(e) => setNewCollectionName(e.target.value)}
                    placeholder="e.g., my_collection"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                  />
                </div>

                {/* Vector Size */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Vector Size
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="10000"
                    value={newVectorSize}
                    onChange={(e) => setNewVectorSize(parseInt(e.target.value) || 1536)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    Default: 1536 (for OpenAI text-embedding-3-small)
                  </p>
                </div>

                {/* Distance Metric */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Distance Metric
                  </label>
                  <select
                    value={newDistance}
                    onChange={(e) => setNewDistance(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                  >
                    <option value="Cosine">Cosine</option>
                    <option value="Euclidean">Euclidean</option>
                    <option value="Dot">Dot</option>
                  </select>
                </div>

                {/* Message */}
                {createMessage && (
                  <div className={`p-3 rounded-md text-sm ${
                    createMessage.startsWith('✓') ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                  }`}>
                    {createMessage}
                  </div>
                )}

                {/* Actions */}
                <div className="flex space-x-3 pt-4">
                  <Button
                    onClick={handleCreateCollection}
                    variant="primary"
                    isLoading={creatingCollection}
                    className="flex-1"
                  >
                    Create
                  </Button>
                  <Button
                    onClick={() => {
                      setShowCreateDialog(false)
                      setCreateMessage('')
                      setNewCollectionName('')
                      setNewVectorSize(1536)
                      setNewDistance('Cosine')
                    }}
                    variant="secondary"
                    className="flex-1"
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Model Test Tab */}
        {activeTab === 'modeltest' && (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="space-y-6">
              {/* Vendor Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Vendor
                </label>
                <div className="flex items-center gap-4">
                  <select
                    value={vendor}
                    onChange={(e) => handleVendorChange(e.target.value)}
                    className="w-64 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                  >
                    <option value="">Select a vendor</option>
                    <option value="deepinfra">DeepInfra</option>
                    <option value="openai">OpenAI</option>
                    <option value="openrouter">OpenRouter</option>
                    <option value="groq">Groq</option>
                  </select>
                  {vendor === 'deepinfra' && (
                    <a
                      href="https://deepinfra.com/models"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary-600 hover:text-primary-700 underline text-sm"
                    >
                      View Models
                    </a>
                  )}
                  {vendor === 'openai' && (
                    <a
                      href="https://platform.openai.com/docs/models/compare"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary-600 hover:text-primary-700 underline text-sm"
                    >
                      View Models
                    </a>
                  )}
                </div>
              </div>

              {/* Model Selection */}
              {vendor && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Model
                  </label>
                  <div className="flex items-center gap-4">
                    <select
                      value={selectedModel}
                      onChange={(e) => handleModelChange(e.target.value)}
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                    >
                      <option value="">Select a model</option>
                      {availableModels.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.display_name || model.id} - {model.cost}
                        </option>
                      ))}
                    </select>
                    {selectedModelUrl && (
                      <a
                        href={selectedModelUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary-600 hover:text-primary-700 underline text-sm whitespace-nowrap"
                      >
                        View Model Details
                      </a>
                    )}
                  </div>
                </div>
              )}

              {/* System Prompt */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  System Prompt <span className="text-gray-500 text-xs font-normal">(optional)</span>
                </label>
                <textarea
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  rows={6}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 font-mono text-sm"
                  placeholder="Enter system prompt here (optional)..."
                />
              </div>

              {/* Prompt */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Prompt
                </label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={6}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 font-mono text-sm"
                  placeholder="Enter prompt here..."
                />
              </div>

              {/* Placeholders Table */}
              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="block text-sm font-medium text-gray-700">
                    Placeholders
                  </label>
                  <Button onClick={addPlaceholder} variant="secondary" className="text-sm">
                    Add Placeholder
                  </Button>
                </div>
                <div className="border border-gray-300 rounded-md overflow-hidden">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Key</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Text</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">File</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {placeholders.map((placeholder, index) => (
                        <tr key={index}>
                          <td className="px-4 py-3">
                            <input
                              type="text"
                              value={placeholder.key}
                              onChange={(e) => updatePlaceholder(index, 'key', e.target.value)}
                              placeholder="e.g., {key}"
                              className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                            />
                          </td>
                          <td className="px-4 py-3">
                            <textarea
                              value={placeholder.text}
                              onChange={(e) => updatePlaceholder(index, 'text', e.target.value)}
                              rows={2}
                              placeholder="Paste text or upload file"
                              className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                            />
                          </td>
                          <td className="px-4 py-3">
                            <input
                              type="file"
                              onChange={(e) => {
                                const file = e.target.files?.[0]
                                if (file) {
                                  handlePlaceholderFile(index, file)
                                }
                              }}
                              className="text-sm"
                            />
                          </td>
                          <td className="px-4 py-3">
                            {placeholders.length > 1 && (
                              <button
                                onClick={() => removePlaceholder(index)}
                                className="text-red-500 hover:text-red-700"
                              >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Process Button */}
              <Button
                onClick={handleProcess}
                variant="primary"
                isLoading={processing}
                disabled={!vendor || !selectedModel || !systemPrompt || !prompt}
              >
                Process
              </Button>

              {/* Answer Display */}
              {answer && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Answer from Model
                  </label>
                  <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                    <pre className="whitespace-pre-wrap text-sm text-gray-700 font-mono">
                      {answer}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Prompts Tab */}
        {activeTab === 'prompts' && (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="space-y-6">
              {/* Template Name Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Template Name
                </label>
                <select
                  value={selectedTemplateName}
                  onChange={(e) => {
                    setSelectedTemplateName(e.target.value)
                    setSelectedEditor('')
                    setTemplateBody('')
                    setEditComment('')
                    setPromptMessage('')
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                >
                  <option value="">Select a template</option>
                  {templateNames.map((name) => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
              </div>

              {/* Editor Filter (optional) */}
              {selectedTemplateName && editors.length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Filter by Editor <span className="text-gray-500 text-xs font-normal">(optional)</span>
                  </label>
                  <select
                    value={selectedEditor}
                    onChange={(e) => setSelectedEditor(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                  >
                    <option value="">All editors</option>
                    {editors.map((editor) => (
                      <option key={editor} value={editor}>{editor}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Version Selection */}
              {selectedTemplateName && versions.length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Version (Edited Date - newest first)
                  </label>
                  <select
                    value={selectedVersion || ''}
                    onChange={(e) => setSelectedVersion(parseInt(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                  >
                    <option value="">Select a version</option>
                    {versions.map((version) => (
                      <option key={version.edited_at_iso} value={version.edited_at_iso}>
                        {new Date(version.edited_at_iso * 1000).toLocaleString()} - {version.edited_by_sub}
                        {version.edit_comment && ` - ${version.edit_comment}`}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Edit Comment */}
              {selectedTemplateName && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Edit Comment <span className="text-gray-500 text-xs font-normal">(optional)</span>
                  </label>
                  <input
                    type="text"
                    value={editComment}
                    onChange={(e) => setEditComment(e.target.value)}
                    placeholder="Brief description of changes..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                  />
                </div>
              )}

              {/* Template Body Editor */}
              {selectedTemplateName && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Template Body
                  </label>
                  {loadingTemplate ? (
                    <div className="text-sm text-gray-500">Loading template...</div>
                  ) : (
                    <textarea
                      value={templateBody}
                      onChange={(e) => setTemplateBody(e.target.value)}
                      rows={20}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 font-mono text-sm"
                      placeholder="Template content will appear here..."
                    />
                  )}
                </div>
              )}

              {/* Update Button */}
              {selectedTemplateName && templateBody && (
                <Button
                  onClick={handleUpdateTemplate}
                  variant="primary"
                  isLoading={updatingTemplate}
                >
                  Update Template
                </Button>
              )}

              {/* Message */}
              {promptMessage && (
                <div className={`p-4 rounded-md ${
                  promptMessage.startsWith('✓') ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                }`}>
                  {promptMessage}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Delete Collection Confirmation Dialog */}
        {showDeleteDialog && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-xl font-bold text-gray-900">Delete Collection</h2>
                <button
                  onClick={() => {
                    setShowDeleteDialog(false)
                    setDeleteMessage('')
                  }}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="space-y-4">
                {/* Warning Message */}
                <div className="bg-red-50 border border-red-200 rounded-md p-4">
                  <div className="flex">
                    <svg className="w-5 h-5 text-red-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <div>
                      <h3 className="text-sm font-medium text-red-800">Are you sure?</h3>
                      <p className="mt-1 text-sm text-red-700">
                        This will permanently delete the collection <strong>"{selectedCollection}"</strong> and all its data.
                        This action cannot be undone.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Message */}
                {deleteMessage && (
                  <div className={`p-3 rounded-md text-sm ${
                    deleteMessage.startsWith('✓') ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                  }`}>
                    {deleteMessage}
                  </div>
                )}

                {/* Actions */}
                <div className="flex space-x-3 pt-4">
                  <Button
                    onClick={handleDeleteCollection}
                    variant="primary"
                    isLoading={deletingCollection}
                    disabled={deletingCollection}
                    className="flex-1 bg-red-600 hover:bg-red-700"
                  >
                    Delete
                  </Button>
                  <Button
                    onClick={() => {
                      setShowDeleteDialog(false)
                      setDeleteMessage('')
                    }}
                    variant="secondary"
                    disabled={deletingCollection}
                    className="flex-1"
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}


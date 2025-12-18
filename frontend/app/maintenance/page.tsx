'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Navbar } from '@/components/Navbar'
import { Button } from '@/components/Button'
import { isAdmin, isAuthenticated } from '@/lib/auth'
import { maintenanceAPI } from '@/lib/api'

type TabType = 'vectordb' | 'upsert'

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

  useEffect(() => {
    if (!isAuthenticated()) {
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


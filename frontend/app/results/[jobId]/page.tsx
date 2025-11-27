'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Navbar } from '@/components/Navbar'
import { ragAPI } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'

export default function ResultsPage() {
  const params = useParams()
  const router = useRouter()
  const jobId = params?.jobId as string

  // Redirect if not authenticated
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/auth/login')
    }
  }, [router])

  const { data: results, isLoading, error } = useQuery({
    queryKey: ['rag-results', jobId],
    queryFn: () => ragAPI.getResults(jobId),
    enabled: !!jobId && isAuthenticated(),
  })

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Navbar />
        <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading results...</p>
          </div>
        </main>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Navbar />
        <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
          <div className="bg-white rounded-lg shadow p-8">
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
              {error instanceof Error
                ? error.message
                : 'Failed to load results. Please try again.'}
            </div>
          </div>
        </main>
      </div>
    )
  }

  if (!results) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Navbar />
        <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
          <div className="bg-white rounded-lg shadow p-8">
            <p className="text-gray-600">No results found.</p>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        <div className="space-y-8">
          {/* Header */}
          <div className="bg-gradient-to-r from-primary-600 to-primary-700 rounded-lg shadow-lg p-8 text-white">
            <h1 className="text-3xl font-bold">
              🎯 Marketing Content Results
            </h1>
            <p className="mt-2 text-primary-100">
              Job ID: {results.job_id}
            </p>
            <p className="mt-1 text-sm text-primary-200">
              Generated on {new Date().toLocaleDateString()} at {new Date().toLocaleTimeString()}
            </p>
          </div>

          {/* Original Request Section */}
          {results.original_request && (
            <section className="bg-white rounded-lg shadow-md p-6 border-l-4 border-blue-500">
              <div className="flex items-center mb-4">
                <svg className="w-6 h-6 text-blue-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <h2 className="text-xl font-semibold text-gray-900">
                  Original Request
                </h2>
              </div>
              
              {/* Topics */}
              {results.topics && results.topics.length > 0 && (
                <div className="mb-4">
                  <p className="text-sm font-medium text-gray-600 mb-2">Topics:</p>
                  <div className="flex flex-wrap gap-2">
                    {results.topics.map((topic: string, index: number) => (
                      <span
                        key={index}
                        className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800 capitalize"
                      >
                        {topic}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Original Text */}
              <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
                <p className="text-sm font-medium text-gray-600 mb-2">Your Request:</p>
                <div className="whitespace-pre-wrap text-gray-700">
                  {results.original_request}
                </div>
              </div>
            </section>
          )}

          {/* AI Response Section */}
          <section className="bg-white rounded-lg shadow-md p-6 border-l-4 border-green-500">
            <div className="flex items-center mb-4">
              <svg className="w-6 h-6 text-green-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              <h2 className="text-xl font-semibold text-gray-900">
                AI-Refined Marketing Content
              </h2>
            </div>
            <div className="prose max-w-none">
              <div className="whitespace-pre-wrap text-gray-700 bg-green-50 p-6 rounded-lg border border-green-200 leading-relaxed">
                {results.refined_text}
              </div>
            </div>
            
            {/* Copy to Clipboard Button */}
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(results.refined_text)
                  alert('Copied to clipboard!')
                }}
                className="inline-flex items-center px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors text-sm font-medium"
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Copy to Clipboard
              </button>
            </div>
          </section>

          {/* Sources Section */}
          <section className="bg-white rounded-lg shadow-md p-6 border-l-4 border-purple-500">
            <div className="flex items-center mb-4">
              <svg className="w-6 h-6 text-purple-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <h2 className="text-xl font-semibold text-gray-900">
                Sources from Qdrant Vector Search
              </h2>
            </div>
            
            {results.sources && results.sources.length > 0 ? (
              <div className="space-y-4">
                <p className="text-sm text-gray-600 mb-4">
                  The following {results.sources.length} document{results.sources.length !== 1 ? 's were' : ' was'} retrieved 
                  and used as context for generating the refined content:
                </p>
                {results.sources.map((source: any, index: number) => (
                  <div
                    key={index}
                    className="border border-purple-200 rounded-lg p-5 hover:shadow-md transition-shadow bg-gradient-to-r from-white to-purple-50"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="px-3 py-1 text-xs font-bold text-purple-700 bg-purple-200 rounded-full">
                            Source {index + 1}
                          </span>
                          <span className="text-xs text-gray-500">
                            Relevance Score: {(source.score * 100)?.toFixed(1) || 'N/A'}%
                          </span>
                        </div>
                        <h3 className="font-semibold text-gray-900 text-lg flex items-center">
                          <svg className="w-5 h-5 text-purple-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                          </svg>
                          {source.filename || 'Unknown Document'}
                        </h3>
                        <p className="text-sm text-gray-500 mt-1">
                          <span className="font-medium">Type:</span> {source.file_type || 'Unknown'}
                          {source.doc_id && <span className="ml-3"><span className="font-medium">ID:</span> {source.doc_id}</span>}
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 bg-white p-4 rounded-lg border-l-4 border-purple-500 shadow-inner">
                      <p className="text-xs font-medium text-gray-500 mb-2">Excerpt:</p>
                      <div className="text-sm text-gray-700 leading-relaxed italic">
                        "{source.snippet || 'No excerpt available'}"
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
                <svg className="w-12 h-12 text-gray-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-gray-500 font-medium">No sources were used for this refinement.</p>
                <p className="text-sm text-gray-400 mt-1">The AI generated content without retrieving documents from the vector database.</p>
              </div>
            )}
          </section>

          {/* Actions */}
          <section className="flex justify-between items-center bg-white rounded-lg shadow p-6">
            <button
              onClick={() => router.push('/')}
              className="inline-flex items-center px-6 py-3 bg-primary-600 text-white rounded-md hover:bg-primary-700 transition-colors font-medium"
            >
              <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Process Another Request
            </button>
            
            <button
              onClick={() => window.print()}
              className="inline-flex items-center px-6 py-3 bg-gray-200 text-gray-900 rounded-md hover:bg-gray-300 transition-colors font-medium"
            >
              <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
              </svg>
              Print Results
            </button>
          </section>
        </div>
      </main>
    </div>
  )
}


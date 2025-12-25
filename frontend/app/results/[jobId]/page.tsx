'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Navbar } from '@/components/Navbar'
import { ragAPI } from '@/lib/api'
import { isAuthenticated, isAdmin } from '@/lib/auth'

export default function ResultsPage() {
  const params = useParams()
  const router = useRouter()
  const jobId = params?.jobId as string
  const [mounted, setMounted] = useState(false)
  const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set())
  
  const toggleSource = (index: number) => {
    setExpandedSources(prev => {
      const newSet = new Set(prev)
      if (newSet.has(index)) {
        newSet.delete(index)
      } else {
        newSet.add(index)
      }
      return newSet
    })
  }

  // Redirect if not authenticated
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/auth/login')
    }
  }, [router])

  // Set mounted to true on client side
  useEffect(() => {
    setMounted(true)
  }, [])

  const { data: results, isLoading, error } = useQuery({
    queryKey: ['rag-results', jobId],
    queryFn: () => ragAPI.getResults(jobId),
    enabled: !!jobId && isAuthenticated(),
  })

  // Don't render until mounted to avoid hydration issues
  if (!mounted) {
    return null
  }

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

  const isPodcast = (source: any) =>
    source.doc_type === 'podcast_summary' || source.type === 'podcast_summary'

  // Very small markdown-style formatter: supports **bold** and newlines.
  const formatRefinedText = (text: string): string => {
    if (!text) return ''

    // Escape HTML first
    let escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')

    // Basic bold: **TEXT** → <strong>TEXT</strong>
    escaped = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

    // Preserve newlines
    escaped = escaped.replace(/\n/g, '<br/>')

    return escaped
  }

  // Deduplicate sources by stable keys (thread URL, video URL, podcast episode URL,
  // or doc_id/filename), keeping the entry with the highest score.
  const dedupeSources = (sources: any[]): any[] => {
    const map = new Map<string, any>()

    for (const src of sources || []) {
      let key: string
      if (src.thread_url) {
        key = `reddit:${src.thread_url}`
      } else if (src.video_url) {
        key = `yt:${src.video_url}`
      } else if (isPodcast(src) && src.episode_url) {
        key = `pod:${src.episode_url}`
      } else if (src.doc_id) {
        key = `doc:${src.doc_id}`
      } else if (src.filename || src.source || src.doc_type) {
        key = `generic:${src.source || ''}:${src.doc_type || ''}:${src.filename || ''}`
      } else {
        // Fallback: treat as unique to avoid accidental merges
        key = `unique:${Math.random().toString(36).slice(2)}`
      }

      const existing = map.get(key)
      if (!existing) {
        map.set(key, src)
      } else {
        const existingScore =
          typeof existing.score === 'number' ? existing.score : -Infinity
        const newScore =
          typeof src.score === 'number' ? src.score : -Infinity
        if (newScore > existingScore) {
          map.set(key, src)
        }
      }
    }

    return Array.from(map.values())
  }

  const dedupedSources = dedupeSources(results.sources || [])
  // Debug: Log first source's metadata fields
  if (dedupedSources.length > 0) {
    console.log('First source fields:', {
      pain_phrases: dedupedSources[0].pain_phrases,
      emotional_triggers: dedupedSources[0].emotional_triggers,
      implicit_risks: dedupedSources[0].implicit_risks,
      allKeys: Object.keys(dedupedSources[0])
    })
  }
  return (
    <div className="min-h-screen bg-gray-50" suppressHydrationWarning>
      <Navbar />
      <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8" suppressHydrationWarning>
        <div className="space-y-8" suppressHydrationWarning>
          {/* AI Response Section */}
          <section className="bg-white rounded-lg shadow-md p-6 border-l-4 border-green-500">
            <div className="flex items-center mb-4">
              <svg className="w-6 h-6 text-green-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              <h2 className="text-xl font-semibold text-gray-900">
                Practitioner-Ready Copy
              </h2>
            </div>
            <div className="prose max-w-none">
              <div
                className="text-gray-700 bg-green-50 p-6 rounded-lg border border-green-200 leading-relaxed"
                dangerouslySetInnerHTML={{ __html: formatRefinedText(results.refined_text) }}
              />
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
                Sources used to provide Asset
              </h2>
            </div>
            
            {dedupedSources && dedupedSources.length > 0 ? (
              <div className="space-y-2">
                {dedupedSources.map((source: any, index: number) => {
                  const isExpanded = expandedSources.has(index)
                  return (
                    <div
                      key={index}
                      className="border border-purple-200 rounded-lg hover:shadow-md transition-shadow bg-white"
                    >
                      {/* Compact Header - Always Visible */}
                      <div className="flex items-center justify-between p-3">
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                          {/* Icon */}
                          {source.source === 'reddit' || source.doc_type === 'reddit_post' || source.doc_type === 'reddit_comment' ? (
                            <svg className="w-5 h-5 text-orange-500 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24">
                              <path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z"/>
                            </svg>
                          ) : source.source === 'youtube' || source.doc_type === 'youtube_transcript' || source.doc_type === 'yt_summary' ? (
                            <svg className="w-5 h-5 text-red-500 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24">
                              <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                            </svg>
                          ) : isPodcast(source) ? (
                            <svg className="w-5 h-5 text-pink-500 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24">
                              <path d="M12 1a9 9 0 00-9 9c0 4.418 3.134 8.063 7.234 8.838L10 23l4-1-0.234-4.162C17.866 18.063 21 14.418 21 10a9 9 0 00-9-9zm0 4a3 3 0 110 6 3 3 0 010-6z" />
                            </svg>
                          ) : (
                            <svg className="w-5 h-5 text-purple-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                            </svg>
                          )}
                          
                          {/* Title */}
                          <h3 className="font-semibold text-gray-900 text-sm flex-1 min-w-0 truncate">
                            {source.source === 'youtube' || source.doc_type === 'youtube_transcript' || source.doc_type === 'yt_summary'
                              ? `YouTube: ${source.title || 'Unknown Video'}`
                              : isPodcast(source)
                                ? source.filename || 'Podcast'
                                : source.filename || 'Unknown Document'}
                          </h3>
                        </div>
                        
                        {/* Expand Button */}
                        <button
                          onClick={() => toggleSource(index)}
                          className="px-3 py-1.5 text-sm font-medium text-purple-600 hover:text-purple-800 hover:bg-purple-50 rounded-md transition-colors flex items-center gap-1 flex-shrink-0"
                        >
                          {isExpanded ? (
                            <>
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                              </svg>
                              Collapse
                            </>
                          ) : (
                            <>
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                              </svg>
                              Expand
                            </>
                          )}
                        </button>
                      </div>
                      
                      {/* Expanded Content */}
                      {isExpanded && (
                        <div className="border-t border-purple-200 p-4 bg-gradient-to-r from-white to-purple-50">
                          <div className="flex items-center gap-2 mb-3">
                            <span className="px-3 py-1 text-xs font-bold text-purple-700 bg-purple-200 rounded-full">
                              Source {index + 1}
                            </span>
                            {source.source && (
                              <span className="px-2 py-1 text-xs font-medium text-indigo-700 bg-indigo-100 rounded">
                                {source.source}
                              </span>
                            )}
                            {source.score !== undefined && (
                              <span className="text-xs text-gray-500">
                                Score: {(source.score * 100)?.toFixed(1)}%
                              </span>
                            )}
                          </div>
                          
                          {/* Metadata Grid */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
                          {/* Document Type (hidden for YouTube and Podcasts) */}
                          {source.doc_type &&
                            source.source !== 'youtube' &&
                            source.doc_type !== 'youtube_transcript' &&
                            !isPodcast(source) && (
                              <div>
                                <span className="font-medium text-gray-600">Document Type:</span>{' '}
                                <span className="text-gray-700 capitalize">
                                  {source.doc_type.replace('_', ' ')}
                                </span>
                              </div>
                            )}
                          {source.file_type && (
                            <div>
                              <span className="font-medium text-gray-600">File Type:</span>{' '}
                              <span className="text-gray-700">{source.file_type}</span>
                            </div>
                          )}
                          
                          {/* Common fields across document types */}
                          {source.icp_role_type && (
                            <div>
                              <span className="font-medium text-gray-600">ICP Role:</span>{' '}
                              <span className="text-gray-700">{source.icp_role_type}</span>
                            </div>
                          )}
                          {source.citation_start_time !== undefined && source.citation_start_time !== null && (
                            <div>
                              <span className="font-medium text-gray-600">Citation Time:</span>{' '}
                              <span className="text-gray-700">
                                {Math.floor(source.citation_start_time / 60)}:{(source.citation_start_time % 60).toFixed(0).padStart(2, '0')}
                              </span>
                            </div>
                          )}
                          
                          {/* Reddit-specific fields */}
                          {source.subreddit && (
                            <div>
                              <span className="font-medium text-gray-600">Subreddit:</span>{' '}
                              <span className="text-gray-700">r/{source.subreddit}</span>
                            </div>
                          )}
                          {(source.thread_author || source.author) && (
                            <div>
                              <span className="font-medium text-gray-600">Author:</span>{' '}
                              <span className="text-gray-700">{source.thread_author || source.author}</span>
                            </div>
                          )}
                          {source.flair_text && (
                            <div>
                              <span className="font-medium text-gray-600">Flair:</span>{' '}
                              <span className="text-gray-700">{source.flair_text}</span>
                            </div>
                          )}
                          {source.ups !== undefined && source.ups !== null && (
                            <div>
                              <span className="font-medium text-gray-600">Upvotes:</span>{' '}
                              <span className="text-gray-700">{source.ups}</span>
                            </div>
                          )}
                          
                          {/* YouTube-specific fields */}
                          {source.channel && !isPodcast(source) && (
                            <div>
                              <span className="font-medium text-gray-600">Channel:</span>{' '}
                              <span className="text-gray-700">{source.channel}</span>
                            </div>
                          )}
                          {('youtube' === source.source || source.doc_type === 'youtube_transcript' || source.doc_type === 'yt_summary') &&
                            source.description && (
                              <div className="md:col-span-2">
                                <span className="font-medium text-gray-600">Description:</span>{' '}
                                <span className="text-gray-700">{source.description}</span>
                              </div>
                            )}
                          {source.start_sec !== undefined && source.start_sec !== null && (
                            <div>
                              <span className="font-medium text-gray-600">Timestamp:</span>{' '}
                              <span className="text-gray-700">
                                {Math.floor(source.start_sec / 60)}:{(source.start_sec % 60).toFixed(0).padStart(2, '0')}
                                {source.end_sec && ` - ${Math.floor(source.end_sec / 60)}:${(source.end_sec % 60).toFixed(0).padStart(2, '0')}`}
                              </span>
                            </div>
                          )}

                          {/* Podcast-specific fields */}
                          {isPodcast(source) && (
                            <>
                              {source.channel && (
                                <div>
                                  <span className="font-medium text-gray-600">Podcast Series:</span>{' '}
                                  <span className="text-gray-700">{source.channel}</span>
                                </div>
                              )}
                              {/* Episode title is already surfaced in the main heading; no extra Episode: line */}
                              {source.episode_number !== undefined && source.episode_number !== null && (
                                <div>
                                  <span className="font-medium text-gray-600">Episode #:</span>{' '}
                                  <span className="text-gray-700">{source.episode_number}</span>
                                </div>
                              )}
                            </>
                          )}
                          
                          {/* Date */}
                          {source.timestamp && mounted && (
                            <div>
                              <span className="font-medium text-gray-600">Date:</span>{' '}
                              <span className="text-gray-700">{new Date(source.timestamp).toLocaleDateString()}</span>
                            </div>
                          )}
                          
                          {/* Doc ID */}
                          {source.doc_id && (
                            <div>
                              <span className="font-medium text-gray-600">Doc ID:</span>{' '}
                              <span className="text-gray-700">{source.doc_id}</span>
                            </div>
                          )}
                        </div>
                        
                        {/* Additional detailed explanation sections */}
                        {source.detailed_explanation && (
                          <div className="mt-3 p-3 bg-blue-50 rounded border border-blue-200">
                            <p className="text-xs font-medium text-gray-600 mb-1">Detailed Explanation:</p>
                            <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                              {source.detailed_explanation}
                            </p>
                          </div>
                        )}
                        {(source.detailed_explanation || source.selftext) && (
                          <div className="mt-3 p-3 bg-orange-50 rounded border border-orange-200">
                            <p className="text-xs font-medium text-gray-600 mb-1">discussion_description:</p>
                            <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                              {source.detailed_explanation || source.selftext}
                            </p>
                          </div>
                        )}
                        {source.citation && (
                          <div className="mt-3 p-3 bg-purple-50 rounded border border-purple-200">
                            <p className="text-xs font-medium text-gray-600 mb-1">Citation:</p>
                            <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                              {source.citation}
                            </p>
                          </div>
                        )}
                        
                        {/* URL Links */}
                        <div className="mt-3 flex flex-wrap gap-3">
                          {/* Main URL Link - Check for any available URL field (exclude podcasts) */}
                          {!isPodcast(source) && (source.url || source.thread_url || source.video_url) && (
                            <a
                              href={
                                source.thread_url || source.video_url || source.url
                              }
                              target="_blank"
                              rel="noopener noreferrer"
                              className={`inline-flex items-center text-sm font-medium hover:underline ${
                                source.thread_url ? 'text-blue-600 hover:text-blue-800' :
                                source.video_url ? 'text-red-600 hover:text-red-800' :
                                'text-blue-600 hover:text-blue-800'
                              }`}
                            >
                              <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                              </svg>
                              {source.thread_url ? 'View Thread' :
                               source.video_url ? 'Watch Video' :
                               'View Source'}
                            </a>
                          )}

                          {/* YouTube timestamp link if available */}
                          {source.video_url && (source.citation_start_time || source.start_sec) && (() => {
                            const timestamp = Math.floor(source.citation_start_time || source.start_sec);
                            // Strip existing timestamp parameters from URL
                            const baseUrl = source.video_url.replace(/[?&]t=\d+[s]?/gi, '');
                            const separator = baseUrl.includes('?') ? '&' : '?';
                            const youtubeUrl = `${baseUrl}${separator}t=${timestamp}`;
                            return (
                              <a
                                href={youtubeUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center text-sm font-medium text-red-600 hover:text-red-800 hover:underline"
                              >
                                <svg className="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 24 24">
                                  <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                                </svg>
                                Jump to {Math.floor(timestamp / 60)}:{(timestamp % 60).toFixed(0).padStart(2, '0')}
                              </a>
                            );
                          })()}

                          {/* Podcast timestamp link if available */}
                          {isPodcast(source) && source.episode_url && source.citation_start_time && (() => {
                            const timestamp = Math.floor(source.citation_start_time);
                            let podcastUrl: string;
                            
                            // Darknet Diaries uses #t= format
                            if (source.episode_url.includes('darknetdiaries.com')) {
                              podcastUrl = `${source.episode_url}#t=${timestamp}`;
                            } else {
                              // For other podcasts (including Buzzsprout), use ?t= or &t= format
                              // Strip existing timestamp parameters first
                              const baseUrl = source.episode_url.replace(/[?&]t=\d+/gi, '');
                              const separator = baseUrl.includes('?') ? '&' : '?';
                              podcastUrl = `${baseUrl}${separator}t=${timestamp}`;
                            }
                            
                            return (
                              <a
                                href={podcastUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center text-sm font-medium text-pink-600 hover:text-pink-800 hover:underline"
                              >
                                <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                </svg>
                                Jump to {Math.floor(timestamp / 60)}:{(timestamp % 60).toFixed(0).padStart(2, '0')}
                              </a>
                            );
                          })()}
                        </div>

                        {/* Podcast MP3 player */}
                        {isPodcast(source) && source.mp3_url && (
                          <div className="mt-3">
                            <p className="text-xs font-medium text-gray-600 mb-1">Play Podcast Excerpt:</p>
                            <audio
                              controls
                              className="w-full max-w-md"
                              src={source.mp3_url+'?t='+source.citation_start_time}
                              onLoadedMetadata={(e) => {
                                const audio = e.currentTarget as HTMLAudioElement
                                const start = Number(source.citation_start_time ?? 0)
                                if (!Number.isNaN(start) && start > 0 && start < (audio.duration || Infinity)) {
                                  audio.currentTime = start
                                }
                              }}
                            />
                          </div>
                        )}
                        
                        {/* Excerpt */}
                        <div className="mt-4 bg-white p-4 rounded-lg border-l-4 border-purple-500 shadow-inner">
                          <p className="text-xs font-medium text-gray-500 mb-2">Context Excerpt:</p>
                          <div className="text-sm text-gray-700 leading-relaxed space-y-1">
                            {(() => {
                              // Parse text field to extract Pain Phrases, Emotional Triggers, and Implicit Risks
                              // Format: "Pain Phrases: value1, value2 | Emotional Triggers: value1, value2 | Implicit Risks: value1, value2"
                              const parseTextField = (text: string) => {
                                const result = {
                                  painPhrases: [] as string[],
                                  emotionalTriggers: [] as string[],
                                  implicitRisks: [] as string[]
                                };

                                if (!text) return result;

                                // Split by " | " to get individual sections
                                const sections = text.split(' | ');
                                
                                for (const section of sections) {
                                  // Extract Pain Phrases
                                  if (section.startsWith('Pain Phrases:')) {
                                    const content = section.replace('Pain Phrases:', '').trim();
                                    if (content) {
                                      result.painPhrases = content.split(',').map(p => p.trim()).filter(p => p);
                                    }
                                  }
                                  // Extract Emotional Triggers
                                  else if (section.startsWith('Emotional Triggers:')) {
                                    const content = section.replace('Emotional Triggers:', '').trim();
                                    if (content) {
                                      result.emotionalTriggers = content.split(',').map(e => e.trim()).filter(e => e);
                                    }
                                  }
                                  // Extract Implicit Risks
                                  else if (section.startsWith('Implicit Risks:')) {
                                    const content = section.replace('Implicit Risks:', '').trim();
                                    if (content) {
                                      result.implicitRisks = content.split(',').map(r => r.trim()).filter(r => r);
                                    }
                                  }
                                }

                                return result;
                              };

                              const parsed = parseTextField(source.text || '');
                              const { painPhrases, emotionalTriggers, implicitRisks } = parsed;

                              if (painPhrases.length === 0 && emotionalTriggers.length === 0 && implicitRisks.length === 0) {
                                return <div>No excerpt available</div>;
                              }

                              return (
                                <>
                                  {painPhrases.length > 0 && (
                                    <div>
                                      <span className="font-bold">Pain Phrases:</span> {painPhrases.join(', ')}
                                    </div>
                                  )}
                                  {emotionalTriggers.length > 0 && (
                                    <div>
                                      <span className="font-bold">Emotional Triggers:</span> {emotionalTriggers.join(', ')}
                                    </div>
                                  )}
                                  {implicitRisks.length > 0 && (
                                    <div>
                                      <span className="font-bold">Implicit Risks:</span> {implicitRisks.join(', ')}
                                    </div>
                                  )}
                                </>
                              );
                            })()}
                          </div>
                        </div>
                      </div>
                    )}
                    </div>
                  )
                })}
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

          {/* Original Request Section (moved to bottom) */}
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
              
              {/* Keywords */}
              {results.topics && results.topics.length > 0 && (
                <div className="mb-4">
                  <p className="text-sm font-medium text-gray-600 mb-2">Keywords:</p>
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

          {/* Full Prompt Section - Admin only */}
          {isAdmin() && results.final_prompt && (
            <section className="bg-white rounded-lg shadow-md p-6 border-l-4 border-purple-500">
              <div className="flex items-center mb-4">
                <svg className="w-6 h-6 text-purple-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <h2 className="text-xl font-semibold text-gray-900">
                  Full Prompt Used by AI
                </h2>
              </div>

              <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
                <p className="text-sm font-medium text-gray-600 mb-2">Complete prompt sent to the LLM:</p>
                <div className="whitespace-pre-wrap text-gray-700 text-sm font-mono bg-white p-3 rounded border max-h-96 overflow-y-auto">
                  {results.final_prompt}
                </div>
              </div>
            </section>
          )}

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

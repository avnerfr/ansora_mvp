'use client'

import { useState, useEffect, useRef, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Navbar } from '@/components/Navbar'
import { TextArea } from '@/components/TextArea'
import { Button } from '@/components/Button'
import { Dialog } from '@/components/Dialog'
import { ragAPI } from '@/lib/api'
import { isAuthenticated, isAdmin, getAuthToken } from '@/lib/auth'

function HomePageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  
  // Tab state
  const [activeTab, setActiveTab] = useState<'generator' | 'assistant'>('generator')
  
  // Asset Generator states
  const [selectedOperationalPain, setSelectedOperationalPain] = useState<string>('')
  const [contextText, setContextText] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [hasToken, setHasToken] = useState(false)
  const [assetType, setAssetType] = useState<string>('')
  const [icp, setIcp] = useState<string>('')
  const [selectedCompany, setSelectedCompany] = useState<string>('')
  const [isAdminUser, setIsAdminUser] = useState(false)
  const [showCompanyDialog, setShowCompanyDialog] = useState(false)
  const [isUploadingContextDocs, setIsUploadingContextDocs] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [icpOptions, setIcpOptions] = useState<string[]>([])
  const [isLoadingICPs, setIsLoadingICPs] = useState(false)
  const [operationalPainOptions, setOperationalPainOptions] = useState<string[]>([])
  const [isLoadingOperationalPains, setIsLoadingOperationalPains] = useState(false)
  const [assetTypeOptions, setAssetTypeOptions] = useState<string[]>([])
  const [isLoadingAssetTypes, setIsLoadingAssetTypes] = useState(false)
  const [competitors, setCompetitors] = useState<string[]>([])
  const [selectedCompetitor, setSelectedCompetitor] = useState<string>('')
  const [isLoadingCompetitors, setIsLoadingCompetitors] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  // Asset Assistant states
  const [originalAsset, setOriginalAsset] = useState<string>('')
  const [modifiedAsset, setModifiedAsset] = useState<string>('')
  const [isGettingRecommendations, setIsGettingRecommendations] = useState(false)
  const [modifiedAssetViewMode, setModifiedAssetViewMode] = useState<'edit' | 'diff'>('edit')
  const [recommendationItems, setRecommendationItems] = useState<any[]>([])
  const [hoveredItem, setHoveredItem] = useState<any | null>(null)
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number; y: number } | null>(null)

  const COMPANY_OPTIONS = ['Algosec', 'CyberArk', 'JFrog', 'Cloudinary', 'Incredibuild']

  // Check if battle cards is selected
  const isBattleCards = assetType === 'battle-cards'

  // Define fetch functions before they're used in useEffect
  const fetchAssetTypes = async () => {
    setIsLoadingAssetTypes(true)
    try {
      const response = await ragAPI.getAssetTypes()
      if (response && response.asset_types && response.asset_types.length > 0) {
        setAssetTypeOptions(response.asset_types)
        console.log('✓ Loaded asset types from DynamoDB:', response.asset_types)
      } else {
        // Fallback to default asset types
        setAssetTypeOptions([
          "one-pager",
          "email",
          "landing-page",
          "blog",
          "linkedin-post",
          "blog-post"
        ])
      }
    } catch (error) {
      console.error('Error fetching asset types:', error)
      setAssetTypeOptions([
        "one-pager",
        "email",
        "landing-page",
        "blog",
        "linkedin-post",
        "blog-post"
      ])
    } finally {
      setIsLoadingAssetTypes(false)
    }
  }

  const fetchCompetitors = async (companyName: string) => {
    if (!companyName) return
    
    setIsLoadingCompetitors(true)
    try {
      const response = await ragAPI.getCompetitors(companyName)
      if (response && response.competitors && response.competitors.length > 0) {
        setCompetitors(response.competitors)
        console.log('✓ Loaded competitors from S3:', response.competitors)
      } else {
        console.warn('No competitors found for company')
        setCompetitors([])
      }
    } catch (error) {
      console.error('Error fetching competitors:', error)
      setCompetitors([])
    } finally {
      setIsLoadingCompetitors(false)
    }
  }

  const fetchCompanyData = async (companyName: string) => {
    if (!companyName) return
    
    setIsLoadingICPs(true)
    setIsLoadingOperationalPains(true)
    
    try {
      const response = await ragAPI.getCompanyData(companyName)
      
      // Set target audience (ICPs)
      if (response && response.target_audience && response.target_audience.length > 0) {
        setIcpOptions(response.target_audience)
        console.log('✓ Loaded target_audience from S3:', response.target_audience)
      } else {
        // Fallback to default ICPs
        console.warn('No target_audience in S3, using defaults')
        setIcpOptions([
          "Network & Security Operations",
          "Application & Service Delivery",
          "CIO",
          "CISO",
          "Risk and Compliance"
        ])
      }
      
      // Set operational pains
      if (response && response.operational_pains && response.operational_pains.length > 0) {
        setOperationalPainOptions(response.operational_pains)
        console.log('✓ Loaded operational_pains from S3:', response.operational_pains)
      } else {
        // Fallback to default operational pains
        console.warn('No operational_pains in S3, using defaults')
        setOperationalPainOptions([
          "Network visibility gaps during incidents",
          "Configuration drift and compliance failures",
          "Alert fatigue and false positives",
          "Slow incident response times",
          "Cloud security misconfigurations"
        ])
      }
      
    } catch (error) {
      console.error('Error fetching company data:', error)
      // Fallback to defaults on error
      setIcpOptions([
        "Network & Security Operations",
        "Application & Service Delivery",
        "CIO",
        "CISO",
        "Risk and Compliance"
      ])
      setOperationalPainOptions([
        "Network visibility gaps during incidents",
        "Configuration drift and compliance failures",
        "Alert fatigue and false positives",
        "Slow incident response times",
        "Cloud security misconfigurations"
      ])
    } finally {
      setIsLoadingICPs(false)
      setIsLoadingOperationalPains(false)
    }
  }

  // Handle Cognito callback - if there's a code parameter, redirect to callback API
  useEffect(() => {
    const code = searchParams.get('code')
    if (code) {
      // Redirect to callback API with the code
      window.location.href = `/api/auth/callback?code=${code}`
      return
    }
  }, [searchParams])

  // Load asset types on mount
  useEffect(() => {
    fetchAssetTypes()
  }, [])

  // Check authentication only after component mounts
  useEffect(() => {
    const code = searchParams.get('code')
    // Skip auth check if we're processing a callback
    if (code) return
    
    const token = isAuthenticated()
    console.log('Auth check:', token)
    setHasToken(token)
    setAuthChecked(true)
    
    // Check if user is admin
    if (token) {
      const adminStatus = isAdmin()
      setIsAdminUser(adminStatus)
      // Show company selection dialog for admins if no company is selected
      // Only show on initial load (when authChecked transitions from false to true)
      if (adminStatus && !selectedCompany && !showCompanyDialog) {
        setShowCompanyDialog(true)
      } else if (!adminStatus) {
        // For non-admin users, get company from Cognito groups and fetch ICPs
        try {
          const authToken = getAuthToken()
          if (authToken) {
            // Decode JWT payload to get groups
            const payload = JSON.parse(atob(authToken.split('.')[1]))
            const groups = payload['cognito:groups'] || []
            console.log('Cognito groups:', groups)
            // Filter out Administrators group
            const companyGroups = groups.filter((g: string) => g !== 'Administrators')
            console.log('Company groups:', companyGroups)
            if (companyGroups.length > 0) {
              const companyName = companyGroups[0]
              console.log('Fetching data for company:', companyName)
              fetchCompanyData(companyName)
            } else {
              console.warn('No company groups found for non-admin user')
            }
          } else {
            console.warn('No auth token found for non-admin user')
          }
        } catch (error) {
          console.error('Error extracting company from groups:', error)
        }
      }
    }
    
    if (!token) {
      router.push('/auth/login')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, searchParams])

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

  // Function to highlight differences between original and modified text
  const highlightDifferences = (original: string, modified: string): string => {
    if (!modified) return ''
    
    // Escape HTML
    const escapeHtml = (text: string) => {
      const div = document.createElement('div')
      div.textContent = text
      return div.innerHTML
    }
    
    if (!original) {
      // All text is new - mark in dark green
      return `<span style="color: #006400; font-weight: bold;">${escapeHtml(modified)}</span>`
    }
    
    // Split into words (preserving whitespace)
    const originalWords = original.split(/(\s+)/)
    const modifiedWords = modified.split(/(\s+)/)
    
    // Track matched indices
    const origMatched = new Set<number>()
    const modMatched = new Set<number>()
    
    // First pass: find exact sequential matches
    let origIdx = 0
    let modIdx = 0
    
    while (origIdx < originalWords.length && modIdx < modifiedWords.length) {
      if (originalWords[origIdx] === modifiedWords[modIdx]) {
        origMatched.add(origIdx)
        modMatched.add(modIdx)
        origIdx++
        modIdx++
      } else {
        // Try to find the word in the other array
        let foundInMod = false
        for (let i = modIdx + 1; i < Math.min(modIdx + 20, modifiedWords.length); i++) {
          if (originalWords[origIdx] === modifiedWords[i] && !modMatched.has(i)) {
            // Found match later in modified - words between are additions
            foundInMod = true
            break
          }
        }
        
        let foundInOrig = false
        for (let i = origIdx + 1; i < Math.min(origIdx + 20, originalWords.length); i++) {
          if (originalWords[i] === modifiedWords[modIdx] && !origMatched.has(i)) {
            // Found match later in original - words between are deletions
            foundInOrig = true
            break
          }
        }
        
        if (!foundInMod && !foundInOrig) {
          // No match found - this is a change
          origIdx++
          modIdx++
        } else if (foundInMod) {
          origIdx++
        } else {
          modIdx++
        }
      }
    }
    
    // Second pass: find remaining matches (non-sequential)
    for (let mIdx = 0; mIdx < modifiedWords.length; mIdx++) {
      if (modMatched.has(mIdx)) continue
      for (let oIdx = 0; oIdx < originalWords.length; oIdx++) {
        if (origMatched.has(oIdx)) continue
        if (originalWords[oIdx] === modifiedWords[mIdx]) {
          origMatched.add(oIdx)
          modMatched.add(mIdx)
          break
        }
      }
    }
    
    // Build result with proper highlighting
    let result = ''
    origIdx = 0
    modIdx = 0
    
    while (origIdx < originalWords.length || modIdx < modifiedWords.length) {
      if (origIdx >= originalWords.length) {
        // Remaining in modified are additions - dark green
        result += `<span style="color: #006400; font-weight: bold;">${escapeHtml(modifiedWords[modIdx])}</span>`
        modIdx++
      } else if (modIdx >= modifiedWords.length) {
        // Remaining in original are deletions - dark red with strikethrough
        result += `<span style="color: #8B0000; font-weight: bold; text-decoration: line-through;">${escapeHtml(originalWords[origIdx])}</span>`
        origIdx++
      } else if (origMatched.has(origIdx) && modMatched.has(modIdx) && originalWords[origIdx] === modifiedWords[modIdx]) {
        // Matched words - no highlighting
        result += escapeHtml(modifiedWords[modIdx])
        origIdx++
        modIdx++
      } else if (!origMatched.has(origIdx) && !modMatched.has(modIdx)) {
        // Both unmatched - this is a change: show original (dark red strikethrough) + modified (dark green)
        result += `<span style="color: #8B0000; font-weight: bold; text-decoration: line-through;">${escapeHtml(originalWords[origIdx])}</span>`
        result += `<span style="color: #006400; font-weight: bold;">${escapeHtml(modifiedWords[modIdx])}</span>`
        origIdx++
        modIdx++
      } else if (!origMatched.has(origIdx)) {
        // Original word not matched - deletion (dark red with strikethrough)
        result += `<span style="color: #8B0000; font-weight: bold; text-decoration: line-through;">${escapeHtml(originalWords[origIdx])}</span>`
        origIdx++
      } else if (!modMatched.has(modIdx)) {
        // Modified word not matched - addition (dark green)
        result += `<span style="color: #006400; font-weight: bold;">${escapeHtml(modifiedWords[modIdx])}</span>`
        modIdx++
      } else {
        // Both matched but at different positions - advance both
        result += escapeHtml(modifiedWords[modIdx])
        origIdx++
        modIdx++
      }
    }
    
    return result
  }

  const handleGetRecommendations = async () => {
    if (!originalAsset.trim()) {
      alert('Please enter an original asset')
      return
    }

    // For admins, ensure company is selected
    if (isAdminUser && !selectedCompany.trim()) {
      alert('Please select a company')
      setShowCompanyDialog(true)
      return
    }

    setIsGettingRecommendations(true)
    try {
      const response = await ragAPI.getRecommendations(
        originalAsset,
        isAdminUser ? selectedCompany : undefined
      )
      setModifiedAsset(response.modified_asset || response.recommended_text || '')
      setRecommendationItems(response.items || [])
    } catch (error: any) {
      console.error('Error getting recommendations:', error)
      alert(
        error.response?.data?.detail ||
          'Failed to get recommendations. Please try again.'
      )
    } finally {
      setIsGettingRecommendations(false)
    }
  }

  // Function to highlight source snippets in the original asset
  const highlightSourceSnippets = (text: string, items: any[]): string => {
    if (!items || items.length === 0) return text
    
    // Create array with original indices before sorting
    const itemsWithOriginalIndex = items.map((item, originalIndex) => ({
      item,
      originalIndex
    }))
    
    // Sort items by source_snippet length (longest first) to avoid partial matches
    const sortedItems = [...itemsWithOriginalIndex].sort((a, b) => {
      const aSnippet = a.item.source_snippet || ''
      const bSnippet = b.item.source_snippet || ''
      return bSnippet.length - aSnippet.length
    })
    
    // Build array of ranges to highlight (start, end, originalItemIndex, item)
    const ranges: Array<{start: number, end: number, originalItemIndex: number, item: any}> = []
    const processedRanges: Array<{start: number, end: number}> = []
    
    // Process each item to find all matches
    sortedItems.forEach(({ item, originalIndex }) => {
      const sourceSnippet = item.source_snippet || ''
      if (!sourceSnippet) return
      
      // Find all occurrences of the snippet in the text (case-insensitive)
      const escapedSnippet = escapeRegExp(sourceSnippet)
      const regex = new RegExp(escapedSnippet, 'gi')
      const matches = [...text.matchAll(regex)]
      
      matches.forEach((match) => {
        const startIndex = match.index!
        const endIndex = startIndex + match[0].length
        
        // Check if this range overlaps with any already processed range
        let overlaps = false
        for (const processedRange of processedRanges) {
          if (!(endIndex <= processedRange.start || startIndex >= processedRange.end)) {
            overlaps = true
            break
          }
        }
        
        if (!overlaps) {
          ranges.push({ start: startIndex, end: endIndex, originalItemIndex: originalIndex, item })
          processedRanges.push({ start: startIndex, end: endIndex })
        }
      })
    })
    
    // Sort ranges by start position (descending) so we can replace from end to start
    ranges.sort((a, b) => b.start - a.start)
    
    // Build highlighted text by replacing from end to start (to preserve indices)
    let highlightedText = text
    ranges.forEach(({ start, end, originalItemIndex, item }) => {
      const sourceSnippet = item.source_snippet || ''
      const matchedText = text.substring(start, end)
      const isPainSignal = item.classification === 'pain_signal'
      const bgColor = isPainSignal ? 'bg-blue-200' : 'bg-orange-200'
      const itemId = `item-${originalItemIndex}-${start}`
      
      const highlight = `<span class="${bgColor} cursor-pointer hover:${bgColor.replace('200', '300')} relative highlight-span" data-item-index="${originalItemIndex}" data-item-id="${itemId}">${matchedText}</span>`
      highlightedText = highlightedText.substring(0, start) + highlight + highlightedText.substring(end)
    })
    
    return highlightedText
  }

  // Escape special regex characters
  const escapeRegExp = (string: string): string => {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  }

  // Handle mouse enter on highlighted text
  const handleHighlightMouseEnter = (e: React.MouseEvent<HTMLSpanElement>, itemIndex: number) => {
    const item = recommendationItems[itemIndex]
    if (!item) return
    
    setHoveredItem(item)
    const rect = e.currentTarget.getBoundingClientRect()
    setTooltipPosition({
      x: rect.left + rect.width / 2,
      y: rect.top - 10
    })
  }

  // Handle mouse leave
  const handleHighlightMouseLeave = () => {
    setHoveredItem(null)
    setTooltipPosition(null)
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

    // For battle cards, check competitor selection
    if (isBattleCards && !selectedCompetitor.trim()) {
      alert('Please select a competitor for battle cards')
      return
    }

    // For admins, ensure company is selected
    if (isAdminUser && !selectedCompany.trim()) {
      alert('Please select a company')
      setShowCompanyDialog(true)
      return
    }

    setIsProcessing(true)

    try {
      let response
      
      if (isBattleCards) {
        // Use battle cards endpoint
        response = await ragAPI.processBattleCards(
          selectedCompetitor,
          contextText.trim() || "",
          {
            icp,
            company: isAdminUser ? selectedCompany : undefined,
          }
        )
      } else {
        // Use regular endpoint
        response = await ragAPI.process(
          selectedOperationalPain ? [selectedOperationalPain] : [""],
          contextText.trim() || "",
          {
            assetType,
            icp,
            company: isAdminUser ? selectedCompany : undefined,
          }
        )
      }
      
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

  const handleCompanySelect = (company: string) => {
    setSelectedCompany(company)
    setShowCompanyDialog(false)
    // Fetch ICPs, operational pain points, and competitors for the selected company
    if (company) {
      fetchCompanyData(company)
      fetchCompetitors(company)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      
      {/* Company Selection Dialog for Administrators */}
      <Dialog
        isOpen={showCompanyDialog}
        onClose={() => {
          // Only allow closing if a company is selected
          if (selectedCompany) {
            setShowCompanyDialog(false)
          }
        }}
        title="Select Company"
        showCloseButton={!!selectedCompany}
        allowBackdropClose={!!selectedCompany}
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Please select a company to continue.
          </p>
          <div>
            <label
              htmlFor="company-dialog"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              Company
            </label>
            <select
              id="company-dialog"
              value={selectedCompany}
              onChange={(e) => handleCompanySelect(e.target.value)}
              className="block w-full px-3 py-2 text-sm border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white"
            >
              <option value="">Select a company</option>
              {COMPANY_OPTIONS.map((company) => (
                <option key={company} value={company}>
                  {company}
                </option>
              ))}
            </select>
          </div>
          {selectedCompany && (
            <div className="flex justify-end pt-2">
              <Button
                variant="primary"
                onClick={() => setShowCompanyDialog(false)}
              >
                Continue
              </Button>
            </div>
          )}
        </div>
      </Dialog>

      <main className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        <div className="space-y-4">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">
              Ground your copy in real-world operational insights
            </h1>
            <p className="mt-1 text-sm text-slate-600">
              
            </p>
          </div>

          {/* Tabs */}
          <div className="border-b border-gray-200 mb-6">
            <nav className="-mb-px flex space-x-8">
              <button
                onClick={() => setActiveTab('generator')}
                className={`py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'generator'
                    ? 'border-primary-500 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Asset Generator
              </button>
              <button
                onClick={() => setActiveTab('assistant')}
                className={`py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'assistant'
                    ? 'border-primary-500 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Asset Assistant
              </button>
            </nav>
          </div>

          {/* Asset Generator Tab */}
          {activeTab === 'generator' && (
            <div className="space-y-4">

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
                    disabled={isLoadingAssetTypes}
                    className="block w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <option value="">{isLoadingAssetTypes ? 'Loading...' : 'Select'}</option>
                    {assetTypeOptions.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
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
                    disabled={isLoadingICPs || icpOptions.length === 0}
                    className="block w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <option value="">
                      {isLoadingICPs ? 'Loading...' : icpOptions.length === 0 ? 'Select company first' : 'Select'}
                    </option>
                    {icpOptions.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Conditional: Show either Competitor (for battle cards) or Operational Pain */}
                {isBattleCards ? (
                  <div>
                    <label
                      htmlFor="competitor"
                      className="block text-xs font-medium text-slate-700 mb-1"
                    >
                      Competitor
                    </label>
                    <select
                      id="competitor"
                      value={selectedCompetitor}
                      onChange={(e) => setSelectedCompetitor(e.target.value)}
                      disabled={isLoadingCompetitors || competitors.length === 0}
                      className="block w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <option value="">
                        {isLoadingCompetitors ? 'Loading...' : competitors.length === 0 ? 'Select company first' : 'Select'}
                      </option>
                      {competitors.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
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
                      disabled={isLoadingOperationalPains || operationalPainOptions.length === 0}
                      className="block w-full px-2 py-1.5 text-xs border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <option value="">
                        {isLoadingOperationalPains ? 'Loading...' : operationalPainOptions.length === 0 ? 'Select company first' : 'Select'}
                      </option>
                      {operationalPainOptions.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

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
          )}

          {/* Asset Assistant Tab */}
          {activeTab === 'assistant' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4">
                {/* Original Asset Box - Full Width */}
                <div className="bg-gray-100 rounded-lg border border-slate-200 p-4 relative">
                  <h2 className="text-sm font-medium text-slate-900 mb-3">
                    Original Asset
                  </h2>
                  {recommendationItems.length > 0 ? (
                    <div 
                      className="bg-white rounded border border-slate-300 p-3 min-h-[600px] max-h-[calc(100vh-250px)] overflow-y-auto text-sm text-slate-700 whitespace-pre-wrap"
                      onMouseMove={(e) => {
                        // Use event delegation to handle mouse events on dynamically inserted spans
                        const target = e.target as HTMLElement
                        if (target.classList.contains('highlight-span') || target.closest('.highlight-span')) {
                          const span = target.classList.contains('highlight-span') ? target : target.closest('.highlight-span') as HTMLElement
                          if (span) {
                            const itemIndex = parseInt(span.getAttribute('data-item-index') || '0')
                            const item = recommendationItems[itemIndex]
                            if (item) {
                              setHoveredItem(item)
                              const rect = span.getBoundingClientRect()
                              const containerRect = e.currentTarget.getBoundingClientRect()
                              setTooltipPosition({
                                x: rect.left + rect.width / 2 - containerRect.left,
                                y: rect.top - containerRect.top - 10
                              })
                            }
                          }
                        } else {
                          setHoveredItem(null)
                          setTooltipPosition(null)
                        }
                      }}
                      onMouseLeave={handleHighlightMouseLeave}
                    >
                      <div
                        dangerouslySetInnerHTML={{
                          __html: highlightSourceSnippets(originalAsset, recommendationItems)
                        }}
                      />
                    </div>
                  ) : (
                    <TextArea
                      label=""
                      rows={20}
                      value={originalAsset}
                      onChange={(e) => setOriginalAsset(e.target.value)}
                      placeholder="Paste or type your original asset text here..."
                      className="w-full"
                    />
                  )}
                  
                  {/* Tooltip */}
                  {hoveredItem && tooltipPosition && (
                    <div
                      className="absolute z-50 bg-white border border-gray-300 rounded-lg shadow-lg p-4 max-w-sm pointer-events-auto"
                      style={{
                        left: `${tooltipPosition.x}px`,
                        top: `${tooltipPosition.y}px`,
                        transform: 'translate(-50%, -100%)',
                        marginTop: '-8px'
                      }}
                      onMouseEnter={(e) => {
                        e.stopPropagation()
                      }}
                      onMouseLeave={handleHighlightMouseLeave}
                    >
                      <div className="text-xs space-y-2">
                        <div>
                          <span className="font-semibold">Classification:</span>{' '}
                          <span className={hoveredItem.classification === 'pain_signal' ? 'text-blue-600' : 'text-orange-600'}>
                            {hoveredItem.classification || 'N/A'}
                          </span>
                        </div>
                        {hoveredItem.source_snippet && (
                          <div>
                            <span className="font-semibold">Source Snippet:</span>{' '}
                            <span className="text-gray-700">{hoveredItem.source_snippet}</span>
                          </div>
                        )}

                        {/* Signals from RAG (up to 3 matches) */}
                        {[1, 2, 3].map((i) => {
                          const signal = (hoveredItem as any)[`signal_from_rag${i}`]
                          if (!signal) return null

                          const score = (hoveredItem as any)[`match_score${i}`]
                          const url = (hoveredItem as any)[`doc_url${i}`]
                          const citation = (hoveredItem as any)[`cytation_from_rag${i}`]

                          return (
                            <div key={`rag-block-${i}`} className="border-t border-slate-200 pt-2 mt-2">
                              <div>
                                <span className="font-semibold">Signal from RAG #{i}:</span>{' '}
                                <span className="text-gray-700">{signal}</span>
                              </div>
                              {typeof score === 'number' && (
                                <div>
                                  <span className="font-semibold">Match Score #{i}:</span>{' '}
                                  <span className="text-gray-700">{score.toFixed(2)}</span>
                                </div>
                              )}
                              {url && (
                                <div>
                                  <span className="font-semibold">Source URL #{i}:</span>{' '}
                                  <a href={url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                                    View Source
                                  </a>
                                </div>
                              )}
                              {citation && (
                                <div>
                                  <span className="font-semibold">Citation from RAG #{i}:</span>{' '}
                                  <span className="text-gray-700">{citation}</span>
                                </div>
                              )}
                            </div>
                          )
                        })}

                        {/* Show any other fields that aren't part of the RAG metadata */}
                        {Object.entries(hoveredItem).map(([key, value]) => {
                          if (
                            [
                              'classification',
                              'source_snippet',
                              // RAG-specific fields (1..3)
                              'signal_from_rag1',
                              'signal_from_rag2',
                              'signal_from_rag3',
                              'match_score1',
                              'match_score2',
                              'match_score3',
                              'doc_url1',
                              'doc_url2',
                              'doc_url3',
                              'cytation_from_rag1',
                              'cytation_from_rag2',
                              'cytation_from_rag3'
                            ].includes(key)
                          ) {
                            return null
                          }
                          if (value === null || value === undefined || value === '') {
                            return null
                          }
                          return (
                            <div key={key}>
                              <span className="font-semibold">{key.replace(/_/g, ' ')}:</span>{' '}
                              <span className="text-gray-700">{String(value)}</span>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>

                {/* Modified Asset Box - Temporarily Hidden */}
                {false && (
                  <div className="bg-gray-100 rounded-lg border border-slate-200 p-4">
                    <h2 className="text-sm font-medium text-slate-900 mb-3">
                      Modified Asset
                    </h2>
                    {modifiedAssetViewMode === 'edit' ? (
                      <TextArea
                        label=""
                        rows={20}
                        value={modifiedAsset}
                        onChange={(e) => setModifiedAsset(e.target.value)}
                        placeholder="Modified text will appear here after clicking 'Provide Recommendations', or you can type directly..."
                        className="w-full"
                      />
                    ) : (
                      <div className="bg-white rounded border border-slate-300 p-3 min-h-[400px] max-h-[500px] overflow-y-auto">
                        {modifiedAsset && originalAsset ? (
                          <div
                            className="text-sm text-slate-700 whitespace-pre-wrap"
                            dangerouslySetInnerHTML={{
                              __html: highlightDifferences(originalAsset, modifiedAsset)
                            }}
                          />
                        ) : (
                          <p className="text-slate-400 text-sm">
                            No content to display. Switch to Edit mode to add text.
                          </p>
                        )}
                      </div>
                    )}
                    {/* Toggle buttons at the bottom */}
                    <div className="mt-3 flex justify-end space-x-2">
                      <button
                        type="button"
                        onClick={() => setModifiedAssetViewMode('edit')}
                        className={`px-3 py-1.5 text-xs font-medium rounded ${
                          modifiedAssetViewMode === 'edit'
                            ? 'bg-primary-600 text-white'
                            : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                        }`}
                      >
                        Modify
                      </button>
                      <button
                        type="button"
                        onClick={() => setModifiedAssetViewMode('diff')}
                        className={`px-3 py-1.5 text-xs font-medium rounded ${
                          modifiedAssetViewMode === 'diff'
                            ? 'bg-primary-600 text-white'
                            : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                        }`}
                        disabled={!modifiedAsset || !originalAsset}
                      >
                        View Diff
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Provide Recommendations Button */}
              <section className="bg-gray-100 rounded-lg border border-slate-200 p-3 flex justify-center">
                <Button
                  variant="primary"
                  onClick={handleGetRecommendations}
                  isLoading={isGettingRecommendations}
                  loadingText="Getting Recommendations..."
                  className="w-fit py-2 text-sm"
                  disabled={!originalAsset.trim()}
                >
                  Provide Recommendations
                </Button>
              </section>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default function HomePage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    }>
      <HomePageContent />
    </Suspense>
  )
}


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


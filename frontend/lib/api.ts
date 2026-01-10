import axios from 'axios'

const API_BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add auth token to requests
apiClient.interceptors.request.use(
  (config) => {
    if (typeof window !== 'undefined') {
      // Get Cognito access token from cookie
      const match = document.cookie.match(/(?:^|; )cognito_access_token=([^;]*)/)
      const token = match ? decodeURIComponent(match[1]) : null
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Handle auth errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const url = error.config?.url as string | undefined

    // For 401s on non-auth endpoints, redirect to login
    if (
      status === 401 &&
      url &&
      !url.includes('/auth/login') &&
      !url.includes('/auth/register')
    ) {
      if (typeof window !== 'undefined') {
        // Store current path as redirect destination
        const currentPath = window.location.pathname
        if (currentPath && currentPath !== '/auth/login') {
          document.cookie = `redirect_after_login=${currentPath}; path=/; max-age=300` // 5 minutes
        }
        window.location.href = '/api/auth/logout'
      }
    }
    return Promise.reject(error)
  }
)

// Auth API
export const authAPI = {
  register: async (email: string, password: string, isSubscribed: boolean = false) => {
    const response = await apiClient.post('/auth/register', {
      email,
      password,
      is_subscribed: isSubscribed,
    })
    return response.data
  },
  login: async (email: string, password: string) => {
    const response = await apiClient.post('/auth/login', {
      email,
      password,
    })
    return response.data
  },
  me: async () => {
    const response = await apiClient.get('/auth/me')
    return response.data
  },
}

// RAG API
export const ragAPI = {
  process: async (
    backgrounds: string[],
    marketingText: string,
    options?: {
      assetType?: string
      icp?: string
      templateOverride?: string
      company?: string
    }
  ) => {
    const response = await apiClient.post('/rag/process', {
      backgrounds,
      marketing_text: marketingText,
      asset_type: options?.assetType,
      icp: options?.icp,
      template_override: options?.templateOverride,
      company: options?.company,
    })
    return response.data
  },
  uploadContext: async (files: File[]) => {
    const formData = new FormData()
    files.forEach((file) => {
      formData.append('files', file)
    })
    const response = await apiClient.post('/rag/upload-context', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  },
  getResults: async (jobId: string) => {
    const response = await apiClient.get(`/rag/results/${jobId}`)
    return response.data
  },
  getPromptTemplate: async () => {
    const response = await apiClient.get('/rag/prompt-template')
    return response.data
  },
  getDefaultPromptTemplate: async () => {
    const response = await apiClient.get('/rag/prompt-template/default')
    return response.data
  },
  savePromptTemplate: async (template: string) => {
    const response = await apiClient.post('/rag/prompt-template', {
      template,
    })
    return response.data
  },
  getCompanyData: async (companyName: string) => {
    const response = await apiClient.get(`/rag/company-data/${companyName}`)
    return response.data
  },
}

// Maintenance API (Admin only)
export const maintenanceAPI = {
  getCollections: async () => {
    const response = await apiClient.get('/maintenance/collections')
    return response.data
  },
  createCollection: async (collectionName: string, vectorSize: number, distance: string) => {
    const formData = new FormData()
    formData.append('collection_name', collectionName)
    formData.append('vector_size', vectorSize.toString())
    formData.append('distance', distance)
    const response = await apiClient.post('/maintenance/collections', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  },
  deleteCollection: async (collectionName: string) => {
    const response = await apiClient.delete(`/maintenance/collections/${collectionName}`)
    return response.data
  },
  getCollectionStats: async (collection: string) => {
    const response = await apiClient.get(`/maintenance/collection-stats/${collection}`)
    return response.data
  },
  getRecords: async (collection: string, limit: number = 10, docType?: string) => {
    const response = await apiClient.get(`/maintenance/records/${collection}`, {
      params: { limit, doc_type: docType }
    })
    return response.data
  },
  upsertData: async (dataType: 'reddit' | 'podcast' | 'youtube', files: File[], collection?: string, podcastFormat?: string) => {
    const formData = new FormData()
    files.forEach((file) => {
      formData.append('files', file)
    })
    if (collection) {
      formData.append('collection', collection)
    }
    if (podcastFormat) {
      formData.append('podcast_format', podcastFormat)
    }
    const response = await apiClient.post(`/maintenance/upsert/${dataType}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  },
  // Model testing
  getModels: async (vendor: string) => {
    const response = await apiClient.get('/maintenance/model-test/models', {
      params: { vendor }
    })
    return response.data
  },
  getModelCost: async (vendor: string, model: string) => {
    const response = await apiClient.get('/maintenance/model-test/cost', {
      params: { vendor, model }
    })
    return response.data
  },
  testModel: async (vendor: string, model: string, systemPrompt: string | undefined, prompt: string, placeholders: Record<string, string>) => {
    const response = await apiClient.post('/maintenance/model-test', {
      vendor,
      model,
      system_prompt: systemPrompt || null,
      prompt,
      placeholders
    })
    return response.data
  },
  // Prompts management
  getTemplateNames: async () => {
    const response = await apiClient.get('/maintenance/prompts/template-names')
    return response.data
  },
  getEditors: async (templateName: string) => {
    const response = await apiClient.get('/maintenance/prompts/editors', {
      params: { template_name: templateName }
    })
    return response.data
  },
  getTemplateVersions: async (templateName: string, editedBy?: string) => {
    const response = await apiClient.get('/maintenance/prompts/versions', {
      params: { template_name: templateName, edited_by: editedBy }
    })
    return response.data
  },
  getTemplate: async (templateName: string, editedAtIso: number) => {
    const response = await apiClient.get('/maintenance/prompts/template', {
      params: { template_name: templateName, edited_at_iso: editedAtIso }
    })
    return response.data
  },
  updateTemplate: async (templateName: string, templateBody: string, editComment?: string) => {
    const response = await apiClient.post('/maintenance/prompts/template', {
      template_name: templateName,
      template_body: templateBody,
      edit_comment: editComment || ''
    })
    return response.data
  },
}

export default apiClient


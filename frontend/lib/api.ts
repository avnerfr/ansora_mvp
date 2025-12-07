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
      const token = localStorage.getItem('auth_token')
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

    // For 401s on non-auth endpoints, clear token and redirect to login.
    // This avoids redirect loops when the user simply mistypes their password on /auth/login.
    if (
      status === 401 &&
      url &&
      !url.includes('/auth/login') &&
      !url.includes('/auth/register')
    ) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('auth_token')
        window.location.href = '/auth/login'
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

// Documents API
export const documentsAPI = {
  upload: async (files: File[]) => {
    const formData = new FormData()
    files.forEach((file) => {
      formData.append('files', file)
    })
    const response = await apiClient.post('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  },
  list: async () => {
    const response = await apiClient.get('/documents/list')
    return response.data
  },
}

// RAG API
export const ragAPI = {
  process: async (
    backgrounds: string[],
    marketingText: string,
    options?: {
      tone?: string
      assetType?: string
      icp?: string
      templateOverride?: string
    }
  ) => {
    const response = await apiClient.post('/rag/process', {
      backgrounds,
      marketing_text: marketingText,
      tone: options?.tone,
      asset_type: options?.assetType,
      icp: options?.icp,
      template_override: options?.templateOverride,
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
  savePromptTemplate: async (template: string) => {
    const response = await apiClient.post('/rag/prompt-template', {
      template,
    })
    return response.data
  },
}

export default apiClient


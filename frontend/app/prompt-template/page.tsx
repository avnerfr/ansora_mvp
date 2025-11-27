'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Navbar } from '@/components/Navbar'
import { TextArea } from '@/components/TextArea'
import { Button } from '@/components/Button'
import { ragAPI } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'

export default function PromptTemplatePage() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [template, setTemplate] = useState('')

  // Redirect if not authenticated
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/auth/login')
    }
  }, [router])

  // Fetch current template
  const { data: templateData, isLoading } = useQuery({
    queryKey: ['prompt-template'],
    queryFn: ragAPI.getPromptTemplate,
    enabled: isAuthenticated(),
  })

  // Update local state when template data is loaded
  useEffect(() => {
    if (templateData?.template) {
      setTemplate(templateData.template)
    }
  }, [templateData])

  // Save template mutation
  const saveMutation = useMutation({
    mutationFn: (template: string) => ragAPI.savePromptTemplate(template),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompt-template'] })
      alert('Prompt template saved successfully!')
    },
    onError: (error: any) => {
      alert(
        error.response?.data?.detail ||
          'Failed to save prompt template. Please try again.'
      )
    },
  })

  const handleSave = () => {
    if (!template.trim()) {
      alert('Template cannot be empty')
      return
    }
    saveMutation.mutate(template)
  }

  const handleReset = () => {
    if (templateData?.template) {
      setTemplate(templateData.template)
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Navbar />
        <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading template...</p>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        <div className="space-y-6">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              Edit Prompt Template
            </h1>
            <p className="mt-2 text-gray-600">
              Customize the prompt template used for refining marketing materials.
              Use placeholders: {`{{backgrounds}}, {{marketing_text}}, {{context}}`}
            </p>
          </div>

          <section className="bg-white rounded-lg shadow p-6">
            <TextArea
              label="Prompt Template"
              rows={20}
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              placeholder="Enter your custom prompt template here..."
              className="font-mono text-sm"
            />
          </section>

          <section className="flex justify-end space-x-4">
            <Button variant="secondary" onClick={handleReset}>
              Reset
            </Button>
            <Button
              variant="primary"
              onClick={handleSave}
              isLoading={saveMutation.isPending}
            >
              Save Template
            </Button>
          </section>
        </div>
      </main>
    </div>
  )
}


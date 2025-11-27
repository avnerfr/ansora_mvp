'use client'

import React, { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'

interface FileDropzoneProps {
  onFilesSelected: (files: File[]) => void
  acceptedTypes?: string[]
}

export const FileDropzone: React.FC<FileDropzoneProps> = ({
  onFilesSelected,
  acceptedTypes = [
    'application/pdf',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'image/png',
    'image/jpeg',
    'image/jpg',
    'image/gif',
  ],
}) => {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      onFilesSelected(acceptedFiles)
    },
    [onFilesSelected]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: acceptedTypes.reduce((acc, type) => {
      acc[type] = []
      return acc
    }, {} as Record<string, string[]>),
    multiple: true,
  } as any)

  return (
    <div
      {...getRootProps()}
      className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
        isDragActive
          ? 'border-primary-500 bg-primary-50'
          : 'border-gray-300 hover:border-gray-400'
      }`}
    >
      <input {...getInputProps()} />
      {isDragActive ? (
        <p className="text-primary-600">Drop the files here...</p>
      ) : (
        <div>
          <p className="text-gray-600 mb-2">
            Drag and drop files here, or click to select files
          </p>
          <p className="text-sm text-gray-500">
            Supports: PDF, PowerPoint (PPT/PPTX), Images (PNG, JPG, GIF)
          </p>
        </div>
      )}
    </div>
  )
}


'use client'

import { useState, useCallback, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import { uploadVideo } from '@/lib/api'
import { useI18n } from '@/components/providers/I18nProvider'

interface UploadAreaProps {
  onUploadSuccess: () => void
}

interface UploadState {
  [filename: string]: {
    isUploading: boolean
    progress: number
    videoId?: string
    sessionId?: string
    abortController?: AbortController
  }
}

export function UploadArea({ onUploadSuccess }: UploadAreaProps) {
  const { t } = useI18n()
  const [uploadState, setUploadState] = useState<UploadState>({})

  const handleUpload = useCallback(async (file: File) => {
    const filename = file.name
    
    // Create abort controller for this upload
    const abortController = new AbortController()
    
    // Initialize upload state
    setUploadState(prev => ({
      ...prev,
      [filename]: {
        isUploading: true,
        progress: 0,
        abortController
      }
    }))

    try {
      await uploadVideo(file, {
        signal: abortController.signal,
        onProgress: (progress) => {
          setUploadState(prev => ({
            ...prev,
            [filename]: {
              ...prev[filename],
              progress
            }
          }))
        }
      })

      // Upload completed successfully
      setUploadState(prev => {
        const newState = { ...prev }
        delete newState[filename]
        return newState
      })

      onUploadSuccess()

    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.log('Upload cancelled:', filename)
      } else {
        console.error('Upload failed:', filename, error)
      }
      
      // Remove from upload state
      setUploadState(prev => {
        const newState = { ...prev }
        delete newState[filename]
        return newState
      })
    }
  }, [onUploadSuccess])

  const cancelUpload = useCallback((filename: string) => {
    const uploadInfo = uploadState[filename]
    if (uploadInfo?.abortController) {
      uploadInfo.abortController.abort()
    }
  }, [uploadState])

  const onDrop = useCallback((acceptedFiles: File[]) => {
    acceptedFiles.forEach(handleUpload)
  }, [handleUpload])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'video/*': ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
    },
    multiple: true,
    disabled: false // Allow new uploads even if others are in progress
  })

  return (
    <div className="space-y-4">
      {/* Drop Zone */}
      <div
        {...getRootProps()}
        className={`
          border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
          ${isDragActive 
            ? 'border-primary bg-primary/5' 
            : 'border-gray-300 dark:border-gray-600 hover:border-primary hover:bg-primary/5'
          }
        `}
      >
        <input {...getInputProps()} />
        <div className="space-y-2">
          <svg
            className="mx-auto h-12 w-12 text-gray-400"
            stroke="currentColor"
            fill="none"
            viewBox="0 0 48 48"
          >
            <path
              d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <div>
            <p className="text-sm font-medium">
              {isDragActive 
                ? t('dashboard.upload.dropActive') 
                : t('dashboard.upload.dropZone')
              }
            </p>
            <p className="text-xs text-gray-500">
              {t('dashboard.upload.supportedFormats')}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

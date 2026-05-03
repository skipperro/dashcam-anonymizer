/**
 * API client for frontend-backend communication
 */

import { ContactFormData, ContactResponse, VideoInfo, UploadResponse, ProgressResponse, DeleteResponse, ProcessingSettings, UploadInitiateResponse, ChunkUploadResponse, UploadCompleteResponse, UploadProgressUpdate } from '@/types'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

class ApiError extends Error {
  constructor(
    public status: number,
    public message: string,
    public details?: any
  ) {
    super(message)
  }
}

async function handleApiResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}: ${response.statusText}`
    let errorDetails = null
    
    try {
      const errorData = await response.json()
      errorMessage = errorData.message || errorMessage
      errorDetails = errorData.details
    } catch {
      // If we can't parse JSON, use the status text
    }
    
    throw new ApiError(response.status, errorMessage, errorDetails)
  }
  
  return response.json()
}

export const api = {
  contact: {
    async send(data: ContactFormData): Promise<ContactResponse> {
      const response = await fetch(`${API_BASE_URL}/contact`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      })
      
      return handleApiResponse<ContactResponse>(response)
    },
  },

  // Video management endpoints
  videos: {
    async upload(file: File, settings: ProcessingSettings): Promise<UploadResponse> {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('settings', JSON.stringify(settings))

      const response = await fetch(`${API_BASE_URL}/videos/upload`, {
        method: 'POST',
        body: formData,
      })
      
      return handleApiResponse<UploadResponse>(response)
    },

    async list(params?: { page?: number; per_page?: number; status?: string }) {
      const searchParams = new URLSearchParams()
      
      if (params?.page) searchParams.append('page', params.page.toString())
      if (params?.per_page) searchParams.append('per_page', params.per_page.toString())
      if (params?.status) searchParams.append('status', params.status)

      const response = await fetch(`${API_BASE_URL}/videos?${searchParams}`)
      
      return handleApiResponse(response)
    },

    async getProgress(videoId: string): Promise<ProgressResponse> {
      const response = await fetch(`${API_BASE_URL}/videos/${videoId}/progress`)
      
      return handleApiResponse<ProgressResponse>(response)
    },

    async getThumbnail(videoId: string): Promise<string> {
      try {
        const response = await fetch(`${API_BASE_URL}/videos/${videoId}/thumbnail`, {
          method: 'GET'
        })
        
        if (response.ok) {
          // Backend now returns JSON with the pre-signed URL
          const data = await response.json()
          
          if (data.thumbnail_url) {
            return data.thumbnail_url
          } else {
            throw new ApiError(500, 'Invalid thumbnail response format')
          }
        }
        
        if (response.status === 404) {
          throw new ApiError(404, 'Thumbnail not yet available')
        }
        
        throw new ApiError(response.status, `Failed to get thumbnail (status: ${response.status})`)
      } catch (error) {
        if (error instanceof ApiError) {
          throw error
        }
        throw new ApiError(500, `Network error: ${error instanceof Error ? error.message : 'Unknown error'}`)
      }
    },

    async delete(videoId: string): Promise<DeleteResponse> {
      const response = await fetch(`${API_BASE_URL}/videos/${videoId}`, {
        method: 'DELETE'
      })
      
      return handleApiResponse<DeleteResponse>(response)
    },
  },

  // Health check
  health: async () => {
    const response = await fetch(`${API_BASE_URL}/health`)
    return handleApiResponse(response)
  },
}

// Export individual functions for easier imports
export const sendContactForm = api.contact.send

// Chunked upload API functions
export async function initiateUpload(file: File): Promise<UploadInitiateResponse> {
  const formData = new FormData()
  formData.append('filename', file.name)
  formData.append('file_size', file.size.toString())

  const response = await fetch(`${API_BASE_URL}/videos/upload/initiate`, {
    method: 'POST',
    body: formData,
  })
  
  return handleApiResponse<UploadInitiateResponse>(response)
}

export async function uploadChunk(
  sessionId: string, 
  chunkNumber: number, 
  chunkData: Blob,
  signal?: AbortSignal
): Promise<ChunkUploadResponse> {
  const formData = new FormData()
  formData.append('chunk_data', chunkData)

  const response = await fetch(`${API_BASE_URL}/videos/upload/chunk/${sessionId}/${chunkNumber}`, {
    method: 'POST',
    body: formData,
    signal,
  })
  
  return handleApiResponse<ChunkUploadResponse>(response)
}

export async function completeUpload(sessionId: string): Promise<UploadCompleteResponse> {
  const response = await fetch(`${API_BASE_URL}/videos/upload/complete/${sessionId}`, {
    method: 'POST',
  })
  
  return handleApiResponse<UploadCompleteResponse>(response)
}

export async function cancelUpload(sessionId: string): Promise<void> {
  // For now, we'll just abandon the session
  // Backend will clean up incomplete sessions periodically
  console.log('Cancelling upload session:', sessionId)
}

// WebSocket connection for real-time progress
export class UploadProgressWebSocket {
  private ws: WebSocket | null = null
  private userId: string
  private onProgress: (update: UploadProgressUpdate) => void
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000

  constructor(userId: string, onProgress: (update: UploadProgressUpdate) => void) {
    this.userId = userId
    this.onProgress = onProgress
  }

  connect(): void {
    const wsUrl = `${API_BASE_URL.replace('http', 'ws')}/videos/ws/${this.userId}`
    
    try {
      this.ws = new WebSocket(wsUrl)
      
      this.ws.onopen = () => {
        console.log('WebSocket connected for upload progress')
        this.reconnectAttempts = 0
        // Send ping to keep connection alive
        setInterval(() => {
          if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send('ping')
          }
        }, 30000)
      }
      
      this.ws.onmessage = (event) => {
        try {
          if (event.data === 'pong') return // Ignore pong responses
          
          const update: UploadProgressUpdate = JSON.parse(event.data)
          this.onProgress(update)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }
      
      this.ws.onclose = () => {
        console.log('WebSocket disconnected')
        this.reconnect()
      }
      
      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error)
    }
  }

  private reconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      console.log(`Attempting to reconnect WebSocket (${this.reconnectAttempts}/${this.maxReconnectAttempts})`)
      
      setTimeout(() => {
        this.connect()
      }, this.reconnectDelay * this.reconnectAttempts)
    }
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }
}

// Enhanced chunked upload function
export async function uploadVideo(
  file: File, 
  options?: { 
    onProgress?: (progress: number) => void
    signal?: AbortSignal 
  }
): Promise<UploadResponse> {
  try {
    // Initiate chunked upload
    const initResponse = await initiateUpload(file)
    const { session_id, chunk_size, total_chunks, video_id } = initResponse
    
    console.log('Upload initiated:', initResponse)
    
    // Upload chunks
    for (let chunkNumber = 0; chunkNumber < total_chunks; chunkNumber++) {
      // Check if cancelled
      if (options?.signal?.aborted) {
        await cancelUpload(session_id)
        throw new Error('Upload cancelled')
      }
      
      // Create chunk
      const start = chunkNumber * chunk_size
      const end = Math.min(start + chunk_size, file.size)
      const chunkData = file.slice(start, end)
      
      // Upload chunk
      const chunkResponse = await uploadChunk(session_id, chunkNumber, chunkData, options?.signal)
      
      // Report progress
      if (options?.onProgress) {
        options.onProgress(chunkResponse.progress_percentage)
      }
      
      console.log(`Chunk ${chunkNumber + 1}/${total_chunks} uploaded (${chunkResponse.progress_percentage}%)`)
    }
    
    // Complete upload
    const completeResponse = await completeUpload(session_id)
    console.log('Upload completed:', completeResponse)
    
    return {
      video_id: completeResponse.video_id,
      status: completeResponse.status,
      message: completeResponse.message
    }
    
  } catch (error) {
    console.error('Chunked upload failed:', error)
    throw error
  }
}

export async function listVideos(): Promise<VideoInfo[]> {
  const response = await fetch(`${API_BASE_URL}/videos`)
  const result = await handleApiResponse<{videos: VideoInfo[]}>(response)
  
  // Console logging to debug the videos endpoint response
  console.log('=== /videos endpoint response ===')
  console.log('Full response:', result)
  console.log('Videos array:', result.videos)
  console.log('Total videos:', result.videos?.length || 0)
  
  if (result.videos && result.videos.length > 0) {
    console.log('Video statuses:')
    result.videos.forEach((video, index) => {
      console.log(`  ${index + 1}. ${video.filename} - Status: ${video.status}, Progress: ${video.upload_progress}%`)
    })
    
    const uploadingVideos = result.videos.filter(v => v.status === 'uploading')
    console.log(`Found ${uploadingVideos.length} uploading videos:`, uploadingVideos)
  }
  console.log('================================')
  
  return result.videos || []
}

export async function getThumbnail(videoId: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/videos/${videoId}/thumbnail`)
  
  if (!response.ok) {
    throw new ApiError(response.status, 'Failed to get thumbnail')
  }
  
  return response.blob()
}

export async function deleteVideo(videoId: string): Promise<DeleteResponse> {
  const response = await fetch(`${API_BASE_URL}/videos/${videoId}`, {
    method: 'DELETE'
  })
  
  if (!response.ok) {
    throw new ApiError(response.status, 'Failed to delete video')
  }
  
  return response.json()
}

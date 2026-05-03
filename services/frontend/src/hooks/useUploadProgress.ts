'use client'

import { useEffect, useRef, useState } from 'react'
import { UploadProgressWebSocket, UploadProgressUpdate } from '@/lib/api'

interface UploadProgressState {
  [videoId: string]: {
    progress: number
    status?: string
    timestamp: string
  }
}

export function useUploadProgress(userId: string = 'anonymous') {
  const [progressState, setProgressState] = useState<UploadProgressState>({})
  const wsRef = useRef<UploadProgressWebSocket | null>(null)

  useEffect(() => {
    // Create WebSocket connection
    const handleProgressUpdate = (update: UploadProgressUpdate) => {
      setProgressState(prev => ({
        ...prev,
        [update.video_id]: {
          progress: update.progress,
          status: update.status,
          timestamp: update.timestamp
        }
      }))
    }

    wsRef.current = new UploadProgressWebSocket(userId, handleProgressUpdate)
    wsRef.current.connect()

    // Cleanup on unmount
    return () => {
      if (wsRef.current) {
        wsRef.current.disconnect()
        wsRef.current = null
      }
    }
  }, [userId])

  // Function to get progress for a specific video
  const getVideoProgress = (videoId: string) => {
    return progressState[videoId]
  }

  // Function to remove completed uploads from state
  const clearVideoProgress = (videoId: string) => {
    setProgressState(prev => {
      const newState = { ...prev }
      delete newState[videoId]
      return newState
    })
  }

  return {
    progressState,
    getVideoProgress,
    clearVideoProgress
  }
}

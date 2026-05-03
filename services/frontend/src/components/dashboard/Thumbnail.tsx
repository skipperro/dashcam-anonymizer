'use client'

import { useState, useEffect, useCallback } from 'react'
import ThumbnailService, { ThumbnailState } from '@/lib/thumbnailService'

interface ThumbnailProps {
  videoId: string
  className?: string
  fallbackClassName?: string
  onLoad?: () => void
  onError?: (error: string) => void
}

export default function Thumbnail({ 
  videoId, 
  className = '',
  fallbackClassName = '',
  onLoad,
  onError
}: ThumbnailProps) {
  const [state, setState] = useState<ThumbnailState>({
    url: null,
    loading: true,
    error: null,
    retryCount: 0,
    nextRetryIn: 0,
    maxRetriesReached: false
  })

  const [retryTimeout, setRetryTimeout] = useState<NodeJS.Timeout | null>(null)

  const fetchThumbnail = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }))
    
    try {
      const result = await ThumbnailService.fetchThumbnail(videoId)
      setState(result)
      
      if (result.url) {
        onLoad?.()
      } else if (result.error) {
        onError?.(result.error)
        
        // Schedule retry if there's a retry delay and max retries not reached
        if (result.nextRetryIn > 0 && !result.maxRetriesReached) {
          const timeout = setTimeout(() => {
            fetchThumbnail()
          }, result.nextRetryIn)
          setRetryTimeout(timeout)
        }
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to load thumbnail'
      setState({
        url: null,
        loading: false,
        error: errorMessage,
        retryCount: 0,
        nextRetryIn: 10000, // Fallback retry in 10 seconds
        maxRetriesReached: false
      })
      onError?.(errorMessage)
    }
  }, [videoId, onLoad, onError])

  useEffect(() => {
    fetchThumbnail()
    
    // Cleanup timeout on unmount
    return () => {
      if (retryTimeout) {
        clearTimeout(retryTimeout)
      }
    }
  }, [fetchThumbnail])

  // Cleanup timeout when videoId changes
  useEffect(() => {
    if (retryTimeout) {
      clearTimeout(retryTimeout)
      setRetryTimeout(null)
    }
  }, [videoId])

  // Handle retry manually (for user-triggered refresh)
  const handleRetry = useCallback(() => {
    if (retryTimeout) {
      clearTimeout(retryTimeout)
      setRetryTimeout(null)
    }
    fetchThumbnail()
  }, [fetchThumbnail])

  if (state.loading) {
    return (
      <div className={`${className} ${fallbackClassName} flex items-center justify-center bg-gray-200 dark:bg-gray-700`}>
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  if (state.url) {
    return (
      <img
        src={state.url}
        alt={`Video ${videoId} thumbnail`}
        className={className}
        onError={(e) => {
          // If the cached URL fails to load, clear cache and retry
          ThumbnailService.clearCache(videoId)
          fetchThumbnail()
        }}
      />
    )
  }

  // Show fallback for error state - clean placeholder without text
  return (
    <div className={`${className} ${fallbackClassName} flex items-center justify-center bg-gray-200 dark:bg-gray-700 text-gray-400 dark:text-gray-500`}>
      <svg 
        className="w-8 h-8" 
        fill="none" 
        stroke="currentColor" 
        viewBox="0 0 24 24"
      >
        <path 
          strokeLinecap="round" 
          strokeLinejoin="round" 
          strokeWidth={2} 
          d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" 
        />
      </svg>
    </div>
  )
}

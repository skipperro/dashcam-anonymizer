/**
 * Thumbnail service with caching and retry logic
 */

import { api } from './api'
import ThumbnailCache from './thumbnailCache'

export interface ThumbnailState {
  url: string | null
  loading: boolean
  error: string | null
  retryCount: number
  nextRetryIn: number
  maxRetriesReached: boolean
}

export class ThumbnailService {
  /**
   * Fetch thumbnail with caching and exponential backoff retry logic
   */
  static async fetchThumbnail(videoId: string): Promise<ThumbnailState> {
    // Check cache first
    const cachedUrl = ThumbnailCache.getCachedThumbnail(videoId)
    if (cachedUrl) {
      return {
        url: cachedUrl,
        loading: false,
        error: null,
        retryCount: 0,
        nextRetryIn: 0,
        maxRetriesReached: false
      }
    }

    // Get current retry information
    const retryInfo = this.getRetryInfo(videoId)

    // Check if we should retry
    if (!ThumbnailCache.shouldRetry(videoId)) {
      const nextRetryIn = ThumbnailCache.getTimeUntilNextRetry(videoId)
      return {
        url: null,
        loading: false,
        error: retryInfo.maxRetriesReached ? 'Thumbnail unavailable after 10 attempts' : 'Thumbnail not yet available',
        retryCount: retryInfo.retryCount,
        nextRetryIn,
        maxRetriesReached: retryInfo.maxRetriesReached
      }
    }

    try {
      // Attempt to fetch thumbnail
      const redirectUrl = await api.videos.getThumbnail(videoId)
      
      // Cache the URL
      ThumbnailCache.cacheThumbnail(videoId, redirectUrl)
      
      return {
        url: redirectUrl,
        loading: false,
        error: null,
        retryCount: 0,
        nextRetryIn: 0,
        maxRetriesReached: false
      }
      
    } catch (error: any) {
      // Record failed attempt
      ThumbnailCache.recordFailedAttempt(videoId)
      
      // Get updated retry information
      const updatedRetryInfo = this.getRetryInfo(videoId)
      const nextRetryIn = ThumbnailCache.getTimeUntilNextRetry(videoId)
      
      if (error.status === 404) {
        return {
          url: null,
          loading: false,
          error: updatedRetryInfo.maxRetriesReached ? 'Thumbnail unavailable after 10 attempts' : 'Thumbnail not yet available',
          retryCount: updatedRetryInfo.retryCount,
          nextRetryIn,
          maxRetriesReached: updatedRetryInfo.maxRetriesReached
        }
      }
      
      return {
        url: null,
        loading: false,
        error: updatedRetryInfo.maxRetriesReached ? 'Thumbnail unavailable after 10 attempts' : (error.message || 'Failed to load thumbnail'),
        retryCount: updatedRetryInfo.retryCount,
        nextRetryIn,
        maxRetriesReached: updatedRetryInfo.maxRetriesReached
      }
    }
  }

  /**
   * Get retry information for a video
   */
  private static getRetryInfo(videoId: string): { retryCount: number; maxRetriesReached: boolean } {
    try {
      const requestKey = 'thumbnail_request_' + videoId
      const cached = localStorage.getItem(requestKey)
      
      if (!cached) {
        return { retryCount: 0, maxRetriesReached: false }
      }
      
      const request = JSON.parse(cached)
      return {
        retryCount: request.retryCount || 0,
        maxRetriesReached: (request.retryCount || 0) >= 10
      }
    } catch (error) {
      return { retryCount: 0, maxRetriesReached: false }
    }
  }

  /**
   * Clean up expired cache entries
   */
  static cleanup(): void {
    ThumbnailCache.cleanup()
  }

  /**
   * Clear cache for specific video (and reset retry tracking)
   */
  static clearCache(videoId: string): void {
    ThumbnailCache.removeCachedThumbnail(videoId)
    ThumbnailCache.clearRetryTracking(videoId)
  }

  /**
   * Refresh thumbnail (force refetch)
   */
  static async refreshThumbnail(videoId: string): Promise<ThumbnailState> {
    this.clearCache(videoId)
    return this.fetchThumbnail(videoId)
  }
}

export default ThumbnailService

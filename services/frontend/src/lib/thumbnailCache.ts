/**
 * Thumbnail caching utility with localStorage and retry logic
 */

interface CachedThumbnail {
  url: string
  expiresAt: number
  videoId: string
}

interface ThumbnailRequest {
  videoId: string
  retryCount: number
  lastAttempt: number
}

class ThumbnailCache {
  private static readonly CACHE_KEY_PREFIX = 'thumbnail_cache_'
  private static readonly REQUEST_KEY_PREFIX = 'thumbnail_request_'
  private static readonly CACHE_DURATION = 10 * 60 * 1000 // 10 minutes
  private static readonly BASE_DELAY = 5 * 1000 // Start with 5 seconds
  private static readonly MAX_DELAY = 30 * 1000 // Maximum 30 seconds
  private static readonly MAX_RETRIES = 10 // Maximum 10 retries

  /**
   * Calculate exponential backoff delay for retry attempt
   * Retry pattern: 5s, 7s, 10s, 14s, 18s, 22s, 26s, 28s, 29s, 30s
   */
  private static calculateRetryDelay(retryCount: number): number {
    if (retryCount <= 0) return this.BASE_DELAY
    
    // Exponential backoff with factor 1.4, capped at MAX_DELAY
    const delay = this.BASE_DELAY * Math.pow(1.4, retryCount - 1)
    return Math.min(delay, this.MAX_DELAY)
  }

  /**
   * Get cached thumbnail URL if available and not expired
   */
  static getCachedThumbnail(videoId: string): string | null {
    try {
      const cacheKey = this.CACHE_KEY_PREFIX + videoId
      const cached = localStorage.getItem(cacheKey)
      
      if (!cached) return null
      
      const thumbnail: CachedThumbnail = JSON.parse(cached)
      
      // Check if expired
      if (Date.now() > thumbnail.expiresAt) {
        this.removeCachedThumbnail(videoId)
        return null
      }
      
      return thumbnail.url
    } catch (error) {
      console.warn('Error reading thumbnail cache:', error)
      return null
    }
  }

  /**
   * Cache a thumbnail URL with expiration
   */
  static cacheThumbnail(videoId: string, url: string): void {
    try {
      const cacheKey = this.CACHE_KEY_PREFIX + videoId
      const thumbnail: CachedThumbnail = {
        url,
        expiresAt: Date.now() + this.CACHE_DURATION,
        videoId
      }
      
      localStorage.setItem(cacheKey, JSON.stringify(thumbnail))
      
      // Clear any retry tracking since we got a successful response
      this.clearRetryTracking(videoId)
    } catch (error) {
      console.warn('Error caching thumbnail:', error)
    }
  }

  /**
   * Remove cached thumbnail
   */
  static removeCachedThumbnail(videoId: string): void {
    try {
      const cacheKey = this.CACHE_KEY_PREFIX + videoId
      localStorage.removeItem(cacheKey)
    } catch (error) {
      console.warn('Error removing cached thumbnail:', error)
    }
  }

  /**
   * Check if we should retry fetching a thumbnail
   */
  static shouldRetry(videoId: string): boolean {
    try {
      const requestKey = this.REQUEST_KEY_PREFIX + videoId
      const cached = localStorage.getItem(requestKey)
      
      if (!cached) return true
      
      const request: ThumbnailRequest = JSON.parse(cached)
      
      // Check if we've exceeded max retries
      if (request.retryCount >= this.MAX_RETRIES) {
        return false
      }
      
      // Calculate the delay for the current retry count
      const retryDelay = this.calculateRetryDelay(request.retryCount)
      
      // Check if enough time has passed since last attempt
      return Date.now() - request.lastAttempt >= retryDelay
    } catch (error) {
      console.warn('Error checking retry status:', error)
      return true
    }
  }

  /**
   * Record a failed attempt
   */
  static recordFailedAttempt(videoId: string): void {
    try {
      const requestKey = this.REQUEST_KEY_PREFIX + videoId
      const cached = localStorage.getItem(requestKey)
      
      let request: ThumbnailRequest
      
      if (cached) {
        request = JSON.parse(cached)
        request.retryCount += 1
        request.lastAttempt = Date.now()
      } else {
        request = {
          videoId,
          retryCount: 1,
          lastAttempt: Date.now()
        }
      }
      
      localStorage.setItem(requestKey, JSON.stringify(request))
    } catch (error) {
      console.warn('Error recording failed attempt:', error)
    }
  }

  /**
   * Clear retry tracking (successful fetch or manual clear)
   */
  static clearRetryTracking(videoId: string): void {
    try {
      const requestKey = this.REQUEST_KEY_PREFIX + videoId
      localStorage.removeItem(requestKey)
    } catch (error) {
      console.warn('Error clearing retry tracking:', error)
    }
  }

  /**
   * Get time until next retry attempt (in milliseconds)
   */
  static getTimeUntilNextRetry(videoId: string): number {
    try {
      const requestKey = this.REQUEST_KEY_PREFIX + videoId
      const cached = localStorage.getItem(requestKey)
      
      if (!cached) return 0
      
      const request: ThumbnailRequest = JSON.parse(cached)
      
      // Calculate the delay for the current retry count
      const retryDelay = this.calculateRetryDelay(request.retryCount)
      const nextAttemptTime = request.lastAttempt + retryDelay
      
      return Math.max(0, nextAttemptTime - Date.now())
    } catch (error) {
      console.warn('Error calculating retry time:', error)
      return 0
    }
  }

  /**
   * Clean up expired cache entries and old retry tracking
   */
  static cleanup(): void {
    try {
      const keys = Object.keys(localStorage)
      const now = Date.now()
      
      keys.forEach(key => {
        if (key.startsWith(this.CACHE_KEY_PREFIX)) {
          try {
            const cached = localStorage.getItem(key)
            if (cached) {
              const thumbnail: CachedThumbnail = JSON.parse(cached)
              if (now > thumbnail.expiresAt) {
                localStorage.removeItem(key)
              }
            }
          } catch {
            // Remove corrupted entries
            localStorage.removeItem(key)
          }
        } else if (key.startsWith(this.REQUEST_KEY_PREFIX)) {
          try {
            const cached = localStorage.getItem(key)
            if (cached) {
              const request: ThumbnailRequest = JSON.parse(cached)
              // Remove old retry tracking (older than 1 hour)
              if (now - request.lastAttempt > 60 * 60 * 1000) {
                localStorage.removeItem(key)
              }
            }
          } catch {
            // Remove corrupted entries
            localStorage.removeItem(key)
          }
        }
      })
    } catch (error) {
      console.warn('Error during cache cleanup:', error)
    }
  }
}

export default ThumbnailCache

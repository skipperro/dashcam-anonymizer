'use client'

import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listVideos, deleteVideo, getDownloadUrl, getProcessingProgress } from '@/lib/api'
import { VideoInfo, ProgressResponse } from '@/types'
import { useI18n } from '@/components/providers/I18nProvider'
import { useToast } from '@/components/providers/ToastProvider'
import { useUploadProgress } from '@/hooks/useUploadProgress'
import Thumbnail from './Thumbnail'

interface VideoListProps {
  refreshTrigger: number
}

interface VideoCardProps {
  video: VideoInfo
  onVideoDeleted: () => void
  realTimeProgress?: {
    progress: number
    status?: string
    timestamp: string
  }
  onCancelUpload?: (videoId: string) => void
}

function VideoCard({ video, onVideoDeleted, realTimeProgress, onCancelUpload }: VideoCardProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const [isDeleting, setIsDeleting] = useState(false)
  const [showConfirmDialog, setShowConfirmDialog] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)

  // WebSocket progress is used ONLY for the upload progress bar (smoother %).
  // Status always comes from the polled API (video.status) to avoid stale WebSocket overrides.
  const currentProgress = realTimeProgress?.progress ?? video.upload_progress
  const currentStatus = video.status

  const isProcessing = currentStatus === 'processing' || currentStatus === 'queued'
  const isProcessingComplete = currentStatus === 'processed' || currentStatus === 'completed'

  // Poll processing progress for videos currently being processed
  const { data: processingProgress } = useQuery<ProgressResponse>({
    queryKey: ['processing-progress', video.video_id],
    queryFn: () => getProcessingProgress(video.video_id),
    enabled: isProcessing,
    refetchInterval: isProcessing ? 3000 : false,
    staleTime: 2000,
  })

  const handleDelete = async () => {
    if (!showConfirmDialog) {
      setShowConfirmDialog(true)
      return
    }

    setIsDeleting(true)
    try {
      await deleteVideo(video.video_id)
      addToast(t('dashboard.videos.deleteSuccess'), 'success')
      onVideoDeleted() // Trigger refresh of the video list
    } catch (error) {
      console.error('Delete failed:', error)
      addToast(t('dashboard.videos.deleteError'), 'error')
    } finally {
      setIsDeleting(false)
      setShowConfirmDialog(false)
    }
  }

  const handleCancelUpload = () => {
    if (onCancelUpload) {
      onCancelUpload(video.video_id)
    }
  }

  const handleDownload = async () => {
    setIsDownloading(true)
    try {
      const { download_url } = await getDownloadUrl(video.video_id)
      // Open pre-signed URL in a new tab so the browser triggers a download
      const link = document.createElement('a')
      link.href = download_url
      link.target = '_blank'
      link.rel = 'noopener noreferrer'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    } catch (error) {
      console.error('Download failed:', error)
      addToast(t('dashboard.videos.downloadError'), 'error')
    } finally {
      setIsDownloading(false)
    }
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'uploading':
        return 'text-blue-600 dark:text-blue-400'
      case 'uploaded':
        return 'text-green-600 dark:text-green-400'
      case 'processing':
        return 'text-yellow-600 dark:text-yellow-400'
      case 'completed':
        return 'text-green-600 dark:text-green-400'
      case 'failed':
        return 'text-red-600 dark:text-red-400'
      default:
        return 'text-gray-600 dark:text-gray-400'
    }
  }

  return (
    <div className={`border rounded-lg p-4 hover:shadow-md transition-shadow ${currentStatus === 'uploading' ? 'border-blue-300 dark:border-blue-600 bg-blue-50 dark:bg-blue-900/20' : 'border-gray-200 dark:border-gray-700'}`}>
      <div className="flex items-start space-x-4">
        {/* Thumbnail */}
        <div className="flex-shrink-0 w-32 h-20 bg-gray-100 dark:bg-gray-800 rounded overflow-hidden">
          <Thumbnail
            videoId={video.video_id}
            className="w-full h-full object-cover"
            fallbackClassName="w-full h-full"
          />
        </div>

        {/* Video Info */}
        <div className="flex-1 min-w-0">
          <h3 className="font-medium truncate" title={video.filename}>
            {video.filename}
          </h3>
          <div className="mt-1 space-y-1 text-sm text-gray-600 dark:text-gray-400">
            <div className="flex items-center space-x-4">
              <span>{formatFileSize(video.file_size)}</span>
              <span>{formatDate(video.upload_date)}</span>
              {/* Hide status text when processing — the progress bar below already communicates it */}
              {!isProcessing && (
                <span className={getStatusColor(currentStatus)}>
                  {t(`dashboard.videos.status.${currentStatus}`) || currentStatus}
                </span>
              )}
            </div>
            
            {/* Show upload progress for uploading videos */}
            {currentStatus === 'uploading' && (
              <div className="space-y-1 mt-2">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-blue-600 dark:text-blue-400">
                    {t('dashboard.videos.uploading')}
                  </span>
                  <span className="text-xs text-blue-600 dark:text-blue-400">
                    {Math.round(currentProgress)}%
                  </span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                  <div
                    className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${Math.min(currentProgress, 100)}%` }}
                  />
                </div>
                  {realTimeProgress && (
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    {t('dashboard.videos.lastUpdate')}: {new Date(realTimeProgress.timestamp).toLocaleTimeString()}
                  </div>
                )}
              </div>
            )}

            {/* Show processing progress for videos being processed */}
            {isProcessing && (
              <div className="space-y-1 mt-2">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-yellow-600 dark:text-yellow-400 font-medium">
                    {currentStatus === 'queued' ? t('dashboard.videos.queued') : t('dashboard.videos.processing')}
                  </span>
                  {processingProgress && processingProgress.progress_percentage > 0 && (
                    <span className="text-xs text-yellow-600 dark:text-yellow-400">
                      {Math.round(processingProgress.progress_percentage)}%
                    </span>
                  )}
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-yellow-500 dark:bg-yellow-400 h-2 rounded-full transition-all duration-500"
                    style={{ width: `${processingProgress && processingProgress.progress_percentage > 0 ? Math.min(processingProgress.progress_percentage, 100) : 0}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex-shrink-0">
          {currentStatus === 'uploading' ? (
            /* Cancel upload button for uploading videos */
            <button
              onClick={handleCancelUpload}
              className="inline-flex items-center justify-center px-3 py-1.5 border border-orange-300 dark:border-orange-600 text-sm font-medium rounded text-orange-700 dark:text-orange-200 bg-orange-50 dark:bg-orange-900/20 hover:bg-orange-100 dark:hover:bg-orange-900/40 transition-colors whitespace-nowrap"
            >
              <svg className="w-4 h-4 mr-1.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
              </svg>
              {t('dashboard.videos.cancel')}
            </button>
          ) : isProcessing ? (
            /* No action allowed while processing — spinner only, no text (label is in progress bar) */
            <div className="inline-flex items-center justify-center w-8 h-8 text-yellow-500 dark:text-yellow-400">
              <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            </div>
          ) : showConfirmDialog ? (
            /* Delete confirmation for completed videos */
            <div className="flex space-x-2">
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="inline-flex items-center justify-center px-3 py-1.5 border border-red-300 dark:border-red-600 text-sm font-medium rounded text-red-700 dark:text-red-200 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors disabled:opacity-50 whitespace-nowrap"
              >
                {isDeleting ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-red-600 mr-1.5"></div>
                ) : (
                  <svg className="w-4 h-4 mr-1.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                )}
                {isDeleting ? t('dashboard.videos.deleting') : t('dashboard.videos.confirm')}
              </button>
              <button
                onClick={() => setShowConfirmDialog(false)}
                disabled={isDeleting}
                className="inline-flex items-center justify-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 whitespace-nowrap"
              >
                {t('dashboard.videos.cancel')}
              </button>
            </div>
          ) : (
            /* Action buttons for non-uploading, non-confirming state */
            <div className="flex flex-col space-y-2">
              {/* Download button — only visible when processing is complete */}
              {isProcessingComplete && (
                <button
                  onClick={handleDownload}
                  disabled={isDownloading}
                  className="inline-flex items-center justify-center px-3 py-1.5 border border-green-300 dark:border-green-600 text-sm font-medium rounded text-green-700 dark:text-green-200 bg-green-50 dark:bg-green-900/20 hover:bg-green-100 dark:hover:bg-green-900/40 transition-colors disabled:opacity-50 whitespace-nowrap"
                >
                  {isDownloading ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-green-600 mr-1.5"></div>
                  ) : (
                    <svg className="w-4 h-4 mr-1.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                  )}
                  {isDownloading ? t('dashboard.videos.downloading') : t('dashboard.videos.download')}
                </button>
              )}
              {/* Delete button */}
              <button
                onClick={handleDelete}
                className="inline-flex items-center justify-center px-3 py-1.5 border border-red-300 dark:border-red-600 text-sm font-medium rounded text-red-700 dark:text-red-200 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors whitespace-nowrap"
              >
                <svg className="w-4 h-4 mr-1.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z" clipRule="evenodd" />
                </svg>
                {t('dashboard.videos.delete')}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function VideoList({ refreshTrigger }: VideoListProps) {
  const { t } = useI18n()
  const { progressState, getVideoProgress, clearVideoProgress } = useUploadProgress()

  const { data: videos, isLoading, error, refetch } = useQuery({
    queryKey: ['videos', refreshTrigger],
    queryFn: listVideos,
    // Poll fast while videos are actively uploading/processing, slow otherwise
    refetchInterval: (query) => {
      const data = query.state.data as VideoInfo[] | undefined
      if (!data || !Array.isArray(data)) return 3000
      const hasActiveVideos = data.some(v => ['uploading', 'processing'].includes(v.status))
      return hasActiveVideos ? 3000 : 15000
    },
    placeholderData: [],           // Show empty list while first fetch is in-flight (not cached)
  })

  // Clear stale WebSocket progress entries when a video is no longer uploading
  useEffect(() => {
    if (!videos) return
    videos.forEach((video) => {
      if (video.status !== 'uploading' && progressState[video.video_id]) {
        clearVideoProgress(video.video_id)
      }
    })
  }, [videos, progressState, clearVideoProgress])

  useEffect(() => {
    refetch()
  }, [refreshTrigger, refetch])

  const handleCancelUpload = (videoId: string) => {
    // TODO: Implement proper upload cancellation via API
    console.log('Cancel upload for video:', videoId)
    clearVideoProgress(videoId)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-600 dark:text-red-400">
          {t('dashboard.videos.errorLoading')}
        </p>
        <button
          onClick={() => refetch()}
          className="mt-2 text-sm text-primary hover:underline"
        >
          {t('dashboard.videos.retry')}
        </button>
      </div>
    )
  }

  if (!videos || videos.length === 0) {
    return (
      <div className="text-center py-12">
        <svg className="mx-auto h-12 w-12 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
          <path d="M2 6a2 2 0 012-2h6l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
        </svg>
        <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">
          {t('dashboard.videos.noVideos')}
        </h3>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {t('dashboard.videos.uploadFirst')}
        </p>
      </div>
    )
  }

  // Sort videos: uploading videos first, then by upload date (newest first)
  const sortedVideos = [...videos].sort((a, b) => {
    // First priority: uploading videos go to top
    if (a.status === 'uploading' && b.status !== 'uploading') return -1
    if (b.status === 'uploading' && a.status !== 'uploading') return 1
    
    // Second priority: sort by upload date (newest first)
    return new Date(b.upload_date).getTime() - new Date(a.upload_date).getTime()
  })

  return (
    <div className="space-y-4">
      {sortedVideos.map((video: VideoInfo) => (
        <VideoCard 
          key={video.video_id} 
          video={video} 
          onVideoDeleted={refetch}
          realTimeProgress={getVideoProgress(video.video_id)}
          onCancelUpload={handleCancelUpload}
        />
      ))}
    </div>
  )
}

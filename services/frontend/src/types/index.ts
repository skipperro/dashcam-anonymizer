import { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react'

// API Types
export interface ContactFormData {
  name: string
  email: string
  subject: string
  message: string
}

export interface ContactResponse {
  success: boolean
  message: string
}

export interface ListParams {
  page?: number
  per_page?: number
  status?: 'uploading' | 'processing' | 'completed' | 'failed'
}

export interface VideoListResponse {
  videos: Video[]
  total: number
  page: number
  per_page: number
  has_next: boolean
  has_prev: boolean
}

export interface VideoInfo {
  video_id: string
  filename: string
  upload_date: string
  status: string
  upload_progress: number
  file_size: number
  duration_seconds?: number
  thumbnail_available: boolean
  thumbnail_url?: string
}

export interface Video {
  video_id: string
  filename: string
  upload_date: string
  status: 'uploading' | 'processing' | 'completed' | 'failed'
  progress_percentage: number
  file_size: number
  duration_seconds?: number
  thumbnail_url?: string
  download_url?: string
  error_message?: string
}

export interface ProcessingSettings {
  yolo_classes: number[]
  model_size: 'small' | 'medium' | 'large'
  detection_type: 'bbox' | 'segmentation'
  blur_intensity: number
  frame_sampling: number
  processing_resolution: number
  temporal_stability_enabled: boolean
  enable_hood_detection: boolean
}

export interface VideoInfo {
  video_id: string
  filename: string
  upload_date: string
  status: string
  upload_progress: number
  processing_progress: number
  file_size: number
  duration_seconds?: number
  thumbnail_available: boolean
  thumbnail_url?: string
}

export interface UploadResponse {
  video_id: string
  status: string
  message: string
}

// Chunked Upload Types
export interface UploadInitiateResponse {
  video_id: string
  session_id: string
  chunk_size: number
  total_chunks: number
  status: string
  message: string
}

export interface ChunkUploadResponse {
  session_id: string
  chunk_number: number
  status: string
  progress_percentage: number
  message: string
}

export interface UploadCompleteResponse {
  video_id: string
  session_id: string
  status: string
  file_size: number
  message: string
}

export interface UploadProgressUpdate {
  type: 'upload_progress'
  video_id: string
  progress: number
  status?: string
  timestamp: string
}

export interface ProgressResponse {
  video_id: string
  status: string
  progress_percentage: number
  current_frame?: number
  total_frames?: number
  estimated_time_remaining?: number
  error_message?: string
}

export interface DeleteResponse {
  video_id: string
  message: string
}

export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy'
  database: boolean
  storage: boolean
  workers_active: number
  version: string
}

// WebSocket Types
export interface ProgressUpdateEvent {
  type: 'progress_update'
  video_id: string
  progress_percentage: number
  current_frame?: number
  total_frames?: number
  estimated_time_remaining?: number
}

export interface ProcessingCompleteEvent {
  type: 'processing_complete'
  video_id: string
  status: 'completed' | 'failed'
  download_url?: string
  error_message?: string
}

export type WebSocketEvent = ProgressUpdateEvent | ProcessingCompleteEvent

// UI Component Types
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
}

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
}

export interface ProgressBarProps {
  value: number
  max?: number
  label?: string
  showPercentage?: boolean
  className?: string
}

// Form Types
export interface FileUploadProps {
  onFileSelect: (file: File) => void
  accept: string
  maxSize: number
  disabled?: boolean
}

export interface ProcessingSettingsFormProps {
  initialValues?: Partial<ProcessingSettings>
  onSubmit: (settings: ProcessingSettings) => void
  disabled?: boolean
}

export interface ContactFormProps {
  onSubmit: (data: ContactFormData) => Promise<void>
  loading?: boolean
}

// Navigation Types
export interface HeaderProps {
  showNavigation?: boolean
}

export interface LanguageSelectorProps {
  currentLanguage: string
  onLanguageChange: (language: string) => void
}

// Dashboard Types
export interface VideoListProps {
  videos: Video[]
  loading: boolean
  onDelete: (videoId: string) => void
  onDownload: (videoId: string) => void
  onReprocess: (videoId: string) => void
}

export interface UploadAreaProps {
  onUpload: (file: File, settings: ProcessingSettings) => void
  processing: boolean
  maxFileSize: number
  allowedFormats: string[]
}

// Theme Types
export type Theme = 'light' | 'dark'

export interface ThemeContextType {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

// Language Types
export type Language = 'en' | 'pl' | 'de'

export interface LanguageOption {
  code: Language
  name: string
  flag: string
}

// Store Types
export interface AppState {
  theme: Theme
  language: Language
  setTheme: (theme: Theme) => void
  setLanguage: (language: Language) => void
}

export interface VideoState {
  videos: Video[]
  loading: boolean
  uploadProgress: Record<string, number>
  addVideo: (video: Video) => void
  updateVideo: (videoId: string, updates: Partial<Video>) => void
  updateProgress: (videoId: string, progress: number) => void
  removeVideo: (videoId: string) => void
  setLoading: (loading: boolean) => void
}

// Error Types
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public details?: any
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

// Utility Types
export interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
}

export interface OptimizedImageProps {
  src: string
  alt: string
  width: number
  height: number
  priority?: boolean
}

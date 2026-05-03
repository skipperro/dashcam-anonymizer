# Frontend Service Specification - MVP

## Overview
The frontend is a Single Page Application (SPA) built with React + Next.js that serves as both a marketing website and user dashboard for the Dashcam Anonymizer system. It provides a static export that can be hosted in a Docker container while communicating with the FastAPI backend for dynamic functionality.

## Core Requirements

### MVP Features
- **Homepage**: Landing page with product information and call-to-action
- **Contact Form**: Contact form for user inquiries 
- **Dashboard**: File upload and video management dashboard (no authentication required)
- **Multi-language Support**: Internationalization with easy translation management
- **Theme System**: Light/dark mode toggle with purple color scheme
- **Real-time Updates**: Live progress tracking via WebSocket
- **Responsive Design**: Mobile-first responsive layout
- **Accessibility**: WCAG 2.1 AA compliance

### Technical Requirements
- **Static Export**: Deploy as static files in Docker container
- **SEO Optimized**: Server-side generation for marketing pages
- **Performance**: Code splitting and lazy loading
- **Type Safety**: Full TypeScript implementation
- **Error Handling**: Graceful error boundaries and user feedback

## Architecture and Technology Stack

### Technology Stack
- **Framework**: Next.js 14+ with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS + Headless UI
- **State Management**: Zustand + TanStack Query
- **Internationalization**: next-i18next for multi-language support
- **Theme System**: next-themes for light/dark mode with purple color scheme
- **File Upload**: react-dropzone + custom progress tracking
- **Real-time**: Native WebSocket API
- **Forms**: React Hook Form + Zod validation
- **Icons**: Lucide React
- **Build**: Static export (`output: 'export'`)

### Project Structure
```
src/
├── app/                    # Next.js App Router
│   ├── (marketing)/       # Marketing pages group
│   │   ├── page.tsx       # Homepage
│   │   ├── contact/       # Contact page
│   │   └── layout.tsx     # Marketing layout
│   ├── dashboard/         # Dashboard pages (no auth required)
│   │   ├── page.tsx       # Dashboard home
│   │   ├── upload/        # Upload page
│   │   └── layout.tsx     # Dashboard layout
│   ├── globals.css        # Global styles
│   └── layout.tsx         # Root layout
├── components/            # Reusable components
│   ├── ui/               # Base UI components
│   ├── forms/            # Form components
│   ├── dashboard/        # Dashboard-specific components
│   ├── marketing/        # Marketing components
│   └── theme/            # Theme and language switchers
├── lib/                  # Utilities and configurations
│   ├── api.ts           # API client
│   ├── websocket.ts     # WebSocket client
│   ├── i18n.ts          # Internationalization config
│   └── utils.ts         # Utility functions
├── stores/              # Zustand stores
├── types/               # TypeScript type definitions
├── hooks/               # Custom React hooks
├── locales/             # Translation files
│   ├── en/              # English translations
│   ├── pl/              # Polish translations
│   └── de/              # German translations
└── styles/              # Theme configurations
```

## API Integration

### Backend API Client
```typescript
// lib/api.ts
interface ApiClient {
  // Video Management (no authentication required)
  videos: {
    list(params?: ListParams): Promise<VideoListResponse>
    upload(file: File, settings: ProcessingSettings): Promise<UploadResponse>
    getProgress(videoId: string): Promise<ProgressResponse>
    download(videoId: string): Promise<string>
    delete(videoId: string): Promise<void>
  }
  
  // Contact
  contact: {
    send(data: ContactFormData): Promise<ContactResponse>
  }
  
  // System
  health(): Promise<HealthResponse>
}
```

### API Request/Response Schemas

#### Contact Form
```typescript
// POST /contact
interface ContactFormData {
  name: string
  email: string
  subject: string
  message: string
}

interface ContactResponse {
  success: boolean
  message: string
}
```

#### Video Management
```typescript
// GET /videos
interface ListParams {
  page?: number
  per_page?: number
  status?: 'uploading' | 'processing' | 'completed' | 'failed'
}

interface VideoListResponse {
  videos: Video[]
  total: number
  page: number
  per_page: number
  has_next: boolean
  has_prev: boolean
}

interface Video {
  video_id: string
  filename: string
  upload_date: string
  status: 'uploading' | 'processing' | 'completed' | 'failed'
  progress_percentage: number
  file_size: number
  duration_seconds?: number
  thumbnail_url?: string
  download_url?: string
  processing_settings: ProcessingSettings
  error_message?: string
}

// POST /videos/upload
interface ProcessingSettings {
  yolo_classes: number[]
  model_size: 'small' | 'medium' | 'large'
  detection_type: 'bbox' | 'segmentation'
  blur_intensity: number
  frame_sampling: number
  processing_resolution: number
  temporal_stability_enabled: boolean
  enable_hood_detection: boolean
}

interface UploadResponse {
  video_id: string
  upload_url: string
  message: string
}

// GET /videos/{video_id}/progress
interface ProgressResponse {
  video_id: string
  status: string
  progress_percentage: number
  current_frame?: number
  total_frames?: number
  estimated_time_remaining?: number
  error_message?: string
}

// GET /videos/{video_id}/download
interface DownloadResponse {
  download_url: string
  expires_at: string
}
```

#### System
```typescript
// GET /health
interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy'
  database: boolean
  storage: boolean
  workers_active: number
  version: string
}
```

## Page Specifications

### Homepage (`/`)
**Purpose**: Landing page with product information and authentication

**Components**:
- Header with navigation and auth button
- Hero section with value proposition
- Features showcase
- Pricing information
- Footer

**Key Features**:
- Theme toggle (light/dark mode)
- Language selector
- Responsive design
- SEO optimized (meta tags, structured data)
- Call-to-action to dashboard

```typescript
// components/marketing/Hero.tsx
interface HeroProps {
  onNavigateToDashboard: () => void
}

// components/marketing/Features.tsx
interface Feature {
  icon: LucideIcon
  titleKey: string // Translation key instead of direct text
  descriptionKey: string // Translation key instead of direct text
}
```

### Contact Page (`/contact`)
**Purpose**: Contact form for user inquiries

**Components**:
- Contact form with validation
- Company information
- Success/error feedback

**Form Fields**:
- Name (required)
- Email (required, validated)
- Subject (required)
- Message (required, min 10 chars)
- reCAPTCHA (spam protection)

```typescript
// components/forms/ContactForm.tsx
interface ContactFormData {
  name: string
  email: string
  subject: string
  message: string
}

interface ContactFormProps {
  onSubmit: (data: ContactFormData) => Promise<void>
  loading?: boolean
}
```

### Dashboard (`/dashboard`)
**Purpose**: Main dashboard for video upload and management

**Access Control**: No authentication required (testing environment)

**Components**:
- Navigation header with theme and language toggles
- Video list with status
- Upload area
- Progress indicators

**Features**:
- Real-time progress updates via WebSocket
- File drag-and-drop upload
- Video status filtering
- Pagination for large lists
- Download completed videos
- Multi-language interface
- Dark/light theme support

```typescript
// components/dashboard/VideoList.tsx
interface VideoListProps {
  videos: Video[]
  loading: boolean
  onDelete: (videoId: string) => void
  onDownload: (videoId: string) => void
  onReprocess: (videoId: string) => void
}

// components/dashboard/UploadArea.tsx
interface UploadAreaProps {
  onUpload: (file: File, settings: ProcessingSettings) => void
  processing: boolean
  maxFileSize: number
  allowedFormats: string[]
}
```

## Real-time Communication

### WebSocket Integration
```typescript
// lib/websocket.ts
class WebSocketClient {
  private ws: WebSocket | null = null
  private listeners: Map<string, (data: any) => void> = new Map()
  
  connect(userId: string): void
  disconnect(): void
  subscribe(event: string, callback: (data: any) => void): void
  unsubscribe(event: string): void
}

// WebSocket Events
interface ProgressUpdateEvent {
  type: 'progress_update'
  video_id: string
  progress_percentage: number
  current_frame?: number
  total_frames?: number
  estimated_time_remaining?: number
}

interface ProcessingCompleteEvent {
  type: 'processing_complete'
  video_id: string
  status: 'completed' | 'failed'
  download_url?: string
  error_message?: string
}
```

### Usage in Components
```typescript
// hooks/useVideoProgress.ts
export function useVideoProgress(videoId: string) {
  const [progress, setProgress] = useState<ProgressData>()
  
  useEffect(() => {
    const ws = new WebSocketClient()
    ws.connect(userId)
    ws.subscribe('progress_update', (data) => {
      if (data.video_id === videoId) {
        setProgress(data)
      }
    })
    
    return () => ws.disconnect()
  }, [videoId])
  
  return progress
}
```

## Internationalization (i18n)

### Language Support
- **Default Language**: English (en)
- **Additional Languages**: Polish (pl), German (de)
- **Easy Extension**: JSON-based translation files for adding new languages

### Translation Structure
```typescript
// locales/en/common.json
{
  "navigation": {
    "home": "Home",
    "contact": "Contact",
    "dashboard": "Dashboard"
  },
  "theme": {
    "light": "Light mode",
    "dark": "Dark mode",
    "toggle": "Toggle theme"
  },
  "language": {
    "select": "Select language",
    "english": "English",
    "polish": "Polski",
    "german": "Deutsch"
  },
  "homepage": {
    "hero": {
      "title": "Anonymize Your Dashcam Videos",
      "subtitle": "Automatically blur faces and license plates in your dashcam footage",
      "cta": "Try Dashboard"
    },
    "features": {
      "title": "Key Features",
      "ai_detection": "AI-powered object detection",
      "privacy": "Privacy-first approach", 
      "fast": "Fast processing"
    }
  },
  "dashboard": {
    "title": "Video Dashboard",
    "upload": {
      "title": "Upload Video",
      "dragdrop": "Drag and drop your video here",
      "or": "or",
      "browse": "Browse files",
      "formats": "Supported formats: MP4, AVI, MOV, MKV",
      "maxSize": "Maximum file size: 2GB"
    },
    "videos": {
      "title": "Your Videos",
      "status": {
        "uploading": "Uploading",
        "processing": "Processing",
        "completed": "Completed",
        "failed": "Failed"
      },
      "actions": {
        "download": "Download",
        "delete": "Delete",
        "reprocess": "Reprocess"
      }
    }
  },
  "contact": {
    "title": "Contact Us",
    "name": "Name",
    "email": "Email",
    "subject": "Subject", 
    "message": "Message",
    "send": "Send Message",
    "success": "Message sent successfully!",
    "error": "Failed to send message"
  }
}
```

### i18n Configuration
```typescript
// lib/i18n.ts
import { createInstance } from 'i18next'
import resourcesToBackend from 'i18next-resources-to-backend'
import { initReactI18next } from 'react-i18next/initReactI18next'

const initI18next = async (lng: string, ns: string) => {
  const i18nInstance = createInstance()
  await i18nInstance
    .use(initReactI18next)
    .use(resourcesToBackend((language: string, namespace: string) => 
      import(`../locales/${language}/${namespace}.json`)))
    .init({
      lng,
      fallbackLng: 'en',
      supportedLngs: ['en', 'pl', 'de'],
      defaultNS: 'common',
      fallbackNS: 'common',
      ns,
      interpolation: {
        escapeValue: false,
      },
    })
  return i18nInstance
}

export default initI18next
```

### Language Selector Component
```typescript
// components/theme/LanguageSelector.tsx
interface LanguageSelectorProps {
  currentLanguage: string
  onLanguageChange: (language: string) => void
}

export function LanguageSelector({ currentLanguage, onLanguageChange }: LanguageSelectorProps) {
  const { t } = useTranslation('common')
  
  const languages = [
    { code: 'en', name: t('language.english'), flag: '🇺🇸' },
    { code: 'pl', name: t('language.polish'), flag: '🇵🇱' },
    { code: 'de', name: t('language.german'), flag: '🇩🇪' }
  ]
  
  return (
    <Listbox value={currentLanguage} onChange={onLanguageChange}>
      <div className="relative">
        <Listbox.Button className="relative w-full cursor-default rounded-lg bg-white dark:bg-gray-800 py-2 pl-3 pr-10 text-left shadow-md focus:outline-none focus-visible:border-purple-500 focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-opacity-75 focus-visible:ring-offset-2 focus-visible:ring-offset-purple-300 sm:text-sm">
          {/* Language button content */}
        </Listbox.Button>
        <Listbox.Options className="absolute mt-1 max-h-60 w-full overflow-auto rounded-md bg-white dark:bg-gray-800 py-1 text-base shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none sm:text-sm">
          {/* Language options */}
        </Listbox.Options>
      </div>
    </Listbox>
  )
}
```

## Theme System (Purple Color Scheme)

### Theme Configuration
```typescript
// lib/theme.ts
export const themes = {
  light: {
    name: 'light',
    colors: {
      background: '#ffffff',
      foreground: '#0f0f23',
      card: '#ffffff',
      cardForeground: '#0f0f23',
      popover: '#ffffff',
      popoverForeground: '#0f0f23',
      primary: '#8b5cf6', // Purple-500
      primaryForeground: '#ffffff',
      secondary: '#f1f5f9',
      secondaryForeground: '#0f172a',
      muted: '#f1f5f9',
      mutedForeground: '#64748b',
      accent: '#f1f5f9',
      accentForeground: '#0f172a',
      destructive: '#ef4444',
      destructiveForeground: '#ffffff',
      border: '#e2e8f0',
      input: '#e2e8f0',
      ring: '#8b5cf6',
    }
  },
  dark: {
    name: 'dark',
    colors: {
      background: '#0f0f23',
      foreground: '#f8fafc',
      card: '#1e1e2e',
      cardForeground: '#f8fafc',
      popover: '#1e1e2e',
      popoverForeground: '#f8fafc',
      primary: '#a78bfa', // Purple-400 (lighter for dark mode)
      primaryForeground: '#1e1e2e',
      secondary: '#262640',
      secondaryForeground: '#f8fafc',
      muted: '#262640',
      mutedForeground: '#94a3b8',
      accent: '#262640',
      accentForeground: '#f8fafc',
      destructive: '#f87171',
      destructiveForeground: '#1e1e2e',
      border: '#374151',
      input: '#374151',
      ring: '#a78bfa',
    }
  }
} as const
```

### Tailwind CSS Configuration (Purple Theme)
```javascript
// tailwind.config.js
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
          50: '#faf5ff',
          100: '#f3e8ff',
          200: '#e9d5ff',
          300: '#d8b4fe',
          400: '#c084fc',
          500: '#a855f7',
          600: '#9333ea',
          700: '#7c3aed',
          800: '#6b21a8',
          900: '#581c87',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ]
}
```

### Theme Provider
```typescript
// components/providers/ThemeProvider.tsx
'use client'

import { createContext, useContext, useEffect, useState } from 'react'
import { themes } from '@/lib/theme'

type Theme = 'light' | 'dark'

interface ThemeContextType {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>('light')
  
  useEffect(() => {
    const stored = localStorage.getItem('theme') as Theme
    if (stored && ['light', 'dark'].includes(stored)) {
      setTheme(stored)
    } else {
      // Check system preference
      const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
      setTheme(systemTheme)
    }
  }, [])
  
  useEffect(() => {
    const root = document.documentElement
    
    // Remove previous theme classes
    root.classList.remove('light', 'dark')
    
    // Add current theme class
    root.classList.add(theme)
    
    // Apply CSS custom properties
    const themeColors = themes[theme].colors
    Object.entries(themeColors).forEach(([key, value]) => {
      const cssVar = `--${key.replace(/([A-Z])/g, '-$1').toLowerCase()}`
      root.style.setProperty(cssVar, value)
    })
    
    // Store in localStorage
    localStorage.setItem('theme', theme)
  }, [theme])
  
  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light')
  }
  
  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
```

### Theme Toggle Component
```typescript
// components/theme/ThemeToggle.tsx
'use client'

import { Moon, Sun } from 'lucide-react'
import { useTheme } from '@/components/providers/ThemeProvider'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/Button'

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const { t } = useTranslation('common')
  
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={toggleTheme}
      aria-label={t('theme.toggle')}
      className="h-9 w-9 p-0"
    >
      <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
      <span className="sr-only">{t('theme.toggle')}</span>
    </Button>
  )
}
```

## State Management

### Zustand Stores
```typescript
// stores/appStore.ts
interface AppState {
  theme: 'light' | 'dark'
  language: string
  setTheme: (theme: 'light' | 'dark') => void
  setLanguage: (language: string) => void
}

// stores/videoStore.ts
interface VideoState {
  videos: Video[]
  loading: boolean
  uploadProgress: Record<string, number>
  addVideo: (video: Video) => void
  updateProgress: (videoId: string, progress: number) => void
  removeVideo: (videoId: string) => void
}
```

### TanStack Query Integration
```typescript
// hooks/useVideos.ts
export function useVideos(params?: ListParams) {
  return useQuery({
    queryKey: ['videos', params],
    queryFn: () => api.videos.list(params),
    refetchOnWindowFocus: false,
    staleTime: 30000,
  })
}

export function useUploadVideo() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: ({ file, settings }: { file: File, settings: ProcessingSettings }) =>
      api.videos.upload(file, settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['videos'] })
    },
  })
}
```

## UI Components

### Base Components (Headless UI with Purple Theme)
```typescript
// components/ui/Button.tsx
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
}

export function Button({ variant = 'primary', size = 'md', className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        // Base styles
        'inline-flex items-center justify-center rounded-md font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        'disabled:pointer-events-none disabled:opacity-50',
        
        // Variants
        {
          'bg-primary text-primary-foreground hover:bg-primary/90': variant === 'primary',
          'bg-secondary text-secondary-foreground hover:bg-secondary/80': variant === 'secondary',
          'border border-input bg-background hover:bg-accent hover:text-accent-foreground': variant === 'outline',
          'hover:bg-accent hover:text-accent-foreground': variant === 'ghost',
        },
        
        // Sizes
        {
          'h-9 rounded-md px-3 text-sm': size === 'sm',
          'h-10 px-4 py-2': size === 'md',
          'h-11 rounded-md px-8': size === 'lg',
        },
        
        className
      )}
      {...props}
    />
  )
}

// components/ui/Card.tsx
interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
}

export function Card({ className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-card text-card-foreground shadow-sm',
        className
      )}
      {...props}
    />
  )
}

// components/ui/ProgressBar.tsx
interface ProgressBarProps {
  value: number
  max?: number
  label?: string
  showPercentage?: boolean
  className?: string
}

export function ProgressBar({ 
  value, 
  max = 100, 
  label, 
  showPercentage = true,
  className 
}: ProgressBarProps) {
  const percentage = Math.round((value / max) * 100)
  
  return (
    <div className={cn('w-full', className)}>
      {(label || showPercentage) && (
        <div className="flex justify-between text-sm text-muted-foreground mb-2">
          {label && <span>{label}</span>}
          {showPercentage && <span>{percentage}%</span>}
        </div>
      )}
      <div className="w-full bg-secondary rounded-full h-2">
        <div 
          className="bg-primary h-2 rounded-full transition-all duration-300 ease-in-out"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  )
}
```

### Form Components
```typescript
// components/forms/FileUpload.tsx
interface FileUploadProps {
  onFileSelect: (file: File) => void
  accept: string
  maxSize: number
  disabled?: boolean
}

// components/forms/ProcessingSettingsForm.tsx
interface ProcessingSettingsFormProps {
  initialValues?: Partial<ProcessingSettings>
  onSubmit: (settings: ProcessingSettings) => void
  disabled?: boolean
}
```

### Navigation Components
```typescript
// components/layout/Header.tsx
interface HeaderProps {
  showNavigation?: boolean
}

export function Header({ showNavigation = true }: HeaderProps) {
  const { t } = useTranslation('common')
  const router = useRouter()
  
  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 items-center">
        <div className="mr-4 hidden md:flex">
          <Link href="/" className="mr-6 flex items-center space-x-2">
            <span className="hidden font-bold sm:inline-block">
              Dashcam Anonymizer
            </span>
          </Link>
          {showNavigation && (
            <nav className="flex items-center space-x-6 text-sm font-medium">
              <Link
                href="/"
                className="transition-colors hover:text-foreground/80 text-foreground/60"
              >
                {t('navigation.home')}
              </Link>
              <Link
                href="/contact"
                className="transition-colors hover:text-foreground/80 text-foreground/60"
              >
                {t('navigation.contact')}
              </Link>
              <Link
                href="/dashboard"
                className="transition-colors hover:text-foreground/80 text-foreground/60"
              >
                {t('navigation.dashboard')}
              </Link>
            </nav>
          )}
        </div>
        <div className="flex flex-1 items-center justify-between space-x-2 md:justify-end">
          <div className="w-full flex-1 md:w-auto md:flex-none">
            {/* Mobile menu button */}
          </div>
          <nav className="flex items-center space-x-2">
            <LanguageSelector />
            <ThemeToggle />
          </nav>
        </div>
      </div>
    </header>
  )
}

// components/layout/Footer.tsx
export function Footer() {
  const { t } = useTranslation('common')
  
  return (
    <footer className="border-t border-border">
      <div className="container flex flex-col items-center justify-between gap-4 py-10 md:h-24 md:flex-row md:py-0">
        <div className="flex flex-col items-center gap-4 px-8 md:flex-row md:gap-2 md:px-0">
          <p className="text-center text-sm leading-loose text-muted-foreground md:text-left">
            © 2025 Dashcam Anonymizer. All rights reserved.
          </p>
        </div>
        <div className="flex items-center space-x-4">
          <Link
            href="/privacy"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            Privacy Policy
          </Link>
          <Link
            href="/terms"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            Terms of Service
          </Link>
        </div>
      </div>
    </footer>
  )
}
```

## Styling and Theming

### Global CSS with Theme Variables
```css
/* app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 222.2 84% 4.9%;
    --primary: 262.1 83.3% 57.8%;
    --primary-foreground: 210 20% 98%;
    --secondary: 210 40% 96%;
    --secondary-foreground: 222.2 84% 4.9%;
    --muted: 210 40% 96%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96%;
    --accent-foreground: 222.2 84% 4.9%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 20% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 262.1 83.3% 57.8%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 20% 98%;
    --card: 222.2 84% 4.9%;
    --card-foreground: 210 20% 98%;
    --popover: 222.2 84% 4.9%;
    --popover-foreground: 210 20% 98%;
    --primary: 263.4 70% 50.4%;
    --primary-foreground: 222.2 84% 4.9%;
    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 20% 98%;
    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;
    --accent: 217.2 32.6% 17.5%;
    --accent-foreground: 210 20% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 210 20% 98%;
    --border: 217.2 32.6% 17.5%;
    --input: 217.2 32.6% 17.5%;
    --ring: 263.4 70% 50.4%;
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}

/* Custom purple gradient for special elements */
.gradient-purple {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.gradient-purple-light {
  background: linear-gradient(135deg, #a78bfa 0%, #c084fc 100%);
}
```

### Root Layout with Providers
```typescript
// app/layout.tsx
import { Inter } from 'next/font/google'
import { ThemeProvider } from '@/components/providers/ThemeProvider'
import { I18nProvider } from '@/components/providers/I18nProvider'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider>
          <I18nProvider>
            <div className="min-h-screen bg-background text-foreground">
              {children}
            </div>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
```

## Error Handling

### Error Boundaries
```typescript
// components/ErrorBoundary.tsx
interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
}

class ErrorBoundary extends React.Component<Props, ErrorBoundaryState> {
  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }
  
  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo)
  }
  
  render() {
    if (this.state.hasError) {
      return <ErrorFallback error={this.state.error} />
    }
    
    return this.props.children
  }
}
```

### API Error Handling
```typescript
// lib/api.ts
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
    const error = await response.json()
    throw new ApiError(response.status, error.message, error.details)
  }
  return response.json()
}
```

## Performance Optimization

### Code Splitting
```typescript
// Dynamic imports for large components
const VideoPlayer = dynamic(() => import('@/components/VideoPlayer'), {
  loading: () => <VideoPlayerSkeleton />,
  ssr: false
})

const AdminPanel = dynamic(() => import('@/components/admin/AdminPanel'), {
  loading: () => <div>Loading admin panel...</div>
})
```

### Image Optimization
```typescript
// components/ui/OptimizedImage.tsx
import Image from 'next/image'

interface OptimizedImageProps {
  src: string
  alt: string
  width: number
  height: number
  priority?: boolean
}
```

## Accessibility (WCAG 2.1 AA)

### Accessibility Features
- **Keyboard Navigation**: Full keyboard support for all interactive elements
- **Screen Reader**: Proper ARIA labels and announcements
- **Color Contrast**: Minimum 4.5:1 contrast ratio
- **Focus Management**: Visible focus indicators and logical tab order
- **Alternative Text**: Descriptive alt text for all images
- **Form Accessibility**: Associated labels and error messages

### Implementation
```typescript
// components/ui/Button.tsx
export function Button({ children, loading, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      disabled={loading || props.disabled}
      aria-disabled={loading || props.disabled}
      aria-label={loading ? 'Loading...' : props['aria-label']}
      className={cn(
        'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        props.className
      )}
    >
      {loading && <Spinner className="mr-2" aria-hidden="true" />}
      {children}
    </button>
  )
}
```

## Testing Strategy

### Test Types
- **Unit Tests**: Component logic with Jest + React Testing Library
- **Integration Tests**: User workflows and API integration
- **E2E Tests**: Complete user journeys with Playwright
- **Accessibility Tests**: Automated a11y testing with axe-core

### Test Configuration
```typescript
// jest.config.js
module.exports = {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  moduleNameMapping: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  collectCoverageFrom: [
    'src/**/*.{js,jsx,ts,tsx}',
    '!src/**/*.d.ts',
  ],
}
```

## Build and Deployment

### Next.js Configuration
```javascript
// next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  images: {
    unoptimized: true
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL,
  }
}

module.exports = nextConfig
```

### Docker Configuration
```dockerfile
# Dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/out /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Environment Variables
```bash
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
NEXT_PUBLIC_DEFAULT_LANGUAGE=en
```

## Implementation Phases

The frontend development is organized into manageable phases that build upon each other, ensuring a systematic approach to creating the complete SPA.

### Phase 1: Core Foundation & Setup
**Objective**: Establish the basic project structure and essential infrastructure

**Tasks**:
- Initialize Next.js 14+ project with TypeScript and App Router
- Configure Tailwind CSS with purple color scheme and custom design tokens
- Set up project structure with organized folders (`app/`, `components/`, `lib/`, etc.)
- Implement base UI components (Button, Card, Input, etc.) with Headless UI
- Configure build system for static export (`output: 'export'`)
- Set up ESLint, Prettier, and development tools
- Create initial routing structure for marketing and dashboard sections

**Deliverables**:
- Working Next.js project with proper TypeScript configuration
- Base UI component library with consistent purple theming
- Static export capability validated
- Project structure ready for development

**Testing Requirements**:
- Verify static export builds successfully
- Test base components in Storybook (if implemented)
- Validate TypeScript configuration and build process

---

### Phase 2: Theme System & i18n Infrastructure
**Objective**: Implement comprehensive theming and internationalization foundation

**Tasks**:
- Implement light/dark mode toggle with next-themes integration
- Create comprehensive purple color palette for both themes
- Set up next-i18next for multi-language support (EN, PL, DE)
- Create translation files structure and management system
- Implement ThemeProvider and I18nProvider components
- Build LanguageSelector and ThemeToggle components
- Configure CSS custom properties for dynamic theming
- Add support for system theme preference detection

**Deliverables**:
- Fully functional light/dark mode system with purple theme
- Complete internationalization setup with 3 languages
- Theme and language persistence in localStorage
- Smooth theme transitions and proper contrast ratios

**Testing Requirements**:
- Test theme switching in all components
- Verify language switching works across all pages
- Test theme persistence across browser sessions
- Validate accessibility contrast ratios in both themes

---

### Phase 3: Homepage & Contact Pages (Marketing)
**Objective**: Create the marketing website with homepage and contact functionality

**Tasks**:
- Design and implement responsive homepage with hero section
- Create features showcase with internationalized content
- Build contact form with validation (React Hook Form + Zod)
- Implement contact form submission to backend API
- Add SEO optimization with proper meta tags and structured data
- Create responsive navigation header and footer
- Implement mobile-first responsive design
- Add loading states and error handling for contact form

**Deliverables**:
- Fully functional homepage with responsive design
- Working contact form with backend integration
- SEO-optimized marketing pages
- Proper error handling and user feedback

**Testing Requirements**:
- Test responsive design on various screen sizes
- Validate contact form submission and error handling
- Test SEO meta tags and structured data
- Verify internationalization on marketing pages

---

### Phase 4: Dashboard Foundation & Navigation
**Objective**: Build the core dashboard structure and navigation system

**Tasks**:
- Create dashboard layout with proper navigation
- Implement dashboard home page with video overview
- Build responsive sidebar/navigation for dashboard
- Create video list component with status filtering
- Implement pagination for video lists
- Add search and filtering capabilities
- Create empty states and loading skeletons
- Set up state management with Zustand and TanStack Query

**Deliverables**:
- Complete dashboard navigation and layout
- Video list with filtering and pagination
- Responsive dashboard design
- State management foundation

**Testing Requirements**:
- Test dashboard navigation and responsive behavior
- Verify video list filtering and pagination
- Test state management and data persistence
- Validate loading states and empty state handling

---

### Phase 5: File Upload & Processing Settings
**Objective**: Implement file upload functionality with processing configuration

**Tasks**:
- Create drag-and-drop file upload component with react-dropzone
- Implement file validation (size, format, etc.)
- Build processing settings form with all YOLO configuration options
- Create upload progress tracking and visual feedback
- Implement chunked file upload for large files
- Add file preview and metadata display
- Create processing settings presets for common use cases
- Handle upload errors and retry logic

**Deliverables**:
- Complete file upload system with drag-and-drop
- Processing settings configuration interface
- Upload progress tracking and error handling
- File validation and preview functionality

**Testing Requirements**:
- Test file upload with various file sizes and formats
- Verify processing settings form validation
- Test upload progress tracking and error scenarios
- Validate file size limits and format restrictions

---

### Phase 6: Real-time Updates & WebSocket Integration
**Objective**: Implement real-time progress tracking and notifications

**Tasks**:
- Create WebSocket client for real-time communication
- Implement connection management and reconnection logic
- Build progress update components and notifications
- Create real-time video status updates in dashboard
- Implement WebSocket event handling for processing updates
- Add connection status indicators
- Create notification system for completed/failed processing
- Handle WebSocket errors and fallback polling

**Deliverables**:
- Complete WebSocket integration with backend
- Real-time progress tracking for video processing
- Notification system for processing events
- Robust connection management

**Testing Requirements**:
- Test WebSocket connections and reconnection logic
- Verify real-time progress updates display correctly
- Test notification system for various events
- Validate fallback mechanisms for connection failures

---

### Phase 7: Video Management & Download
**Objective**: Complete video lifecycle management functionality

**Tasks**:
- Implement video download functionality with progress tracking
- Create video preview/thumbnail display
- Build video status management and actions (delete, reprocess)
- Add video metadata display (duration, file size, etc.)
- Implement bulk actions for multiple videos
- Create video history and processing logs
- Add download progress tracking and resume capability
- Implement video sharing functionality (if required)

**Deliverables**:
- Complete video management interface
- Download functionality with progress tracking
- Video actions and bulk operations
- Video metadata and history display

**Testing Requirements**:
- Test video download with various file sizes
- Verify video actions (delete, reprocess) work correctly
- Test bulk operations and selection
- Validate video metadata display accuracy

---

### Phase 8: Performance Optimization & Error Handling
**Objective**: Optimize performance and implement comprehensive error handling

**Tasks**:
- Implement code splitting and lazy loading for components
- Optimize bundle size and loading performance
- Create comprehensive error boundaries
- Implement retry logic for API failures
- Add performance monitoring and metrics
- Optimize images and static assets
- Implement caching strategies for API responses
- Add comprehensive logging for debugging

**Deliverables**:
- Optimized application performance
- Comprehensive error handling system
- Performance monitoring setup
- Improved user experience with better loading states

**Testing Requirements**:
- Performance testing with Lighthouse
- Error boundary testing with simulated failures
- Load testing with large file uploads
- Bundle size analysis and optimization verification

---

### Phase 9: Accessibility & Final Polish
**Objective**: Ensure WCAG 2.1 AA compliance and final user experience polish

**Tasks**:
- Implement comprehensive keyboard navigation
- Add proper ARIA labels and screen reader support
- Ensure color contrast meets WCAG 2.1 AA standards
- Create focus management and skip links
- Add alternative text for all images and icons
- Implement form accessibility with proper labels and error messages
- Conduct accessibility testing with screen readers
- Final UI/UX polish and consistency improvements

**Deliverables**:
- WCAG 2.1 AA compliant application
- Complete keyboard navigation support
- Screen reader optimized interface
- Polished user experience

**Testing Requirements**:
- Automated accessibility testing with axe-core
- Manual testing with screen readers (NVDA, JAWS, VoiceOver)
- Keyboard navigation testing
- Color contrast validation

---

### Phase 10: Integration Testing & Deployment
**Objective**: Comprehensive testing and production deployment setup

**Tasks**:
- Create end-to-end tests with Playwright
- Implement comprehensive integration testing
- Set up Docker containerization with Nginx
- Configure production build optimization
- Create deployment documentation and procedures
- Set up monitoring and health checks
- Perform load testing and performance validation
- Final security review and hardening

**Deliverables**:
- Complete test suite (unit, integration, e2e)
- Production-ready Docker container
- Deployment documentation
- Performance and security validation

**Testing Requirements**:
- Run complete test suite including e2e tests
- Verify Docker container works in production environment
- Load testing with expected user volumes
- Security scanning and vulnerability assessment

---

### Implementation Guidelines

**Development Best Practices**:
- Test-driven development approach where applicable
- Code reviews for all phases before proceeding
- Continuous integration with automated testing
- Regular progress reviews and phase validation
- Documentation updates with each phase completion

**Phase Dependencies**:
- Each phase builds upon the previous phases
- Backend API development should align with frontend phases
- Theme and i18n infrastructure must be completed before UI phases
- Real-time features depend on backend WebSocket implementation

**Quality Gates**:
- All tests must pass before phase completion
- Code coverage requirements must be met
- Performance benchmarks must be achieved
- Accessibility standards must be validated
- Security requirements must be satisfied

**Risk Mitigation**:
- Early prototype validation for complex features
- Fallback mechanisms for real-time features
- Progressive enhancement approach
- Regular stakeholder feedback and validation

This phased approach ensures systematic development while maintaining quality standards and enabling early feedback on each component of the frontend application.

## Security Considerations

### Client-Side Security
- **Input Validation**: Client-side validation with server-side verification
- **XSS Prevention**: Sanitize user inputs and use CSP headers
- **File Upload Security**: File type and size validation
- **API Rate Limiting**: Client-side request throttling
- **Theme Persistence**: Secure localStorage usage for theme preferences
- **Language Persistence**: Secure localStorage usage for language preferences

### Application Security
- **Route Protection**: Client-side route validation (when needed in future)
- **CORS Configuration**: Proper CORS setup for API communication
- **Content Security Policy**: CSP headers for XSS protection
- **Safe HTML Rendering**: Proper sanitization of dynamic content

This MVP specification provides a solid foundation for building a production-ready frontend that integrates seamlessly with your FastAPI backend while maintaining high standards for performance, accessibility, and user experience.

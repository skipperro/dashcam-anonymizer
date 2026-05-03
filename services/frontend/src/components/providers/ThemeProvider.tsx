'use client'

import * as React from 'react'

type Theme = 'light' | 'dark'

interface ThemeContextType {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  mounted: boolean
}

const ThemeContext = React.createContext<ThemeContextType | undefined>(undefined)

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = React.useState<Theme>('light')
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    // Get stored theme or system preference
    const stored = localStorage.getItem('theme') as Theme
    if (stored && ['light', 'dark'].includes(stored)) {
      setTheme(stored)
    } else {
      // Check system preference
      const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
      setTheme(systemTheme)
    }
    setMounted(true)
  }, [])

  React.useEffect(() => {
    const root = document.documentElement
    
    // Remove previous theme classes
    root.classList.remove('light', 'dark')
    
    // Add current theme class
    root.classList.add(theme)
    
    // Store in localStorage
    if (mounted) {
      localStorage.setItem('theme', theme)
    }
  }, [theme, mounted])

  const toggleTheme = React.useCallback(() => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light')
  }, [])

  const value = React.useMemo(() => ({
    theme,
    setTheme,
    toggleTheme,
    mounted,
  }), [theme, toggleTheme, mounted])

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = React.useContext(ThemeContext)
  if (!context) {
    // Return fallback values for SSR/SSG
    return {
      theme: 'light' as Theme,
      setTheme: () => {},
      toggleTheme: () => {},
      mounted: false,
    }
  }
  return context
}

'use client'

import * as React from 'react'

export function LoadingScreen() {
  return (
    <div className="fixed inset-0 bg-background flex items-center justify-center z-50">
      <div className="flex flex-col items-center space-y-4">
        {/* Loading spinner */}
        <div className="relative">
          <div className="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
        </div>
        
        {/* Loading text */}
        <div className="text-sm text-muted-foreground font-medium">
          Loading...
        </div>
      </div>
    </div>
  )
}

export function AppInitializer({ children }: { children: React.ReactNode }) {
  const [isReady, setIsReady] = React.useState(false)
  
  React.useEffect(() => {
    // Small delay to ensure themes are applied
    const timer = setTimeout(() => {
      setIsReady(true)
    }, 100)
    
    return () => clearTimeout(timer)
  }, [])
  
  if (!isReady) {
    return <LoadingScreen />
  }
  
  return <>{children}</>
}

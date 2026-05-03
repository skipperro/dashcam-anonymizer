'use client'

import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { UploadArea } from './UploadArea'
import { VideoList } from './VideoListNew'
import { useI18n } from '@/components/providers/I18nProvider'

export function DashboardLayout() {
  const { t } = useI18n()
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  const handleUploadSuccess = () => {
    // Trigger video list refresh
    setRefreshTrigger(prev => prev + 1)
  }

  return (
    <div className="container mx-auto px-4 py-8 space-y-8">
      <div className="max-w-6xl mx-auto">
        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold">{t('dashboard.title')}</h1>
          <p className="text-muted-foreground mt-2">
            {t('dashboard.subtitle')}
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Upload Area */}
          <div className="lg:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle>{t('dashboard.upload.title')}</CardTitle>
                <CardDescription>
                  {t('dashboard.upload.description')}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <UploadArea onUploadSuccess={handleUploadSuccess} />
              </CardContent>
            </Card>
          </div>

          {/* Video List */}
          <div className="lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle>{t('dashboard.videos.title')}</CardTitle>
                <CardDescription>
                  {t('dashboard.videos.description')}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <VideoList refreshTrigger={refreshTrigger} />
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}

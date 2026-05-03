'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { useI18n } from '@/components/providers/I18nProvider'

export default function HomePage() {
  const { t } = useI18n()

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Hero Section */}
      <section className="text-center py-20">
        <h1 className="text-4xl md:text-6xl font-bold text-foreground mb-6">
          {t('hero.title')}
        </h1>
        <p className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto">
          {t('hero.subtitle')}
        </p>
        <Link href="/dashboard">
          <Button size="lg" className="text-lg px-8 py-6">
            {t('hero.cta')}
          </Button>
        </Link>
      </section>

      {/* Features Section */}
      <section className="py-20">
        <div className="grid md:grid-cols-3 gap-8">
          <Card>
            <CardHeader>
              <CardTitle>{t('features.ai.title')}</CardTitle>
              <CardDescription>
                {t('features.ai.description')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                {t('features.ai.detail')}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('features.privacy.title')}</CardTitle>
              <CardDescription>
                {t('features.privacy.description')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                {t('features.privacy.detail')}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('features.speed.title')}</CardTitle>
              <CardDescription>
                {t('features.speed.description')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                {t('features.speed.detail')}
              </p>
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  )
}
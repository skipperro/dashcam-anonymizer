'use client'

import { useI18n } from '@/components/providers/I18nProvider'

export function Footer() {
  const { t } = useI18n()

  return (
    <footer className="border-t">
      <div className="container flex flex-col items-center justify-between gap-4 py-10 md:h-24 md:flex-row md:py-0">
        <div className="flex flex-col items-center gap-4 px-8 md:flex-row md:gap-2 md:px-0">
          <p className="text-center text-sm leading-loose text-muted-foreground md:text-left">
            {t('footer.copyright')}
          </p>
        </div>
        <div className="flex items-center space-x-4">
          <a
            href="#"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            {t('footer.privacy')}
          </a>
          <a
            href="#"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            {t('footer.terms')}
          </a>
        </div>
      </div>
    </footer>
  )
}
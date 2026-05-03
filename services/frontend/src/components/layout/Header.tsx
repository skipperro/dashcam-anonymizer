'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useTheme } from '@/components/providers/ThemeProvider'
import { useI18n } from '@/components/providers/I18nProvider'
import { Button } from '@/components/ui/Button'
import { Moon, Sun, Menu, X, ChevronDown } from 'lucide-react'

export function Header() {
  const { theme, toggleTheme } = useTheme()
  const { t, language, setLanguage } = useI18n()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const languages = [
    { code: 'en', name: 'EN', flag: '🇬🇧' }, // Changed to UK flag
    { code: 'pl', name: 'PL', flag: '🇵🇱' },
    { code: 'de', name: 'DE', flag: '🇩🇪' }
  ]

  const currentLanguage = languages.find(lang => lang.code === language) || languages[0]

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 items-center">
        {/* Logo */}
        <div className="mr-4 flex">
          <Link href="/" className="mr-6 flex items-center space-x-2">
            <span className="font-bold text-primary">
              Dashcam Anonymizer
            </span>
          </Link>
        </div>

        {/* Desktop Navigation */}
        <nav className="hidden md:flex items-center space-x-6 text-sm font-medium">
          <Link
            href="/"
            className="transition-colors hover:text-foreground/80 text-foreground/60"
          >
            {t('nav.home')}
          </Link>
          <Link
            href="/contact"
            className="transition-colors hover:text-foreground/80 text-foreground/60"
          >
            {t('nav.contact')}
          </Link>
          <Link
            href="/dashboard"
            className="transition-colors hover:text-foreground/80 text-foreground/60"
          >
            {t('nav.dashboard')}
          </Link>
        </nav>

        {/* Right side controls */}
        <div className="flex flex-1 items-center justify-end space-x-2">
          {/* Desktop Language Selector */}
          <div className="hidden md:block relative">
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="appearance-none text-sm bg-background border border-input rounded pl-2 pr-8 h-10 cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              style={{ 
                backgroundImage: 'none',
                WebkitAppearance: 'none',
                MozAppearance: 'none'
              }}
            >
              {languages.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.flag} {lang.name}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" />
          </div>
          
          {/* Theme Toggle */}
          <Button
            variant="outline"
            size="icon"
            onClick={toggleTheme}
            aria-label={t('theme.toggle')}
            className="hidden md:flex"
          >
            <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
            <span className="sr-only">{t('theme.toggle')}</span>
          </Button>

          {/* Mobile menu button */}
          <Button
            variant="outline"
            size="icon"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle menu"
            className="md:hidden"
          >
            {mobileMenuOpen ? (
              <X className="h-4 w-4" />
            ) : (
              <Menu className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>

      {/* Mobile Navigation */}
      {mobileMenuOpen && (
        <div className="md:hidden border-t bg-background">
          <div className="container py-4 space-y-4">
            {/* Mobile Navigation Links */}
            <nav className="flex flex-col space-y-3">
              <Link
                href="/"
                className="text-sm font-medium transition-colors hover:text-foreground/80 text-foreground/60 py-2"
                onClick={() => setMobileMenuOpen(false)}
              >
                {t('nav.home')}
              </Link>
              <Link
                href="/contact"
                className="text-sm font-medium transition-colors hover:text-foreground/80 text-foreground/60 py-2"
                onClick={() => setMobileMenuOpen(false)}
              >
                {t('nav.contact')}
              </Link>
              <Link
                href="/dashboard"
                className="text-sm font-medium transition-colors hover:text-foreground/80 text-foreground/60 py-2"
                onClick={() => setMobileMenuOpen(false)}
              >
                {t('nav.dashboard')}
              </Link>
            </nav>

            {/* Mobile Controls */}
            <div className="flex items-center justify-between pt-4 border-t">
              {/* Mobile Language Selector */}
              <div className="relative">
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="appearance-none text-sm bg-background border border-input rounded pl-2 pr-8 h-10 cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                  style={{ 
                    backgroundImage: 'none',
                    WebkitAppearance: 'none',
                    MozAppearance: 'none'
                  }}
                >
                  {languages.map((lang) => (
                    <option key={lang.code} value={lang.code}>
                      {lang.flag} {lang.name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" />
              </div>

              {/* Mobile Theme Toggle */}
              <Button
                variant="outline"
                size="icon"
                onClick={toggleTheme}
                aria-label={t('theme.toggle')}
              >
                <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
                <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
                <span className="sr-only">{t('theme.toggle')}</span>
              </Button>
            </div>
          </div>
        </div>
      )}
    </header>
  )
}

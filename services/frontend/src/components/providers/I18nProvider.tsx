'use client'

import * as React from 'react'

interface I18nContextType {
  language: string
  setLanguage: (language: string) => void
  t: (key: string) => string
  mounted: boolean
}

const I18nContext = React.createContext<I18nContextType | undefined>(undefined)

// Simple translation implementation for MVP
// In a real implementation, you'd use next-i18next or similar
const translations: Record<string, Record<string, string>> = {
  en: {
    'nav.home': 'Home',
    'nav.contact': 'Contact',
    'nav.dashboard': 'Dashboard',
    'hero.title': 'Anonymize Your Dashcam Videos',
    'hero.subtitle': 'Automatically blur faces and license plates in your dashcam footage',
    'hero.cta': 'Try Dashboard',
    'theme.toggle': 'Toggle theme',
    'language.select': 'Select language',
    // Contact form translations
    'contact.title': 'Contact Us',
    'contact.subtitle': 'Get in touch with our team for support or inquiries',
    'contact.form.name': 'Name',
    'contact.form.email': 'Email',
    'contact.form.subject': 'Subject',
    'contact.form.message': 'Message',
    'contact.form.send': 'Send Message',
    'contact.form.sending': 'Sending...',
    'contact.success': 'Message sent successfully! We\'ll get back to you soon.',
    'contact.error': 'Failed to send message. Please try again.',
    'contact.validation.name.required': 'Name is required',
    'contact.validation.email.required': 'Email is required',
    'contact.validation.email.invalid': 'Please enter a valid email address',
    'contact.validation.subject.required': 'Subject is required',
    'contact.validation.message.required': 'Message is required',
    'contact.validation.message.min': 'Message must be at least 10 characters',
    // Dashboard translations
    'dashboard.title': 'Dashboard',
    'dashboard.subtitle': 'Upload and manage your dashcam videos',
    'dashboard.upload.title': 'Upload Video',
    'dashboard.upload.description': 'Drag and drop your dashcam videos here',
    'dashboard.upload.dropZone': 'Click to select videos or drag and drop here',
    'dashboard.upload.dropActive': 'Drop the videos here',
    'dashboard.upload.uploading': 'Uploading...',
    'dashboard.upload.supportedFormats': 'MP4, AVI, MOV, MKV, WMV, FLV, WEBM',
    'dashboard.upload.cancel': 'Cancel',
    'dashboard.upload.completed': 'Upload completed',
    'dashboard.upload.error': 'Upload failed',
    'dashboard.upload.activeUploads': 'Active Uploads',
    'dashboard.upload.uploaded': 'uploaded',
    'dashboard.videos.title': 'Your Videos',
    'dashboard.videos.description': 'View and manage your videos',
    'dashboard.videos.thumbnailReady': 'Thumbnail ready',
    'dashboard.videos.uploading': 'Uploading...',
    'dashboard.videos.cancelUpload': 'Cancel',
    'dashboard.videos.download': 'Download',
    'dashboard.videos.downloading': 'Fetching...',
    'dashboard.videos.downloadError': 'Download link unavailable',
    'dashboard.videos.delete': 'Delete',
    'dashboard.videos.deleteConfirm': 'Are you sure you want to delete this video?',
    'dashboard.videos.deleteSuccess': 'Video deleted successfully',
    'dashboard.videos.deleteError': 'Failed to delete video',
    'dashboard.videos.cancel': 'Cancel',
    'dashboard.videos.errorLoading': 'Failed to load videos',
    'dashboard.videos.retry': 'Retry',
    'dashboard.videos.noVideos': 'No videos uploaded yet',
    'dashboard.videos.uploadFirst': 'Upload your first video to get started',
    // Home page features
    'features.ai.title': 'AI-Powered Detection',
    'features.ai.description': 'Advanced YOLO models detect faces and license plates with high accuracy',
    'features.ai.detail': 'Choose from different model sizes for the perfect balance of speed and accuracy.',
    'features.privacy.title': 'Privacy First',
    'features.privacy.description': 'Your videos are processed securely and deleted after completion',
    'features.privacy.detail': 'No data is stored permanently. Full control over your content.',
    'features.speed.title': 'Fast Processing',
    'features.speed.description': 'Optimized processing pipeline for quick turnaround times',
    'features.speed.detail': 'Multiple processing workers ensure your videos are ready quickly.',
    // Footer
    'footer.copyright': '© 2025 Dashcam Anonymizer. All rights reserved.',
    'footer.privacy': 'Privacy Policy',
    'footer.terms': 'Terms of Service',
    'dashboard.videos.queued': 'Queued…',
    'dashboard.videos.processing': 'Processing…',
    'dashboard.videos.deleting': 'Deleting...',
    'dashboard.videos.confirm': 'Confirm',
    'dashboard.videos.lastUpdate': 'Last update',
    'dashboard.videos.status.uploading': 'Uploading',
    'dashboard.videos.status.uploaded': 'Uploaded',
    'dashboard.videos.status.processing': 'Processing',
    'dashboard.videos.status.processed': 'Processed',
    'dashboard.videos.status.completed': 'Completed',
    'dashboard.videos.status.failed': 'Failed',
    'dashboard.videos.status.queued': 'Queued',
  },
  pl: {
    'nav.home': 'Strona główna',
    'nav.contact': 'Kontakt',
    'nav.dashboard': 'Panel',
    'hero.title': 'Anonimizuj swoje nagrania z kamerki',
    'hero.subtitle': 'Automatycznie zamazuj twarze i tablice rejestracyjne',
    'hero.cta': 'Przejdź do panelu',
    'theme.toggle': 'Przełącz motyw',
    'language.select': 'Wybierz język',
    // Contact form translations
    'contact.title': 'Skontaktuj się z nami',
    'contact.subtitle': 'Skontaktuj się z naszym zespołem w sprawie wsparcia lub zapytań',
    'contact.form.name': 'Imię',
    'contact.form.email': 'Email',
    'contact.form.subject': 'Temat',
    'contact.form.message': 'Wiadomość',
    'contact.form.send': 'Wyślij wiadomość',
    'contact.form.sending': 'Wysyłanie...',
    'contact.success': 'Wiadomość została wysłana pomyślnie! Odpowiemy wkrótce.',
    'contact.error': 'Nie udało się wysłać wiadomości. Spróbuj ponownie.',
    'contact.validation.name.required': 'Imię jest wymagane',
    'contact.validation.email.required': 'Email jest wymagany',
    'contact.validation.email.invalid': 'Wprowadź prawidłowy adres email',
    'contact.validation.subject.required': 'Temat jest wymagany',
    'contact.validation.message.required': 'Wiadomość jest wymagana',
    'contact.validation.message.min': 'Wiadomość musi mieć co najmniej 10 znaków',
    // Dashboard translations
    'dashboard.title': 'Panel',
    'dashboard.subtitle': 'Prześlij i zarządzaj swoimi nagraniami z kamerki',
    'dashboard.upload.title': 'Prześlij wideo',
    'dashboard.upload.description': 'Przeciągnij i upuść swoje nagrania z kamerki tutaj',
    'dashboard.upload.dropZone': 'Kliknij aby wybrać pliki lub przeciągnij je tutaj',
    'dashboard.upload.dropActive': 'Upuść pliki tutaj',
    'dashboard.upload.uploading': 'Przesyłanie...',
    'dashboard.upload.supportedFormats': 'MP4, AVI, MOV, MKV, WMV, FLV, WEBM',
    'dashboard.upload.cancel': 'Anuluj',
    'dashboard.upload.completed': 'Przesyłanie zakończone',
    'dashboard.upload.error': 'Przesyłanie nie powiodło się',
    'dashboard.upload.activeUploads': 'Aktywne przesyłania',
    'dashboard.upload.uploaded': 'przesłano',
    'dashboard.videos.title': 'Twoje filmy',
    'dashboard.videos.description': 'Przeglądaj i zarządzaj swoje filmy',
    'dashboard.videos.thumbnailReady': 'Miniatura gotowa',
    'dashboard.videos.uploading': 'Przesyłanie...',
    'dashboard.videos.cancelUpload': 'Anuluj',
    'dashboard.videos.download': 'Pobierz',
    'dashboard.videos.downloading': 'Pobieranie...',
    'dashboard.videos.downloadError': 'Link niedostępny',
    'dashboard.videos.delete': 'Usuń',
    'dashboard.videos.deleteConfirm': 'Czy na pewno chcesz usunąć ten film?',
    'dashboard.videos.deleteSuccess': 'Film został pomyślnie usunięty',
    'dashboard.videos.deleteError': 'Nie udało się usunąć filmu',
    'dashboard.videos.cancel': 'Anuluj',
    'dashboard.videos.errorLoading': 'Nie udało się załadować filmów',
    'dashboard.videos.retry': 'Spróbuj ponownie',
    'dashboard.videos.noVideos': 'Nie przesłano jeszcze żadnych filmów',
    'dashboard.videos.uploadFirst': 'Prześlij swój pierwszy film, aby rozpocząć',
    // Home page features
    'features.ai.title': 'Wykrywanie AI',
    'features.ai.description': 'Zaawansowane modele YOLO wykrywają twarze i tablice rejestracyjne z wysoką dokładnością',
    'features.ai.detail': 'Wybierz spośród różnych rozmiarów modeli dla idealnego balansu szybkości i dokładności.',
    'features.privacy.title': 'Prywatność przede wszystkim',
    'features.privacy.description': 'Twoje filmy są przetwarzane bezpiecznie i usuwane po zakończeniu',
    'features.privacy.detail': 'Żadne dane nie są przechowywane na stałe. Pełna kontrola nad swoją treścią.',
    'features.speed.title': 'Szybkie przetwarzanie',
    'features.speed.description': 'Zoptymalizowany potok przetwarzania dla krótkich czasów realizacji',
    'features.speed.detail': 'Wielu pracowników przetwarzania zapewnia szybką gotowość filmów.',
    // Footer
    'footer.copyright': '© 2025 Dashcam Anonymizer. Wszelkie prawa zastrzeżone.',
    'footer.privacy': 'Polityka prywatności',
    'footer.terms': 'Warunki korzystania',
    'dashboard.videos.queued': 'W kolejce…',
    'dashboard.videos.processing': 'Przetwarzanie…',
    'dashboard.videos.deleting': 'Usuwanie...',
    'dashboard.videos.confirm': 'Potwierdź',
    'dashboard.videos.lastUpdate': 'Ostatnia aktualizacja',
    'dashboard.videos.status.uploading': 'Przesyłanie',
    'dashboard.videos.status.uploaded': 'Przesłano',
    'dashboard.videos.status.processing': 'Przetwarzanie',
    'dashboard.videos.status.processed': 'Przetworzone',
    'dashboard.videos.status.completed': 'Zakończone',
    'dashboard.videos.status.failed': 'Nieudane',
    'dashboard.videos.status.queued': 'W kolejce',
  },
  de: {
    'nav.home': 'Startseite',
    'nav.contact': 'Kontakt',
    'nav.dashboard': 'Dashboard',
    'hero.title': 'Anonymisiere deine Dashcam-Videos',
    'hero.subtitle': 'Gesichter und Kennzeichen automatisch unkenntlich machen',
    'hero.cta': 'Zum Dashboard',
    'theme.toggle': 'Theme wechseln',
    'language.select': 'Sprache wählen',
    // Contact form translations
    'contact.title': 'Kontaktiere uns',
    'contact.subtitle': 'Kontaktiere unser Team für Support oder Anfragen',
    'contact.form.name': 'Name',
    'contact.form.email': 'E-Mail',
    'contact.form.subject': 'Betreff',
    'contact.form.message': 'Nachricht',
    'contact.form.send': 'Nachricht senden',
    'contact.form.sending': 'Senden...',
    'contact.success': 'Nachricht erfolgreich gesendet! Wir melden uns bald zurück.',
    'contact.error': 'Nachricht konnte nicht gesendet werden. Bitte versuche es erneut.',
    'contact.validation.name.required': 'Name ist erforderlich',
    'contact.validation.email.required': 'E-Mail ist erforderlich',
    'contact.validation.email.invalid': 'Bitte geben Sie eine gültige E-Mail-Adresse ein',
    'contact.validation.subject.required': 'Betreff ist erforderlich',
    'contact.validation.message.required': 'Nachricht ist erforderlich',
    'contact.validation.message.min': 'Nachricht muss mindestens 10 Zeichen lang sein',
    // Dashboard translations
    'dashboard.title': 'Dashboard',
    'dashboard.subtitle': 'Lade deine Dashcam-Videos hoch und verwalte sie',
    'dashboard.upload.title': 'Video hochladen',
    'dashboard.upload.description': 'Ziehe deine Dashcam-Videos hierher',
    'dashboard.upload.dropZone': 'Klicken zum Auswählen oder hier ablegen',
    'dashboard.upload.dropActive': 'Videos hier ablegen',
    'dashboard.upload.uploading': 'Wird hochgeladen...',
    'dashboard.upload.supportedFormats': 'MP4, AVI, MOV, MKV, WMV, FLV, WEBM',
    'dashboard.upload.cancel': 'Abbrechen',
    'dashboard.upload.completed': 'Upload abgeschlossen',
    'dashboard.upload.error': 'Upload fehlgeschlagen',
    'dashboard.upload.activeUploads': 'Aktive Uploads',
    'dashboard.upload.uploaded': 'hochgeladen',
    'dashboard.videos.title': 'Deine Videos',
    'dashboard.videos.description': 'Betrachte und verwalte deine Videos',
    'dashboard.videos.thumbnailReady': 'Vorschaubild bereit',
    'dashboard.videos.uploading': 'Wird hochgeladen...',
    'dashboard.videos.cancelUpload': 'Abbrechen',
    'dashboard.videos.download': 'Herunterladen',
    'dashboard.videos.downloading': 'Wird geladen...',
    'dashboard.videos.downloadError': 'Download-Link nicht verfügbar',
    'dashboard.videos.delete': 'Löschen',
    'dashboard.videos.deleteConfirm': 'Bist du sicher, dass du dieses Video löschen möchtest?',
    'dashboard.videos.deleteSuccess': 'Video erfolgreich gelöscht',
    'dashboard.videos.deleteError': 'Video konnte nicht gelöscht werden',
    'dashboard.videos.cancel': 'Abbrechen',
    'dashboard.videos.errorLoading': 'Videos konnten nicht geladen werden',
    'dashboard.videos.retry': 'Erneut versuchen',
    'dashboard.videos.noVideos': 'Noch keine Videos hochgeladen',
    'dashboard.videos.uploadFirst': 'Lade dein erstes Video hoch um zu beginnen',
    // Home page features
    'features.ai.title': 'KI-gestützte Erkennung',
    'features.ai.description': 'Fortschrittliche YOLO-Modelle erkennen Gesichter und Kennzeichen mit hoher Genauigkeit',
    'features.ai.detail': 'Wähle aus verschiedenen Modellgrößen für die perfekte Balance aus Geschwindigkeit und Genauigkeit.',
    'features.privacy.title': 'Datenschutz zuerst',
    'features.privacy.description': 'Deine Videos werden sicher verarbeitet und nach Abschluss gelöscht',
    'features.privacy.detail': 'Es werden keine Daten dauerhaft gespeichert. Volle Kontrolle über deine Inhalte.',
    'features.speed.title': 'Schnelle Verarbeitung',
    'features.speed.description': 'Optimierte Verarbeitungspipeline für schnelle Durchlaufzeiten',
    'features.speed.detail': 'Mehrere Verarbeitungsworker stellen sicher, dass deine Videos schnell bereit sind.',
    // Footer
    'footer.copyright': '© 2025 Dashcam Anonymizer. Alle Rechte vorbehalten.',
    'footer.privacy': 'Datenschutzerklärung',
    'footer.terms': 'Nutzungsbedingungen',
    'dashboard.videos.queued': 'In Warteschlange…',
    'dashboard.videos.processing': 'Verarbeitung…',
    'dashboard.videos.deleting': 'Löschen...',
    'dashboard.videos.confirm': 'Bestätigen',
    'dashboard.videos.lastUpdate': 'Letzte Aktualisierung',
    'dashboard.videos.status.uploading': 'Wird hochgeladen',
    'dashboard.videos.status.uploaded': 'Hochgeladen',
    'dashboard.videos.status.processing': 'In Verarbeitung',
    'dashboard.videos.status.processed': 'Verarbeitet',
    'dashboard.videos.status.completed': 'Abgeschlossen',
    'dashboard.videos.status.failed': 'Fehlgeschlagen',
    'dashboard.videos.status.queued': 'In Warteschlange',
  },
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguage] = React.useState('en')
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
    // Get stored language or browser preference
    const stored = localStorage.getItem('language')
    if (stored && Object.keys(translations).includes(stored)) {
      setLanguage(stored)
    } else {
      // Check browser language
      const browserLang = navigator.language.split('-')[0]
      if (Object.keys(translations).includes(browserLang)) {
        setLanguage(browserLang)
      }
    }
  }, [])

  React.useEffect(() => {
    if (!mounted) return
    localStorage.setItem('language', language)
  }, [language, mounted])

  const t = React.useCallback((key: string): string => {
    return translations[language]?.[key] || key
  }, [language])

  const value = React.useMemo(() => ({
    language,
    setLanguage,
    t,
    mounted,
  }), [language, t, mounted])

  return (
    <I18nContext.Provider value={value}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n() {
  const context = React.useContext(I18nContext)
  if (!context) {
    // Return fallback values for SSR/SSG
    return {
      language: 'en',
      setLanguage: () => {},
      t: (key: string) => key,
      mounted: false,
    }
  }
  return context
}

import type { Metadata } from 'next'
import { ContactForm } from '@/components/forms/ContactForm'

export const metadata: Metadata = {
  title: 'Contact Us - Dashcam Anonymizer',
  description: 'Get in touch with our team for support or inquiries about dashcam video anonymization',
}

export default function ContactPage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-2xl mx-auto">
        <ContactForm />
      </div>
    </div>
  )
}

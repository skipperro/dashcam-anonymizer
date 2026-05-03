'use client'

import * as React from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { useI18n } from '@/components/providers/I18nProvider'
import { api } from '@/lib/api'
import { ContactFormData } from '@/types'

// Validation schema
const getContactSchema = (t: (key: string) => string) => z.object({
  name: z.string().min(1, t('contact.validation.name.required')),
  email: z.string()
    .min(1, t('contact.validation.email.required'))
    .email(t('contact.validation.email.invalid')),
  subject: z.string().min(1, t('contact.validation.subject.required')),
  message: z.string()
    .min(1, t('contact.validation.message.required'))
    .min(10, t('contact.validation.message.min')),
})

interface ContactFormProps {
  className?: string
}

export function ContactForm({ className }: ContactFormProps) {
  const { t } = useI18n()
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const [submitStatus, setSubmitStatus] = React.useState<{
    type: 'success' | 'error' | null
    message: string
  }>({ type: null, message: '' })

  const contactSchema = React.useMemo(() => getContactSchema(t), [t])
  
  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<ContactFormData>({
    resolver: zodResolver(contactSchema),
  })

  const onSubmit = async (data: ContactFormData) => {
    setIsSubmitting(true)
    setSubmitStatus({ type: null, message: '' })

    try {
      await api.contact.send(data)
      setSubmitStatus({
        type: 'success',
        message: t('contact.success'),
      })
      reset() // Clear form on success
    } catch (error) {
      console.error('Contact form submission error:', error)
      setSubmitStatus({
        type: 'error',
        message: t('contact.error'),
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{t('contact.title')}</CardTitle>
        <CardDescription>
          {t('contact.subtitle')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {submitStatus.type && (
          <div
            className={`mb-6 p-4 rounded-md ${
              submitStatus.type === 'success'
                ? 'bg-green-50 text-green-800 border border-green-200 dark:bg-green-900/20 dark:text-green-300 dark:border-green-800'
                : 'bg-red-50 text-red-800 border border-red-200 dark:bg-red-900/20 dark:text-red-300 dark:border-red-800'
            }`}
          >
            {submitStatus.message}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {/* Name Field */}
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-foreground mb-2">
              {t('contact.form.name')} *
            </label>
            <input
              id="name"
              type="text"
              className={`w-full px-3 py-2 border rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent ${
                errors.name
                  ? 'border-red-500 focus:ring-red-500'
                  : 'border-input'
              }`}
              {...register('name')}
            />
            {errors.name && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                {errors.name.message}
              </p>
            )}
          </div>

          {/* Email Field */}
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-foreground mb-2">
              {t('contact.form.email')} *
            </label>
            <input
              id="email"
              type="email"
              className={`w-full px-3 py-2 border rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent ${
                errors.email
                  ? 'border-red-500 focus:ring-red-500'
                  : 'border-input'
              }`}
              {...register('email')}
            />
            {errors.email && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                {errors.email.message}
              </p>
            )}
          </div>

          {/* Subject Field */}
          <div>
            <label htmlFor="subject" className="block text-sm font-medium text-foreground mb-2">
              {t('contact.form.subject')} *
            </label>
            <input
              id="subject"
              type="text"
              className={`w-full px-3 py-2 border rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent ${
                errors.subject
                  ? 'border-red-500 focus:ring-red-500'
                  : 'border-input'
              }`}
              {...register('subject')}
            />
            {errors.subject && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                {errors.subject.message}
              </p>
            )}
          </div>

          {/* Message Field */}
          <div>
            <label htmlFor="message" className="block text-sm font-medium text-foreground mb-2">
              {t('contact.form.message')} *
            </label>
            <textarea
              id="message"
              rows={5}
              className={`w-full px-3 py-2 border rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent resize-vertical ${
                errors.message
                  ? 'border-red-500 focus:ring-red-500'
                  : 'border-input'
              }`}
              {...register('message')}
            />
            {errors.message && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                {errors.message.message}
              </p>
            )}
          </div>

          {/* Submit Button */}
          <Button
            type="submit"
            disabled={isSubmitting}
            className="w-full"
          >
            {isSubmitting ? t('contact.form.sending') : t('contact.form.send')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

import { Metadata } from 'next'
import { DashboardLayout } from '@/components/dashboard/DashboardLayout'

export const metadata: Metadata = {
  title: 'Dashboard - Dashcam Anonymizer',
  description: 'Upload and manage your dashcam videos',
}

export default function DashboardPage() {
  return <DashboardLayout />
}

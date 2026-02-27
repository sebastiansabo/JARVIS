import { useAuth } from '@/hooks/useAuth'
import { PageHeader } from '@/components/shared/PageHeader'
import SupplierManager from './SupplierManager'

export default function SuppliersPage() {
  const { user } = useAuth()
  const companyId = user?.company_id || undefined

  return (
    <div className="space-y-6">
      <PageHeader
        title="Suppliers"
        description="Master supplier list"
      />
      <SupplierManager companyId={companyId} />
    </div>
  )
}

import { useAuth } from '@/hooks/useAuth'
import SupplierManager from './SupplierManager'

export default function SuppliersPage() {
  const { user } = useAuth()
  const companyId = user?.company_id || undefined

  return <SupplierManager companyId={companyId} />
}

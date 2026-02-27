import CategoryManager from '@/pages/Dms/CategoryManager'
import PartyRoleManager from '@/pages/Dms/PartyRoleManager'

export default function DocumentsTab() {
  return (
    <div className="space-y-8">
      <CategoryManager />
      <div className="border-t pt-6">
        <PartyRoleManager />
      </div>
    </div>
  )
}

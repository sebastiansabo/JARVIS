import { MapPin } from 'lucide-react'

export default function FieldSales() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <MapPin className="h-6 w-6 text-red-500" />
        <h1 className="text-2xl font-bold">Field Sales</h1>
      </div>
      <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
        <MapPin className="mx-auto h-12 w-12 mb-4 opacity-40" />
        <p className="text-lg font-medium">Field Sales is available on the mobile app</p>
        <p className="mt-2 text-sm">Plan visits, enrich clients, and manage fleet on the go.</p>
      </div>
    </div>
  )
}

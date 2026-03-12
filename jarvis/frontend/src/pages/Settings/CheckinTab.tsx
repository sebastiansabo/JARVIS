import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, MapPin, Wifi, QrCode, Copy } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { EmptyState } from '@/components/shared/EmptyState'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { checkinApi } from '@/api/checkin'
import { toast } from 'sonner'
import type { CheckinLocation } from '@/types/checkin'

type LocationForm = {
  name: string
  latitude: string
  longitude: string
  allowed_radius_meters: string
  auto_checkout_radius_meters: string
  allowed_ips: string
  is_active: boolean
}

const emptyForm: LocationForm = {
  name: '',
  latitude: '',
  longitude: '',
  allowed_radius_meters: '50',
  auto_checkout_radius_meters: '200',
  allowed_ips: '',
  is_active: true,
}

export default function CheckinTab() {
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<LocationForm>(emptyForm)
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)

  const { data: locations = [], isLoading } = useQuery<CheckinLocation[]>({
    queryKey: ['settings', 'checkin-locations'],
    queryFn: async () => {
      const res = await checkinApi.getAllLocations()
      return (res as any).data ?? res
    },
    staleTime: 10 * 60_000,
  })

  const saveMutation = useMutation({
    mutationFn: async (data: LocationForm) => {
      const payload = {
        name: data.name,
        latitude: parseFloat(data.latitude),
        longitude: parseFloat(data.longitude),
        allowed_radius_meters: parseInt(data.allowed_radius_meters) || 50,
        auto_checkout_radius_meters: parseInt(data.auto_checkout_radius_meters) || 200,
        allowed_ips: data.allowed_ips
          .split('\n')
          .map(ip => ip.trim())
          .filter(Boolean),
        is_active: data.is_active,
      }
      if (editingId) {
        return checkinApi.updateLocation(editingId, payload)
      }
      return checkinApi.createLocation(payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'checkin-locations'] })
      toast.success(editingId ? 'Location updated' : 'Location created')
      closeDialog()
    },
    onError: () => toast.error('Failed to save location'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => checkinApi.deleteLocation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'checkin-locations'] })
      toast.success('Location deleted')
      setDeleteConfirm(null)
    },
    onError: () => toast.error('Failed to delete location'),
  })

  function openCreate() {
    setEditingId(null)
    setForm(emptyForm)
    setDialogOpen(true)
  }

  function openEdit(loc: CheckinLocation) {
    setEditingId(loc.id)
    setForm({
      name: loc.name,
      latitude: String(loc.latitude),
      longitude: String(loc.longitude),
      allowed_radius_meters: String(loc.allowed_radius_meters),
      auto_checkout_radius_meters: String(loc.auto_checkout_radius_meters ?? 200),
      allowed_ips: (loc.allowed_ips || []).join('\n'),
      is_active: loc.is_active,
    })
    setDialogOpen(true)
  }

  function closeDialog() {
    setDialogOpen(false)
    setEditingId(null)
    setForm(emptyForm)
  }

  function handleSave() {
    if (!form.name || !form.latitude || !form.longitude) {
      toast.error('Name, latitude and longitude are required')
      return
    }
    if (isNaN(parseFloat(form.latitude)) || isNaN(parseFloat(form.longitude))) {
      toast.error('Latitude and longitude must be valid numbers')
      return
    }
    saveMutation.mutate(form)
  }

  function copyQrToken(locId: number) {
    navigator.clipboard.writeText(`checkin:${locId}`)
    toast.success('QR token copied to clipboard')
  }

  if (isLoading) {
    return <div className="space-y-4"><div className="h-8 w-48 animate-pulse rounded bg-muted" /><div className="h-64 w-full animate-pulse rounded bg-muted" /></div>
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2">
              <MapPin className="h-5 w-5" />
              Check-in Locations
            </CardTitle>
            <CardDescription>
              Configure GPS locations where mobile check-in is allowed. Users within the allowed radius can punch in/out.
            </CardDescription>
          </div>
          <Button onClick={openCreate} size="sm">
            <Plus className="mr-1 h-4 w-4" />
            Add Location
          </Button>
        </CardHeader>
        <CardContent>
          {locations.length === 0 ? (
            <EmptyState
              icon={<MapPin className="h-10 w-10" />}
              title="No check-in locations"
              description="Add your first office location to enable mobile GPS check-in."
              action={<Button onClick={openCreate} size="sm"><Plus className="mr-1 h-4 w-4" />Add Location</Button>}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Coordinates</TableHead>
                  <TableHead>Check-in</TableHead>
                  <TableHead>Auto-Out</TableHead>
                  <TableHead>WiFi IPs</TableHead>
                  <TableHead>QR Token</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-[100px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {locations.map((loc) => (
                  <TableRow key={loc.id}>
                    <TableCell className="font-medium">{loc.name}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {loc.latitude}, {loc.longitude}
                    </TableCell>
                    <TableCell>{loc.allowed_radius_meters}m</TableCell>
                    <TableCell>{loc.auto_checkout_radius_meters ?? 200}m</TableCell>
                    <TableCell>
                      {(loc.allowed_ips || []).length > 0 ? (
                        <div className="flex items-center gap-1">
                          <Wifi className="h-3.5 w-3.5 text-blue-500" />
                          <span className="text-xs">{loc.allowed_ips.length} IP{loc.allowed_ips.length !== 1 ? 's' : ''}</span>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">None</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 gap-1 px-2 text-xs font-mono"
                        onClick={() => copyQrToken(loc.id)}
                      >
                        <QrCode className="h-3.5 w-3.5" />
                        checkin:{loc.id}
                        <Copy className="h-3 w-3 text-muted-foreground" />
                      </Button>
                    </TableCell>
                    <TableCell>
                      <Badge variant={loc.is_active ? 'default' : 'secondary'}>
                        {loc.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(loc)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          onClick={() => setDeleteConfirm(loc.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Help card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">How Check-in Works</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <p><strong>GPS:</strong> User opens the check-in page on their phone. The app reads GPS coordinates and compares with location presets. If within the allowed radius, the punch is accepted.</p>
          <p><strong>WiFi/IP:</strong> If GPS is unavailable or out of range, the app checks the user's IP address against the allowed IPs list for each location. Add your office public IP(s) to enable this fallback.</p>
          <p><strong>QR Code:</strong> As a last resort, users can scan a QR code placed at the office. Generate a QR code containing the token shown in the table above (e.g., <code className="bg-muted px-1 rounded">checkin:1</code>).</p>
          <p><strong>Auto-Checkout:</strong> While the check-in page is open, the phone continuously monitors GPS. If a checked-in user moves beyond the auto-checkout radius, they are automatically punched out.</p>
        </CardContent>
      </Card>

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingId ? 'Edit Location' : 'Add Location'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input
                placeholder="e.g. Office HQ"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Latitude</Label>
                <Input
                  placeholder="44.4268"
                  value={form.latitude}
                  onChange={(e) => setForm({ ...form, latitude: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label>Longitude</Label>
                <Input
                  placeholder="26.1025"
                  value={form.longitude}
                  onChange={(e) => setForm({ ...form, longitude: e.target.value })}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Check-in Radius (m)</Label>
                <Input
                  type="number"
                  min="10"
                  max="500"
                  value={form.allowed_radius_meters}
                  onChange={(e) => setForm({ ...form, allowed_radius_meters: e.target.value })}
                />
                <p className="text-xs text-muted-foreground">Max distance to punch in/out</p>
              </div>
              <div className="space-y-2">
                <Label>Auto-Checkout (m)</Label>
                <Input
                  type="number"
                  min="50"
                  max="2000"
                  value={form.auto_checkout_radius_meters}
                  onChange={(e) => setForm({ ...form, auto_checkout_radius_meters: e.target.value })}
                />
                <p className="text-xs text-muted-foreground">Auto check-out when leaving this radius</p>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Allowed IPs (one per line)</Label>
              <textarea
                className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="e.g. 203.0.113.50&#10;198.51.100.25"
                value={form.allowed_ips}
                onChange={(e) => setForm({ ...form, allowed_ips: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">Public IP addresses of your office WiFi network for IP-based fallback.</p>
            </div>
            {editingId && (
              <div className="flex items-center gap-2">
                <Switch
                  checked={form.is_active}
                  onCheckedChange={(checked) => setForm({ ...form, is_active: checked })}
                />
                <Label>Active</Label>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeDialog}>Cancel</Button>
            <Button onClick={handleSave} disabled={saveMutation.isPending}>
              {saveMutation.isPending ? 'Saving...' : editingId ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteConfirm !== null} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Location</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete this location? Users will no longer be able to check in here.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={() => deleteConfirm && deleteMutation.mutate(deleteConfirm)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

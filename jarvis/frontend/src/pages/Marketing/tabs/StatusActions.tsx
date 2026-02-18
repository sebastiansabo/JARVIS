import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import { Play, Pause, CheckCircle, Send, Copy, Trash2 } from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import { usersApi } from '@/api/users'
import type { MktProject } from '@/types/marketing'

export function StatusActions({ project, onDone }: { project: MktProject; onDone: () => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [submitOpen, setSubmitOpen] = useState(false)
  const [selectedApprover, setSelectedApprover] = useState<number | undefined>()
  const { data: membersData } = useQuery({ queryKey: ['mkt-members', project.id], queryFn: () => marketingApi.getMembers(project.id) })
  const stakeholders = (membersData?.members ?? []).filter((m) => m.role === 'stakeholder')
  const hasStakeholders = stakeholders.length > 0
  const { data: allUsers } = useQuery({ queryKey: ['users-list'], queryFn: () => usersApi.getUsers(), enabled: submitOpen && !hasStakeholders })
  const submitMut = useMutation({
    mutationFn: () => marketingApi.submitApproval(project.id, hasStakeholders ? undefined : selectedApprover),
    onSuccess: () => { setSubmitOpen(false); setSelectedApprover(undefined); onDone() },
  })
  const activateMut = useMutation({ mutationFn: () => marketingApi.activateProject(project.id), onSuccess: onDone })
  const pauseMut = useMutation({ mutationFn: () => marketingApi.pauseProject(project.id), onSuccess: onDone })
  const completeMut = useMutation({ mutationFn: () => marketingApi.completeProject(project.id), onSuccess: onDone })
  const dupMut = useMutation({
    mutationFn: () => marketingApi.duplicateProject(project.id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
      if (data?.id) navigate(`/app/marketing/projects/${data.id}`)
      else onDone()
    },
  })
  const deleteMut = useMutation({
    mutationFn: () => marketingApi.deleteProject(project.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
      navigate('/app/marketing')
    },
  })

  const s = project.status
  return (
    <div className="flex items-center gap-1.5">
      {(s === 'draft' || s === 'cancelled') && hasStakeholders ? (
        <Button size="sm" onClick={() => submitMut.mutate()} disabled={submitMut.isPending}>
          <Send className="h-3.5 w-3.5 mr-1.5" />
          {submitMut.isPending ? 'Submitting...' : `Submit (${stakeholders.length} stakeholder${stakeholders.length === 1 ? '' : 's'})`}
        </Button>
      ) : (s === 'draft' || s === 'cancelled') && (
        <Popover open={submitOpen} onOpenChange={(o) => { setSubmitOpen(o); if (!o) setSelectedApprover(undefined) }}>
          <PopoverTrigger asChild>
            <Button size="sm">
              <Send className="h-3.5 w-3.5 mr-1.5" /> Submit
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-64 p-3 space-y-2" align="end">
            <label className="text-xs font-medium text-muted-foreground">Select Approver</label>
            <select
              className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
              value={selectedApprover ?? ''}
              onChange={(e) => setSelectedApprover(e.target.value ? Number(e.target.value) : undefined)}
            >
              <option value="">Choose...</option>
              {(allUsers ?? []).map((u) => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </select>
            <Button size="sm" className="w-full" disabled={!selectedApprover || submitMut.isPending} onClick={() => submitMut.mutate()}>
              {submitMut.isPending ? 'Submitting...' : 'Submit for Approval'}
            </Button>
          </PopoverContent>
        </Popover>
      )}
      {s === 'approved' && (
        <Button size="sm" onClick={() => activateMut.mutate()} disabled={activateMut.isPending}>
          <Play className="h-3.5 w-3.5 mr-1.5" /> Activate
        </Button>
      )}
      {s === 'active' && (
        <>
          <Button size="sm" variant="outline" onClick={() => pauseMut.mutate()} disabled={pauseMut.isPending}>
            <Pause className="h-3.5 w-3.5 mr-1.5" /> Pause
          </Button>
          <Button size="sm" onClick={() => completeMut.mutate()} disabled={completeMut.isPending}>
            <CheckCircle className="h-3.5 w-3.5 mr-1.5" /> Complete
          </Button>
        </>
      )}
      {s === 'paused' && (
        <>
          <Button size="sm" onClick={() => activateMut.mutate()} disabled={activateMut.isPending}>
            <Play className="h-3.5 w-3.5 mr-1.5" /> Resume
          </Button>
          <Button size="sm" variant="outline" onClick={() => completeMut.mutate()} disabled={completeMut.isPending}>
            <CheckCircle className="h-3.5 w-3.5 mr-1.5" /> Complete
          </Button>
        </>
      )}
      <Button size="sm" variant="ghost" onClick={() => dupMut.mutate()} disabled={dupMut.isPending}>
        <Copy className="h-3.5 w-3.5" />
      </Button>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete project?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete &quot;{project.name}&quot; and all associated data (budget lines, KPIs, files, comments). This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleteMut.mutate()}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

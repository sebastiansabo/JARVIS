import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import {
  ListTodo, Plus, ChevronDown, ChevronRight, Send,
  Calendar as CalendarIcon, Clock,
} from 'lucide-react'
import { toast } from 'sonner'
import { fieldSalesApi, type FSVisitTask, type FSTaskFollowUp } from '@/api/fieldSales'

interface Props {
  visitId: number
}

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-700',
  in_progress: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  cancelled: 'bg-red-100 text-red-700',
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'In asteptare',
  in_progress: 'In lucru',
  completed: 'Finalizat',
  cancelled: 'Anulat',
}

function formatDate(d?: string | null) {
  if (!d) return null
  try {
    const dt = new Date(d)
    return dt.toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric' })
  } catch {
    return d
  }
}

function FollowUpSection({ taskId }: { taskId: number }) {
  const [newNote, setNewNote] = useState('')
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['fs-task-follow-ups', taskId],
    queryFn: () => fieldSalesApi.getTaskFollowUps(taskId),
  })

  const addMutation = useMutation({
    mutationFn: (note: string) => fieldSalesApi.addTaskFollowUp(taskId, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fs-task-follow-ups', taskId] })
      queryClient.invalidateQueries({ queryKey: ['fs-visit-tasks'] })
      setNewNote('')
      toast.success('Follow-up adaugat')
    },
    onError: () => toast.error('Eroare la adaugare follow-up'),
  })

  const followUps: FSTaskFollowUp[] = data?.follow_ups || []

  return (
    <div className="pl-6 border-l-2 border-muted space-y-2 mt-2">
      {isLoading ? (
        <Skeleton className="h-4 w-32" />
      ) : (
        followUps.map(fu => (
          <div key={fu.id} className="text-xs space-y-0.5">
            <p className="text-sm">{fu.note}</p>
            <p className="text-muted-foreground">
              {fu.created_by_name && <span>{fu.created_by_name} · </span>}
              {formatDate(fu.created_at)}
            </p>
          </div>
        ))
      )}
      <div className="flex items-center gap-1.5">
        <Input
          value={newNote}
          onChange={e => setNewNote(e.target.value)}
          placeholder="Adauga follow-up..."
          className="h-7 text-xs flex-1"
          onKeyDown={e => {
            if (e.key === 'Enter' && newNote.trim()) {
              addMutation.mutate(newNote.trim())
            }
          }}
        />
        <Button
          size="sm"
          variant="ghost"
          className="h-7 w-7 p-0"
          disabled={!newNote.trim() || addMutation.isPending}
          onClick={() => newNote.trim() && addMutation.mutate(newNote.trim())}
        >
          <Send className="h-3 w-3" />
        </Button>
      </div>
    </div>
  )
}

function TaskRow({ task }: { task: FSVisitTask }) {
  const [expanded, setExpanded] = useState(false)
  const queryClient = useQueryClient()

  const toggleMutation = useMutation({
    mutationFn: (newStatus: string) => fieldSalesApi.updateTask(task.id, { status: newStatus }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fs-visit-tasks'] })
      queryClient.invalidateQueries({ queryKey: ['fs-visit-detail'] })
    },
    onError: () => toast.error('Eroare la actualizare task'),
  })

  const isCompleted = task.status === 'completed'
  const isDue = task.due_date && new Date(task.due_date) < new Date() && !isCompleted

  return (
    <div className="space-y-0">
      <div className="flex items-start gap-2 py-1.5">
        <Checkbox
          checked={isCompleted}
          disabled={toggleMutation.isPending}
          onCheckedChange={v => {
            toggleMutation.mutate(v ? 'completed' : 'pending')
          }}
          className="mt-0.5"
        />
        <div className="flex-1 min-w-0">
          <p className={`text-sm ${isCompleted ? 'line-through text-muted-foreground' : ''}`}>
            {task.description}
          </p>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${STATUS_STYLES[task.status] || ''}`}>
              {STATUS_LABELS[task.status] || task.status}
            </span>
            {task.due_date && (
              <span className={`flex items-center gap-0.5 text-[10px] ${isDue ? 'text-red-600 font-medium' : 'text-muted-foreground'}`}>
                <CalendarIcon className="h-2.5 w-2.5" />
                {formatDate(task.due_date)}
              </span>
            )}
            {task.assigned_to_name && (
              <span className="text-[10px] text-muted-foreground">
                → {task.assigned_to_name}
              </span>
            )}
            {(task.follow_up_count || 0) > 0 && (
              <Badge variant="outline" className="text-[10px] h-4 px-1">
                {task.follow_up_count} follow-up
              </Badge>
            )}
          </div>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="p-1 hover:bg-muted rounded text-muted-foreground"
        >
          {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>
      </div>
      {expanded && <FollowUpSection taskId={task.id} />}
    </div>
  )
}

export function TaskList({ visitId }: Props) {
  const [adding, setAdding] = useState(false)
  const [newDesc, setNewDesc] = useState('')
  const [newDue, setNewDue] = useState('')
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['fs-visit-tasks', visitId],
    queryFn: () => fieldSalesApi.getVisitTasks(visitId),
  })

  const createMutation = useMutation({
    mutationFn: (taskData: { description: string; due_date?: string }) =>
      fieldSalesApi.createTask(visitId, taskData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fs-visit-tasks', visitId] })
      setNewDesc('')
      setNewDue('')
      setAdding(false)
      toast.success('Task creat')
    },
    onError: () => toast.error('Eroare la creare task'),
  })

  const tasks: FSVisitTask[] = data?.tasks || []
  const pendingCount = tasks.filter(t => t.status === 'pending' || t.status === 'in_progress').length

  return (
    <div className="rounded-lg border p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-1.5">
          <ListTodo className="h-4 w-4" />
          Task-uri
          {tasks.length > 0 && (
            <span className="text-xs font-normal text-muted-foreground">
              ({pendingCount} active / {tasks.length} total)
            </span>
          )}
        </h3>
        {!adding && (
          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setAdding(true)}>
            <Plus className="h-3 w-3 mr-1" />
            Adauga
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : (
        <>
          {tasks.length === 0 && !adding && (
            <p className="text-xs text-muted-foreground py-2">Niciun task inca</p>
          )}
          <div className="divide-y">
            {tasks.map(task => (
              <TaskRow key={task.id} task={task} />
            ))}
          </div>
        </>
      )}

      {adding && (
        <div className="border rounded p-2 space-y-2 bg-muted/30">
          <Textarea
            value={newDesc}
            onChange={e => setNewDesc(e.target.value)}
            placeholder="Descriere task..."
            rows={2}
            className="text-sm"
            autoFocus
          />
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              Termen:
            </div>
            <Input
              type="date"
              value={newDue}
              onChange={e => setNewDue(e.target.value)}
              className="h-7 text-xs w-36"
            />
            <div className="flex-1" />
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => { setAdding(false); setNewDesc(''); setNewDue('') }}
            >
              Anuleaza
            </Button>
            <Button
              size="sm"
              className="h-7 text-xs"
              disabled={!newDesc.trim() || createMutation.isPending}
              onClick={() => {
                const taskData: { description: string; due_date?: string } = { description: newDesc.trim() }
                if (newDue) taskData.due_date = newDue
                createMutation.mutate(taskData)
              }}
            >
              {createMutation.isPending ? 'Se creeaza...' : 'Creeaza'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

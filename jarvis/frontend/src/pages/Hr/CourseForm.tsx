import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DateField } from '@/components/ui/date-field'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Loader2 } from 'lucide-react'
import { coursesApi } from '@/api/courses'
import { hrApi } from '@/api/hr'
import { dmsApi } from '@/api/dms'
import { cn } from '@/lib/utils'
import { useFormValidation } from '@/hooks/useFormValidation'
import { FieldError } from '@/components/shared/FieldError'
import { toast } from 'sonner'
import type { Course } from '@/types/courses'

interface Props {
  course?: Course | null
  onSuccess: (id: number) => void
  onCancel: () => void
}

export default function CourseForm({ course, onSuccess, onCancel }: Props) {
  const isEdit = !!course
  const queryClient = useQueryClient()

  const [form, setForm] = useState({
    name: course?.name ?? '',
    course_type_id: course?.course_type_id ? String(course.course_type_id) : '',
    company_id: course?.company_id ? String(course.company_id) : '',
    supplier_id: course?.supplier_id ? String(course.supplier_id) : '',
    trainer_name: course?.trainer_name ?? '',
    start_date: course?.start_date ?? '',
    end_date: course?.end_date ?? '',
    location: course?.location ?? '',
    description: course?.description ?? '',
    budget: course?.budget ? String(course.budget) : '',
    currency: course?.currency ?? 'RON',
    course_code: course?.course_code ?? '',
    duration_hours: course?.duration_hours ? String(course.duration_hours) : '',
    travel_mode: course?.travel_mode ?? '',
  })

  const set = (key: string, val: string) => setForm(prev => ({ ...prev, [key]: val }))

  // Populate form when course data changes (for edit)
  useEffect(() => {
    if (course) {
      setForm({
        name: course.name ?? '',
        course_type_id: course.course_type_id ? String(course.course_type_id) : '',
        company_id: course.company_id ? String(course.company_id) : '',
        supplier_id: course.supplier_id ? String(course.supplier_id) : '',
        trainer_name: course.trainer_name ?? '',
        start_date: course.start_date ?? '',
        end_date: course.end_date ?? '',
        location: course.location ?? '',
        description: course.description ?? '',
        budget: course.budget ? String(course.budget) : '',
        currency: course.currency ?? 'RON',
        course_code: course.course_code ?? '',
        duration_hours: course.duration_hours ? String(course.duration_hours) : '',
        travel_mode: course.travel_mode ?? '',
      })
    }
  }, [course])

  const v = useFormValidation(
    { name: form.name, course_type_id: form.course_type_id, start_date: form.start_date, end_date: form.end_date },
    {
      name: (val) => (!val.trim() ? 'Course name is required' : undefined),
      course_type_id: (val) => (!val ? 'Course type is required' : undefined),
      start_date: (val) => (!val ? 'Start date is required' : undefined),
      end_date: (val) => (!val ? 'End date is required' : undefined),
    },
  )

  const { data: courseTypes = [] } = useQuery({
    queryKey: ['course-types'],
    queryFn: () => coursesApi.getCourseTypes(),
    staleTime: 5 * 60_000,
  })

  const { data: companies = [] } = useQuery({
    queryKey: ['hr-structure-companies'],
    queryFn: () => hrApi.getStructureCompanies(),
  })

  const { data: suppliersData } = useQuery({
    queryKey: ['suppliers-list'],
    queryFn: () => dmsApi.listSuppliers({ active_only: true, limit: 500 }),
    staleTime: 5 * 60_000,
  })
  const suppliers = suppliersData?.suppliers ?? []

  const mutation = useMutation({
    mutationFn: async () => {
      const payload: any = {
        name: form.name.trim(),
        course_type_id: Number(form.course_type_id),
        company_id: form.company_id ? Number(form.company_id) : null,
        supplier_id: form.supplier_id ? Number(form.supplier_id) : null,
        trainer_name: form.trainer_name || null,
        start_date: form.start_date,
        end_date: form.end_date,
        location: form.location || null,
        description: form.description || null,
        budget: form.budget ? Number(form.budget) : null,
        currency: form.currency,
        course_code: form.course_code || null,
        duration_hours: form.duration_hours ? Number(form.duration_hours) : null,
        travel_mode: form.travel_mode || null,
      }
      if (isEdit) {
        await coursesApi.updateCourse(course!.id, payload)
        return course!.id
      } else {
        const res = await coursesApi.createCourse(payload)
        return res.id
      }
    },
    onSuccess: (id) => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      if (isEdit) queryClient.invalidateQueries({ queryKey: ['course', course!.id] })
      toast.success(isEdit ? 'Course updated' : 'Course created')
      onSuccess(id)
    },
    onError: () => toast.error(isEdit ? 'Failed to update course' : 'Failed to create course'),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    v.touchAll()
    if (!v.isValid) return
    if (form.start_date && form.end_date && form.start_date > form.end_date) {
      toast.error('Start date must be before end date')
      return
    }
    mutation.mutate()
  }

  const selectedType = courseTypes.find((t: any) => String(t.id) === form.course_type_id)

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Name */}
        <div className="md:col-span-2 space-y-1.5">
          <Label className="text-xs">Course Name *</Label>
          <Input value={form.name} onChange={e => set('name', e.target.value)} onBlur={() => v.touch('name')}
            className={cn(v.error('name') && 'border-destructive')} placeholder="e.g., SSM Annual Training" />
          <FieldError message={v.error('name')} />
        </div>

        {/* Course Type */}
        <div className="space-y-1.5">
          <Label className="text-xs">Course Type *</Label>
          <Select value={form.course_type_id || '__none__'} onValueChange={val => set('course_type_id', val === '__none__' ? '' : val)}>
            <SelectTrigger className={cn(v.error('course_type_id') && 'border-destructive')}>
              <SelectValue placeholder="Select type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__" disabled>Select type</SelectItem>
              {courseTypes.map((t: any) => <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <FieldError message={v.error('course_type_id')} />
          {selectedType?.default_validity_months && (
            <div className="text-xs text-muted-foreground">
              Validity: {selectedType.default_validity_months} months
              {selectedType.requires_certification && ' — requires certification'}
            </div>
          )}
        </div>

        {/* Course Code */}
        <div className="space-y-1.5">
          <Label className="text-xs">Course Code</Label>
          <Input value={form.course_code} onChange={e => set('course_code', e.target.value)} placeholder="e.g., SSM-2026-001" />
        </div>

        {/* Dates */}
        <div className="space-y-1.5">
          <Label className="text-xs">Start Date *</Label>
          <DateField value={form.start_date} onChange={val => set('start_date', val)}
            className={cn('w-full', v.error('start_date') && 'border-destructive')} />
          <FieldError message={v.error('start_date')} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">End Date *</Label>
          <DateField value={form.end_date} onChange={val => set('end_date', val)}
            className={cn('w-full', v.error('end_date') && 'border-destructive')} />
          <FieldError message={v.error('end_date')} />
        </div>

        {/* Company */}
        <div className="space-y-1.5">
          <Label className="text-xs">Company</Label>
          <Select value={form.company_id || '__none__'} onValueChange={val => set('company_id', val === '__none__' ? '' : val)}>
            <SelectTrigger><SelectValue placeholder="Optional" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">None</SelectItem>
              {(companies as any[]).map((c: any) =>
                typeof c === 'string'
                  ? <SelectItem key={c} value={c}>{c}</SelectItem>
                  : <SelectItem key={c.id} value={String(c.id)}>{c.company ?? c.name}</SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>

        {/* Supplier */}
        <div className="space-y-1.5">
          <Label className="text-xs">Supplier</Label>
          <Select value={form.supplier_id || '__none__'} onValueChange={val => set('supplier_id', val === '__none__' ? '' : val)}>
            <SelectTrigger><SelectValue placeholder="Optional" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">None</SelectItem>
              {suppliers.map((s: any) => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        {/* Trainer */}
        <div className="space-y-1.5">
          <Label className="text-xs">Trainer</Label>
          <Input value={form.trainer_name} onChange={e => set('trainer_name', e.target.value)} placeholder="Trainer name" />
        </div>

        {/* Duration hours */}
        <div className="space-y-1.5">
          <Label className="text-xs">Duration (hours)</Label>
          <Input type="number" step="0.5" min={0} value={form.duration_hours} onChange={e => set('duration_hours', e.target.value)} placeholder="e.g., 8" />
        </div>

        {/* Location */}
        <div className="space-y-1.5">
          <Label className="text-xs">Location</Label>
          <Input value={form.location} onChange={e => set('location', e.target.value)} placeholder="e.g., Sala Conferinte, Etaj 2" />
        </div>

        {/* Travel Mode */}
        <div className="space-y-1.5">
          <Label className="text-xs">Travel Mode</Label>
          <Select value={form.travel_mode || '__none__'} onValueChange={val => set('travel_mode', val === '__none__' ? '' : val)}>
            <SelectTrigger><SelectValue placeholder="Optional" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">None</SelectItem>
              <SelectItem value="Avion">Avion</SelectItem>
              <SelectItem value="Masina">Masina</SelectItem>
              <SelectItem value="Tren">Tren</SelectItem>
              <SelectItem value="Local">Local</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Budget + Currency */}
        <div className="space-y-1.5">
          <Label className="text-xs">Budget</Label>
          <Input type="number" step="0.01" min={0} value={form.budget} onChange={e => set('budget', e.target.value)} placeholder="0.00" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Currency</Label>
          <Select value={form.currency} onValueChange={val => set('currency', val)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="RON">RON</SelectItem>
              <SelectItem value="EUR">EUR</SelectItem>
              <SelectItem value="USD">USD</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Description */}
        <div className="md:col-span-2 space-y-1.5">
          <Label className="text-xs">Description</Label>
          <Textarea value={form.description} onChange={e => set('description', e.target.value)} rows={3} />
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-3 pt-2 border-t">
        <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={mutation.isPending} className="min-w-[120px]">
          {mutation.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
          {mutation.isPending ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Course'}
        </Button>
      </div>
    </form>
  )
}

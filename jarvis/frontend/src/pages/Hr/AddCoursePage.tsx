import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Search, Loader2, Users, CheckCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { DateField } from '@/components/ui/date-field'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState } from '@/components/shared/EmptyState'
import { coursesApi } from '@/api/courses'
import { hrApi } from '@/api/hr'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { useFormValidation } from '@/hooks/useFormValidation'
import { FieldError } from '@/components/shared/FieldError'
import type { HrEmployee } from '@/types/hr'
import type { Enrollment } from '@/types/courses'

export default function AddCoursePage() {
  const { courseId } = useParams<{ courseId: string }>()
  const isEdit = !!courseId
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Course fields
  const [name, setName] = useState('')
  const [courseTypeId, setCourseTypeId] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [supplierId, setSupplierId] = useState('')
  const [trainerName, setTrainerName] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [location, setLocation] = useState('')
  const [description, setDescription] = useState('')
  const [budget, setBudget] = useState('')
  const [currency, setCurrency] = useState('RON')

  // Validation
  const v = useFormValidation(
    { name, courseTypeId, startDate, endDate },
    {
      name: (val) => (!val.trim() ? 'Course name is required' : undefined),
      courseTypeId: (val) => (!val ? 'Course type is required' : undefined),
      startDate: (val) => (!val ? 'Start date is required' : undefined),
      endDate: (val) => (!val ? 'End date is required' : undefined),
    },
  )

  // Queries
  const { data: courseTypes = [] } = useQuery({
    queryKey: ['course-types'],
    queryFn: () => coursesApi.getCourseTypes(),
    staleTime: 5 * 60_000,
  })

  const { data: companies = [] } = useQuery({
    queryKey: ['hr-structure-companies'],
    queryFn: () => hrApi.getStructureCompanies(),
  })

  const { data: existingCourse } = useQuery({
    queryKey: ['course', courseId],
    queryFn: () => coursesApi.getCourse(Number(courseId)),
    enabled: isEdit,
  })

  const { data: enrollments = [] } = useQuery({
    queryKey: ['course-enrollments', courseId],
    queryFn: () => coursesApi.getEnrollments(Number(courseId)),
    enabled: isEdit,
  })

  // Populate form in edit mode
  useEffect(() => {
    if (existingCourse) {
      setName(existingCourse.name)
      setCourseTypeId(String(existingCourse.course_type_id ?? ''))
      setCompanyName(existingCourse.company_name ?? '')
      setSupplierId(String(existingCourse.supplier_id ?? ''))
      setTrainerName(existingCourse.trainer_name ?? '')
      setStartDate(existingCourse.start_date)
      setEndDate(existingCourse.end_date)
      setLocation(existingCourse.location ?? '')
      setDescription(existingCourse.description ?? '')
      setBudget(existingCourse.budget ? String(existingCourse.budget) : '')
      setCurrency(existingCourse.currency ?? 'RON')
    }
  }, [existingCourse])

  // Employee management
  const [newEmployees, setNewEmployees] = useState<HrEmployee[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<HrEmployee[]>([])
  const [searching, setSearching] = useState(false)

  const handleSearch = async (q: string) => {
    setSearchQuery(q)
    if (q.length < 2) { setSearchResults([]); return }
    setSearching(true)
    try {
      const results = await hrApi.searchEmployees(q)
      const existingIds = new Set([
        ...newEmployees.map(e => e.id),
        ...enrollments.map(e => e.employee_id),
      ])
      setSearchResults(results.filter(e => !existingIds.has(e.id)))
    } catch { setSearchResults([]) }
    finally { setSearching(false) }
  }

  const addEmployee = (emp: HrEmployee) => {
    setNewEmployees(prev => [...prev, emp])
    setSearchQuery('')
    setSearchResults([])
  }

  const removeNewEmployee = (id: number) => {
    setNewEmployees(prev => prev.filter(e => e.id !== id))
  }

  // Mutations
  const createMutation = useMutation({
    mutationFn: async () => {
      const res = await coursesApi.createCourse({
        name: name.trim(),
        course_type_id: Number(courseTypeId),
        company_id: null,
        supplier_id: supplierId ? Number(supplierId) : null,
        trainer_name: trainerName || null,
        start_date: startDate,
        end_date: endDate,
        location: location || null,
        description: description || null,
        budget: budget ? Number(budget) : null,
        currency,
      } as any)
      if (newEmployees.length > 0) {
        await coursesApi.addEnrollments(res.id, newEmployees.map(e => e.id))
      }
      return res
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      toast.success('Course created')
      navigate('/app/hr/courses')
    },
    onError: () => toast.error('Failed to create course'),
  })

  const updateMutation = useMutation({
    mutationFn: async () => {
      await coursesApi.updateCourse(Number(courseId), {
        name: name.trim(),
        course_type_id: Number(courseTypeId),
        supplier_id: supplierId ? Number(supplierId) : null,
        trainer_name: trainerName || null,
        start_date: startDate,
        end_date: endDate,
        location: location || null,
        description: description || null,
        budget: budget ? Number(budget) : null,
        currency,
      } as any)
      if (newEmployees.length > 0) {
        await coursesApi.addEnrollments(Number(courseId), newEmployees.map(e => e.id))
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      queryClient.invalidateQueries({ queryKey: ['course', courseId] })
      queryClient.invalidateQueries({ queryKey: ['course-enrollments', courseId] })
      toast.success('Course updated')
      navigate('/app/hr/courses')
    },
    onError: () => toast.error('Failed to update course'),
  })

  // Enrollment actions (edit mode only)
  const completeMutation = useMutation({
    mutationFn: ({ enrollmentId }: { enrollmentId: number }) =>
      coursesApi.completeEnrollment(Number(courseId), enrollmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['course-enrollments', courseId] })
      toast.success('Enrollment marked as completed')
    },
  })

  const removeEnrollmentMutation = useMutation({
    mutationFn: ({ enrollmentId }: { enrollmentId: number }) =>
      coursesApi.deleteEnrollment(Number(courseId), enrollmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['course-enrollments', courseId] })
      toast.success('Employee removed from course')
    },
  })

  // Submit handler
  const handleSubmit = () => {
    v.touchAll()
    if (!v.isValid) return toast.error('Please fix the highlighted fields')
    if (isEdit) {
      updateMutation.mutate()
    } else {
      createMutation.mutate()
    }
  }
  const isPending = createMutation.isPending || updateMutation.isPending

  return (
    <form onSubmit={(e) => { e.preventDefault(); handleSubmit() }} className="space-y-4">
      <PageHeader
        title={isEdit ? 'Edit Course' : 'Add Course'}
        breadcrumbs={[
          { label: 'HR', href: '/app/hr/employees' },
          { label: 'Courses', href: '/app/hr/courses' },
          { label: isEdit ? 'Edit' : 'Add Course' },
        ]}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* LEFT: Course Details */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Course Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* Name field */}
              <div className="space-y-1.5">
                <Label className="text-xs">Course Name *</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} onBlur={() => v.touch('name')} className={cn(v.error('name') && 'border-destructive')} placeholder="e.g., SSM Annual Training" />
                <FieldError message={v.error('name')} />
              </div>

              {/* Course Type selector */}
              <div className="space-y-1.5">
                <Label className="text-xs">Course Type *</Label>
                <Select value={courseTypeId || '__none__'} onValueChange={(val) => setCourseTypeId(val === '__none__' ? '' : val)}>
                  <SelectTrigger className={cn(v.error('courseTypeId') && 'border-destructive')}>
                    <SelectValue placeholder="Select type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__" disabled>Select type</SelectItem>
                    {courseTypes.map((t: any) => (
                      <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldError message={v.error('courseTypeId')} />
              </div>

              {/* Date range */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Start Date *</Label>
                  <DateField value={startDate} onChange={setStartDate} className={cn('w-full', v.error('startDate') && 'border-destructive')} />
                  <FieldError message={v.error('startDate')} />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">End Date *</Label>
                  <DateField value={endDate} onChange={setEndDate} className={cn('w-full', v.error('endDate') && 'border-destructive')} />
                  <FieldError message={v.error('endDate')} />
                </div>
              </div>

              {/* Company + Trainer */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Company</Label>
                  <Select value={companyName || '__none__'} onValueChange={(val) => setCompanyName(val === '__none__' ? '' : val)}>
                    <SelectTrigger><SelectValue placeholder="Optional" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">None</SelectItem>
                      {(companies as string[]).map(c => (
                        <SelectItem key={c} value={c}>{c}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Trainer</Label>
                  <Input value={trainerName} onChange={(e) => setTrainerName(e.target.value)} placeholder="Trainer name" />
                </div>
              </div>

              {/* Location */}
              <div className="space-y-1.5">
                <Label className="text-xs">Location</Label>
                <Input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g., Sala Conferinte, Etaj 2" />
              </div>

              {/* Budget + Currency */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Budget</Label>
                  <Input type="number" step="0.01" min={0} value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="0.00" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Currency</Label>
                  <Select value={currency} onValueChange={setCurrency}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="RON">RON</SelectItem>
                      <SelectItem value="EUR">EUR</SelectItem>
                      <SelectItem value="USD">USD</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Description */}
              <div className="space-y-1.5">
                <Label className="text-xs">Description</Label>
                <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* RIGHT: Employee Enrollment */}
        <div className="lg:col-span-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-sm">Employees</CardTitle>
              <span className="text-xs text-muted-foreground">
                {enrollments.length + newEmployees.length} enrolled
              </span>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Search input */}
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  className="pl-8"
                  placeholder="Search employees by name..."
                  value={searchQuery}
                  onChange={(e) => handleSearch(e.target.value)}
                />
                {searchResults.length > 0 && (
                  <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-lg max-h-48 overflow-y-auto">
                    {searchResults.map(emp => (
                      <button key={emp.id} type="button"
                        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-accent text-sm"
                        onClick={() => addEmployee(emp)}>
                        <Plus className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <div>
                          <div className="font-medium">{emp.name}</div>
                          <div className="text-xs text-muted-foreground">{emp.company ?? ''}{emp.departments ? ` — ${emp.departments}` : ''}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
                {searching && <div className="absolute right-3 top-2.5"><Loader2 className="h-4 w-4 animate-spin" /></div>}
              </div>

              {/* Existing enrollments (edit mode) */}
              {isEdit && enrollments.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-xs font-medium text-muted-foreground px-1">Current Enrollments</div>
                  <div className="space-y-1 max-h-[250px] overflow-y-auto">
                    {enrollments.map((e: Enrollment) => (
                      <div key={e.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
                        <div>
                          <div className="text-sm font-medium">{e.employee_name}</div>
                          <div className="text-xs text-muted-foreground">{e.company ?? ''}{e.department ? ` — ${e.department}` : ''}</div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-xs">{e.enrollment_status}</Badge>
                          {e.enrollment_status === 'enrolled' && (
                            <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-green-600"
                              onClick={() => completeMutation.mutate({ enrollmentId: e.id })}
                              title="Mark Completed">
                              <CheckCircle className="h-3.5 w-3.5" />
                            </Button>
                          )}
                          <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-destructive"
                            onClick={() => removeEnrollmentMutation.mutate({ enrollmentId: e.id })}
                            title="Remove">
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* New employees (to be enrolled on save) */}
              {newEmployees.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-xs font-medium text-muted-foreground px-1">New Employees to Add</div>
                  <div className="space-y-1">
                    {newEmployees.map(emp => (
                      <div key={emp.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
                        <div>
                          <div className="text-sm font-medium">{emp.name}</div>
                          <div className="text-xs text-muted-foreground">{emp.company ?? ''}{emp.departments ? ` — ${emp.departments}` : ''}</div>
                        </div>
                        <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-destructive" onClick={() => removeNewEmployee(emp.id)}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {enrollments.length === 0 && newEmployees.length === 0 && (
                <EmptyState icon={<Users className="h-8 w-8" />} title="No employees added" description="Search and add employees above." />
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Sticky bottom bar */}
      <div className="sticky bottom-0 -mx-6 -mb-6 z-40 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="flex items-center justify-end gap-3 px-6 py-3">
          <Button type="button" variant="outline" onClick={() => navigate('/app/hr/courses')}>
            Cancel
          </Button>
          <Button type="submit" disabled={isPending} className="min-w-[140px]">
            {isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
            {isPending ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Course'}
          </Button>
        </div>
      </div>
    </form>
  )
}

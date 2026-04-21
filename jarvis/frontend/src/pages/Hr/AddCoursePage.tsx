import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Search, Loader2, Users, CheckCircle, FileText, FolderOpen, Award, Unlink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { DateField } from '@/components/ui/date-field'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState } from '@/components/shared/EmptyState'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { coursesApi } from '@/api/courses'
import { dmsApi } from '@/api/dms'
import { hrApi } from '@/api/hr'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { useFormValidation } from '@/hooks/useFormValidation'
import { FieldError } from '@/components/shared/FieldError'
import type { HrEmployee } from '@/types/hr'
import type { Enrollment, Certification } from '@/types/courses'
import type { DmsModuleLink } from '@/types/dms'

function formatDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ro-RO')
}

function expiryColor(days: number | null) {
  if (days === null) return ''
  if (days <= 0) return 'text-red-600 bg-red-50'
  if (days <= 30) return 'text-red-600 bg-red-50'
  if (days <= 90) return 'text-yellow-700 bg-yellow-50'
  return 'text-green-700 bg-green-50'
}

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

  // Delete state
  const [deleteOpen, setDeleteOpen] = useState(false)

  // Right panel active tab
  const [rightTab, setRightTab] = useState('employees')

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

  const { data: invoices = [] } = useQuery({
    queryKey: ['course-invoices', courseId],
    queryFn: () => coursesApi.getCourseInvoices(Number(courseId)),
    enabled: isEdit,
  })

  const { data: dmsLinks } = useQuery({
    queryKey: ['course-dms-links', courseId],
    queryFn: () => dmsApi.getModuleLinks('hr_course', Number(courseId)),
    enabled: isEdit,
  })
  const documents: DmsModuleLink[] = dmsLinks?.links ?? []

  const { data: certifications = [] } = useQuery({
    queryKey: ['course-certifications', courseId],
    queryFn: () => coursesApi.getCertifications({ employee_id: undefined }),
    enabled: isEdit,
    select: (data: Certification[]) => {
      // Filter certs to only those for employees enrolled in this course
      const enrolledEmployeeIds = new Set(enrollments.map(e => e.employee_id))
      return data.filter(c => enrolledEmployeeIds.has(c.employee_id))
    },
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

  const deleteMutation = useMutation({
    mutationFn: () => coursesApi.deleteCourse(Number(courseId)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      toast.success('Course moved to bin')
      navigate('/app/hr/courses')
    },
    onError: () => toast.error('Failed to delete course'),
  })

  const approvalMutation = useMutation({
    mutationFn: () => coursesApi.submitApproval(Number(courseId)),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['course', courseId] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      toast.success(`Course ${res.status === 'approved' ? 'approved' : 'submitted for approval'}`)
    },
    onError: () => toast.error('Failed to submit for approval'),
  })

  // Enrollment actions (edit mode only)
  const completeMutation = useMutation({
    mutationFn: ({ enrollmentId }: { enrollmentId: number }) =>
      coursesApi.completeEnrollment(Number(courseId), enrollmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['course-enrollments', courseId] })
      queryClient.invalidateQueries({ queryKey: ['course-certifications', courseId] })
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

  // Invoice unlink
  const unlinkInvoiceMutation = useMutation({
    mutationFn: (invoiceId: number) => coursesApi.unlinkInvoice(Number(courseId), invoiceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['course-invoices', courseId] })
      toast.success('Invoice unlinked')
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

  // Selected course type info
  const selectedType = courseTypes.find(t => String(t.id) === courseTypeId)

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
        <div className="lg:col-span-2 space-y-4">
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
                {selectedType?.default_validity_months && (
                  <div className="text-xs text-muted-foreground">
                    Validity: {selectedType.default_validity_months} months
                    {selectedType.requires_certification && ' — requires certification'}
                  </div>
                )}
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

          {/* Status info card (edit mode) */}
          {isEdit && existingCourse && (
            <Card>
              <CardContent className="py-3 flex items-center justify-between">
                <div className="text-xs text-muted-foreground">
                  Status: <Badge variant="outline" className="ml-1">{existingCourse.status}</Badge>
                </div>
                {existingCourse.status === 'draft' && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    disabled={approvalMutation.isPending}
                    onClick={() => approvalMutation.mutate()}
                  >
                    {approvalMutation.isPending ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
                    Submit for Approval
                  </Button>
                )}
              </CardContent>
            </Card>
          )}
        </div>

        {/* RIGHT: Tabbed panels */}
        <div className="lg:col-span-3">
          <Card>
            <Tabs value={rightTab} onValueChange={setRightTab}>
              <CardHeader className="pb-0">
                <TabsList className="w-full justify-start">
                  <TabsTrigger value="employees" className="text-xs gap-1.5">
                    <Users className="h-3.5 w-3.5" /> Employees
                    {(enrollments.length + newEmployees.length) > 0 && (
                      <Badge variant="secondary" className="h-4 px-1 text-[10px]">{enrollments.length + newEmployees.length}</Badge>
                    )}
                  </TabsTrigger>
                  {isEdit && (
                    <>
                      <TabsTrigger value="invoices" className="text-xs gap-1.5">
                        <FileText className="h-3.5 w-3.5" /> Invoices
                        {invoices.length > 0 && (
                          <Badge variant="secondary" className="h-4 px-1 text-[10px]">{invoices.length}</Badge>
                        )}
                      </TabsTrigger>
                      <TabsTrigger value="documents" className="text-xs gap-1.5">
                        <FolderOpen className="h-3.5 w-3.5" /> Documents
                        {documents.length > 0 && (
                          <Badge variant="secondary" className="h-4 px-1 text-[10px]">{documents.length}</Badge>
                        )}
                      </TabsTrigger>
                      <TabsTrigger value="certifications" className="text-xs gap-1.5">
                        <Award className="h-3.5 w-3.5" /> Certifications
                        {certifications.length > 0 && (
                          <Badge variant="secondary" className="h-4 px-1 text-[10px]">{certifications.length}</Badge>
                        )}
                      </TabsTrigger>
                    </>
                  )}
                </TabsList>
              </CardHeader>
              <CardContent className="pt-4">
                {/* EMPLOYEES TAB */}
                <TabsContent value="employees" className="mt-0 space-y-4">
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
                </TabsContent>

                {/* INVOICES TAB */}
                {isEdit && (
                  <TabsContent value="invoices" className="mt-0 space-y-3">
                    {invoices.length === 0 ? (
                      <EmptyState icon={<FileText className="h-8 w-8" />} title="No invoices linked" description="Link invoices from the accounting module." />
                    ) : (
                      <div className="space-y-1.5 max-h-[350px] overflow-y-auto">
                        {invoices.map((inv) => (
                          <div key={inv.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
                            <div>
                              <div className="text-sm font-medium">{inv.invoice_number}</div>
                              <div className="text-xs text-muted-foreground">
                                {inv.supplier} — {formatDate(inv.invoice_date)} — {Number(inv.invoice_value).toLocaleString()} {inv.currency}
                              </div>
                            </div>
                            <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-destructive"
                              onClick={() => unlinkInvoiceMutation.mutate(inv.id)} title="Unlink">
                              <Unlink className="h-3 w-3" />
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}
                  </TabsContent>
                )}

                {/* DOCUMENTS TAB */}
                {isEdit && (
                  <TabsContent value="documents" className="mt-0 space-y-3">
                    {documents.length === 0 ? (
                      <EmptyState icon={<FolderOpen className="h-8 w-8" />} title="No documents linked" description="Link documents from the DMS module." />
                    ) : (
                      <div className="space-y-1.5 max-h-[350px] overflow-y-auto">
                        {documents.map((doc) => (
                          <div key={doc.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
                            <div>
                              <div className="text-sm font-medium">
                                {doc.link_type === 'folder' ? doc.folder_name : doc.document_title}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {doc.link_type === 'folder' ? 'Folder' : 'Document'} — Linked by {doc.linked_by_name ?? 'Unknown'} on {formatDate(doc.created_at)}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </TabsContent>
                )}

                {/* CERTIFICATIONS TAB */}
                {isEdit && (
                  <TabsContent value="certifications" className="mt-0 space-y-3">
                    {certifications.length === 0 ? (
                      <EmptyState icon={<Award className="h-8 w-8" />} title="No certifications" description="Certifications are auto-created when enrollments are marked as completed." />
                    ) : (
                      <div className="space-y-1.5 max-h-[350px] overflow-y-auto">
                        {certifications.map((cert) => (
                          <div key={cert.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
                            <div>
                              <div className="text-sm font-medium">{cert.employee_name}</div>
                              <div className="text-xs text-muted-foreground">
                                {cert.course_type_name} — #{cert.certificate_number ?? 'N/A'}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                Issued: {formatDate(cert.issued_date)} — Expires: {formatDate(cert.expiry_date)}
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              {cert.days_until_expiry !== null && (
                                <Badge className={cn('text-xs border-0', expiryColor(cert.days_until_expiry))}>
                                  {cert.days_until_expiry <= 0 ? 'Expired' : `${cert.days_until_expiry}d`}
                                </Badge>
                              )}
                              <Badge variant="outline" className="text-xs">{cert.status}</Badge>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </TabsContent>
                )}
              </CardContent>
            </Tabs>
          </Card>
        </div>
      </div>

      {/* Sticky bottom bar */}
      <div className="sticky bottom-0 -mx-6 -mb-6 z-40 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="flex items-center justify-between gap-3 px-6 py-3">
          <div>
            {isEdit && (
              <Button type="button" variant="destructive" size="sm" onClick={() => setDeleteOpen(true)}>
                <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Delete
              </Button>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Button type="button" variant="outline" onClick={() => navigate('/app/hr/courses')}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending} className="min-w-[140px]">
              {isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
              {isPending ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Course'}
            </Button>
          </div>
        </div>
      </div>

      {/* Delete confirm dialog */}
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Course"
        description="This course will be moved to the bin. You can restore it later from the Bin view."
        onConfirm={() => {
          deleteMutation.mutate()
          setDeleteOpen(false)
        }}
        destructive
      />
    </form>
  )
}

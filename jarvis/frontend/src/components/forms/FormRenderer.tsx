import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import type { FormField } from '@/types/forms'

interface FormRendererProps {
  schema: FormField[]
  onSubmit: (answers: Record<string, unknown>) => void
  submitting?: boolean
  submitLabel?: string
}

export function FormRenderer({ schema, onSubmit, submitting, submitLabel = 'Submit' }: FormRendererProps) {
  const [answers, setAnswers] = useState<Record<string, unknown>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})

  const setValue = (fieldId: string, value: unknown) => {
    setAnswers((prev) => ({ ...prev, [fieldId]: value }))
    if (errors[fieldId]) {
      setErrors((prev) => { const copy = { ...prev }; delete copy[fieldId]; return copy })
    }
  }

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {}
    for (const field of schema) {
      if (field.type === 'heading' || field.type === 'paragraph') continue
      if (field.required) {
        const val = answers[field.id]
        if (val === undefined || val === null || val === '' || (Array.isArray(val) && val.length === 0)) {
          newErrors[field.id] = `${field.label || 'This field'} is required`
        }
      }
      // Email validation
      if (field.type === 'email' && answers[field.id]) {
        if (!String(answers[field.id]).includes('@')) {
          newErrors[field.id] = 'Please enter a valid email'
        }
      }
    }
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (validate()) onSubmit(answers)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {schema.map((field) => (
        <FieldComponent
          key={field.id}
          field={field}
          value={answers[field.id]}
          error={errors[field.id]}
          onChange={(val) => setValue(field.id, val)}
        />
      ))}
      <Button type="submit" className="w-full" disabled={submitting}>
        {submitting ? 'Submitting...' : submitLabel}
      </Button>
    </form>
  )
}

interface FieldProps {
  field: FormField
  value: unknown
  error?: string
  onChange: (value: unknown) => void
}

function FieldComponent({ field, value, error, onChange }: FieldProps) {
  switch (field.type) {
    case 'heading':
      return <h2 className="text-lg font-bold pt-2">{field.label}</h2>

    case 'paragraph':
      return <p className="text-sm text-muted-foreground">{field.label}</p>

    case 'hidden':
      return null

    case 'short_text':
    case 'email':
    case 'phone':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Input
            type={field.type === 'email' ? 'email' : field.type === 'phone' ? 'tel' : 'text'}
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'number':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Input
            type="number"
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'long_text':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Textarea
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder}
            rows={3}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'date':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Input
            type="date"
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'dropdown':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Select value={(value as string) ?? ''} onValueChange={onChange}>
            <SelectTrigger>
              <SelectValue placeholder={field.placeholder || 'Select...'} />
            </SelectTrigger>
            <SelectContent>
              {(field.options || []).map((opt) => (
                <SelectItem key={opt} value={opt}>{opt}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'radio':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <RadioGroup value={(value as string) ?? ''} onValueChange={onChange}>
            {(field.options || []).map((opt) => (
              <div key={opt} className="flex items-center space-x-2">
                <RadioGroupItem value={opt} id={`${field.id}-${opt}`} />
                <Label htmlFor={`${field.id}-${opt}`} className="font-normal">{opt}</Label>
              </div>
            ))}
          </RadioGroup>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'checkbox':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <div className="space-y-1">
            {(field.options || []).map((opt) => {
              const checked = Array.isArray(value) && value.includes(opt)
              return (
                <div key={opt} className="flex items-center space-x-2">
                  <Checkbox
                    id={`${field.id}-${opt}`}
                    checked={checked}
                    onCheckedChange={(isChecked) => {
                      const current = Array.isArray(value) ? [...value] : []
                      if (isChecked) {
                        current.push(opt)
                      } else {
                        const idx = current.indexOf(opt)
                        if (idx >= 0) current.splice(idx, 1)
                      }
                      onChange(current)
                    }}
                  />
                  <Label htmlFor={`${field.id}-${opt}`} className="font-normal">{opt}</Label>
                </div>
              )
            })}
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'file_upload':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Input
            type="file"
            onChange={(e) => {
              const file = e.target.files?.[0]
              onChange(file?.name ?? '')
            }}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    default:
      return null
  }
}

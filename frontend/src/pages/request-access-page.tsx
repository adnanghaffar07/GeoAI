import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { CircleCheck } from 'lucide-react'
import { useId } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'
import { z } from 'zod'

import { sendOrganizationRequest } from '@/api/platform'
import { AuthCard } from '@/components/auth-card'
import { ErrorMessage } from '@/components/error-message'
import { Button } from '@/components/ui/button'
import { TextField } from '@/components/ui/field'

const schema = z.object({
  organization_name: z.string().trim().min(2, 'Enter your organization’s name.').max(200),
  city_or_agency: z.string().trim().min(2, 'Enter your city or agency.').max(200),
  contact_name: z.string().trim().min(2, 'Enter your name.').max(200),
  contact_email: z.string().trim().min(1, 'Enter your work email.').email('Enter a valid email address.').max(320),
  phone: z.string().trim().max(40, 'Phone number is too long.'),
  note: z.string().trim().max(2000, 'Please keep it under 2,000 characters.'),
  website: z.string(),
})
type FormValues = z.infer<typeof schema>

/**
 * Public page (CR-004): a new organization asks for access. Nothing is created until a
 * platform admin approves; then the contact person receives an invitation link and sets
 * their own password (no password is asked for here).
 */
export function RequestAccessPage() {
  const noteId = useId()
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { organization_name: '', city_or_agency: '', contact_name: '', contact_email: '', phone: '', note: '', website: '' },
  })
  const mutation = useMutation({ mutationFn: (values: FormValues) => sendOrganizationRequest(values) })
  const errors = form.formState.errors

  if (mutation.isSuccess) {
    return (
      <AuthCard title="Request sent">
        <div role="status" className="flex gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
          <CircleCheck className="mt-0.5 size-5 shrink-0" aria-hidden />
          <div className="space-y-2">
            <p className="font-medium">{mutation.data.message}</p>
            <p>You cannot sign in yet. When your request is approved, you will receive a link to set your password.</p>
          </div>
        </div>
        <Link to="/sign-in" className="link mt-6 inline-block text-sm">
          Back to sign in
        </Link>
      </AuthCard>
    )
  }

  return (
    <AuthCard
      title="Request access"
      subtitle="Tell us about your organization. We review every request and email you an invitation link when it is approved."
    >
      <form noValidate onSubmit={form.handleSubmit((values) => mutation.mutate(values))} className="space-y-4">
        <TextField label="Organization name" autoComplete="organization" error={errors.organization_name?.message} {...form.register('organization_name')} />
        <TextField
          label="City or agency"
          hint="For example: City of Naperville, Public Works"
          error={errors.city_or_agency?.message}
          {...form.register('city_or_agency')}
        />
        <TextField label="Your name" autoComplete="name" error={errors.contact_name?.message} {...form.register('contact_name')} />
        <TextField
          label="Work email"
          type="email"
          autoComplete="email"
          hint="The invitation link will be sent to this address."
          error={errors.contact_email?.message}
          {...form.register('contact_email')}
        />
        <TextField label="Phone (optional)" type="tel" autoComplete="tel" error={errors.phone?.message} {...form.register('phone')} />
        <div>
          <label htmlFor={noteId} className="mb-1.5 block text-sm font-medium text-asphalt-800">
            What would you like to use it for? (optional)
          </label>
          <textarea
            id={noteId}
            className="control min-h-24"
            maxLength={2000}
            aria-invalid={errors.note ? true : undefined}
            {...form.register('note')}
          />
          {errors.note && <p className="mt-1.5 text-sm text-red-700">{errors.note.message}</p>}
        </div>
        {/* Trap for robots: hidden from people and screen readers, so only robots fill it in. */}
        <div aria-hidden className="absolute -left-[9999px] h-px w-px overflow-hidden">
          <label>
            Website
            <input tabIndex={-1} autoComplete="off" {...form.register('website')} />
          </label>
        </div>
        {mutation.isError && <ErrorMessage title="Could not send your request" error={mutation.error} />}
        <Button type="submit" variant="accent" busy={mutation.isPending} className="w-full">
          Send request
        </Button>
      </form>
      <p className="mt-4 text-sm text-asphalt-500">
        Already have an account?{' '}
        <Link to="/sign-in" className="link">
          Sign in
        </Link>
      </p>
    </AuthCard>
  )
}

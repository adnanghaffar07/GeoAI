import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'
import { z } from 'zod'

import { signIn } from '@/api/auth'
import { useAuth } from '@/auth/auth-context'
import { AuthCard } from '@/components/auth-card'
import { ErrorMessage } from '@/components/error-message'
import { Button } from '@/components/ui/button'
import { PasswordField, TextField } from '@/components/ui/field'
import { safeNextPath } from '@/lib/safe-redirect'

const schema = z.object({
  email: z.string().trim().min(1, 'Enter your email.').email('Enter a valid email address.'),
  password: z.string().min(1, 'Enter your password.'),
})
type FormValues = z.infer<typeof schema>

const NOTICES: Record<string, string> = {
  'password-changed': 'Your password was changed. Sign in with your new password.',
  'joined': 'You have joined the organization. Sign in to continue.',
}

/** S01 Sign in. */
export function SignInPage() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNextPath(params.get('next'))
  const notice = NOTICES[params.get('notice') ?? '']

  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: '', password: '' } })
  const mutation = useMutation({
    mutationFn: (values: FormValues) => signIn(values.email, values.password),
    onSuccess: (me) => {
      auth.setSignedIn(me)
      void navigate(next, { replace: true })
    },
  })

  if (auth.status === 'signed_in') return <Navigate to={next} replace />

  return (
    <AuthCard title="Sign in" subtitle="Use the email and password you chose when you accepted your invitation.">
      {notice && (
        <p role="status" className="mb-4 rounded-lg bg-green-50 p-3 text-sm text-green-800">
          {notice}
        </p>
      )}
      <form noValidate onSubmit={form.handleSubmit((values) => mutation.mutate(values))} className="space-y-4">
        <TextField
          label="Email"
          type="email"
          autoComplete="username"
          error={form.formState.errors.email?.message}
          {...form.register('email')}
        />
        <PasswordField
          label="Password"
          autoComplete="current-password"
          error={form.formState.errors.password?.message}
          {...form.register('password')}
        />
        {mutation.isError && <ErrorMessage title="Could not sign in" error={mutation.error} />}
        <Button type="submit" variant="accent" busy={mutation.isPending} className="w-full">
          Sign in
        </Button>
      </form>
      <p className="mt-4 text-sm text-asphalt-500">Forgot your password? Ask your administrator to make a password reset link for you.</p>
      <div className="mt-8 border-t border-asphalt-100 pt-6 text-sm">
        <p className="text-asphalt-600">New organization?</p>
        <Link to="/request-access" className="btn btn-secondary mt-2 w-full">
          Request access
        </Link>
      </div>
    </AuthCard>
  )
}

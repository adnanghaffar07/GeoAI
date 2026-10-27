import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useNavigate, useParams } from 'react-router'
import { z } from 'zod'

import { getPasswordReset, PASSWORD_MIN_LENGTH, setNewPassword } from '@/api/auth'
import { useAuth } from '@/auth/auth-context'
import { AuthCard } from '@/components/auth-card'
import { ErrorMessage } from '@/components/error-message'
import { LinkProblem } from '@/components/link-problem'
import { Button } from '@/components/ui/button'
import { PasswordField } from '@/components/ui/field'
import { LoadingScreen } from '@/components/ui/loading-screen'

const schema = z
  .object({
    password: z.string().min(PASSWORD_MIN_LENGTH, `Use at least ${PASSWORD_MIN_LENGTH} characters.`).max(128),
    confirm: z.string(),
  })
  .refine((values) => values.password === values.confirm, {
    path: ['confirm'],
    message: 'The two passwords do not match.',
  })
type FormValues = z.infer<typeof schema>

/** S03 Set new password (from an admin-created reset link). */
export function ResetPasswordPage() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const auth = useAuth()
  const info = useQuery({ queryKey: ['password-reset', token], queryFn: () => getPasswordReset(token), retry: false })
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { password: '', confirm: '' } })
  const mutation = useMutation({
    mutationFn: (values: FormValues) => setNewPassword(token, values.password),
    onSuccess: () => {
      auth.clearSession() // the server signed this person out everywhere
      void navigate('/sign-in?notice=password-changed', { replace: true })
    },
  })

  if (info.isPending) return <LoadingScreen label="Checking your link…" />
  if (info.isError) {
    return (
      <AuthCard title="Set a new password">
        <LinkProblem error={info.error} whatToDo="Ask your administrator for a new reset link." />
      </AuthCard>
    )
  }

  return (
    <AuthCard
      title="Set a new password"
      subtitle={
        <>
          For <strong>{info.data.email}</strong>. After you set it, you will be signed out on all your devices and can sign in again
          with the new password.
        </>
      }
    >
      <form noValidate className="space-y-4" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
        <PasswordField
          label="New password"
          autoComplete="new-password"
          hint={`At least ${PASSWORD_MIN_LENGTH} characters.`}
          error={form.formState.errors.password?.message}
          {...form.register('password')}
        />
        <PasswordField
          label="Repeat new password"
          autoComplete="new-password"
          error={form.formState.errors.confirm?.message}
          {...form.register('confirm')}
        />
        {mutation.isError && <ErrorMessage title="Could not set your password" error={mutation.error} />}
        <Button type="submit" variant="accent" className="w-full" busy={mutation.isPending}>
          Set password
        </Button>
      </form>
    </AuthCard>
  )
}

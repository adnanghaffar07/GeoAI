import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useNavigate, useParams } from 'react-router'
import { z } from 'zod'

import { acceptInvitation, authQueryKeys, getInvitation, PASSWORD_MIN_LENGTH, roleLabel } from '@/api/auth'
import { AuthCard } from '@/components/auth-card'
import { ErrorMessage } from '@/components/error-message'
import { LinkProblem } from '@/components/link-problem'
import { Button } from '@/components/ui/button'
import { PasswordField, TextField } from '@/components/ui/field'
import { LoadingScreen } from '@/components/ui/loading-screen'

const schema = z
  .object({
    full_name: z.string().trim().min(1, 'Enter your name.').max(200),
    password: z.string().min(PASSWORD_MIN_LENGTH, `Use at least ${PASSWORD_MIN_LENGTH} characters.`).max(128),
    confirm: z.string(),
  })
  .refine((values) => values.password === values.confirm, {
    path: ['confirm'],
    message: 'The two passwords do not match.',
  })
type FormValues = z.infer<typeof schema>

/** S02 Accept invitation. */
export function AcceptInvitationPage() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const info = useQuery({ queryKey: ['invitation', token], queryFn: () => getInvitation(token), retry: false })
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: '', password: '', confirm: '' },
  })

  const mutation = useMutation({
    mutationFn: (body: { full_name?: string; password?: string }) => acceptInvitation(token, body),
    onSuccess: async ({ result }) => {
      if (result === 'signed_in') {
        await queryClient.invalidateQueries({ queryKey: authQueryKeys.me })
        void navigate('/', { replace: true })
      } else {
        void navigate('/sign-in?notice=joined', { replace: true })
      }
    },
  })

  if (info.isPending) return <LoadingScreen label="Checking your invitation…" />
  if (info.isError) {
    return (
      <AuthCard title="Invitation">
        <LinkProblem error={info.error} whatToDo="Ask your administrator to send you a new invitation." />
      </AuthCard>
    )
  }

  const invitation = info.data
  const subtitle = (
    <>
      You have been invited to <strong>{invitation.organization_name}</strong> as{' '}
      <strong>{roleLabel(invitation.org_role)}</strong>.
    </>
  )

  if (invitation.account_exists) {
    return (
      <AuthCard title="Join organization" subtitle={subtitle}>
        <p className="mb-4 text-sm text-asphalt-500">
          You already have an account ({invitation.email}). Click the button to join, then sign in with your usual password.
        </p>
        {mutation.isError && <ErrorMessage title="Could not join the organization" error={mutation.error} />}
        <Button className="w-full" busy={mutation.isPending} onClick={() => mutation.mutate({})}>
          Join {invitation.organization_name}
        </Button>
      </AuthCard>
    )
  }

  return (
    <AuthCard title="Create your account" subtitle={subtitle}>
      <form
        noValidate
        className="space-y-4"
        onSubmit={form.handleSubmit(({ full_name, password }) => mutation.mutate({ full_name, password }))}
      >
        <TextField label="Email" value={invitation.email} readOnly disabled />
        <TextField label="Your name" autoComplete="name" error={form.formState.errors.full_name?.message} {...form.register('full_name')} />
        <PasswordField
          label="Password"
          autoComplete="new-password"
          hint={`At least ${PASSWORD_MIN_LENGTH} characters.`}
          error={form.formState.errors.password?.message}
          {...form.register('password')}
        />
        <PasswordField
          label="Repeat password"
          autoComplete="new-password"
          error={form.formState.errors.confirm?.message}
          {...form.register('confirm')}
        />
        {mutation.isError && <ErrorMessage title="Could not create your account" error={mutation.error} />}
        <Button type="submit" variant="accent" className="w-full" busy={mutation.isPending}>
          Create account
        </Button>
      </form>
    </AuthCard>
  )
}

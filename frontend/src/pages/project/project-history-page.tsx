import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { listProjectMembers, projectQueryKeys } from '@/api/projects'
import { HistoryView } from '@/components/history-view'
import { PageIntro } from '@/components/ui/page-intro'
import { useProject } from '@/pages/project/project-layout'

/** S19 History of one project. */
export function ProjectHistoryPage() {
  const project = useProject()
  const members = useQuery({ queryKey: projectQueryKeys.members(project.id), queryFn: ({ signal }) => listProjectMembers(project.id, signal) })
  const people = useMemo(() => {
    const seen = new Map<string, string>()
    for (const member of members.data?.items ?? []) seen.set(member.user_id, member.full_name)
    return [...seen.entries()].map(([id, name]) => ({ id, name }))
  }, [members.data])
  return (
    <div className="space-y-4">
      <PageIntro title="History">Everything that was done in this project: who did it and when. Nothing here can be changed or deleted.</PageIntro>
      <HistoryView scope={{ projectId: project.id }} people={people} />
    </div>
  )
}

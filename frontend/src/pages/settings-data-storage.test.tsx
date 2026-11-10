import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { DataStorage } from '@/api/data-storage'
import { SettingsDataStoragePage } from '@/pages/settings-data-storage-page'
import { expectNoAccessibilityProblems } from '@/test/a11y'
import { ADMIN_WITH_PROJECTS, json } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

const APP: DataStorage = {
  kind: 'app', place: 'GeoInfraLens AI private storage', endpoint: null, bucket: null, region: null, prefix: null,
  access_key_id: null, has_secret: false, location_note: null, verified_at: null, updated_at: null,
  encryption: 'AES-256-GCM, every file', can_edit: true,
}  // prettier-ignore

describe('Data storage (team lead plan, Phase 2)', () => {
  it('lets an admin move new files to the organization\'s own storage, tested first', async () => {
    const own = { ...APP, kind: 's3' as const, place: "Your organization's own storage", endpoint: 'https://minio.city.example', bucket: 'photos', access_key_id: 'AKEY', has_secret: true }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((_input, init) =>
      Promise.resolve(json(init?.method === 'PUT' ? own : APP)),
    )
    const { container } = renderWithProviders(<SettingsDataStoragePage />, { me: ADMIN_WITH_PROJECTS })
    expect(await screen.findByText('GeoInfraLens AI private storage')).toBeInTheDocument()
    expect(screen.getByText(/Encrypted \(AES-256-GCM/)).toBeInTheDocument()
    await expectNoAccessibilityProblems(container)

    await userEvent.click(screen.getByRole('radio', { name: /Your own storage/ }))
    await userEvent.type(screen.getByLabelText('Storage address'), 'https://minio.city.example')
    await userEvent.type(screen.getByLabelText('Bucket name'), 'photos')
    await userEvent.type(screen.getByLabelText('Access key'), 'AKEY')
    await userEvent.type(screen.getByLabelText('Secret key'), 'very-secret')
    await userEvent.click(screen.getByRole('button', { name: 'Test and save' }))

    expect(await screen.findByText(/minio.city.example · photos/)).toBeInTheDocument()
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')!
    expect(JSON.parse(String(put[1]!.body))).toMatchObject({ kind: 's3', bucket: 'photos', secret_key: 'very-secret' })
  })

  it('shows members where the data is, without the form', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...APP, can_edit: false }))
    renderWithProviders(<SettingsDataStoragePage />, { me: ADMIN_WITH_PROJECTS })
    expect(await screen.findByText('GeoInfraLens AI private storage')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Save/ })).not.toBeInTheDocument()
  })
})

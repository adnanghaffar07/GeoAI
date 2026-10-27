import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import * as imagesApi from '@/api/images'
import { ApiError } from '@/lib/api-client'
import { ProjectLayout } from '@/pages/project/project-layout'
import { ProjectUploadPage } from '@/pages/project/project-upload-page'
import { json, makeImage, PROJECT } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'

function renderUpload() {
  vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(json(PROJECT)))
  renderWithProviders(
    <Routes>
      <Route path="/projects/:projectId" element={<ProjectLayout />}>
        <Route path="upload" element={<ProjectUploadPage />} />
      </Route>
    </Routes>,
    { route: '/projects/p1/upload' },
  )
}

const photo = (name: string, type = 'image/jpeg') => new File(['x'], name, { type })

describe('ProjectUploadPage', () => {
  it('uploads only after the permission box is ticked and reports location and duplicates', async () => {
    const upload = vi
      .spyOn(imagesApi, 'uploadImage')
      .mockResolvedValueOnce({ duplicate: false, image: makeImage({ location: null, location_source: 'none' }) })
      .mockResolvedValueOnce({ duplicate: true, image: makeImage() })
    renderUpload()
    const chooser = await screen.findByLabelText('Choose photos')

    await userEvent.upload(chooser, [photo('a.jpg'), photo('b.jpg')])
    const button = screen.getByRole('button', { name: 'Upload 2 photos' })
    expect(button).toBeDisabled()

    await userEvent.click(screen.getByLabelText(/I am allowed to upload these photos/))
    await userEvent.click(button)

    expect(await screen.findByText(/Already uploaded/)).toBeInTheDocument()
    expect(screen.getByText(/^Uploaded/)).toBeInTheDocument()
    expect(screen.getByText('No location yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Add location on map' })).toHaveAttribute('href', '/projects/p1/photos?missing=1')
    expect(upload).toHaveBeenCalledTimes(2)
  })

  it('refuses files that are not photos before uploading', async () => {
    renderUpload()
    const chooser = await screen.findByLabelText('Choose photos')

    await userEvent.upload(chooser, photo('notes.pdf', 'application/pdf'), { applyAccept: false })

    expect(screen.getByText('Only JPEG and PNG photos can be uploaded.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('offers Retry after a network failure and does not resend finished files', async () => {
    const upload = vi
      .spyOn(imagesApi, 'uploadImage')
      .mockResolvedValueOnce({ duplicate: false, image: makeImage() })
      .mockRejectedValueOnce(new ApiError({ status: 0, code: 'network_error', message: 'Cannot reach the server.' }))
      .mockResolvedValueOnce({ duplicate: false, image: makeImage({ id: 'img2' }) })
    renderUpload()
    await userEvent.upload(await screen.findByLabelText('Choose photos'), [photo('a.jpg'), photo('b.jpg')])
    await userEvent.click(screen.getByLabelText(/I am allowed to upload these photos/))
    await userEvent.click(screen.getByRole('button', { name: 'Upload 2 photos' }))

    await userEvent.click(await screen.findByRole('button', { name: 'Try again' }))

    await screen.findAllByText('Done')
    expect(screen.getAllByText('Done')).toHaveLength(2)
    expect(upload).toHaveBeenCalledTimes(3)
    expect(upload.mock.calls.map(([, file]) => file.name)).toEqual(['a.jpg', 'b.jpg', 'b.jpg'])
  })
})

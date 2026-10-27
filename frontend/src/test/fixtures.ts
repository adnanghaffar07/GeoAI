/** Shared test data for project screens. */

import type { Me } from '@/api/auth'
import type { Finding, ReviewOptions } from '@/api/findings'
import type { ImageInfo } from '@/api/images'
import type { ProjectDetail } from '@/api/projects'
import { ADMIN_ME } from '@/test/render'

export const page = <T,>(items: T[]) => ({ items, page: 1, page_size: items.length, total: items.length })
export const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

const membership = ADMIN_ME.memberships[0]!

export const ADMIN_WITH_PROJECTS: Me = {
  ...ADMIN_ME,
  memberships: [{ ...membership, permissions: [...membership.permissions, 'project.create', 'org.settings.edit'] }],
}

export const MEMBER_ME: Me = {
  user: { id: 'u2', email: 'bo@city.test', full_name: 'Bo Worker' },
  memberships: [{ ...membership, org_role: 'org_member', permissions: ['org.view'] }],
}

export const AREA = {
  type: 'Polygon' as const,
  coordinates: [
    [
      [-122.43, 37.77],
      [-122.41, 37.77],
      [-122.41, 37.79],
      [-122.43, 37.79],
      [-122.43, 37.77],
    ],
  ],
}

export const PROJECT: ProjectDetail = {
  id: 'p1',
  organization_id: 'org1',
  name: 'Downtown streets',
  archived: false,
  created_at: '2026-10-10T00:00:00Z',
  my_roles: ['field_collector'],
  counts: {
    images: 0,
    images_missing_location: 0,
    images_with_quality_flags: 0,
    images_analysed: 0,
    findings_to_review: 0,
    findings_needs_field_check: 0,
    findings_verified: 0,
    verified_location_unconfirmed: 0,
    verified_by_type: {},
    inspections_open: 0,
  },
  boundary: AREA,
  finding_type_keys: ['pothole'],
  road_category: null,
  survey_start: null,
  survey_end: null,
  partner_reference: null,
  archived_at: null,
  my_permissions: ['project.view', 'image.upload', 'image.status.view', 'image.view', 'image.location.set', 'image.withdraw'],
}

export function makeImage(change: Partial<ImageInfo> = {}): ImageInfo {
  return {
    id: 'img1',
    project_id: 'p1',
    original_filename: 'street.jpg',
    content_type: 'image/jpeg',
    size_bytes: 1000,
    width_px: 400,
    height_px: 300,
    captured_at: '2026-10-01T10:00:00Z',
    location: { latitude: 37.775, longitude: -122.42 },
    location_source: 'photo_gps',
    location_quality: 'approximate',
    quality_flags: [],
    status: 'stored',
    uploaded_by: 'u1',
    uploaded_by_name: 'Ada Admin',
    created_at: '2026-10-14T00:00:00Z',
    analysis: null,
    ...change,
  }
}

export function makeFinding(change: Partial<Finding> = {}): Finding {
  return {
    id: 'f1',
    project_id: 'p1',
    origin: 'ai',
    review_status: 'ai_generated',
    inspection_status: 'none',
    predicted_type_key: 'pothole',
    predicted_confidence: 0.91,
    predicted_bbox: [100, 150, 300, 300],
    model_version: 'stand-in-0.1',
    is_test_detector: true,
    analysis_job_id: 'job1',
    type_key: null,
    severity_key: null,
    severity_rubric_id: null,
    severity_rubric_version: null,
    notes: null,
    reviewed_by_name: null,
    reviewed_at: null,
    created_by_name: null,
    location: { latitude: 37.775, longitude: -122.42 },
    original_location: { latitude: 37.775, longitude: -122.42 },
    corrected_location: null,
    location_source: 'photo_gps',
    location_quality: 'approximate',
    photo: { id: 'a', original_filename: 'a.jpg', width_px: 400, height_px: 300 },
    version: 1,
    created_at: '2026-10-15T00:00:00Z',
    updated_at: '2026-10-15T00:00:00Z',
    ...change,
  }
}

export const REVIEW_OPTIONS: ReviewOptions = {
  finding_types: [
    { key: 'pothole', label: 'Pothole', source: 'ai', is_placeholder: true, in_project: true },
    { key: 'surface_cracking', label: 'Surface cracking', source: 'ai', is_placeholder: true, in_project: true },
    { key: 'sidewalk_observation', label: 'Sidewalk observation', source: 'manual', is_placeholder: true, in_project: false },
  ],
  severity_rubric: {
    id: 'r1',
    version: 1,
    levels: [
      { key: 'low', label: 'Low', definition: '' },
      { key: 'medium', label: 'Medium', definition: '' },
      { key: 'high', label: 'High', definition: '' },
    ],
    is_placeholder: true,
    is_current: true,
    created_at: '2026-10-01T00:00:00Z',
  },
}

/** A reviewer who is also project manager (the usual pilot set-up). */
export const REVIEWER_PROJECT: ProjectDetail = {
  ...PROJECT,
  my_roles: ['project_manager', 'technical_reviewer'],
  my_permissions: [
    ...PROJECT.my_permissions,
    'project.edit',
    'analysis.run',
    'analysis.status.view',
    'finding.view_verified',
    'finding.view_candidates',
    'finding.view_rejected',
    'finding.create_manual',
    'finding.review',
    'finding.history.view',
  ],
}

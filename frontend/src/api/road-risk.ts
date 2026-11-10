/**
 * Road-risk forecast (api-spec F4c/F4d notes; forecasting-f4d-design.md).
 *
 * Levels only (owner decision F4-D2): high / medium / low with reasons in plain words, never a
 * percentage. Every answer carries the TRIAL label and the notice, and screens show both.
 */

import type { Page } from '@/api/organizations'
import { apiRequest } from '@/lib/api-client'

export type RiskLevel = 'high' | 'medium' | 'low'
export type FactorLevel = RiskLevel | 'missing'
export type ForecastStatus = 'off' | 'setting_up' | 'ready' | 'failed' | 'too_large'
export type VisibleRole = 'technical_reviewer' | 'viewer' | 'field_collector'

export interface ForecastStatusInfo {
  enabled: boolean
  status: ForecastStatus
  /** 2 = tested Chicago levels, 1 = risk factors only. Only when ready. */
  level: 1 | 2 | null
  level_label: string | null
  message: string | null
  area_km2: number | null
  max_area_km2: number
  last_weekly_run: string | null
  last_daily_run: string | null
  can_configure: boolean
  /** Roles that can see road risk besides project managers. */
  visible_to_roles: VisibleRole[]
  /** CR-006: "Ask about road risk" switched on by the project manager. */
  assistant_enabled?: boolean
  label: string
  notice: string
}

export interface RiskRun {
  id: string
  kind: string
  as_of: string
  model_version: string
  data_dates: Record<string, string | null>
  finished_at: string | null
}

export interface Reason {
  input: string
  label: string
  value: number | null
}

export interface RiskFactor {
  factor: string
  label: string
  value: number | null
  level: FactorLevel
  kind: 'risk' | 'background'
}

export interface SectionRisk {
  section_id: string
  name: string | null
  road_type: string
  length_m: number
  /** 1 = inspect first, within this project. */
  position: number
  level: RiskLevel | null
  rank_in_area: number | null
  reasons: Reason[]
  missing_inputs: string[]
  factors: RiskFactor[]
}

export interface RiskList extends Page<SectionRisk> {
  status: ForecastStatusInfo
  levels_run: RiskRun | null
  factors_run: RiskRun | null
  counts: Record<RiskLevel, number>
  label: string
  notice: string
}

export interface RiskMapFeature {
  type: 'Feature'
  geometry: { type: 'LineString'; coordinates: [number, number][] }
  properties: { section_id: string; name: string | null; level: RiskLevel | null; position: number }
}

export interface RiskMap {
  type: 'FeatureCollection'
  features: RiskMapFeature[]
}

/** Team-lead item 12: from OpenStreetMap; null = not on the map. */
export interface RoadDetails {
  speed_limit_mph: number | null
  lanes: number | null
  surface: string | null
  oneway: boolean | null
  road_ref: string | null
  source: string
}

export interface SectionDetail {
  section: SectionRisk
  road?: RoadDetails | null
  geometry: { type: 'LineString'; coordinates: [number, number][] }
  history: { as_of: string; level: RiskLevel; rank_in_area: number }[]
  inspections: { id: string; status: string; planned_date: string | null }[]
  levels_run: RiskRun | null
  factors_run: RiskRun | null
  label: string
  notice: string
}

export interface OutlookDay {
  date: string
  max_c: number | null
  min_c: number | null
  rain_mm: number | null
  snow_mm: number | null
}

export interface Weather {
  outlook: {
    source: string
    issued_at: string
    fetched_at: string
    days: OutlookDay[]
    freeze_thaw_days: number
    frost_days: number
    heavy_rain_days: number
    snow_mm: number
  } | null
  recent: { as_of: string; values: RiskFactor[] } | null
}

export const VISIBLE_ROLE_LABELS: Record<VisibleRole, string> = {
  technical_reviewer: 'Technical reviewers',
  viewer: 'Viewers',
  field_collector: 'Field collectors',
}

export const roadRiskQueryKeys = {
  all: (projectId: string) => ['projects', projectId, 'road-risk'] as const,
  settings: (projectId: string) => ['projects', projectId, 'road-risk', 'settings'] as const,
  list: (projectId: string, level: string, page: number) => ['projects', projectId, 'road-risk', 'list', level, page] as const,
  map: (projectId: string) => ['projects', projectId, 'road-risk', 'map'] as const,
  weather: (projectId: string) => ['projects', projectId, 'road-risk', 'weather'] as const,
  section: (projectId: string, sectionId: string) => ['projects', projectId, 'road-risk', 'section', sectionId] as const,
  inspections: (projectId: string, sectionId: string) => ['projects', projectId, 'road-risk', 'inspections', sectionId] as const,
}

export function getForecastSettings(projectId: string, signal?: AbortSignal): Promise<ForecastStatusInfo> {
  return apiRequest(`/v1/projects/${projectId}/forecast-settings`, { signal })
}

export function saveForecastSettings(projectId: string, body: { enabled?: boolean; visible_to_roles?: VisibleRole[]; assistant_enabled?: boolean }): Promise<ForecastStatusInfo> {
  return apiRequest(`/v1/projects/${projectId}/forecast-settings`, { method: 'PUT', body })
}

export function requestRiskUpdate(projectId: string): Promise<ForecastStatusInfo> {
  return apiRequest(`/v1/projects/${projectId}/risk-runs`, { method: 'POST' })
}

export function getRiskList(projectId: string, options: { level?: string; page?: number; pageSize?: number }, signal?: AbortSignal): Promise<RiskList> {
  const query = new URLSearchParams({ page: String(options.page ?? 1), page_size: String(options.pageSize ?? 50) })
  if (options.level) query.set('level', options.level)
  return apiRequest(`/v1/projects/${projectId}/risk?${query}`, { signal })
}

export function getRiskMap(projectId: string, signal?: AbortSignal): Promise<RiskMap> {
  return apiRequest(`/v1/projects/${projectId}/risk/map`, { signal })
}

export function getSectionRisk(projectId: string, sectionId: string, signal?: AbortSignal): Promise<SectionDetail> {
  return apiRequest(`/v1/projects/${projectId}/road-sections/${sectionId}/risk`, { signal })
}

export function getWeather(projectId: string, signal?: AbortSignal): Promise<Weather> {
  return apiRequest(`/v1/projects/${projectId}/weather`, { signal })
}

/** A plain link: the browser downloads the file with the session cookie (permission-checked). */
export const riskExportUrl = (projectId: string, format: 'csv' | 'geojson') => `/api/v1/projects/${projectId}/risk/export?format=${format}`

/** Level words, so a level is never shown by colour alone. */
export const LEVEL_WORDS: Record<FactorLevel, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  missing: 'Not known',
}

export const ROAD_TYPE_LABELS: Record<string, string> = {
  motorway: 'Motorway',
  trunk: 'Main road',
  primary: 'Main road',
  secondary: 'Secondary road',
  tertiary: 'Local main road',
  residential: 'Residential street',
  unclassified: 'Minor road',
  living_street: 'Living street',
  service: 'Service road',
}

export const roadTypeLabel = (roadType: string) => ROAD_TYPE_LABELS[roadType] ?? roadType.replace(/_/g, ' ')

export const roadName = (name: string | null) => name || 'Unnamed road'

/** "Pothole reports here, last 12 months: 4" */
export const reasonText = (reason: Reason) => (reason.value === null ? reason.label : `${reason.label}: ${formatNumber(reason.value)}`)

export function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toLocaleString(undefined, { maximumFractionDigits: 1 })
}

export const formatDay = (day: string) => new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })

// ------------------------------------------------------------------ alerts (F4e)

export type AlertType = 'turned_high' | 'freeze_thaw_coming' | 'heavy_rain_coming' | 'data_problem' | 'inspection_assigned'

export interface AlertRoad {
  section_id: string
  name: string
  level: RiskLevel | null
  previous_level?: string
  reasons: string[]
  missing_inputs: string[]
}

export interface RiskAlert {
  id: string
  project_id: string
  project_name: string
  type: AlertType
  title: string
  details: {
    label?: string
    notice?: string
    when?: string
    days?: string[]
    source?: string
    issued_at?: string
    reason?: string
    roads?: AlertRoad[]
    suggested_action?: string
    model_version?: string | null
    levels_of?: string | null
    /** Personal notifications: the page to open (e.g. My inspections). */
    path?: string
    planned_by?: string
  }
  created_at: string
  closed_at: string | null
  read: boolean
}

export interface Notifications {
  items: RiskAlert[]
  unread_count: number
  manages_projects: boolean
}

export const alertQueryKeys = {
  all: ['notifications'] as const,
  one: (alertId: string) => ['notifications', alertId] as const,
  project: (projectId: string) => ['projects', projectId, 'road-risk', 'alerts'] as const,
}

export function listNotifications(signal?: AbortSignal): Promise<Notifications> {
  return apiRequest('/v1/notifications', { signal })
}

export function getNotification(alertId: string, signal?: AbortSignal): Promise<RiskAlert> {
  return apiRequest(`/v1/notifications/${alertId}`, { signal })
}

export function markAlertRead(alertId: string): Promise<null> {
  return apiRequest(`/v1/notifications/${alertId}/read`, { method: 'POST' })
}

export function markAllAlertsRead(): Promise<null> {
  return apiRequest('/v1/notifications/read-all', { method: 'POST' })
}

export function listProjectAlerts(projectId: string, signal?: AbortSignal): Promise<Page<RiskAlert>> {
  return apiRequest(`/v1/projects/${projectId}/alerts`, { signal })
}

export const ALERT_TYPE_LABELS: Record<AlertType, string> = {
  turned_high: 'Road turned high risk',
  freeze_thaw_coming: 'Freeze-thaw coming',
  heavy_rain_coming: 'Heavy rain coming',
  data_problem: 'Data problem',
  inspection_assigned: 'Inspection for you',
}

// ------------------------------------------------------------------ assistant (CR-006)

export interface AssistantAnswer {
  answer: string
  sources: { label: string; path: string }[]
  /** False: the built-in answer (the free local AI model was off or too slow). */
  used_model: boolean
  questions_left_today: number
  label: string
  notice: string
}

export function askAssistant(projectId: string, question: string): Promise<AssistantAnswer> {
  return apiRequest(`/v1/projects/${projectId}/assistant`, { method: 'POST', body: { question } })
}

export const ASSISTANT_EXAMPLES = [
  'Which roads should we inspect first, and why?',
  'Which high-risk roads have no inspection planned?',
  'Will the weather this week affect our roads?',
  'What changed this week?',
]

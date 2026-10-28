"""Collects all route modules.

- `/api/health...`: health checks (not versioned).
- `/api/v1/...`: all feature requests. A breaking change would go to `/api/v2`
  alongside v1, never replace it (api-spec.md section 1).
"""

from fastapi import APIRouter

from app.api import (
    analysis,
    auth,
    findings,
    health,
    images,
    organizations,
    platform,
    priority,
    projects,
    reports,
)

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(auth.router)
v1_router.include_router(organizations.router)
v1_router.include_router(platform.public_router)
v1_router.include_router(platform.router)
v1_router.include_router(projects.org_router)
v1_router.include_router(projects.router)
v1_router.include_router(images.project_router)
v1_router.include_router(images.router)
v1_router.include_router(analysis.project_router)
v1_router.include_router(analysis.job_router)
v1_router.include_router(findings.project_router)
v1_router.include_router(findings.finding_router)
v1_router.include_router(priority.project_router)
v1_router.include_router(priority.finding_router)
v1_router.include_router(priority.inspection_router)
v1_router.include_router(reports.project_router)
v1_router.include_router(reports.report_router)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(v1_router)

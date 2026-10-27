"""Health endpoints.

- `GET /api/health`       liveness: the API process is running.
- `GET /api/health/ready` readiness: the database and job queue are reachable.
"""

from fastapi import APIRouter

from app.core.database import check_database
from app.core.errors import ServiceUnavailableError
from app.core.queue import check_queue
from app.schemas.health import CheckStatus, LivenessResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=LivenessResponse)
def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get("/ready", response_model=ReadinessResponse)
def readiness() -> ReadinessResponse:
    """Check dependencies.

    Raises:
        ServiceUnavailableError: if any dependency is unreachable; `details.checks`
            says which one.
    """
    checks: dict[str, CheckStatus] = {
        "database": "ok" if check_database() else "unavailable",
        "queue": "ok" if check_queue() else "unavailable",
    }
    if any(value != "ok" for value in checks.values()):
        raise ServiceUnavailableError(details={"checks": checks})
    return ReadinessResponse(checks=checks)

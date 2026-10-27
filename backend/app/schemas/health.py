"""Response shapes for the health endpoints."""

from typing import Literal

from pydantic import BaseModel

CheckStatus = Literal["ok", "unavailable"]


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    checks: dict[str, CheckStatus]

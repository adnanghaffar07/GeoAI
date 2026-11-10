"""Terms of use accepted after sign-in (team lead plan, Phase 1, tl-phase1-design.md section 1).

Change AGREEMENT_VERSION whenever the text in the screens changes: everyone is asked again.
"""

import uuid

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.models import UserAgreement

AGREEMENT_VERSION = "2026-11-10"

# Allowed before accepting: who am I, accept, sign out.
OPEN_PATHS = {"/api/v1/auth/me", "/api/v1/auth/agreement", "/api/v1/auth/logout"}


def has_agreed(db: Session, user_id: uuid.UUID, session_id: uuid.UUID | None) -> bool:
    """session_id None (just signed in): only a remembered acceptance counts."""
    return bool(
        db.scalar(
            select(
                exists().where(
                    UserAgreement.user_id == user_id,
                    UserAgreement.version == AGREEMENT_VERSION,
                    or_(UserAgreement.remember.is_(True), UserAgreement.session_id == session_id),
                )
            )
        )
    )

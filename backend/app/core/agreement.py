"""Terms of use accepted after sign-in (team lead plan, Phase 1, tl-phase1-design.md section 1).

Change AGREEMENT_VERSION whenever the text in the screens changes: everyone is asked again.
"""

import uuid

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import UserAgreement

AGREEMENT_VERSION = "2026-11-10"

# Allowed before accepting: who am I, accept, sign out.
OPEN_PATHS = {"/api/v1/auth/me", "/api/v1/auth/agreement", "/api/v1/auth/logout"}


def has_agreed(db: Session, user_id: uuid.UUID, session_id: uuid.UUID | None) -> bool:
    """True only when the current version was accepted in THIS sign-in (team lead, 2026-11-10:
    show the terms at every sign-in). A new sign-in has a new session, so it asks again."""
    if session_id is None:
        return False
    return bool(
        db.scalar(
            select(
                exists().where(
                    UserAgreement.user_id == user_id,
                    UserAgreement.version == AGREEMENT_VERSION,
                    UserAgreement.session_id == session_id,
                )
            )
        )
    )

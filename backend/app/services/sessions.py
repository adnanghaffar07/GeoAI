"""Signed-in sessions: create, look up, extend, and end them.

Rule (owner's standing note): all sign-in mechanics live in this module and
`app/core/auth.py`. Other features only ever ask *who* the user is, never *how*
they signed in, so the sign-in method can change later without touching them.
"""

import uuid
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_token, new_token
from app.models import User, UserSession
from app.models.base import utc_now

# Extend a session's expiry at most this often, to avoid a database write per request.
_EXTEND_AFTER = timedelta(minutes=5)


def create_session(
    db: Session, user: User, *, user_agent: str | None, ip_address: str | None
) -> str:
    """Create a session for `user` and return the raw token for the cookie."""
    token = new_token()
    now = utc_now()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(hours=get_settings().session_idle_hours),
            last_seen_at=now,
            user_agent=(user_agent or "")[:500] or None,
            ip_address=ip_address,
        )
    )
    user.last_login_at = now
    return token


def find_active_session(db: Session, token: str) -> tuple[UserSession, User] | None:
    """Return the session and user for a cookie token, or None if signed out/expired."""
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(
            UserSession.token_hash == hash_token(token),
            UserSession.expires_at > utc_now(),
            User.is_active.is_(True),
        )
    ).first()
    if row is None:
        return None
    return row[0], row[1]


def extend_if_due(db: Session, session: UserSession) -> None:
    """Sliding expiry: activity keeps the session alive (commits its own small update)."""
    now = utc_now()
    if now - session.last_seen_at >= _EXTEND_AFTER:
        session.last_seen_at = now
        session.expires_at = now + timedelta(hours=get_settings().session_idle_hours)
        db.commit()


def end_session(db: Session, session_id: uuid.UUID) -> None:
    db.execute(delete(UserSession).where(UserSession.id == session_id))


def end_all_sessions(db: Session, user_id: uuid.UUID) -> None:
    """Sign a person out everywhere (used on removal and password reset)."""
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))

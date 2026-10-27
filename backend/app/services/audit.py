"""Write audit history events.

Events are added in the same database transaction as the change they describe, so a
change and its history are saved together or not at all.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.request_context import get_request_id
from app.models import AuditEvent

activity_log = logging.getLogger("geoinfralens.activity")

# Actions worth a warning in the console (someone may need to look at them).
_WARNING_ACTIONS = {"auth.sign_in_failed"}
_PENDING = "pending_activity_lines"


def record_event(
    db: Session,
    *,
    action: str,
    organization_id: uuid.UUID | None,
    project_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None,
    actor_roles: list[str] | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Add an audit event to the session (the caller commits).

    `action` must be one of the documented audit event types
    (database-schema.md, "Audit event types").
    """
    event = AuditEvent(
        organization_id=organization_id,
        project_id=project_id,
        actor_user_id=actor_user_id,
        actor_roles=sorted(actor_roles or []),
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
        request_id=get_request_id(),
    )
    db.add(event)
    # Printed to the console only after the change is really saved (see below).
    target = f" target={target_type}:{target_id}" if target_type else ""
    project = f" project={project_id}" if project_id else ""
    line = f"{action} by user={actor_user_id or '-'} org={organization_id or '-'}{project}{target}"
    db.info.setdefault(_PENDING, []).append((action, line))
    return event


@event.listens_for(Session, "after_commit")
def _print_saved_activity(session: Session) -> None:
    """One console line per saved action, e.g. 'Activity: project.created by user=… org=…'."""
    for action, line in session.info.pop(_PENDING, []):
        level = logging.WARNING if action in _WARNING_ACTIONS else logging.INFO
        activity_log.log(level, "Activity: %s", line)


@event.listens_for(Session, "after_rollback")
def _forget_unsaved_activity(session: Session) -> None:
    """Changes that were rolled back did not happen, so nothing is printed."""
    session.info.pop(_PENDING, None)

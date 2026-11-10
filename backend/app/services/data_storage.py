# ruff: noqa: E501
"""Where an organization's files are kept (team lead plan, Phase 2: bring your own storage).

Only organization admins change it (org.settings.edit). The secret key of the organization's own storage is kept
encrypted and is never sent back to the screens.
"""

import uuid

from app.core.errors import ValidationFailedError
from app.services.audit import record_event
from sqlalchemy.orm import Session

from app import storage
from app.models import OrganizationStorage

KINDS = ("app", "s3")


def _secret_key_name(organization_id: uuid.UUID) -> str:
    return f"org/{organization_id}/settings/storage-secret"


def get(db: Session, organization_id: uuid.UUID) -> OrganizationStorage | None:
    return db.get(OrganizationStorage, organization_id)


def backend_for(db: Session, organization_id: uuid.UUID) -> storage.Backend | None:
    row = get(db, organization_id)
    if row is None or row.kind != "s3" or not row.secret_encrypted:
        return None
    secret = storage.decrypt(_secret_key_name(organization_id), row.secret_encrypted).decode()
    return storage.S3Backend(
        row.endpoint or "",
        row.bucket or "",
        row.region or "",
        row.access_key_id or "",
        secret,
        row.prefix or "",
    )


def out(row: OrganizationStorage | None) -> dict:
    if row is None or row.kind == "app":
        return {
            "kind": "app",
            "place": "GeoInfraLens AI private storage",
            "endpoint": None,
            "bucket": None,
            "region": None,
            "prefix": None,
            "access_key_id": None,
            "has_secret": False,
            "location_note": row.location_note if row else None,
            "verified_at": None,
            "updated_at": row.updated_at if row else None,
            "encryption": "AES-256-GCM, every file",
        }
    return {
        "kind": "s3",
        "place": "Your organization's own storage",
        "endpoint": row.endpoint,
        "bucket": row.bucket,
        "region": row.region,
        "prefix": row.prefix,
        "access_key_id": row.access_key_id,
        "has_secret": bool(row.secret_encrypted),
        "location_note": row.location_note,
        "verified_at": row.verified_at,
        "updated_at": row.updated_at,
        "encryption": "AES-256-GCM, every file",
    }


def save(
    db: Session, organization_id: uuid.UUID, user_id: uuid.UUID, body: dict
) -> OrganizationStorage:
    """Check the connection first (write, read, delete a small file), then save. Nothing is saved if it fails."""
    kind = body.get("kind")
    if kind not in KINDS:
        raise ValidationFailedError("Choose where the files are kept.")
    row = get(db, organization_id) or OrganizationStorage(organization_id=organization_id)
    row.location_note = (body.get("location_note") or "").strip()[:200] or None
    if kind == "s3":
        for field, label in (
            ("endpoint", "Storage address"),
            ("bucket", "Bucket name"),
            ("access_key_id", "Access key"),
        ):
            if not (body.get(field) or "").strip():
                raise ValidationFailedError(f"{label} is needed.")
        secret = (body.get("secret_key") or "").strip()
        if not secret and not row.secret_encrypted:
            raise ValidationFailedError("Secret key is needed.")
        if not secret:
            secret = storage.decrypt(
                _secret_key_name(organization_id), row.secret_encrypted
            ).decode()
        endpoint = body["endpoint"].strip().rstrip("/")
        if not endpoint.startswith("https://") and not endpoint.startswith("http://localhost"):
            raise ValidationFailedError("The storage address must start with https://")
        backend = storage.S3Backend(endpoint, body["bucket"].strip(), (body.get("region") or "").strip(),
                                    body["access_key_id"].strip(), secret, (body.get("prefix") or "").strip())  # fmt: skip
        try:
            storage.check_backend(backend)
        except storage.StorageUnavailableError as error:
            raise ValidationFailedError(f"Could not use this storage: {error}") from error
        row.endpoint, row.bucket, row.region = endpoint, backend.bucket, backend.region
        row.prefix, row.access_key_id = backend.prefix or None, backend.access_key
        row.secret_encrypted = storage.encrypt(_secret_key_name(organization_id), secret.encode())
        row.verified_at = storage_now()
    else:
        row.endpoint = row.bucket = row.region = row.prefix = row.access_key_id = None
        row.secret_encrypted = None
        row.verified_at = None
    row.kind = kind
    row.updated_by = user_id
    db.add(row)
    record_event(
        db,
        action="storage.changed",
        organization_id=organization_id,
        actor_user_id=user_id,
        details={"kind": kind, "endpoint": row.endpoint, "bucket": row.bucket},
    )
    db.commit()
    storage.forget_settings(organization_id)
    return row


def storage_now():
    from app.models.base import utc_now

    return utc_now()

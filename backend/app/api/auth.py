"""Sign-in, sign-out, current user, invitation links, and password reset links.

Paths (under /api/v1): see documentation/04-design/api-spec.md section 3.2.
"""

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.agreement import AGREEMENT_VERSION, has_agreed
from app.core.auth import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import ConflictError
from app.models import User, UserAgreement
from app.schemas.auth import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    AgreementRequest,
    InvitationInfo,
    MembershipOut,
    MeResponse,
    ResetInfo,
    SetPasswordRequest,
    SignInRequest,
    UserOut,
)
from app.services import accounts
from app.services.audit import record_event
from app.services.sessions import create_session, end_session

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,  # not readable by JavaScript
        secure=settings.session_cookie_secure,
        samesite="lax",  # not sent with cross-site form posts
        path="/",
    )


def _client(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    return request.headers.get("user-agent"), ip


def _me(db: Session, user: User, session_id: uuid.UUID | None = None) -> MeResponse:
    return MeResponse(
        agreement_required=not has_agreed(db, user.id, session_id),
        agreement_version=AGREEMENT_VERSION,
        user=UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_platform_admin=user.is_platform_admin,
        ),
        memberships=[
            MembershipOut(**vars(summary)) for summary in accounts.list_memberships(db, user)
        ],
    )


@router.post("/login", response_model=MeResponse)
def login(
    body: SignInRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> MeResponse:
    user_agent, ip = _client(request)
    user, token = accounts.sign_in(
        db, body.email, body.password, user_agent=user_agent, ip_address=ip
    )
    _set_session_cookie(response, token)
    return _me(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    end_session(db, current.session.id)
    record_event(db, action="auth.signed_out", organization_id=None, actor_user_id=current.user.id)
    db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return response


@router.get("/me", response_model=MeResponse)
def me(
    current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> MeResponse:
    return _me(db, current.user, current.session.id)


@router.post("/agreement", response_model=MeResponse)
def accept_agreement(
    body: AgreementRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    """Accept the terms shown after sign-in. "Remember my choice": until the terms change."""
    if body.version != AGREEMENT_VERSION:
        raise ConflictError("The terms have changed. Please read the new version.")
    db.add(
        UserAgreement(
            user_id=current.user.id,
            version=AGREEMENT_VERSION,
            remember=body.remember,
            session_id=None if body.remember else current.session.id,
        )
    )
    record_event(
        db,
        action="agreement.accepted",
        organization_id=None,
        actor_user_id=current.user.id,
        details={"version": AGREEMENT_VERSION, "remember": body.remember},
    )
    db.commit()
    return _me(db, current.user, current.session.id)


@router.get("/invitations/{token}", response_model=InvitationInfo)
def check_invitation(token: str, db: Session = Depends(get_db)) -> InvitationInfo:
    invitation, organization = accounts.find_usable_invitation(db, token)
    return InvitationInfo(
        organization_name=organization.name,
        email=invitation.email,
        org_role=invitation.org_role,
        account_exists=accounts.account_exists(db, invitation.email),
    )


@router.post("/invitations/{token}/accept", response_model=AcceptInvitationResponse)
def accept_invitation(
    token: str,
    body: AcceptInvitationRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AcceptInvitationResponse:
    result = accounts.accept_invitation(db, token, body.full_name, body.password)
    if not result.created_new_account:
        db.commit()
        return AcceptInvitationResponse(result="sign_in_required")
    user_agent, ip = _client(request)
    session_token = create_session(db, result.user, user_agent=user_agent, ip_address=ip)
    db.commit()
    _set_session_cookie(response, session_token)
    return AcceptInvitationResponse(result="signed_in")


@router.get("/password-resets/{token}", response_model=ResetInfo)
def check_password_reset(token: str, db: Session = Depends(get_db)) -> ResetInfo:
    _, user = accounts.find_usable_reset(db, token)
    return ResetInfo(email=user.email)


@router.post("/password-resets/{token}", status_code=status.HTTP_204_NO_CONTENT)
def set_new_password(
    token: str, body: SetPasswordRequest, db: Session = Depends(get_db)
) -> Response:
    accounts.use_password_reset(db, token, body.password)
    db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return response

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import User, WhatsAppAccount
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    user_id = decode_access_token(creds.credentials) if creds else None
    user = db.get(User, user_id) if user_id else None
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    return user


def get_account(db: Session, organization_id: int) -> WhatsAppAccount | None:
    """Phase 1: one WhatsApp number per organization. The schema already allows many."""
    return db.scalar(
        select(WhatsAppAccount)
        .where(WhatsAppAccount.organization_id == organization_id)
        .order_by(WhatsAppAccount.id)
        .limit(1)
    )


def require_account(db: Session, organization_id: int) -> WhatsAppAccount:
    account = get_account(db, organization_id)
    if not account:
        raise HTTPException(400, "Connect your WhatsApp number in Settings first")
    return account

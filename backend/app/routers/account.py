"""Connecting the business's WhatsApp number.

Phase 1: the IDs and a permanent System User token are pasted in by hand.
Phase 2: Embedded Signup will fill the same table automatically.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import current_user, get_account, require_account
from ..models import User, WhatsAppAccount
from ..security import decrypt, encrypt
from ..whatsapp import WhatsAppAPIError, get_client

router = APIRouter(prefix="/whatsapp-account", tags=["whatsapp account"])


class AccountIn(BaseModel):
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str = Field(min_length=1, max_length=64)
    access_token: str | None = Field(default=None, max_length=1000)  # blank = keep the saved one


class PinIn(BaseModel):
    pin: str = Field(pattern=r"^\d{6}$")


def account_out(account: WhatsAppAccount | None) -> dict | None:
    if not account:
        return None
    return {
        "id": account.id,
        "waba_id": account.waba_id,
        "phone_number_id": account.phone_number_id,
        "display_phone_number": account.display_phone_number,
        "verified_name": account.verified_name,
        "quality_rating": account.quality_rating,
        "messaging_limit": account.messaging_limit,
        "webhook_subscribed": account.webhook_subscribed,
        "updated_at": account.updated_at,
    }


def _api_error(err: WhatsAppAPIError) -> HTTPException:
    return HTTPException(400, f"Meta API error {err.code}: {err.title}. {err.detail}".strip())


def _refresh_info(account: WhatsAppAccount, token: str) -> None:
    client = get_client(token)
    try:
        info = client.get_phone_number(account.phone_number_id)
    finally:
        client.close()
    account.display_phone_number = info.get("display_phone_number")
    account.verified_name = info.get("verified_name")
    account.quality_rating = info.get("quality_rating")
    account.messaging_limit = info.get("messaging_limit_tier")


@router.get("")
def get_whatsapp_account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {
        "account": account_out(get_account(db, user.organization_id)),
        "webhook_path": "/api/webhook",
        "verify_token_configured": bool(settings.webhook_verify_token),
        "app_secret_configured": bool(settings.meta_app_secret),
        "mock_mode": settings.whatsapp_mock,
    }


@router.put("")
def save_whatsapp_account(body: AccountIn, user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    account = get_account(db, user.organization_id)
    token = (body.access_token or "").strip()
    if not token:
        if not account:
            raise HTTPException(400, "Access token is required")
        token = decrypt(account.access_token_encrypted)

    waba_id, phone_number_id = body.waba_id.strip(), body.phone_number_id.strip()
    taken = db.scalar(select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == phone_number_id))
    if taken and taken.organization_id != user.organization_id:
        raise HTTPException(400, "This phone number is already connected to another account")

    # Check the details with Meta before saving.
    client = get_client(token)
    try:
        info = client.get_phone_number(phone_number_id)
        ids = client.list_phone_number_ids(waba_id)
    except WhatsAppAPIError as err:
        raise _api_error(err) from err
    finally:
        client.close()
    if ids and phone_number_id not in ids:
        raise HTTPException(400, "This Phone Number ID doesn't belong to that WhatsApp Business Account ID")

    if not account:
        account = WhatsAppAccount(organization_id=user.organization_id)
        db.add(account)
    if account.waba_id != waba_id:
        account.webhook_subscribed = False
    account.waba_id = waba_id
    account.phone_number_id = phone_number_id
    account.access_token_encrypted = encrypt(token)
    account.display_phone_number = info.get("display_phone_number")
    account.verified_name = info.get("verified_name")
    account.quality_rating = info.get("quality_rating")
    account.messaging_limit = info.get("messaging_limit_tier")
    db.commit()
    return {"account": account_out(account)}


@router.post("/refresh")
def refresh(user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = require_account(db, user.organization_id)
    try:
        _refresh_info(account, decrypt(account.access_token_encrypted))
    except WhatsAppAPIError as err:
        raise _api_error(err) from err
    db.commit()
    return {"account": account_out(account)}


@router.post("/subscribe-webhooks")
def subscribe_webhooks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = require_account(db, user.organization_id)
    client = get_client(decrypt(account.access_token_encrypted))
    try:
        client.subscribe_app(account.waba_id)
    except WhatsAppAPIError as err:
        raise _api_error(err) from err
    finally:
        client.close()
    account.webhook_subscribed = True
    db.commit()
    return {"account": account_out(account)}


@router.post("/register")
def register_number(body: PinIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Only needed if sending fails with error 133010 (number not registered)."""
    account = require_account(db, user.organization_id)
    client = get_client(decrypt(account.access_token_encrypted))
    try:
        client.register_phone(account.phone_number_id, body.pin)
    except WhatsAppAPIError as err:
        raise _api_error(err) from err
    finally:
        client.close()
    return {"ok": True}

"""Meta calls these endpoints.

GET  /api/webhook  - one-time verification when you set the webhook URL in Meta's dashboard
POST /api/webhook  - message statuses (sent/delivered/read/failed) and template updates
"""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from ..config import settings
from ..db import SessionLocal
from ..statuses import process_webhook

router = APIRouter(tags=["webhook"])
log = logging.getLogger(__name__)


@router.get("/webhook")
def verify(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
):
    if mode == "subscribe" and settings.webhook_verify_token and hmac.compare_digest(
        token, settings.webhook_verify_token
    ):
        return PlainTextResponse(challenge)
    raise HTTPException(403, "Verification failed")


def _process(payload: dict) -> None:
    with SessionLocal() as db:
        process_webhook(db, payload)


@router.post("/webhook")
async def receive(request: Request):
    body = await request.body()
    if settings.meta_app_secret:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(settings.meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(401, "Invalid signature")
    else:
        log.warning("META_APP_SECRET is not set: webhook signatures are NOT being checked")

    try:
        payload = json.loads(body)
    except ValueError as err:
        raise HTTPException(400, "Invalid JSON") from err
    try:
        await run_in_threadpool(_process, payload)
    except Exception:  # noqa: BLE001
        # Returning an error makes Meta retry, which is what we want for transient DB problems.
        log.exception("Failed to process webhook")
        raise HTTPException(500, "Processing failed") from None
    return {"ok": True}

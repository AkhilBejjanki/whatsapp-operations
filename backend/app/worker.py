"""Background worker: sends campaign messages at a controlled rate.

Run with:  celery -A app.worker worker --loglevel=info
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import redis
from celery import Celery
from redis.exceptions import LockError
from sqlalchemy import func, select

from .config import settings
from .db import SessionLocal
from .errors import CAMPAIGN_FATAL_CODES, RETRYABLE_CODES, describe
from .models import Campaign, Message, Template, WhatsAppAccount
from .security import decrypt
from .statuses import apply_pending_events, process_webhook, reconcile_unapplied_events
from .templates_util import build_send_components
from .whatsapp import WhatsAppAPIError, get_client

log = logging.getLogger(__name__)

celery_app = Celery("wa_bulk", broker=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
_redis = redis.Redis.from_url(settings.redis_url)

BATCH_SIZE = 50
MAX_ATTEMPTS = 4


class RateLimiter:
    """Thread-safe: spaces out calls to at most `rate` per second."""

    def __init__(self, rate: float):
        self.interval = 1.0 / max(rate, 0.1)
        self.lock = threading.Lock()
        self.next_time = time.monotonic()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            slot = max(self.next_time, now)
            self.next_time = slot + self.interval
        delay = slot - now
        if delay > 0:
            time.sleep(delay)


@dataclass
class SendContext:
    campaign_id: int
    phone_number_id: str
    template_name: str
    language: str
    components: list
    parameter_format: str
    header_media_url: str | None


def _now() -> datetime:
    return datetime.now(UTC)


@celery_app.task(name="send_campaign")
def send_campaign(campaign_id: int) -> str:
    # The lock stops two workers from sending the same campaign twice.
    lock = _redis.lock(f"lock:campaign:{campaign_id}", timeout=300)
    if not lock.acquire(blocking=False):
        return "already running"
    try:
        return _run_campaign(campaign_id, lock)
    finally:
        try:
            lock.release()
        except LockError:
            pass


def _run_campaign(campaign_id: int, lock) -> str:
    with SessionLocal() as db:
        campaign = db.get(Campaign, campaign_id)
        if not campaign or campaign.status not in ("queued", "sending"):
            return "not runnable"
        account = db.get(WhatsAppAccount, campaign.whatsapp_account_id)
        template = db.get(Template, campaign.template_id)
        campaign.status = "sending"
        campaign.started_at = campaign.started_at or _now()
        campaign.last_error = None
        db.commit()
        ctx = SendContext(
            campaign_id=campaign.id,
            phone_number_id=account.phone_number_id,
            template_name=template.name,
            language=template.language,
            components=template.components,
            parameter_format=template.parameter_format,
            header_media_url=campaign.header_media_url,
        )
        token = decrypt(account.access_token_encrypted)

    client = get_client(token)
    limiter = RateLimiter(settings.send_rate_per_second)
    stop = threading.Event()
    fatal: list[WhatsAppAPIError] = []

    try:
        with ThreadPoolExecutor(max_workers=settings.send_concurrency) as pool:
            while not stop.is_set():
                lock.reacquire()
                with SessionLocal() as db:
                    status = db.scalar(select(Campaign.status).where(Campaign.id == campaign_id))
                    if status != "sending":
                        return f"stopped ({status})"
                    rows = db.execute(
                        select(Message.id, Message.phone, Message.variables)
                        .where(Message.campaign_id == campaign_id, Message.status == "queued")
                        .order_by(Message.id)
                        .limit(BATCH_SIZE)
                    ).all()
                if not rows:
                    break
                list(pool.map(lambda r: _send_one(client, ctx, r, limiter, stop, fatal), rows))
                with SessionLocal() as db:
                    reconcile_unapplied_events(db)
    finally:
        client.close()

    with SessionLocal() as db:
        campaign = db.get(Campaign, campaign_id)
        if fatal:
            err = fatal[0]
            campaign.status = "paused"
            campaign.last_error = f"{describe(err.code, err.title)} (Meta error {err.code}). {err.detail}".strip()
            db.commit()
            return "paused on error"
        remaining = db.scalar(
            select(func.count()).where(Message.campaign_id == campaign_id, Message.status == "queued")
        )
        if campaign.status == "sending" and remaining == 0:
            campaign.status = "completed"
            campaign.completed_at = _now()
        db.commit()
    return "done"


def _send_one(client, ctx: SendContext, row, limiter: RateLimiter, stop: threading.Event,
              fatal: list) -> None:
    if stop.is_set():
        return
    components = build_send_components(ctx.components, ctx.parameter_format, row.variables or {},
                                       ctx.header_media_url)
    attempt = 0
    while True:
        attempt += 1
        if stop.is_set():
            return
        limiter.wait()
        try:
            result = client.send_template(ctx.phone_number_id, row.phone, ctx.template_name,
                                          ctx.language, components)
            wamid = result["messages"][0]["id"]
            with SessionLocal() as db:
                message = db.get(Message, row.id, with_for_update=True)
                message.status = "accepted"
                message.wamid = wamid
                message.attempts = attempt
                message.accepted_at = _now()
                apply_pending_events(db, message)
                db.commit()
            if settings.whatsapp_mock:
                _schedule_mock_webhooks(ctx.phone_number_id, wamid, row.phone)
            return
        except WhatsAppAPIError as err:
            if err.code in CAMPAIGN_FATAL_CODES:
                fatal.append(err)
                stop.set()
                return  # message stays queued, so it is sent when the campaign resumes
            if err.code in RETRYABLE_CODES and attempt < MAX_ATTEMPTS:
                time.sleep(2**attempt)
                continue
            _mark_failed(row.id, attempt, err.code, describe(err.code, err.title), err.detail or err.title)
            return
        except (httpx.ConnectError, httpx.ConnectTimeout) as err:
            # Request never reached Meta, so it is safe to retry.
            if attempt < MAX_ATTEMPTS:
                time.sleep(2**attempt)
                continue
            _mark_failed(row.id, attempt, None, "Network error: could not reach Meta", str(err))
            return
        except httpx.HTTPError as err:
            # Request may have reached Meta. Don't retry, to avoid sending twice.
            _mark_failed(row.id, attempt, None, "Network error: delivery status unknown", str(err))
            return
        except Exception as err:  # noqa: BLE001 - one bad row must not stop the campaign
            log.exception("Unexpected error sending message %s", row.id)
            _mark_failed(row.id, attempt, None, "Unexpected error", str(err))
            return


def _mark_failed(message_id: int, attempts: int, code, title: str, detail: str) -> None:
    with SessionLocal() as db:
        message = db.get(Message, message_id, with_for_update=True)
        message.status = "failed"
        message.attempts = attempts
        message.error_code = code
        message.error_title = title[:255]
        message.error_detail = detail
        message.failed_at = _now()
        db.commit()


# --- Mock mode: fake the webhooks Meta would send ----------------------------------


@celery_app.task(name="simulate_webhook")
def simulate_webhook(payload: dict) -> None:
    for entry in payload["entry"]:
        for change in entry["changes"]:
            for status_obj in change["value"]["statuses"]:
                status_obj["timestamp"] = str(int(time.time()))  # time it "happened"
    with SessionLocal() as db:
        process_webhook(db, payload)


def _schedule_mock_webhooks(phone_number_id: str, wamid: str, phone: str) -> None:
    def payload(status: str, errors: list | None = None) -> dict:
        status_obj = {"id": wamid, "status": status, "timestamp": str(int(time.time())),
                      "recipient_id": phone.lstrip("+")}
        if errors:
            status_obj["errors"] = errors
        return {"object": "whatsapp_business_account", "entry": [{"changes": [{
            "field": "messages",
            "value": {"metadata": {"phone_number_id": phone_number_id}, "statuses": [status_obj]},
        }]}]}

    if phone.endswith("00"):
        simulate_webhook.apply_async(args=[payload("failed", [{
            "code": 131026, "title": "Message undeliverable",
            "error_data": {"details": "Message Undeliverable."}}])], countdown=2)
        return
    simulate_webhook.apply_async(args=[payload("sent")], countdown=1)
    simulate_webhook.apply_async(args=[payload("delivered")], countdown=3)
    if not phone.endswith("1"):
        simulate_webhook.apply_async(args=[payload("read")], countdown=6)

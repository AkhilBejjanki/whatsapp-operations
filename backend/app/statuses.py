"""Processing Meta webhooks: message statuses and template approval updates."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .errors import describe
from .models import Message, MessageEvent, Template

log = logging.getLogger(__name__)

# A late "sent" webhook must not overwrite "read", so statuses only move forward.
RANK = {"queued": 0, "accepted": 1, "sent": 2, "delivered": 3, "read": 4}


def _ts(value) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def apply_status(message: Message, status_obj: dict) -> None:
    status = status_obj.get("status")
    when = _ts(status_obj.get("timestamp"))

    if status == "failed":
        if message.status in ("delivered", "read"):
            return
        error = (status_obj.get("errors") or [{}])[0]
        code = error.get("code")
        message.status = "failed"
        message.failed_at = when
        message.error_code = code
        message.error_title = describe(code, error.get("title") or error.get("message"))
        message.error_detail = (error.get("error_data") or {}).get("details") or error.get("message")
        return

    if status not in RANK or message.status in ("failed", "cancelled", "invalid"):
        return

    if status in ("sent", "delivered", "read") and not message.sent_at:
        message.sent_at = when
    if status in ("delivered", "read") and not message.delivered_at:
        message.delivered_at = when
    if status == "read" and not message.read_at:
        message.read_at = when
    if RANK[status] > RANK.get(message.status, 0):
        message.status = status


def apply_pending_events(db: Session, message: Message) -> None:
    """Apply webhook events that arrived before the worker saved this message's wamid."""
    if not message.wamid:
        return
    events = db.scalars(
        select(MessageEvent)
        .where(MessageEvent.wamid == message.wamid, MessageEvent.applied.is_(False))
        .order_by(MessageEvent.timestamp, MessageEvent.id)
    ).all()
    for event in events:
        apply_status(message, event.payload)
        event.applied = True


def reconcile_unapplied_events(db: Session, limit: int = 500) -> int:
    """Safety net for the small race between the worker and the webhook."""
    events = db.scalars(
        select(MessageEvent)
        .where(MessageEvent.applied.is_(False))
        .order_by(MessageEvent.id)
        .limit(limit)
    ).all()
    applied = 0
    for event in events:
        message = db.scalar(select(Message).where(Message.wamid == event.wamid).with_for_update())
        if message:
            apply_status(message, event.payload)
            event.applied = True
            applied += 1
    db.commit()
    return applied


def process_webhook(db: Session, payload: dict) -> None:
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            field = change.get("field")
            value = change.get("value") or {}
            if field == "messages":
                for status_obj in value.get("statuses", []):
                    _handle_status(db, status_obj)
                # value["messages"] holds incoming replies. Not used yet (future: inbox).
            elif field == "message_template_status_update":
                db.execute(
                    update(Template)
                    .where(Template.meta_template_id == str(value.get("message_template_id")))
                    .values(status=value.get("event"), rejected_reason=value.get("reason"))
                )
            elif field == "template_category_update":
                new_category = value.get("new_category") or value.get("correct_category")
                if new_category:
                    db.execute(
                        update(Template)
                        .where(Template.meta_template_id == str(value.get("message_template_id")))
                        .values(category=new_category)
                    )
    db.commit()


def _handle_status(db: Session, status_obj: dict) -> None:
    wamid = status_obj.get("id")
    status = status_obj.get("status")
    if not wamid or not status:
        return
    event = MessageEvent(
        wamid=wamid,
        status=status,
        timestamp=int(status_obj.get("timestamp") or 0),
        payload=status_obj,
    )
    db.add(event)
    message = db.scalar(select(Message).where(Message.wamid == wamid).with_for_update())
    if message:
        apply_status(message, status_obj)
        event.applied = True
    db.flush()

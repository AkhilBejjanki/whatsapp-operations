import csv
import io
from datetime import datetime

import phonenumbers
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..contacts import normalize_phone, parse_file, suggest_columns
from ..db import SessionLocal, get_db
from ..deps import current_user, require_account
from ..errors import NOT_WORTH_RETRYING
from ..models import Campaign, Message, Template, Upload, User
from ..templates_util import header_media_format, resolve_variables, template_variables
from ..worker import send_campaign

router = APIRouter(tags=["campaigns"])

STATUSES = ["invalid", "queued", "accepted", "sent", "delivered", "read", "failed", "cancelled"]


# --- Uploads ---------------------------------------------------------------------------


@router.post("/uploads")
def upload_contacts(file: UploadFile = File(...), user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    content = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB")
    try:
        columns, rows = parse_file(file.filename or "", content)
    except ValueError as err:
        raise HTTPException(400, str(err)) from err
    if not rows:
        raise HTTPException(400, "The file has no rows")
    if len(rows) > settings.max_upload_rows:
        raise HTTPException(400, f"Too many rows (max {settings.max_upload_rows:,})")

    upload = Upload(organization_id=user.organization_id, filename=file.filename or "contacts",
                    columns=columns, rows=rows, row_count=len(rows))
    db.add(upload)
    db.commit()
    return {
        "id": upload.id,
        "filename": upload.filename,
        "columns": columns,
        "row_count": len(rows),
        "sample_rows": rows[:5],
        "suggested": suggest_columns(columns),
    }


# --- Campaigns -------------------------------------------------------------------------


class Mapping(BaseModel):
    type: str = Field(pattern="^(column|static)$")
    value: str = ""


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    upload_id: int
    template_id: int
    phone_column: str
    name_column: str | None = None
    default_country: str = Field(default="IN", min_length=2, max_length=2)
    variable_mapping: dict[str, Mapping] = {}
    header_media_url: str | None = None


def _counts(db: Session, campaign_ids: list[int]) -> dict[int, dict[str, int]]:
    result: dict[int, dict[str, int]] = {cid: {s: 0 for s in STATUSES} for cid in campaign_ids}
    if not campaign_ids:
        return result
    rows = db.execute(
        select(Message.campaign_id, Message.status, func.count())
        .where(Message.campaign_id.in_(campaign_ids))
        .group_by(Message.campaign_id, Message.status)
    )
    for cid, status, count in rows:
        result[cid][status] = count
    return result


def campaign_out(c: Campaign, counts: dict[str, int], template: Template | None = None) -> dict:
    total = sum(counts.values())
    sendable = total - counts.get("invalid", 0)
    return {
        "id": c.id,
        "name": c.name,
        "status": c.status,
        "template": {"id": template.id, "name": template.name, "language": template.language,
                     "category": template.category} if template else None,
        "default_country": c.default_country,
        "total_rows": c.total_rows,
        "duplicate_count": c.duplicate_count,
        "counts": counts,
        "total": total,
        "sendable": sendable,
        # Every message that has left the queue, whatever happened to it.
        "processed": sendable - counts.get("queued", 0),
        "last_error": c.last_error,
        "created_at": c.created_at,
        "started_at": c.started_at,
        "completed_at": c.completed_at,
    }


def _get_campaign(db: Session, user: User, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.organization_id != user.organization_id:
        raise HTTPException(404, "Campaign not found")
    return campaign


@router.get("/campaigns")
def list_campaigns(user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaigns = db.scalars(
        select(Campaign).where(Campaign.organization_id == user.organization_id)
        .order_by(Campaign.id.desc()).limit(200)
    ).all()
    counts = _counts(db, [c.id for c in campaigns])
    templates = {t.id: t for t in db.scalars(
        select(Template).where(Template.id.in_({c.template_id for c in campaigns})))}
    return [campaign_out(c, counts[c.id], templates.get(c.template_id)) for c in campaigns]


@router.post("/campaigns")
def create_campaign(body: CampaignIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Create a draft: validates every row, so the user sees the numbers before sending."""
    account = require_account(db, user.organization_id)
    upload = db.get(Upload, body.upload_id)
    if not upload or upload.organization_id != user.organization_id:
        raise HTTPException(404, "Upload not found")
    template = db.get(Template, body.template_id)
    if not template or template.organization_id != user.organization_id:
        raise HTTPException(404, "Template not found")
    if body.phone_column not in upload.columns:
        raise HTTPException(400, "Phone column not found in the file")
    if body.name_column and body.name_column not in upload.columns:
        raise HTTPException(400, "Name column not found in the file")
    country = body.default_country.upper()
    if country not in phonenumbers.SUPPORTED_REGIONS:
        raise HTTPException(400, "Unknown country code")

    variables = template_variables(template.components)
    mapping = {k: v.model_dump() for k, v in body.variable_mapping.items()}
    for var in variables:
        source = mapping.get(var["key"])
        if not source or not source["value"].strip():
            raise HTTPException(400, f"Choose a column or text for {var['label']}")
        if source["type"] == "column" and source["value"] not in upload.columns:
            raise HTTPException(400, f"Column \"{source['value']}\" not found in the file")
    media = header_media_format(template.components)
    header_media_url = (body.header_media_url or "").strip() or None
    if media and not (header_media_url and header_media_url.startswith("https://")):
        raise HTTPException(400, f"This template needs a public https:// link to a {media.lower()} for its header")

    campaign = Campaign(
        organization_id=user.organization_id, whatsapp_account_id=account.id,
        template_id=template.id, upload_id=upload.id, name=body.name, status="draft",
        phone_column=body.phone_column, name_column=body.name_column,
        variable_mapping=mapping, header_media_url=header_media_url if media else None,
        default_country=country, total_rows=upload.row_count,
    )
    db.add(campaign)
    db.flush()

    labels = {v["key"]: v["label"] for v in variables}
    seen: set[str] = set()
    duplicates = 0
    rows_to_insert = []
    for index, row in enumerate(upload.rows):
        raw_phone = row.get(body.phone_column, "")
        phone, reason = normalize_phone(raw_phone, country)
        if phone and phone in seen:
            duplicates += 1
            continue
        values = resolve_variables(mapping, row)
        status, error = "queued", None
        if not phone:
            status, error = "invalid", reason
        else:
            seen.add(phone)
            missing = [labels[k] for k in labels if not values.get(k)]
            if missing:
                status, error = "invalid", "Empty value for " + ", ".join(missing)
        rows_to_insert.append({
            "campaign_id": campaign.id,
            "organization_id": user.organization_id,
            "row_index": index + 1,
            "contact_name": (row.get(body.name_column, "") if body.name_column else "")[:255] or None,
            "raw_phone": str(raw_phone)[:64],
            "phone": phone,
            "variables": values,
            "status": status,
            "error_title": error,
            "attempts": 0,
        })
    for start in range(0, len(rows_to_insert), 2000):
        db.execute(insert(Message), rows_to_insert[start:start + 2000])
    campaign.duplicate_count = duplicates
    db.commit()
    return campaign_out(campaign, _counts(db, [campaign.id])[campaign.id], template)


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaign = _get_campaign(db, user, campaign_id)
    template = db.get(Template, campaign.template_id)
    out = campaign_out(campaign, _counts(db, [campaign.id])[campaign.id], template)
    errors = db.execute(
        select(Message.error_code, Message.error_title, func.count())
        .where(Message.campaign_id == campaign.id, Message.status.in_(["failed", "invalid"]))
        .group_by(Message.error_code, Message.error_title)
        .order_by(func.count().desc())
        .limit(20)
    )
    out["errors"] = [{"code": code, "title": title, "count": count} for code, title, count in errors]
    return out


@router.get("/campaigns/{campaign_id}/messages")
def list_messages(
    campaign_id: int,
    status: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    campaign = _get_campaign(db, user, campaign_id)
    query = select(Message).where(Message.campaign_id == campaign.id)
    if status:
        query = query.where(Message.status.in_(status.split(",")))
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Message.phone.ilike(like), Message.raw_phone.ilike(like),
                                Message.contact_name.ilike(like)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    messages = db.scalars(query.order_by(Message.row_index).offset((page - 1) * page_size).limit(page_size))
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [{
            "id": m.id, "row_index": m.row_index, "contact_name": m.contact_name,
            "raw_phone": m.raw_phone, "phone": m.phone, "status": m.status,
            "error_code": m.error_code, "error_title": m.error_title, "error_detail": m.error_detail,
            "variables": m.variables, "sent_at": m.sent_at, "delivered_at": m.delivered_at,
            "read_at": m.read_at, "failed_at": m.failed_at,
        } for m in messages],
    }


@router.post("/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaign = _get_campaign(db, user, campaign_id)
    if campaign.status not in ("draft", "paused"):
        raise HTTPException(400, f"Can't start a campaign that is {campaign.status}")
    template = db.get(Template, campaign.template_id)
    if template.status != "APPROVED":
        raise HTTPException(400, f"Template \"{template.name}\" is {template.status}, not APPROVED")
    queued = db.scalar(select(func.count()).where(Message.campaign_id == campaign.id,
                                                  Message.status == "queued"))
    if not queued:
        raise HTTPException(400, "There are no messages waiting to be sent")
    campaign.status = "queued"
    campaign.last_error = None
    db.commit()
    send_campaign.delay(campaign.id)
    return get_campaign(campaign_id, user, db)


@router.post("/campaigns/{campaign_id}/pause")
def pause_campaign(campaign_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaign = _get_campaign(db, user, campaign_id)
    if campaign.status not in ("queued", "sending"):
        raise HTTPException(400, f"Can't pause a campaign that is {campaign.status}")
    campaign.status = "paused"
    db.commit()
    return get_campaign(campaign_id, user, db)


@router.post("/campaigns/{campaign_id}/cancel")
def cancel_campaign(campaign_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaign = _get_campaign(db, user, campaign_id)
    if campaign.status in ("completed", "cancelled"):
        raise HTTPException(400, f"Campaign is already {campaign.status}")
    campaign.status = "cancelled"
    campaign.completed_at = datetime.now().astimezone()
    db.execute(update(Message).where(Message.campaign_id == campaign.id, Message.status == "queued")
               .values(status="cancelled"))
    db.commit()
    return get_campaign(campaign_id, user, db)


@router.post("/campaigns/{campaign_id}/retry-failed")
def retry_failed(campaign_id: int, include_all: bool = False, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    """Re-queue failed messages. By default skips 'not on WhatsApp' and 'opted out'."""
    campaign = _get_campaign(db, user, campaign_id)
    if campaign.status in ("queued", "sending"):
        raise HTTPException(400, "Wait until the campaign finishes or pause it first")
    condition = [Message.campaign_id == campaign.id, Message.status == "failed"]
    if not include_all:
        condition.append(or_(Message.error_code.is_(None), Message.error_code.not_in(NOT_WORTH_RETRYING)))
    result = db.execute(update(Message).where(*condition).values(
        status="queued", wamid=None, error_code=None, error_title=None, error_detail=None,
        failed_at=None, accepted_at=None, sent_at=None))
    if result.rowcount == 0:
        raise HTTPException(400, "No failed messages worth retrying")
    campaign.status = "paused"  # start_campaign moves it on to queued
    campaign.completed_at = None
    db.commit()
    return start_campaign(campaign_id, user, db)


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(campaign_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaign = _get_campaign(db, user, campaign_id)
    if campaign.status not in ("draft", "completed", "cancelled"):
        raise HTTPException(400, "Pause or cancel the campaign before deleting it")
    db.execute(delete(Message).where(Message.campaign_id == campaign.id))
    db.delete(campaign)
    db.commit()
    return {"ok": True}


@router.get("/campaigns/{campaign_id}/export")
def export_campaign(campaign_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    campaign = _get_campaign(db, user, campaign_id)
    var_keys = list(campaign.variable_mapping.keys())
    cid = campaign.id

    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["row", "name", "phone_in_file", "phone", "status", "error_code", "error",
                         "error_detail", "sent_at", "delivered_at", "read_at", "failed_at", *var_keys])
        offset = 0
        while True:
            with SessionLocal() as session:
                batch = session.scalars(select(Message).where(Message.campaign_id == cid)
                                        .order_by(Message.row_index).offset(offset).limit(2000)).all()
            if not batch:
                break
            for m in batch:
                writer.writerow([
                    m.row_index, m.contact_name or "", m.raw_phone or "", m.phone or "", m.status,
                    m.error_code or "", m.error_title or "", m.error_detail or "",
                    m.sent_at or "", m.delivered_at or "", m.read_at or "", m.failed_at or "",
                    *[(m.variables or {}).get(k, "") for k in var_keys],
                ])
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            offset += len(batch)

    safe_name = "".join(ch if ch.isalnum() else "_" for ch in campaign.name)[:50] or "campaign"
    return StreamingResponse(
        generate(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_report.csv"'},
    )

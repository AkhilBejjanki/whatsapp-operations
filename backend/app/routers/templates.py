from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, require_account
from ..models import Template, User, WhatsAppAccount
from ..security import decrypt
from ..templates_util import VAR_RE, header_media_format, template_variables
from ..whatsapp import WhatsAppAPIError, get_client

router = APIRouter(prefix="/templates", tags=["templates"])


class ButtonIn(BaseModel):
    type: Literal["QUICK_REPLY", "URL", "PHONE_NUMBER"]
    text: str = Field(min_length=1, max_length=25)
    url: str | None = None
    url_example: str | None = None
    phone_number: str | None = None


class TemplateIn(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9_]{1,512}$")
    language: str = Field(default="en", max_length=16)
    category: Literal["MARKETING", "UTILITY"]
    header_text: str | None = Field(default=None, max_length=60)
    header_example: str | None = None
    body: str = Field(min_length=1, max_length=1024)
    body_examples: list[str] = []
    footer: str | None = Field(default=None, max_length=60)
    buttons: list[ButtonIn] = Field(default=[], max_length=10)


def template_out(t: Template) -> dict:
    return {
        "id": t.id,
        "meta_template_id": t.meta_template_id,
        "name": t.name,
        "language": t.language,
        "category": t.category,
        "status": t.status,
        "parameter_format": t.parameter_format,
        "components": t.components,
        "rejected_reason": t.rejected_reason,
        "variables": template_variables(t.components),
        "header_media": header_media_format(t.components),
        "updated_at": t.updated_at,
    }


def sync_templates(db: Session, account: WhatsAppAccount) -> None:
    client = get_client(decrypt(account.access_token_encrypted))
    try:
        remote = client.list_templates(account.waba_id)
    except WhatsAppAPIError as err:
        raise HTTPException(400, f"Meta API error {err.code}: {err.title}") from err
    finally:
        client.close()

    existing = {
        (t.name, t.language): t
        for t in db.scalars(select(Template).where(Template.whatsapp_account_id == account.id))
    }
    seen = set()
    for item in remote:
        key = (item["name"], item.get("language", "en"))
        seen.add(key)
        template = existing.get(key)
        if not template:
            template = Template(organization_id=account.organization_id,
                                whatsapp_account_id=account.id, name=key[0], language=key[1])
            db.add(template)
        template.meta_template_id = str(item.get("id"))
        template.status = item.get("status", "PENDING")
        template.category = item.get("category")
        template.components = item.get("components", [])
        template.parameter_format = item.get("parameter_format") or "POSITIONAL"
        template.rejected_reason = item.get("rejected_reason")
    for key, template in existing.items():
        if key not in seen:
            template.status = "DELETED"
    db.commit()


@router.get("")
def list_templates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    templates = db.scalars(
        select(Template)
        .where(Template.organization_id == user.organization_id, Template.status != "DELETED")
        .order_by(Template.name)
    ).all()
    return [template_out(t) for t in templates]


@router.post("/sync")
def sync(user: User = Depends(current_user), db: Session = Depends(get_db)):
    sync_templates(db, require_account(db, user.organization_id))
    return list_templates(user, db)


def _build_components(body: TemplateIn) -> list[dict]:
    components: list[dict] = []
    if body.header_text:
        header = {"type": "HEADER", "format": "TEXT", "text": body.header_text}
        if VAR_RE.search(body.header_text):
            if not body.header_example:
                raise HTTPException(400, "Give an example value for the header variable")
            header["example"] = {"header_text": [body.header_example]}
        components.append(header)

    body_vars = list(dict.fromkeys(VAR_RE.findall(body.body)))
    if any(not v.isdigit() for v in body_vars):
        raise HTTPException(400, "Use numbered variables like {{1}}, {{2}} in the body")
    expected = [str(i) for i in range(1, len(body_vars) + 1)]
    if sorted(body_vars, key=int) != expected:
        raise HTTPException(400, "Body variables must be numbered in order: {{1}}, {{2}}, {{3}}...")
    examples = [e.strip() for e in body.body_examples]
    body_component: dict = {"type": "BODY", "text": body.body}
    if body_vars:
        if len(examples) < len(body_vars) or not all(examples[: len(body_vars)]):
            raise HTTPException(400, f"Give an example value for each of the {len(body_vars)} body variables")
        body_component["example"] = {"body_text": [examples[: len(body_vars)]]}
    components.append(body_component)

    if body.footer:
        components.append({"type": "FOOTER", "text": body.footer})

    if body.buttons:
        buttons = []
        for b in body.buttons:
            if b.type == "QUICK_REPLY":
                buttons.append({"type": "QUICK_REPLY", "text": b.text})
            elif b.type == "URL":
                if not b.url:
                    raise HTTPException(400, f"Button \"{b.text}\" needs a URL")
                button = {"type": "URL", "text": b.text, "url": b.url}
                if VAR_RE.search(b.url):
                    button["example"] = [b.url_example or VAR_RE.sub("example", b.url)]
                buttons.append(button)
            else:
                if not b.phone_number:
                    raise HTTPException(400, f"Button \"{b.text}\" needs a phone number")
                buttons.append({"type": "PHONE_NUMBER", "text": b.text, "phone_number": b.phone_number})
        components.append({"type": "BUTTONS", "buttons": buttons})
    return components


@router.post("")
def create_template(body: TemplateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = require_account(db, user.organization_id)
    payload = {
        "name": body.name,
        "language": body.language,
        "category": body.category,
        "components": _build_components(body),
    }
    client = get_client(decrypt(account.access_token_encrypted))
    try:
        result = client.create_template(account.waba_id, payload)
    except WhatsAppAPIError as err:
        raise HTTPException(400, f"Meta rejected the template: {err.title}. {err.detail}".strip()) from err
    finally:
        client.close()

    template = db.scalar(select(Template).where(
        Template.whatsapp_account_id == account.id,
        Template.name == body.name, Template.language == body.language))
    if not template:
        template = Template(organization_id=user.organization_id, whatsapp_account_id=account.id,
                            name=body.name, language=body.language)
        db.add(template)
    template.meta_template_id = str(result.get("id"))
    template.status = result.get("status", "PENDING")
    template.category = result.get("category") or body.category
    template.components = payload["components"]
    template.parameter_format = "POSITIONAL"
    template.rejected_reason = None
    db.commit()
    return template_out(template)


@router.delete("/{template_id}")
def delete_template(template_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    template = db.get(Template, template_id)
    if not template or template.organization_id != user.organization_id:
        raise HTTPException(404, "Template not found")
    account = require_account(db, user.organization_id)
    client = get_client(decrypt(account.access_token_encrypted))
    try:
        client.delete_template(account.waba_id, template.name)
    except WhatsAppAPIError as err:
        raise HTTPException(400, f"Meta API error {err.code}: {err.title}") from err
    finally:
        client.close()
    # Note: Meta deletes all languages of a template with this name.
    for t in db.scalars(select(Template).where(Template.whatsapp_account_id == account.id,
                                               Template.name == template.name)):
        t.status = "DELETED"
    db.commit()
    return {"ok": True}

"""Database tables.

Every business-owned row carries `organization_id`, so the same schema works for
one business today (phase 1) and many businesses later (phase 2, SaaS).
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="owner")
    created_at: Mapped[datetime] = _created()


class WhatsAppAccount(Base):
    __tablename__ = "whatsapp_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    waba_id: Mapped[str] = mapped_column(String(64))
    phone_number_id: Mapped[str] = mapped_column(String(64), unique=True)
    display_phone_number: Mapped[str | None] = mapped_column(String(64))
    verified_name: Mapped[str | None] = mapped_column(String(255))
    quality_rating: Mapped[str | None] = mapped_column(String(32))
    messaging_limit: Mapped[str | None] = mapped_column(String(64))
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    webhook_subscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (UniqueConstraint("whatsapp_account_id", "name", "language"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    whatsapp_account_id: Mapped[int] = mapped_column(ForeignKey("whatsapp_accounts.id"), index=True)
    meta_template_id: Mapped[str | None] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(512))
    language: Mapped[str] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))  # APPROVED, PENDING, REJECTED, PAUSED, DISABLED, DELETED
    parameter_format: Mapped[str] = mapped_column(String(16), default="POSITIONAL")
    components: Mapped[list] = mapped_column(JSONB, default=list)
    rejected_reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Upload(Base):
    """A parsed CSV/Excel file, kept so the user can map columns before creating a campaign."""

    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    columns: Mapped[list] = mapped_column(JSONB)
    rows: Mapped[list] = mapped_column(JSONB)
    row_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created()


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    whatsapp_account_id: Mapped[int] = mapped_column(ForeignKey("whatsapp_accounts.id"))
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"))
    upload_id: Mapped[int | None] = mapped_column(ForeignKey("uploads.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255))
    # draft -> queued -> sending -> completed   (paused / cancelled along the way)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    phone_column: Mapped[str] = mapped_column(String(255))
    name_column: Mapped[str | None] = mapped_column(String(255))
    variable_mapping: Mapped[dict] = mapped_column(JSONB, default=dict)
    header_media_url: Mapped[str | None] = mapped_column(Text)
    default_country: Mapped[str] = mapped_column(String(2), default="IN")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    """One recipient in a campaign.

    status: invalid | queued | accepted | sent | delivered | read | failed | cancelled
    """

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_campaign_status", "campaign_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    raw_phone: Mapped[str | None] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(32))  # E.164, e.g. +919876543210
    variables: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    wamid: Mapped[str | None] = mapped_column(String(128), unique=True)
    error_code: Mapped[int | None] = mapped_column(Integer)
    error_title: Mapped[str | None] = mapped_column(String(255))
    error_detail: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class MessageEvent(Base):
    """Raw status updates from Meta's webhook.

    Kept as an audit trail, and so a status that arrives before the worker has saved the
    message's wamid can still be applied afterwards.
    """

    __tablename__ = "message_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    wamid: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(20))
    timestamp: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)
    applied: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = _created()

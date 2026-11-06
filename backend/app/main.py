import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from .config import settings
from .db import Base, SessionLocal, engine
from .models import Organization, User
from .routers import account, auth, campaigns, templates, webhook
from .security import hash_password

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")


def _seed_admin() -> None:
    if not settings.admin_email or not settings.admin_password:
        return
    with SessionLocal() as db:
        email = settings.admin_email.lower()
        if db.scalar(select(User).where(func.lower(User.email) == email)):
            return
        org = Organization(name=settings.admin_org_name)
        db.add(org)
        db.flush()
        db.add(User(organization_id=org.id, email=email, name="Admin",
                    password_hash=hash_password(settings.admin_password), role="owner"))
        db.commit()
        log.info("Created admin user %s", email)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fine for phase 1. Switch to Alembic migrations before changing tables in production.
    Base.metadata.create_all(engine)
    _seed_admin()
    if settings.whatsapp_mock:
        log.warning("WHATSAPP_MOCK is on: no real WhatsApp messages will be sent")
    yield


app = FastAPI(title="WhatsApp Bulk Sender API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.frontend_origin.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

for router in (auth.router, account.router, templates.router, campaigns.router, webhook.router):
    app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"ok": True}

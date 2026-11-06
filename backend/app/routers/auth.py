from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..models import Organization, User
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RegisterIn(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200)
    name: str = Field(default="", max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


def _user_out(user: User, org: Organization) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "organization": {"id": org.id, "name": org.name},
        "mock_mode": settings.whatsapp_mock,
    }


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return {"access_token": create_access_token(user.id)}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if not settings.allow_signup:
        raise HTTPException(403, "Sign-up is disabled")
    if db.scalar(select(User).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(400, "An account with this email already exists")
    org = Organization(name=body.organization_name)
    db.add(org)
    db.flush()
    user = User(organization_id=org.id, email=body.email.lower(), name=body.name,
                password_hash=hash_password(body.password), role="owner")
    db.add(user)
    db.commit()
    return {"access_token": create_access_token(user.id)}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _user_out(user, db.get(Organization, user.organization_id))

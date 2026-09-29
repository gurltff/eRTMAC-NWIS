from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from .. import models as m
from ..auth import create_token, current_user, hash_password, verify_password
from ..db import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2)


def user_dict(u: m.User) -> dict:
    d = {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role}
    if u.driller:
        d["driller_status"] = u.driller.status
    return d


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(m.User).filter(m.User.email == body.email.strip().lower()).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password.")
    return {"token": create_token(u), "user": user_dict(u)}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    """Self sign-up is for drilling heads only; office accounts are created by an admin."""
    email = body.email.strip().lower()
    if db.query(m.User).filter(m.User.email == email).first():
        raise HTTPException(409, "An account with this email already exists.")
    u = m.User(email=email, password_hash=hash_password(body.password), full_name=body.full_name.strip(), role="driller")
    db.add(u)
    db.flush()
    db.add(m.DrillerProfile(user_id=u.id, status="draft"))
    db.commit()
    db.refresh(u)
    return {"token": create_token(u), "user": user_dict(u)}


@router.get("/me")
def me(user: m.User = Depends(current_user)):
    return user_dict(user)

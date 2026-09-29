"""Admin review of driller registrations and documents."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models as m
from ..auth import require_roles
from ..db import get_db
from .driller import doc_dict, profile_dict

router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_only = require_roles("admin")
office = require_roles("admin", "engineer")


@router.get("/drillers")
def list_drillers(status: str | None = None, _: m.User = Depends(office), db: Session = Depends(get_db)):
    q = db.query(m.DrillerProfile)
    if status:
        q = q.filter(m.DrillerProfile.status == status)
    order = {"submitted": 0, "draft": 1, "rejected": 2, "approved": 3}
    return sorted([profile_dict(p) for p in q.all()], key=lambda d: (order.get(d["status"], 9), d["full_name"]))


@router.get("/drillers/{driller_id}")
def get_driller(driller_id: int, _: m.User = Depends(office), db: Session = Depends(get_db)):
    p = db.get(m.DrillerProfile, driller_id)
    if not p:
        raise HTTPException(404, "Not found.")
    return profile_dict(p)


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = None


@router.post("/drillers/{driller_id}/decision")
def decide_driller(driller_id: int, body: Decision, _: m.User = Depends(admin_only), db: Session = Depends(get_db)):
    p = db.get(m.DrillerProfile, driller_id)
    if not p:
        raise HTTPException(404, "Not found.")
    if body.decision == "approve":
        pending = [d.doc_type for d in p.documents if d.status != "approved"]
        if pending:
            raise HTTPException(400, "Approve or reject every document first. Not approved yet: " + ", ".join(pending))
        if not p.equipment or p.site_lat is None:
            raise HTTPException(400, "The driller has not declared equipment and a working area.")
    elif not body.note:
        raise HTTPException(400, "Please add a note saying why the registration is rejected.")
    p.status = "approved" if body.decision == "approve" else "rejected"
    p.review_note, p.reviewed_at = body.note, datetime.utcnow()
    db.commit()
    return profile_dict(p)


class DocDecision(BaseModel):
    status: Literal["approved", "rejected", "pending"]
    note: str | None = None


@router.post("/documents/{doc_id}/decision")
def decide_document(doc_id: int, body: DocDecision, _: m.User = Depends(admin_only), db: Session = Depends(get_db)):
    d = db.get(m.DrillerDocument, doc_id)
    if not d:
        raise HTTPException(404, "Not found.")
    if body.status == "rejected" and not body.note:
        raise HTTPException(400, "Please add a note saying why the document is rejected.")
    d.status, d.note, d.reviewed_at = body.status, body.note, datetime.utcnow()
    db.commit()
    return doc_dict(d)


@router.get("/documents/{doc_id}/file")
def document_file(doc_id: int, _: m.User = Depends(office), db: Session = Depends(get_db)):
    d = db.get(m.DrillerDocument, doc_id)
    if not d or not d.stored_path:
        raise HTTPException(404, "This is a seeded sample record without an uploaded file.")
    return FileResponse(d.stored_path, filename=d.filename)

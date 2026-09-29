"""Driller self-service: registration steps, documents, equipment, work area, own tracking history."""
import shutil
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models as m
from ..auth import require_roles
from ..config import UPLOAD_DIR
from ..db import get_db
from ..services.tracking import allowed_zone, breach_dict

router = APIRouter(prefix="/api/driller", tags=["driller"])
driller_only = require_roles("driller")

DOC_TYPES = {
    "licence": "Drilling contractor licence",
    "permit": "Site permit / PML consent",
    "id_proof": "Personal ID (Aadhaar / PAN)",
    "environmental_clearance": "Environmental clearance",
    "insurance": "Insurance certificate",
    "other": "Other document",
}
REQUIRED_DOCS = ["licence", "permit", "id_proof", "environmental_clearance"]
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg"}


def doc_dict(d: m.DrillerDocument) -> dict:
    return {"id": d.id, "doc_type": d.doc_type, "label": DOC_TYPES.get(d.doc_type, d.doc_type), "filename": d.filename,
            "status": d.status, "note": d.note, "uploaded_at": d.uploaded_at.isoformat() + "Z",
            "reviewed_at": d.reviewed_at.isoformat() + "Z" if d.reviewed_at else None, "has_file": bool(d.stored_path)}


def equipment_dict(e: m.Equipment) -> dict:
    return {"id": e.id, "name": e.name, "rig_type": e.rig_type, "max_depth_m": e.max_depth_m,
            "max_horizontal_reach_m": e.max_horizontal_reach_m, "hook_load_t": e.hook_load_t, "power_hp": e.power_hp,
            "year_built": e.year_built}


def checklist(p: m.DrillerProfile) -> list[dict]:
    have = {d.doc_type for d in p.documents}
    return [
        {"step": "personal", "label": "Personal details", "done": bool(p.phone and p.designation)},
        {"step": "company", "label": "Company details", "done": bool(p.company_name and p.licence_number)},
        {"step": "documents", "label": "Required documents uploaded", "done": all(t in have for t in REQUIRED_DOCS),
         "missing": [DOC_TYPES[t] for t in REQUIRED_DOCS if t not in have]},
        {"step": "equipment", "label": "At least one rig declared", "done": bool(p.equipment)},
        {"step": "area", "label": "Working area set", "done": p.site_lat is not None and bool(p.work_radius_m)},
    ]


def profile_dict(p: m.DrillerProfile, include_zone: bool = True) -> dict:
    d = {
        "id": p.id, "user_id": p.user_id, "full_name": p.user.full_name, "email": p.user.email,
        "phone": p.phone, "designation": p.designation, "experience_years": p.experience_years, "id_number": p.id_number,
        "company_name": p.company_name, "company_reg_no": p.company_reg_no, "company_address": p.company_address,
        "licence_number": p.licence_number, "work_area_name": p.work_area_name, "site_lat": p.site_lat, "site_lon": p.site_lon,
        "work_radius_m": p.work_radius_m, "planned_md_m": p.planned_md_m, "planned_kop_m": p.planned_kop_m,
        "planned_build_rate": p.planned_build_rate, "planned_hold_inc": p.planned_hold_inc, "planned_azimuth": p.planned_azimuth,
        "status": p.status, "review_note": p.review_note,
        "submitted_at": p.submitted_at.isoformat() + "Z" if p.submitted_at else None,
        "reviewed_at": p.reviewed_at.isoformat() + "Z" if p.reviewed_at else None,
        "tracking_status": p.tracking_status, "last_lat": p.last_lat, "last_lon": p.last_lon,
        "last_seen_at": p.last_seen_at.isoformat() + "Z" if p.last_seen_at else None,
        "documents": [doc_dict(x) for x in p.documents],
        "equipment": [equipment_dict(x) for x in p.equipment],
        "checklist": checklist(p),
    }
    if include_zone:
        d["zone"] = allowed_zone(p)
    return d


def _profile(user: m.User) -> m.DrillerProfile:
    if not user.driller:
        raise HTTPException(404, "No driller profile.")
    return user.driller


def _editable(p: m.DrillerProfile):
    if p.status == "submitted":
        raise HTTPException(400, "Your registration is under review. You can edit it after the admin replies.")


@router.get("/me")
def me(user: m.User = Depends(driller_only)):
    return profile_dict(_profile(user))


class ProfileIn(BaseModel):
    phone: str | None = None
    designation: str | None = None
    experience_years: int | None = Field(default=None, ge=0, le=60)
    id_number: str | None = None
    company_name: str | None = None
    company_reg_no: str | None = None
    company_address: str | None = None
    licence_number: str | None = None


@router.put("/profile")
def update_profile(body: ProfileIn, user: m.User = Depends(driller_only), db: Session = Depends(get_db)):
    p = _profile(user)
    _editable(p)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    return profile_dict(p)


class WorkAreaIn(BaseModel):
    work_area_name: str
    site_lat: float = Field(ge=-90, le=90)
    site_lon: float = Field(ge=-180, le=180)
    work_radius_m: float = Field(gt=0, le=50_000)
    planned_md_m: float | None = Field(default=None, gt=0, le=10_000)
    planned_kop_m: float | None = Field(default=None, ge=0)
    planned_build_rate: float | None = Field(default=None, ge=0, le=10)
    planned_hold_inc: float | None = Field(default=None, ge=0, le=90)
    planned_azimuth: float | None = Field(default=None, ge=0, lt=360)


@router.put("/work-area")
def update_area(body: WorkAreaIn, user: m.User = Depends(driller_only), db: Session = Depends(get_db)):
    p = _profile(user)
    _editable(p)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    if p.last_lat is None:
        p.last_lat, p.last_lon = p.site_lat, p.site_lon
    db.commit()
    return profile_dict(p)


class EquipmentIn(BaseModel):
    name: str
    rig_type: str
    max_depth_m: float = Field(gt=0, le=12_000)
    max_horizontal_reach_m: float = Field(gt=0, le=15_000)
    hook_load_t: float | None = Field(default=None, ge=0)
    power_hp: float | None = Field(default=None, ge=0)
    year_built: int | None = Field(default=None, ge=1950, le=2030)


@router.post("/equipment")
def add_equipment(body: EquipmentIn, user: m.User = Depends(driller_only), db: Session = Depends(get_db)):
    p = _profile(user)
    _editable(p)
    db.add(m.Equipment(driller_id=p.id, **body.model_dump()))
    db.commit()
    db.refresh(p)
    return profile_dict(p)


@router.delete("/equipment/{eq_id}")
def delete_equipment(eq_id: int, user: m.User = Depends(driller_only), db: Session = Depends(get_db)):
    p = _profile(user)
    _editable(p)
    e = db.get(m.Equipment, eq_id)
    if not e or e.driller_id != p.id:
        raise HTTPException(404, "Not found.")
    db.delete(e)
    db.commit()
    db.refresh(p)
    return profile_dict(p)


@router.post("/documents")
def upload_document(doc_type: str = Form(...), file: UploadFile = File(...), user: m.User = Depends(driller_only),
                    db: Session = Depends(get_db)):
    p = _profile(user)
    _editable(p)
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, "Unknown document type.")
    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Upload a PDF, PNG or JPG file.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / f"doc_{uuid.uuid4().hex}{ext}"
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    # A new upload of the same type replaces the old one and goes back to 'pending'.
    for old in [d for d in p.documents if d.doc_type == doc_type]:
        db.delete(old)
    db.add(m.DrillerDocument(driller_id=p.id, doc_type=doc_type, filename=file.filename, stored_path=str(dest), status="pending"))
    if p.status == "approved":
        p.status = "submitted"  # changed documents need a fresh review
        p.submitted_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    return profile_dict(p)


@router.get("/documents/{doc_id}/file")
def get_document_file(doc_id: int, user: m.User = Depends(driller_only), db: Session = Depends(get_db)):
    d = db.get(m.DrillerDocument, doc_id)
    if not d or d.driller_id != _profile(user).id or not d.stored_path:
        raise HTTPException(404, "File not found.")
    return FileResponse(d.stored_path, filename=d.filename)


@router.post("/submit")
def submit(user: m.User = Depends(driller_only), db: Session = Depends(get_db)):
    p = _profile(user)
    missing = [c["label"] for c in checklist(p) if not c["done"]]
    if missing:
        raise HTTPException(400, "Please complete: " + ", ".join(missing))
    p.status, p.submitted_at, p.review_note = "submitted", datetime.utcnow(), None
    db.commit()
    return profile_dict(p)


@router.get("/breaches")
def my_breaches(user: m.User = Depends(driller_only), db: Session = Depends(get_db)):
    rows = db.query(m.BreachEvent).filter(m.BreachEvent.user_id == user.id).order_by(m.BreachEvent.created_at.desc()).limit(100)
    return [breach_dict(b, user.full_name) for b in rows]


@router.get("/doc-types")
def doc_types():
    return {"types": DOC_TYPES, "required": REQUIRED_DOCS}

"""Upload a drilling report and turn it into structured, searchable data."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models as m
from ..auth import current_user, require_roles
from ..config import ANTHROPIC_API_KEY
from ..db import get_db
from ..services import spatial
from ..services.extraction import extract_fields, extract_text, save_extraction

router = APIRouter(prefix="/api/documents", tags=["documents"])
MAX_BYTES = 15 * 1024 * 1024


def doc_dict(d: m.Document, well_name: str | None = None) -> dict:
    return {"id": d.id, "filename": d.filename, "status": d.status, "text_method": d.text_method, "extract_method": d.extract_method,
            "text_excerpt": d.text_excerpt, "extracted": d.extracted, "well_id": d.well_id, "well_name": well_name,
            "events_created": d.events_created, "warnings": d.warnings, "created_at": d.created_at.isoformat() + "Z"}


@router.get("/mode")
def mode(_: m.User = Depends(current_user)):
    return {"llm_enabled": bool(ANTHROPIC_API_KEY),
            "text": "Claude reads the report" if ANTHROPIC_API_KEY else "Rule-based extraction (no API key set)"}


@router.post("/extract")
async def extract(file: UploadFile = File(...), user: m.User = Depends(require_roles("admin", "engineer")),
                  db: Session = Depends(get_db)):
    name = file.filename or "upload"
    if not name.lower().endswith((".pdf", ".txt", ".png", ".jpg", ".jpeg")):
        raise HTTPException(400, "Upload a PDF (or a .txt / image of a report).")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "File is larger than 15 MB.")
    try:
        text, text_method, warnings = extract_text(data, name)
    except Exception as exc:
        raise HTTPException(400, f"Could not read this file: {exc}")
    if not text.strip():
        raise HTTPException(400, "No text could be read from this file. " + " ".join(warnings))
    fields, method, w2 = extract_fields(text)
    doc = m.Document(filename=name, uploaded_by=user.id, text_method=text_method, extract_method=method,
                     text_excerpt=text[:3000], extracted=fields, warnings=warnings + w2)
    db.add(doc)
    db.flush()
    well, n, w3 = save_extraction(db, doc, fields)
    doc.well_id, doc.events_created, doc.warnings = (well.id if well else None), n, warnings + w2 + w3
    db.commit()
    spatial.refresh(db)  # new well / events show up on the map straight away
    return doc_dict(doc, well.name if well else None)


@router.get("")
def list_docs(_: m.User = Depends(current_user), db: Session = Depends(get_db)):
    names = {w.id: w.name for w in db.query(m.Well.id, m.Well.name)}
    return [doc_dict(d, names.get(d.well_id)) for d in db.query(m.Document).order_by(m.Document.created_at.desc()).limit(50)]

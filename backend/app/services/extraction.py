"""Drilling report → structured data.

Pipeline:
  1. Text: pypdf for digital PDFs; OCR (pytesseract + pdf2image, optional) for
     scanned PDFs and images; plain decode for .txt.
  2. Fields: Claude (if ANTHROPIC_API_KEY is set) with a strict JSON schema,
     otherwise keyword/regex rules. The rules also run as a fallback if the
     LLM call fails.
  3. Save: find or create the well, add formation tops and events, so they
     show up in the knowledge base search and on the map.
"""
from __future__ import annotations

import io
import re

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models as m
from ..config import ANTHROPIC_API_KEY, LLM_MODEL
from .event_classifier import EVENT_TYPES, action_sentences, classify, find_depth_m, find_hours, severity_from
from .subsurface import FORMATION_NAMES

KNOWN_FORMATIONS = FORMATION_NAMES + ["Girujan", "Tipam", "Kopili", "Sylhet", "Lakadong", "Nordland Gp", "Hordaland Gp",
                                      "Shetland Gp", "Draupne Fm", "Heather Fm", "Hugin Fm", "Sleipner Fm", "Skagerrak Fm"]
FORMATION_ALIASES = {"Girujan": "Girujan Clay", "Tipam": "Tipam Sandstone", "Kopili": "Kopili Shale", "Sylhet": "Sylhet Limestone",
                     "Lakadong": "Sylhet Limestone"}


# --------------------------------------------------------------------------- #
# 1. Text extraction
# --------------------------------------------------------------------------- #
def _ocr_images(images) -> str:
    import pytesseract  # optional
    return "\n".join(pytesseract.image_to_string(img) for img in images)


def extract_text(data: bytes, filename: str) -> tuple[str, str, list[str]]:
    name = filename.lower()
    warnings: list[str] = []
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="replace"), "plain-text", warnings
    if name.endswith((".png", ".jpg", ".jpeg")):
        try:
            from PIL import Image
            return _ocr_images([Image.open(io.BytesIO(data))]), "ocr", warnings
        except ImportError:
            return "", "ocr-unavailable", ["OCR engine (pytesseract + Tesseract) is not installed, so images can't be read."]
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    if len(text.strip()) >= 80:
        return text, "pdf-text", warnings
    # Looks scanned: try OCR.
    try:
        from pdf2image import convert_from_bytes
        return _ocr_images(convert_from_bytes(data, dpi=200)), "ocr", warnings
    except ImportError:
        warnings.append("This PDF looks scanned and OCR (pytesseract + pdf2image) is not installed; only a little text was found.")
        return text, "pdf-text", warnings
    except Exception as exc:  # poppler missing etc.
        warnings.append(f"OCR failed: {exc}")
        return text, "pdf-text", warnings


# --------------------------------------------------------------------------- #
# 2a. LLM extraction (Claude)
# --------------------------------------------------------------------------- #
class ExtractedEvent(BaseModel):
    event_type: str = Field(description=f"One of {', '.join(EVENT_TYPES)}")
    depth_m: float | None = Field(description="Depth in metres (convert feet to metres)")
    formation: str | None
    description: str
    cause: str | None
    action_taken: str | None
    lesson: str | None
    npt_hours: float | None


class FormationTop(BaseModel):
    name: str
    top_m: float


class ExtractedReport(BaseModel):
    well_name: str | None
    field: str | None
    operator: str | None
    report_date: str | None
    rig: str | None
    lat: float | None
    lon: float | None
    total_depth_m: float | None
    formations: list[FormationTop]
    events: list[ExtractedEvent]
    lessons: list[str]
    summary: str


PROMPT = """You are reading a drilling report (daily drilling report or well completion report) from an onshore oil well.
Extract the fields into the schema. Rules:
- Depths in metres. Convert feet (ft) to metres.
- event_type must be one of: MUD_LOSS, KICK, STUCK_PIPE, TORQUE_SPIKE, CEMENTING, FISHING, NPT.
- One event per distinct problem. Put what the crew did in action_taken and any advice for future wells in lesson.
- Use null when the report does not say. Do not invent values.
- summary: two plain sentences about the well and its main problems.

REPORT:
"""


def llm_extract(text: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.beta.messages.parse(
        model=LLM_MODEL,
        max_tokens=16000,
        output_config={"effort": "medium"},
        # Server-side fallback: if the request is declined, the API retries on a suitable model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_format=ExtractedReport,
        messages=[{"role": "user", "content": PROMPT + text}],
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError("The model did not return structured output.")
    data = response.parsed_output.model_dump()
    data["events"] = [e for e in data["events"] if e["event_type"] in EVENT_TYPES]
    return data


# --------------------------------------------------------------------------- #
# 2b. Rule-based extraction
# --------------------------------------------------------------------------- #
def _first(rx: str, text: str, flags=re.I) -> str | None:
    mt = re.search(rx, text, flags)
    return mt.group(1).strip() if mt else None


def _num(s: str | None) -> float | None:
    try:
        return float(s.replace(",", "")) if s else None
    except ValueError:
        return None


def _canonical_formation(name: str) -> str:
    return FORMATION_ALIASES.get(name, name)


def _formation_in(sentence: str) -> str | None:
    for fm in sorted(KNOWN_FORMATIONS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(fm) + r"\b", sentence, re.I):
            return _canonical_formation(fm)
    return None


def rule_extract(text: str) -> dict:
    flat = re.sub(r"[ \t]+", " ", text)
    well = _first(r"Well(?:\s*name)?\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9\-/#\. ]{1,30}?)(?:\s{2,}|\n|,|;|$)", flat) \
        or _first(r"\b([A-Z]{2,4}-[A-Z]?\d{1,4}[A-Z]?)\b", flat, 0)
    lat = _num(_first(r"Lat(?:itude)?\s*[:\-]?\s*([0-9]{1,2}\.[0-9]+)", flat))
    lon = _num(_first(r"Lon(?:gitude)?\s*[:\-]?\s*([0-9]{2,3}\.[0-9]+)", flat))
    td = _first(r"(?:Total depth|TD|Final depth)\s*(?:reached)?\s*[:\-]?\s*([0-9][0-9,\.]*\s*(?:m|ft))", flat)
    td_m = find_depth_m(td) if td else None

    # Formation tops: "Tipam Sandstone ... 2150 m" on one line, or "top of Tipam at 2150 m".
    formations = {}
    for line in text.splitlines():
        fm = _formation_in(line)
        if not fm:
            continue
        mt = re.search(r"(?:top|tops?\s*at|at|:)?\s*([0-9]{3,5}(?:\.[0-9]+)?)\s*(m|ft)\b", line, re.I)
        if mt and ("top" in line.lower() or re.match(r"^\s*[A-Za-z ]+\s*[:\-]?\s*[0-9]", line)):
            depth = find_depth_m(mt.group(0))
            if depth and fm not in formations:
                formations[fm] = depth
    tops_sorted = sorted(formations.items(), key=lambda x: x[1])

    def fm_at(depth):
        name = None
        for fm, top in tops_sorted:
            if depth is not None and depth >= top:
                name = fm
        return name

    # Body text only: drop 'Key: value' header lines, then join wrapped lines into sentences.
    header_rx = re.compile(r"^\s*(well( name)?|field|operator|rig|report date|date|latitude|longitude|lat|lon|total depth|td|"
                           r"[A-Za-z ]{3,30}\btop)\s*:", re.I)
    body_lines = [ln for ln in text.splitlines() if not header_rx.match(ln)]
    body = re.sub(r"\s*\n\s*", " ", "\n".join(body_lines))
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", body) if x.strip()]
    events, lessons = [], []
    for i, s in enumerate(sentences):
        low = s.lower()
        if low.startswith(("lesson", "recommendation")) or "in future" in low:
            clean = re.sub(r"^((lessons?( learnt| learned)?|recommendations?)\s*[:\-]?\s*)+", "", s, flags=re.I).strip()
            lessons.append(clean)
            if events and not events[-1]["lesson"] and not low.startswith("lessons learnt"):
                events[-1]["lesson"] = clean  # a 'Lesson:' line right after an event belongs to it
            continue
        etype = classify(s)
        if not etype:
            continue
        depth = find_depth_m(s)
        # A follow-up sentence of the same problem ("Jarred down...", "Losses cured...") is context, not a new event.
        if depth is None and events and events[-1]["event_type"] == etype:
            continue
        ctx = [s] + [t for t in sentences[i + 1:i + 3] if find_depth_m(t) is None and (not classify(t) or classify(t) == etype)]
        context = " ".join(ctx)
        cause = _first(r"(?:cause[d]?\s*(?:by)?|due to|because of)\s*[:\-]?\s*([^.;]+)", context)
        lesson = _first(r"lesson\s*[:\-]\s*(.+?)(?:\.\s|\.$|$)", context)
        hours = find_hours(context)
        events.append({
            "event_type": etype, "depth_m": depth if depth is not None else formations.get(_formation_in(s) or ""),
            "formation": _formation_in(s) or fm_at(depth), "description": s[:400],
            "cause": cause, "action_taken": action_sentences(" ".join(ctx[1:])) or action_sentences(s), "lesson": lesson,
            "npt_hours": hours,
        })
    # merge duplicates (same type within 30 m)
    merged = []
    for e in events:
        dup = next((x for x in merged if x["event_type"] == e["event_type"] and e["depth_m"] and x["depth_m"]
                    and abs(x["depth_m"] - e["depth_m"]) < 30), None)
        if dup:
            dup["description"] += " " + e["description"]
            dup["action_taken"] = dup["action_taken"] or e["action_taken"]
            dup["cause"] = dup["cause"] or e["cause"]
        else:
            merged.append(e)
    return {
        "well_name": well.strip() if well else None,
        "field": _first(r"Field\s*[:\-]\s*([A-Za-z][A-Za-z ]{2,30}?)(?:\s{2,}|\n|,|;|$)", flat),
        "operator": _first(r"Operator\s*[:\-]\s*([A-Za-z][A-Za-z &\.\(\)]{2,60}?)(?:\s{2,}|\n|,|;|$)", flat),
        "report_date": _first(r"(?:Report date|Date)\s*[:\-]\s*([0-9]{1,4}[\-/\.][0-9]{1,2}[\-/\.][0-9]{1,4})", flat),
        "rig": _first(r"Rig\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9\- ]{1,30}?)(?:\s{2,}|\n|,|;|$)", flat),
        "lat": lat, "lon": lon, "total_depth_m": td_m,
        "formations": [{"name": n, "top_m": t} for n, t in tops_sorted],
        "events": merged,
        "lessons": lessons,
        "summary": f"Rule-based extraction found {len(merged)} event(s) and {len(tops_sorted)} formation top(s).",
    }


def extract_fields(text: str) -> tuple[dict, str, list[str]]:
    warnings = []
    if ANTHROPIC_API_KEY:
        try:
            return llm_extract(text), "llm", warnings
        except Exception as exc:
            warnings.append(f"LLM extraction failed ({type(exc).__name__}); used the rule-based extractor instead.")
    return rule_extract(text), "rules", warnings


# --------------------------------------------------------------------------- #
# 3. Save to the database
# --------------------------------------------------------------------------- #
def save_extraction(db: Session, doc: m.Document, data: dict) -> tuple[m.Well | None, int, list[str]]:
    from .geo import destination_point
    warnings = []
    name = (data.get("well_name") or "").strip()
    if not name:
        warnings.append("No well name found, so events were not linked to a well.")
        return None, 0, warnings
    well = db.query(m.Well).filter(m.Well.name.ilike(name)).first()
    tops = sorted(data.get("formations") or [], key=lambda t: t["top_m"])
    tops_full = [{"name": t["name"], "top_m": t["top_m"], "bottom_m": (tops[i + 1]["top_m"] if i + 1 < len(tops)
                                                                        else (data.get("total_depth_m") or t["top_m"] + 200))}
                 for i, t in enumerate(tops)]
    if not well:
        lat, lon = data.get("lat"), data.get("lon")
        field = None
        if data.get("field"):
            field = db.query(m.Field).filter(m.Field.name.ilike(data["field"].strip())).first()
        if lat is None or lon is None:
            if field:
                lat, lon = destination_point(field.lat, field.lon, 45, 1500)
                warnings.append(f"No coordinates in the report; the well was placed next to the {field.name} field centre.")
            else:
                warnings.append("No coordinates or known field in the report; the well was not added to the map.")
                return None, 0, warnings
        well = m.Well(name=name, field_id=field.id if field else None, operator=data.get("operator") or (field.operator if field else None),
                      lat=lat, lon=lon, status="unknown", outcome=None, td_md_m=data.get("total_depth_m"),
                      spud_year=int(data["report_date"][:4]) if (data.get("report_date") or "")[:4].isdigit() else None,
                      formation_tops=tops_full, source=f"Extracted from {doc.filename}")
        db.add(well)
        db.flush()
    elif tops_full and not well.formation_tops:
        well.formation_tops = tops_full
    n = 0
    for e in data.get("events") or []:
        if e.get("depth_m") is None:
            warnings.append(f"Skipped a {e['event_type']} event without a depth.")
            continue
        db.add(m.DrillingEvent(well_id=well.id, event_type=e["event_type"], depth_m=e["depth_m"], formation=e.get("formation"),
                               event_date=data.get("report_date"), severity=severity_from(e["event_type"], e.get("npt_hours")),
                               npt_hours=e.get("npt_hours"), description=e["description"], cause=e.get("cause"),
                               action_taken=e.get("action_taken"), lesson=e.get("lesson") or ((data.get("lessons") or [None])[0]),
                               source=f"Extracted from {doc.filename}", document_id=doc.id))
        n += 1
    return well, n, warnings

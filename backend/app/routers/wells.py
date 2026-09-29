"""Wells, offset-well intelligence, drilling events knowledge base and alerts."""
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models as m
from ..auth import current_user, require_roles
from ..db import get_db
from ..services import ml
from ..services.event_classifier import EVENT_LABELS
from ..services.geo import haversine_m
from ..services.tracking import hub
from ..services.well_monitor import alert_dict, analyse_well, persist_alerts

router = APIRouter(prefix="/api", tags=["wells"])
office = require_roles("admin", "engineer")


def well_summary(w: m.Well) -> dict:
    return {"id": w.id, "name": w.name, "field": w.field.name if w.field else None, "operator": w.operator,
            "lat": w.lat, "lon": w.lon, "status": w.status, "well_type": w.well_type, "spud_year": w.spud_year,
            "td_md_m": w.td_md_m, "is_active": w.is_active, "current_depth_m": w.current_depth_m, "planned_td_m": w.planned_td_m,
            "outcome": w.outcome, "cum_oil_bbl": w.cum_oil_bbl, "source": w.source}


def event_dict(e: m.DrillingEvent, well: m.Well | None = None, distance_m: float | None = None) -> dict:
    well = well or e.well
    return {"id": e.id, "well_id": e.well_id, "well_name": well.name if well else None, "event_type": e.event_type,
            "label": EVENT_LABELS.get(e.event_type, e.event_type), "depth_m": e.depth_m, "formation": e.formation,
            "event_date": e.event_date, "severity": e.severity, "npt_hours": e.npt_hours, "mud_weight_ppg": e.mud_weight_ppg,
            "description": e.description, "cause": e.cause, "action_taken": e.action_taken, "lesson": e.lesson,
            "source": e.source, "document_id": e.document_id,
            "distance_km": round(distance_m / 1000, 2) if distance_m is not None else None}


@router.get("/wells")
def list_wells(active: bool | None = None, _: m.User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(m.Well)
    if active is not None:
        q = q.filter(m.Well.is_active.is_(active))
    counts = Counter(e.well_id for e in db.query(m.DrillingEvent.well_id))
    return [{**well_summary(w), "event_count": counts.get(w.id, 0)} for w in q.order_by(m.Well.name).all()]


@router.get("/wells/{well_id}")
def get_well(well_id: int, _: m.User = Depends(current_user), db: Session = Depends(get_db)):
    w = db.get(m.Well, well_id)
    if not w:
        raise HTTPException(404, "Well not found.")
    events = db.query(m.DrillingEvent).filter(m.DrillingEvent.well_id == w.id).order_by(m.DrillingEvent.depth_m).all()
    logs = db.query(m.DepthLog).filter(m.DepthLog.well_id == w.id).order_by(m.DepthLog.depth_m).all()
    return {**well_summary(w), "formation_tops": w.formation_tops, "trajectory": w.trajectory, "casing_program": w.casing_program,
            "mud_program": w.mud_program, "cementing": w.cementing, "initial_rate_bpd": w.initial_rate_bpd,
            "events": [event_dict(e, w) for e in events],
            "depth_logs": [{"depth_m": l.depth_m, "formation": l.formation, "rop": l.rop_m_hr, "wob": l.wob_t, "torque": l.torque_knm,
                            "rpm": l.rpm, "mud_weight": l.mud_weight_ppg, "pore_pressure": l.pore_pressure_ppg, "gas": l.gas_pct}
                           for l in logs]}


@router.get("/wells/{well_id}/offsets")
def offsets(well_id: int, radius_km: float = Query(10, gt=0, le=60), lookahead_m: float = Query(150, ge=10, le=1000),
            _: m.User = Depends(current_user), db: Session = Depends(get_db)):
    w = db.get(m.Well, well_id)
    if not w:
        raise HTTPException(404, "Well not found.")
    result = analyse_well(db, w, radius_km * 1000, lookahead_m)
    result["well"] = {**well_summary(w), "formation_tops": w.formation_tops}
    return result


@router.get("/wells/{well_id}/correlation")
def correlation(well_id: int, radius_km: float = Query(10, gt=0, le=60), max_wells: int = Query(6, ge=1, le=12),
                _: m.User = Depends(current_user), db: Session = Depends(get_db)):
    """Formation tops, events and key drilling parameters for the well and its nearest offsets, side by side."""
    w = db.get(m.Well, well_id)
    if not w:
        raise HTTPException(404, "Well not found.")
    others = sorted([(o, haversine_m(w.lat, w.lon, o.lat, o.lon)) for o in db.query(m.Well) if o.id != w.id], key=lambda x: x[1])
    others = [(o, d) for o, d in others if d <= radius_km * 1000][:max_wells]
    cols = []
    for o, d in [(w, 0.0)] + others:
        evs = db.query(m.DrillingEvent).filter(m.DrillingEvent.well_id == o.id).all()
        logs = db.query(m.DepthLog).filter(m.DepthLog.well_id == o.id).order_by(m.DepthLog.depth_m).all()
        cols.append({"id": o.id, "name": o.name, "distance_km": round(d / 1000, 2), "is_active": o.is_active,
                     "current_depth_m": o.current_depth_m, "td_m": o.td_md_m or o.planned_td_m, "formation_tops": o.formation_tops,
                     "events": [{"id": e.id, "type": e.event_type, "depth_m": e.depth_m, "severity": e.severity, "formation": e.formation,
                                 "description": e.description} for e in evs],
                     "logs": [{"depth_m": l.depth_m, "mud_weight": l.mud_weight_ppg, "pore_pressure": l.pore_pressure_ppg,
                               "torque": l.torque_knm, "rop": l.rop_m_hr, "gas": l.gas_pct} for l in logs]})
    return {"well_id": w.id, "columns": cols}


@router.get("/wells/{well_id}/risk-profile")
def risk_profile(well_id: int, _: m.User = Depends(current_user), db: Session = Depends(get_db)):
    w = db.get(m.Well, well_id)
    if not w:
        raise HTTPException(404, "Well not found.")
    return ml.risk_profile(db, w)


class DepthIn(BaseModel):
    depth_m: float = Field(ge=0, le=8000)


@router.post("/wells/{well_id}/depth")
async def set_depth(well_id: int, body: DepthIn, _: m.User = Depends(office), db: Session = Depends(get_db)):
    """Manually move the bit (demo control). Runs the alert engine straight away."""
    w = db.get(m.Well, well_id)
    if not w or not w.is_active:
        raise HTTPException(400, "Only active wells have a live depth.")
    w.current_depth_m = body.depth_m
    db.commit()
    await hub.broadcast({"type": "depth", "well_id": w.id, "name": w.name, "depth_m": w.current_depth_m})
    analysis = analyse_well(db, w)
    for a in persist_alerts(db, w, analysis):
        await hub.broadcast({"type": "well_alert", **alert_dict(a, w.name)})
    return {"depth_m": w.current_depth_m, "alerts": analysis["alerts"]}


# --------------------------------------------------------------------------- #
# Knowledge base: search drilling events
# --------------------------------------------------------------------------- #
@router.get("/events")
def search_events(q: str | None = None, event_type: str | None = None, formation: str | None = None,
                  well_id: int | None = None, lat: float | None = None, lon: float | None = None,
                  radius_km: float | None = None, severity: str | None = None, limit: int = Query(200, le=1000),
                  _: m.User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(m.DrillingEvent).join(m.Well)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(m.DrillingEvent.description.ilike(like), m.DrillingEvent.cause.ilike(like),
                                 m.DrillingEvent.action_taken.ilike(like), m.DrillingEvent.lesson.ilike(like),
                                 m.DrillingEvent.formation.ilike(like), m.Well.name.ilike(like)))
    if event_type:
        query = query.filter(m.DrillingEvent.event_type.in_(event_type.split(",")))
    if formation:
        query = query.filter(m.DrillingEvent.formation == formation)
    if well_id:
        query = query.filter(m.DrillingEvent.well_id == well_id)
    if severity:
        query = query.filter(m.DrillingEvent.severity == severity)
    rows = query.all()
    out = []
    for e in rows:
        d = haversine_m(lat, lon, e.well.lat, e.well.lon) if lat is not None and lon is not None else None
        if radius_km and d is not None and d > radius_km * 1000:
            continue
        out.append(event_dict(e, e.well, d))
    out.sort(key=lambda x: (x["distance_km"] if x["distance_km"] is not None else 0, x["well_name"], x["depth_m"]))
    return {"total": len(out), "items": out[:limit],
            "facets": {"event_type": Counter(x["event_type"] for x in out), "formation": Counter(x["formation"] for x in out)}}


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #
@router.get("/alerts")
def list_alerts(well_id: int | None = None, open_only: bool = False, _: m.User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(m.WellAlert)
    if well_id:
        q = q.filter(m.WellAlert.well_id == well_id)
    if open_only:
        q = q.filter(m.WellAlert.acknowledged.is_(False))
    names = {w.id: w.name for w in db.query(m.Well.id, m.Well.name)}
    return [alert_dict(a, names.get(a.well_id)) for a in q.order_by(m.WellAlert.created_at.desc()).limit(200)]


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, _: m.User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(m.WellAlert, alert_id)
    if not a:
        raise HTTPException(404, "Not found.")
    a.acknowledged = True
    db.commit()
    return {"ok": True}

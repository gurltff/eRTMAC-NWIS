"""Runs the alert engine against the database and stores new alerts."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models as m
from .alerts import collect_offset_events, evaluate, events_index

DEFAULT_RADIUS_M = 10_000


def analyse_well(db: Session, well: m.Well, radius_m: float = DEFAULT_RADIUS_M, lookahead_m: float = 150.0) -> dict:
    wells = db.query(m.Well).all()
    idx = events_index(db.query(m.DrillingEvent).all())
    offset_events, offsets = collect_offset_events(well, wells, idx, radius_m)
    active = {"current_depth_m": well.current_depth_m or 0.0, "formation_tops": well.formation_tops or []}
    result = evaluate(active, offset_events, len(offsets), lookahead_m)
    result["offset_wells"] = [{"id": w.id, "name": w.name, "distance_km": round(d / 1000, 2), "status": w.status}
                              for w, d in sorted(offsets, key=lambda x: x[1])]
    result["radius_m"] = radius_m
    return result


def persist_alerts(db: Session, well: m.Well, analysis: dict) -> list[m.WellAlert]:
    """Store alerts we haven't raised before for this well. Returns the new ones."""
    existing = {a.alert_key for a in db.query(m.WellAlert).filter(m.WellAlert.well_id == well.id)}
    new = []
    for a in analysis["alerts"]:
        key = f"{well.id}:{a['key']}"
        if key in existing:
            continue
        row = m.WellAlert(well_id=well.id, alert_key=key, alert_type=a["event_type"], severity=a["severity"], title=a["title"],
                          message=a["message"], recommendation=a["recommendation"], formation=a["formation"],
                          expected_depth_m=a["expected_from_m"], depth_at_alert_m=well.current_depth_m, evidence=a["what_worked"])
        db.add(row)
        new.append(row)
    if new:
        db.commit()
    return new


def alert_dict(a: m.WellAlert, well_name: str | None = None) -> dict:
    return {"id": a.id, "well_id": a.well_id, "well_name": well_name, "alert_type": a.alert_type, "severity": a.severity,
            "title": a.title, "message": a.message, "recommendation": a.recommendation, "formation": a.formation,
            "expected_depth_m": a.expected_depth_m, "depth_at_alert_m": a.depth_at_alert_m, "evidence": a.evidence,
            "acknowledged": a.acknowledged, "created_at": a.created_at.isoformat() + "Z"}

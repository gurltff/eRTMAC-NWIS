"""In-memory copies of the static spatial layers + point lookups.

Zones, geology, fields and landslides change rarely, so they are loaded once
and refreshed on demand (e.g. after a document import adds a well).
"""
from __future__ import annotations

import json
import threading

from sqlalchemy.orm import Session

from .. import models as m
from ..config import SAMPLES_DIR
from .geo import distance_to_polygon_edge_m, distance_to_polyline_m, haversine_m, point_in_polygon

_lock = threading.Lock()
_cache: dict = {}


def refresh(db: Session) -> None:
    with _lock:
        _cache["zones"] = [dict(id=z.id, name=z.name, zone_type=z.zone_type, legal_to_drill=z.legal_to_drill,
                                authority=z.authority, licensee=z.licensee, polygon=z.polygon, source=z.source)
                           for z in db.query(m.Zone).all()]
        _cache["geology"] = [dict(id=g.id, name=g.name, lithology=g.lithology, age=g.age, rock_class=g.rock_class,
                                  strength=g.strength, petroleum_play=g.petroleum_play, polygon=g.polygon, source=g.source)
                             for g in db.query(m.GeologyUnit).order_by(m.GeologyUnit.id).all()]
        _cache["fields"] = [dict(id=f.id, name=f.name, operator=f.operator, lat=f.lat, lon=f.lon, porosity=f.porosity,
                                 water_saturation=f.water_saturation, formation_volume_factor=f.formation_volume_factor,
                                 net_pay_m=f.net_pay_m, recovery_factor=f.recovery_factor, reserves_mmbbl=f.reserves_mmbbl,
                                 discovery_year=f.discovery_year, past_operators=f.past_operators, source=f.source)
                            for f in db.query(m.Field).all()]
        _cache["landslides"] = [dict(lat=s.lat, lon=s.lon, event_date=s.event_date, trigger=s.trigger, size=s.size,
                                     place=s.place, source=s.source) for s in db.query(m.LandslideEvent).all()]
        _cache["wells"] = [dict(id=w.id, name=w.name, lat=w.lat, lon=w.lon, status=w.status, outcome=w.outcome,
                                operator=w.operator, spud_year=w.spud_year, td_md_m=w.td_md_m, is_active=w.is_active,
                                cum_oil_bbl=w.cum_oil_bbl, formation_tops=w.formation_tops, field_id=w.field_id)
                           for w in db.query(m.Well).all()]
        rivers = json.loads((SAMPLES_DIR / "rivers_sample.geojson").read_text())
        _cache["rivers"] = [dict(name=f["properties"]["name"], line=[[lat, lon] for lon, lat in f["geometry"]["coordinates"]])
                            for f in rivers["features"]]


def get(name: str, db: Session | None = None):
    if name not in _cache:
        if db is None:
            from ..db import SessionLocal
            with SessionLocal() as s:
                refresh(s)
        else:
            refresh(db)
    return _cache[name]


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #
def zones_at(lat: float, lon: float, db=None) -> list[dict]:
    return [z for z in get("zones", db) if point_in_polygon(lat, lon, z["polygon"])]


def illegal_zones(db=None) -> list[dict]:
    return [z for z in get("zones", db) if not z["legal_to_drill"]]


def nearest_illegal_zone(lat: float, lon: float, db=None) -> tuple[dict | None, float]:
    best, best_d = None, float("inf")
    for z in illegal_zones(db):
        d = 0.0 if point_in_polygon(lat, lon, z["polygon"]) else distance_to_polygon_edge_m(lat, lon, z["polygon"])
        if d < best_d:
            best, best_d = z, d
    return best, best_d


def legality(lat: float, lon: float, db=None) -> dict:
    """Legal status of a surface location.

    Protected area / reserved forest / wetland / restricted → ILLEGAL.
    Inside a licensed block and nothing illegal → LEGAL.
    Neither → NEEDS_LICENCE (not banned, but no one holds a licence here yet).
    """
    inside = zones_at(lat, lon, db)
    illegal = [z for z in inside if not z["legal_to_drill"]]
    blocks = [z for z in inside if z["zone_type"] == "licensed_block"]
    nearest, dist = nearest_illegal_zone(lat, lon, db)
    if illegal:
        z = illegal[0]
        verdict, text = "ILLEGAL", f"Inside {z['name']} ({z['zone_type'].replace('_', ' ')}). Drilling is not allowed here."
    elif blocks:
        verdict = "LEGAL"
        text = f"Inside licensed block {blocks[0]['name']} (licensee: {blocks[0]['licensee']})."
    else:
        verdict, text = "NEEDS_LICENCE", "Not in any protected or restricted area, but no licence block covers this spot yet."
    return {
        "verdict": verdict,
        "summary": text,
        "zones": [{k: z[k] for k in ("id", "name", "zone_type", "legal_to_drill", "authority", "licensee", "source")} for z in inside],
        "nearest_restricted": None if not nearest else {"name": nearest["name"], "zone_type": nearest["zone_type"], "distance_m": round(dist)},
    }


def geology_at(lat: float, lon: float, db=None) -> dict | None:
    for g in get("geology", db):
        if point_in_polygon(lat, lon, g["polygon"]):
            return {k: v for k, v in g.items() if k != "polygon"}
    return None


def nearest_fields(lat: float, lon: float, k: int = 3, db=None) -> list[tuple[dict, float]]:
    fs = [(f, haversine_m(lat, lon, f["lat"], f["lon"])) for f in get("fields", db)]
    return sorted(fs, key=lambda x: x[1])[:k]


def wells_within(lat: float, lon: float, radius_m: float, db=None, exclude_id: int | None = None) -> list[tuple[dict, float]]:
    out = []
    for w in get("wells", db):
        if w["id"] == exclude_id:
            continue
        d = haversine_m(lat, lon, w["lat"], w["lon"])
        if d <= radius_m:
            out.append((w, d))
    return sorted(out, key=lambda x: x[1])


def landslides_within(lat: float, lon: float, radius_m: float, db=None) -> list[tuple[dict, float]]:
    out = [(s, haversine_m(lat, lon, s["lat"], s["lon"])) for s in get("landslides", db)]
    return sorted([x for x in out if x[1] <= radius_m], key=lambda x: x[1])


def distance_to_river_m(lat: float, lon: float, db=None) -> tuple[str, float]:
    best = ("", float("inf"))
    for r in get("rivers", db):
        d = distance_to_polyline_m(lat, lon, r["line"])
        if d < best[1]:
            best = (r["name"], d)
    return best


def parcel_at(db: Session, lat: float, lon: float) -> m.LandParcel | None:
    return (db.query(m.LandParcel)
            .filter(m.LandParcel.min_lat <= lat, m.LandParcel.max_lat > lat,
                    m.LandParcel.min_lon <= lon, m.LandParcel.max_lon > lon).first())

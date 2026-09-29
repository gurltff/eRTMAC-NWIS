"""Soil at a tapped point: ISRIC SoilGrids v2.0 (free, no key) with a DB cache.

SoilGrids describes only the top ~2 m of soil. We use it for surface safety
(rig pad, access roads, subsidence and flood behaviour), NOT for oil potential,
which comes from the geology and formation data.

If SoilGrids can't be reached (offline demo, blocked network) an estimate from
the surface geology is returned and clearly marked as such.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from .. import models as m
from ..config import SOILGRIDS_ENABLED, SOILGRIDS_TIMEOUT_S

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPERTIES = ["clay", "sand", "silt", "phh2o", "bdod", "soc"]
DEPTHS = ["0-5cm", "30-60cm", "100-200cm"]
CACHE_DAYS = 90
_BACKOFF_S = 300
_down_until = 0.0  # after a failed call, skip SoilGrids for a few minutes so taps stay fast


def texture_class(sand: float, silt: float, clay: float) -> str:
    """Simplified USDA texture triangle."""
    if clay >= 40:
        return "Clay"
    if clay >= 27 and sand <= 45:
        return "Clay loam" if silt < 40 else "Silty clay loam"
    if clay >= 20 and sand > 45:
        return "Sandy clay loam"
    if silt >= 50:
        return "Silt loam"
    if sand >= 70:
        return "Loamy sand" if sand < 85 else "Sand"
    if sand >= 52:
        return "Sandy loam"
    return "Loam"


def surface_notes(clay: float, sand: float, bdod: float | None) -> list[str]:
    notes = []
    if clay >= 35:
        notes.append("High clay: ground turns soft and sticky when wet; build a compacted rig pad with crane mats.")
    if sand >= 60:
        notes.append("Sandy soil drains fast but can wash out; line the cellar and waste pits.")
    if bdod and bdod < 1.2:
        notes.append("Low bulk density: loose soil, check bearing capacity before moving the rig in.")
    if not notes:
        notes.append("Normal soil for a rig pad with standard compaction.")
    return notes


def _parse_soilgrids(data: dict) -> dict:
    out: dict = {}
    for layer in data.get("properties", {}).get("layers", []):
        factor = layer.get("unit_measure", {}).get("d_factor", 1) or 1
        for depth in layer.get("depths", []):
            mean = depth.get("values", {}).get("mean")
            if mean is not None:
                out.setdefault(depth["label"], {})[layer["name"]] = round(mean / factor, 2)
    return out


def _fetch(lat: float, lon: float) -> dict | None:
    global _down_until
    if time.monotonic() < _down_until:
        return None
    params = [("lon", lon), ("lat", lat), ("value", "mean")] + [("property", p) for p in PROPERTIES] + [("depth", d) for d in DEPTHS]
    try:
        r = httpx.get(SOILGRIDS_URL, params=params, timeout=SOILGRIDS_TIMEOUT_S)
        r.raise_for_status()
        layers = _parse_soilgrids(r.json())
        return layers or None
    except (httpx.HTTPError, ValueError):
        _down_until = time.monotonic() + _BACKOFF_S
        return None


def _estimate(lat: float, lon: float, rock_class: str | None) -> dict:
    """Offline estimate from the surface geology (sample)."""
    wiggle = math.sin(lat * 57) * math.cos(lon * 43)
    if rock_class == "alluvium":
        clay, sand, ph, bd = 22 + 6 * wiggle, 30 - 8 * wiggle, 5.3, 1.38
    elif rock_class in ("metamorphic", "igneous"):
        clay, sand, ph, bd = 28 + 4 * wiggle, 45 + 5 * wiggle, 5.0, 1.30
    else:
        clay, sand, ph, bd = 32 + 5 * wiggle, 36 + 6 * wiggle, 4.9, 1.28
    silt = max(5, 100 - clay - sand)
    layer = {"clay": round(clay, 1), "sand": round(sand, 1), "silt": round(silt, 1), "phh2o": ph, "bdod": bd, "soc": round(12 + 5 * wiggle, 1)}
    deeper = {k: (round(v * 1.1, 1) if k == "clay" else v) for k, v in layer.items()}
    return {"0-5cm": layer, "30-60cm": deeper, "100-200cm": deeper}


def soil_at(db: Session, lat: float, lon: float, rock_class: str | None = None) -> dict:
    key = f"{round(lat, 2):.2f},{round(lon, 2):.2f}"  # ~1 km cache cell
    cached = db.get(m.SoilCache, key)
    if cached and cached.fetched_at > datetime.utcnow() - timedelta(days=CACHE_DAYS):
        return {**cached.payload, "cached": True}

    layers = _fetch(lat, lon) if SOILGRIDS_ENABLED else None
    live = layers is not None
    if not live:
        layers = _estimate(lat, lon, rock_class)
    top = layers.get("0-5cm") or next(iter(layers.values()))
    clay, sand, silt = top.get("clay", 0), top.get("sand", 0), top.get("silt", 0)
    payload = {
        "source": "ISRIC SoilGrids v2.0 (live)" if live else "Estimate from surface geology (SoilGrids not reachable)",
        "is_live": live,
        "layers": layers,
        "texture": texture_class(sand, silt, clay),
        "ph": top.get("phh2o"),
        "notes": surface_notes(clay, sand, top.get("bdod")),
        "scope_note": "Soil data covers only the top 2 m. It is used for surface safety (rig pad, roads, flooding), "
                      "not for oil potential, which comes from geology and formation data.",
    }
    if live:  # only cache real answers so a later online request can fill the gap
        if cached:
            cached.payload, cached.fetched_at = payload, datetime.utcnow()
        else:
            db.add(m.SoilCache(key=key, payload=payload))
        db.commit()
    return {**payload, "cached": False}

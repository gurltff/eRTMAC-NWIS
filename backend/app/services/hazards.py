"""Hazard scores (0-100) for a surface location, each with plain reasons.

Simple weighted formulas; the weights are stated in the code so they can be
explained in the demo. Inputs come from terrain, geology, soil, rivers, the
landslide catalog and offset-well events.
"""
from __future__ import annotations

import math

from .spatial import distance_to_river_m, landslides_within, nearest_illegal_zone, wells_within


def _level(score: float) -> str:
    return "High" if score >= 60 else ("Medium" if score >= 35 else "Low")


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def landslide(terrain: dict, geology: dict | None, slides: list) -> dict:
    slope = _clamp(terrain["slope_deg"] / 30)
    relief = _clamp(terrain["local_relief_m"] / 300)
    weak = 1 - (geology["strength"] if geology else 0.5)
    rain = 0.8  # NE India monsoon: 2,000-4,000 mm/yr everywhere in the study area
    hist = _clamp(len(slides) / 3)
    score = 100 * (0.35 * slope + 0.15 * relief + 0.20 * weak + 0.10 * rain + 0.20 * hist)
    why = [f"Ground slope {terrain['slope_deg']:.1f}° and {terrain['local_relief_m']:.0f} m height change within 1 km",
           f"Rock/soil strength: {'weak' if weak > 0.6 else 'moderate' if weak > 0.35 else 'strong'} ({geology['name'] if geology else 'unknown'})",
           "Heavy monsoon rain (June–September)"]
    why.append(f"{len(slides)} recorded landslides within 10 km" if slides else "No recorded landslides within 10 km")
    return {"key": "landslide", "label": "Landslide", "score": round(score), "level": _level(score), "why": why}


def subsidence(soil: dict, geology: dict | None, lat: float, lon: float) -> dict:
    top = soil["layers"].get("0-5cm") or {}
    clay = _clamp((top.get("clay") or 25) / 45)
    alluvial = 1.0 if (geology and geology["rock_class"] == "alluvium") else 0.3
    producers = [w for w, _ in wells_within(lat, lon, 3000) if w["status"] in ("producing", "shut-in")]
    extraction = _clamp(len(producers) / 3)
    score = 100 * (0.35 * clay + 0.35 * alluvial + 0.30 * extraction)
    why = [f"Surface clay about {top.get('clay', '?')}%", "Soft alluvial ground" if alluvial == 1.0 else "Firm rock at surface",
           f"{len(producers)} producing wells within 3 km (fluid withdrawal)"]
    return {"key": "subsidence", "label": "Ground subsidence", "score": round(score), "level": _level(score), "why": why}


def flooding(lat: float, lon: float, terrain: dict) -> dict:
    river, dist_m = distance_to_river_m(lat, lon)
    valley_floor = 95 + 55 * (lon - 93.6) / 2.6  # Brahmaputra valley floor rises gently to the east
    height = max(0.0, terrain["elevation_m"] - valley_floor)
    near = math.exp(-(dist_m / 1000) / 8)
    low = _clamp(1 - height / 40)
    score = 100 * (0.55 * near + 0.45 * low)
    why = [f"{dist_m / 1000:.1f} km from the {river}", f"About {height:.0f} m above the valley floor",
           "Assam valley floods most monsoons (pad should be raised above the 100-year flood level)"]
    return {"key": "flooding", "label": "Flooding", "score": round(score), "level": _level(score), "why": why}


def offset_problem(key: str, label: str, types: tuple, lat: float, lon: float, events_by_well: dict, extra_why: str) -> dict:
    near = wells_within(lat, lon, 10_000)
    if not near:
        return {"key": key, "label": label, "score": 40, "level": "Medium",
                "why": ["No offset wells within 10 km – unknown, treat with care", extra_why]}
    n_events = sum(1 for w, _ in near for e in events_by_well.get(w["id"], []) if e["event_type"] in types)
    per_well = n_events / len(near)
    score = 100 * _clamp(0.15 + 0.45 * per_well)
    return {"key": key, "label": label, "score": round(score), "level": _level(score),
            "why": [f"{n_events} such events in {len(near)} offset wells within 10 km ({per_well:.1f} per well)", extra_why]}


def all_hazards(lat, lon, terrain, geology, soil, events_by_well) -> list[dict]:
    slides = landslides_within(lat, lon, 10_000)
    zone, zone_d = nearest_illegal_zone(lat, lon)
    eco = 100 if zone_d == 0 else 100 * _clamp(1 - zone_d / 5000)
    return [
        offset_problem("gas_kick", "Gas kick / overpressure", ("KICK",), lat, lon, events_by_well,
                       "Kopili Shale is overpressured across Upper Assam"),
        offset_problem("mud_loss", "Mud losses", ("MUD_LOSS",), lat, lon, events_by_well,
                       "Depleted Tipam sands and fractured Sylhet limestone take losses"),
        offset_problem("stuck_pipe", "Stuck pipe", ("STUCK_PIPE",), lat, lon, events_by_well,
                       "Girujan Clay swells and Barail coal seams cave in"),
        landslide(terrain, geology, slides),
        subsidence(soil, geology, lat, lon),
        flooding(lat, lon, terrain),
        {"key": "earthquake", "label": "Earthquake", "score": 75, "level": "High",
         "why": ["All of Assam is in Seismic Zone V (IS 1893), the highest in India",
                 "Design rig foundations and tanks for strong shaking"]},
        {"key": "ecology", "label": "Wildlife / eco-sensitive area", "score": round(eco), "level": _level(eco),
         "why": [f"Nearest protected or restricted area: {zone['name']} ({zone_d / 1000:.1f} km)" if zone else "None nearby",
                 "Blowouts near wetlands cause lasting damage (e.g. Baghjan 2020)"]},
    ]

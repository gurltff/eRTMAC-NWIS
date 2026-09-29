"""Subsurface model: a sample 'seismic structure map' and the stratigraphic column.

Upper Assam stratigraphy (top → bottom) with the drilling problems each unit is
known for. Formation names are real; thicknesses here are typical ranges used
to build sample wells.

The structure map gives the depth to the top of the Tipam Sandstone at any
point: a regional surface that dips to the SE (towards the Naga thrust), with
structural highs (anticlines) at the known fields and at a few undrilled leads.
It is SAMPLE data standing in for an interpreted seismic horizon.
"""
from __future__ import annotations

import math
from functools import lru_cache

from .geo import haversine_m
from .terrain import km_southeast_of_thrust

# name, typical thickness range (m), lithology, the known hazards
STRATIGRAPHY = [
    ("Alluvium", (150, 300), "Unconsolidated sand, gravel, clay", ["MUD_LOSS"]),
    ("Dhekiajuli", (700, 1100), "Sand, clay, pebble beds", ["MUD_LOSS", "NPT"]),
    ("Namsang", (300, 550), "Loose sandstone, clay, lignite", ["MUD_LOSS", "TORQUE_SPIKE"]),
    ("Girujan Clay", (400, 700), "Mottled sticky clay", ["STUCK_PIPE", "TORQUE_SPIKE"]),
    ("Tipam Sandstone", (350, 550), "Massive sandstone (main reservoir)", ["MUD_LOSS", "KICK", "CEMENTING"]),
    ("Barail", (400, 700), "Sandstone, shale and coal seams", ["STUCK_PIPE", "MUD_LOSS", "KICK"]),
    ("Kopili Shale", (150, 300), "Overpressured dark shale", ["KICK", "STUCK_PIPE"]),
    ("Sylhet Limestone", (150, 300), "Fractured limestone (Prang, Narpuh, Lakadong)", ["MUD_LOSS", "CEMENTING"]),
    ("Langpar", (60, 150), "Sandstone and shale", ["KICK", "CEMENTING"]),
    ("Basement", (300, 300), "Granite gneiss", ["TORQUE_SPIKE"]),
]
FORMATION_NAMES = [s[0] for s in STRATIGRAPHY]
FORMATION_INDEX = {n: i for i, n in enumerate(FORMATION_NAMES)}
MEAN_THICKNESS = {n: sum(r) / 2 for n, r, _, _ in STRATIGRAPHY}

# Undrilled structural leads (lat, lon, relief m, radius km) – sample interpretation.
HIDDEN_LEADS = [
    (27.245, 95.105, 230, 4.0),
    (27.070, 94.720, 210, 4.5),
    (27.470, 95.020, 200, 3.5),
    (26.690, 94.300, 190, 4.0),
    (27.135, 95.400, 170, 3.5),
    (27.545, 95.255, 160, 3.0),
]


@lru_cache(maxsize=1)
def _field_highs():
    from loaders.gem_loader import load_fields  # local import to avoid a cycle
    fields, _ = load_fields()
    return [(f["lat"], f["lon"], 150 + 25 * math.log1p(f["reserves_mmbbl"] or 1), 5.0) for f in fields]


def regional_tipam_depth(lat: float, lon: float) -> float:
    """Regional (no-structure) depth to the Tipam top, deepening towards the SE."""
    d = km_southeast_of_thrust(lat, lon)  # negative in the valley
    return 2450 + 15 * max(-40.0, d) + 30 * (95.5 - lon)


def structure_relief_m(lat: float, lon: float) -> float:
    """How much higher the Tipam top is than the regional surface (anticline relief)."""
    relief = 0.0
    for hlat, hlon, amp, radius_km in _field_highs() + HIDDEN_LEADS:
        dist_km = haversine_m(lat, lon, hlat, hlon) / 1000
        relief += amp * math.exp(-((dist_km / radius_km) ** 2))
    return relief


def tipam_depth_m(lat: float, lon: float) -> float:
    return regional_tipam_depth(lat, lon) - structure_relief_m(lat, lon)


def prognosed_column(lat: float, lon: float) -> list[dict]:
    """Expected formation tops at a location, hung from the structure map."""
    tipam_top = tipam_depth_m(lat, lon)
    idx = FORMATION_INDEX["Tipam Sandstone"]
    above = sum(MEAN_THICKNESS[n] for n in FORMATION_NAMES[:idx])
    scale = tipam_top / above  # stretch the shallow section to land on the mapped Tipam top
    tops, depth = [], 0.0
    for i, name in enumerate(FORMATION_NAMES):
        thick = MEAN_THICKNESS[name] * (scale if i < idx else 1.0)
        tops.append({"name": name, "top_m": round(depth, 1), "bottom_m": round(depth + thick, 1)})
        depth += thick
    return tops


def formation_at_depth(tops: list[dict], depth_m: float) -> str | None:
    for t in tops:
        if t["top_m"] <= depth_m < t["bottom_m"]:
            return t["name"]
    return tops[-1]["name"] if tops and depth_m >= tops[-1]["top_m"] else None


def formation_top(tops: list[dict], name: str) -> dict | None:
    return next((t for t in tops if t["name"] == name), None)


def hazards_for(formation: str) -> list[str]:
    for n, _, _, hz in STRATIGRAPHY:
        if n == formation:
            return hz
    return []


def lithology_for(formation: str) -> str | None:
    for n, _, lith, _ in STRATIGRAPHY:
        if n == formation:
            return lith
    return None

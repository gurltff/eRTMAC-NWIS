"""Fill the database with SAMPLE data for Upper Assam.

    cd backend && python -m seed.seed          # wipe and re-create everything

What comes from where:
  * Fields  – loaders/gem_loader.py (real GEM CSV if present, else the sample CSV)
  * Zones   – loaders/zones_loader.py (WDPA/OSM if present, else sample outlines) + generated licence blocks
  * Geology – loaders/geology_loader.py (Bhukosh shapefiles if present, else sample polygons)
  * Landslides – loaders/landslide_loader.py (NASA GLC if present, else sample)
  * Volve events – loaders/volve_ddr_loader.py, attached to a relocated 'VOLVE-F12 (relocated)' well
  * Wells, depth logs, drilling events, drillers, land parcels, candidate sites – generated here.
Everything generated is deterministic (fixed random seed) and labelled as sample data.
"""
from __future__ import annotations

import math
import random
import zlib
from datetime import datetime, timedelta

import numpy as np

from app import models as m
from app.auth import hash_password
from app.config import REGION
from app.db import Base, SessionLocal, engine
from app.services import geo
from app.services.subsurface import (FORMATION_NAMES, STRATIGRAPHY, formation_at_depth, hazards_for,
                                     structure_relief_m, tipam_depth_m)
from loaders.geology_loader import load_units
from loaders.gem_loader import load_fields
from loaders.landslide_loader import load_landslides
from loaders.volve_ddr_loader import VOLVE_TOPS, load_events as load_volve_events
from loaders.zones_loader import load_zones

rng = random.Random(42)
np_rng = np.random.default_rng(42)

FIELD_CODES = {
    "Digboi": "DGB", "Naharkatiya": "NHK", "Moran": "MRN", "Jorajan": "JRJ", "Hugrijan": "HGJ", "Baghjan": "BGN",
    "Makum": "MKM", "Kathaloni": "KTL", "Tengakhat": "TKT", "Chabua": "CBA", "Lakwa": "LKW", "Rudrasagar": "RDS",
    "Geleki": "GLK", "Borholla": "BRH", "Khoraghat": "KRG", "Amguri": "AMG", "Kharsang": "KSG", "Kumchai": "KMC",
}

# --------------------------------------------------------------------------- #
# Event text templates (cause / action / lesson) per event type
# --------------------------------------------------------------------------- #
TEMPLATES = {
    "MUD_LOSS": [
        dict(desc="Partial losses of {rate} bbl/hr while drilling at {depth} m in {fm}.",
             cause="Weak, partly depleted {fm} sands; ECD of {ecd} ppg above the fracture gradient.",
             action="Cut flow rate by 20 %, pumped {pill} bbl LCM pill (CaCO3 medium + fibre). Losses cured after {hrs} hrs.",
             lesson="Pre-treat the mud with 15-20 ppb LCM from 50 m above the {fm} top and keep ECD below {ecd_lim} ppg."),
        dict(desc="Total losses at {depth} m in {fm}, no returns at the shakers.",
             cause="Open natural fractures in {fm}.",
             action="Spotted cross-linked polymer plug, then a cement plug. Drilled ahead after {hrs} hrs.",
             lesson="Keep a loss-control plug mixed on location before drilling into {fm}; drill with minimum mud weight."),
        dict(desc="Seepage losses of {rate} bbl/hr during trip-in at {depth} m ({fm}).",
             cause="Surge pressure while running in too fast.",
             action="Reduced tripping speed to 60 s/stand and broke circulation in stages. Losses stopped.",
             lesson="Limit running speed through {fm}; break circulation slowly every 500 m."),
    ],
    "KICK": [
        dict(desc="Pit gain of {gain} bbl at {depth} m in {fm}; flow check positive.",
             cause="Pore pressure higher than prognosis ({pp} ppg against {mw} ppg mud).",
             action="Shut in the well (SIDPP {sidpp} psi). Circulated the kick out with the Driller's method and raised mud weight to {mw2} ppg.",
             lesson="Raise mud weight to {mw2} ppg before entering {fm}; watch gas and d-exponent from 100 m above the top."),
        dict(desc="Gas-cut mud and background gas up to {gas} % at {depth} m in {fm}.",
             cause="Gas-charged sand within {fm}.",
             action="Controlled drilling, circulated bottoms-up through the choke, weighted up by 0.3 ppg.",
             lesson="Plan a 0.3 ppg margin over pore pressure in {fm} and keep the degasser lined up."),
    ],
    "STUCK_PIPE": [
        dict(desc="Pipe stuck at {depth} m while pulling out in {fm}; overpull {op} t.",
             cause="Swelling clay closing the hole (reactive {fm}).",
             action="Jarred down {jars} times, spotted a pipe-freeing pill. Pipe free after {hrs} hrs.",
             lesson="Use KCl-polymer mud (7 % KCl) and back-ream every stand through {fm}."),
        dict(desc="Differential sticking at {depth} m after a 25 min connection in {fm}.",
             cause="Thick filter cake across a depleted permeable zone.",
             action="Worked the pipe and spotted a spotting fluid; freed after {hrs} hrs.",
             lesson="Keep the string moving during connections in {fm}; keep fluid loss below 5 ml."),
        dict(desc="Hole packed off at {depth} m in {fm}; lost circulation of the string.",
             cause="Coal and shale cavings settling around the BHA.",
             action="Pumped hi-vis sweeps, back-reamed out {hrs} hrs.",
             lesson="Raise mud weight by 0.2 ppg for shale stability and pump sweeps every stand in {fm}."),
    ],
    "TORQUE_SPIKE": [
        dict(desc="Erratic torque up to {tq} kNm at {depth} m in {fm}.",
             cause="Bit balling in sticky clay.",
             action="Reduced RPM to {rpm} and WOB to {wob} t, pumped a detergent sweep.",
             lesson="Use a PDC bit with anti-balling nozzles and control ROP in {fm}."),
        dict(desc="Stick-slip and torque spikes to {tq} kNm at {depth} m ({fm}).",
             cause="Hard stringers inside {fm}.",
             action="Changed drilling parameters and added lubricant (2 %).",
             lesson="Run a torsional-vibration damper and keep RPM in the 90-120 band through {fm}."),
    ],
    "CEMENTING": [
        dict(desc="Lost returns during cement displacement on the {csg} casing at {depth} m.",
             cause="Cement column heavier than the {fm} fracture gradient.",
             action="Top of cement found 180 m below plan by CBL; remedial squeeze with {sq} bbl slurry.",
             lesson="Use a lightweight lead slurry (13.0 ppg) across {fm}."),
        dict(desc="Poor cement bond across {fm} on the {csg} casing (CBL/VDL).",
             cause="Mud channelling from poor centralisation.",
             action="Squeezed {sq} bbl through perforations; re-logged OK.",
             lesson="One rigid centraliser per joint across {fm} and a 20 bbl spacer at turbulent flow."),
        dict(desc="Sustained casing pressure after the {csg} cement job.",
             cause="Gas migration through setting cement from {fm}.",
             action="Bled off and monitored; remedial squeeze planned.",
             lesson="Use a gas-tight (right-angle-set) slurry opposite {fm} gas sands."),
    ],
    "FISHING": [
        dict(desc="Twist-off at {depth} m in {fm}; fish left in hole.",
             cause="Fatigue crack in a drill-pipe tool joint.",
             action="Ran overshot, recovered the fish after {hrs} hrs.",
             lesson="Inspect drill pipe (DS-1 Cat 3) before long hard-rock sections."),
    ],
    "NPT": [
        dict(desc="Rig repair: mud pump liner washout at {depth} m ({hrs} hrs NPT).",
             cause="Worn liner and swab.",
             action="Replaced liner and swab.",
             lesson="Keep spare liners on location and change swabs every 150 pump hours."),
        dict(desc="Waiting on road access after monsoon flooding ({hrs} hrs NPT) at {depth} m.",
             cause="Access road under water.",
             action="Circulated and conditioned mud while waiting.",
             lesson="Stock two weeks of mud chemicals and diesel before the monsoon."),
    ],
}

CASING = [("20\"", 0.02), ("13 3/8\"", 0.25), ("9 5/8\"", None), ("7\"", 1.0)]

FIRST = ["Rituraj", "Ankur", "Pranjal", "Dipankar", "Bhaskar", "Nilotpal", "Jintu", "Manash", "Himangshu", "Pallavi",
         "Rupjyoti", "Bitupan", "Madhurjya", "Trishna", "Kaustav", "Anindita", "Parag", "Mridul"]
LAST = ["Bora", "Gogoi", "Saikia", "Das", "Hazarika", "Phukan", "Borah", "Dutta", "Kalita", "Chetia", "Konwar", "Baruah"]
VILLAGE_SYL = ["Bor", "Hati", "Kho", "Dihing", "Nam", "Kakoti", "Siju", "Lahowal", "Rajgarh", "Tengap", "Jaypur",
               "Dolong", "Moukhowa", "Khanikar", "Tinkhong", "Duliajan", "Sonari", "Nahar"]


def jitter(lo, hi):
    return rng.uniform(lo, hi)


def fmt(template: str, **kw) -> str:
    return template.format(**kw)


# --------------------------------------------------------------------------- #
# Wells
# --------------------------------------------------------------------------- #
def make_formation_tops(lat, lon, rng_local):
    """Formation tops hung from the structure map, with a little well-to-well noise."""
    tipam_top = tipam_depth_m(lat, lon) + rng_local.uniform(-25, 25)
    idx = FORMATION_NAMES.index("Tipam Sandstone")
    shallow = [rng_local.uniform(*STRATIGRAPHY[i][1]) for i in range(idx)]
    scale = tipam_top / sum(shallow)
    tops, depth = [], 0.0
    for i, (name, (lo, hi), _, _) in enumerate(STRATIGRAPHY):
        thick = shallow[i] * scale if i < idx else rng_local.uniform(lo, hi)
        tops.append({"name": name, "top_m": round(depth, 1), "bottom_m": round(depth + thick, 1)})
        depth += thick
    return tops


def true_success_probability(lat, lon, play_prior):
    """Hidden 'truth' used to decide sample outcomes. The ML model never sees this."""
    relief = structure_relief_m(lat, lon)
    z = -2.2 + 0.016 * relief + 2.0 * (play_prior - 0.5)
    return 1 / (1 + math.exp(-z))


def geology_play_at(units, lat, lon):
    for u in units:
        if geo.point_in_polygon(lat, lon, u["polygon"]):
            return u["petroleum_play"]
    return 0.5


def mud_weight_for(fm):
    return {"Alluvium": 8.9, "Dhekiajuli": 9.2, "Namsang": 9.4, "Girujan Clay": 9.8, "Tipam Sandstone": 10.0,
            "Barail": 10.4, "Kopili Shale": 11.6, "Sylhet Limestone": 10.8, "Langpar": 11.0, "Basement": 10.8}[fm]


def pore_pressure_for(fm, rel):
    base = {"Alluvium": 8.6, "Dhekiajuli": 8.7, "Namsang": 8.8, "Girujan Clay": 9.0, "Tipam Sandstone": 9.3,
            "Barail": 9.8, "Kopili Shale": 11.2, "Sylhet Limestone": 10.2, "Langpar": 10.4, "Basement": 9.5}[fm]
    return base + 0.4 * rel


def build_well(name, field, lat, lon, status, outcome, spud_year, td_target_fm, rng_local, active=False, units=None):
    tops = make_formation_tops(lat, lon, rng_local)
    target = next(t for t in tops if t["name"] == td_target_fm)
    td = round(target["bottom_m"] - rng_local.uniform(10, 60) if td_target_fm != "Basement" else target["top_m"] + 80, 1)
    directional = rng_local.random() < 0.35
    traj = None
    if directional:
        traj = {"kop_m": round(rng_local.uniform(600, 1200)), "build_rate_deg_per_30m": round(rng_local.uniform(1.5, 3.0), 1),
                "hold_inc_deg": round(rng_local.uniform(18, 40)), "azimuth_deg": round(rng_local.uniform(0, 359))}
        stations = geo.build_and_hold_plan(traj["kop_m"], traj["build_rate_deg_per_30m"], traj["hold_inc_deg"], td, traj["azimuth_deg"])
        bhl = geo.bottom_hole_location(lat, lon, stations)
        traj.update(bhl_lat=bhl["lat"], bhl_lon=bhl["lon"], td_tvd_m=bhl["tvd_m"], displacement_m=bhl["horizontal_displacement_m"])
    tipam = next(t for t in tops if t["name"] == "Tipam Sandstone")
    casing = [
        {"size": "20\"", "shoe_m": 60, "purpose": "Conductor"},
        {"size": "13 3/8\"", "shoe_m": round(tops[1]["bottom_m"] * 0.6), "purpose": "Surface"},
        {"size": "9 5/8\"", "shoe_m": round(tipam["top_m"] - 20), "purpose": "Intermediate (above Tipam)"},
        {"size": "7\"", "shoe_m": td, "purpose": "Production"},
    ]
    mud = [
        {"from_m": 0, "to_m": casing[1]["shoe_m"], "type": "Spud mud (WBM)", "weight_ppg": 9.0},
        {"from_m": casing[1]["shoe_m"], "to_m": casing[2]["shoe_m"], "type": "KCl-polymer WBM", "weight_ppg": 9.6},
        {"from_m": casing[2]["shoe_m"], "to_m": td, "type": "KCl-PHPA WBM", "weight_ppg": 10.4 if td_target_fm in ("Tipam Sandstone", "Barail") else 11.8},
    ]
    cement = [
        {"casing": c["size"], "lead_ppg": 13.2 if i > 1 else 14.5, "tail_ppg": 15.8, "toc_m": 0 if i < 2 else round(c["shoe_m"] * 0.55),
         "result": "OK"} for i, c in enumerate(casing)
    ]
    initial_rate = cum = None
    if outcome == "success":
        initial_rate = round(rng_local.uniform(180, 650))
        cum = round(initial_rate * 365 * rng_local.uniform(1.5, 12) * (0.6 if status == "abandoned" else 1))
    elif outcome == "marginal":
        initial_rate = round(rng_local.uniform(30, 120))
        cum = round(initial_rate * 365 * rng_local.uniform(0.5, 3))
    return m.Well(
        name=name, field_id=field.id if field else None, operator=field.operator if field else "Oil India Limited",
        lat=lat, lon=lon, status=status, well_type="directional" if directional else "vertical",
        spud_year=spud_year, td_md_m=None if active else td, td_tvd_m=None if active else (traj["td_tvd_m"] if traj else td),
        is_active=active, planned_td_m=td if active else None, outcome=outcome, cum_oil_bbl=cum, initial_rate_bpd=initial_rate,
        formation_tops=tops, trajectory=traj, casing_program=casing, mud_program=mud, cementing=cement,
        source="Sample data (generated)")


# Per-formation event rate per well: how likely each problem type is in that unit.
EVENT_RATES = {
    "Alluvium": {"MUD_LOSS": 0.10, "NPT": 0.05},
    "Dhekiajuli": {"MUD_LOSS": 0.18, "NPT": 0.10, "TORQUE_SPIKE": 0.05},
    "Namsang": {"MUD_LOSS": 0.22, "TORQUE_SPIKE": 0.10, "STUCK_PIPE": 0.06},
    "Girujan Clay": {"STUCK_PIPE": 0.50, "TORQUE_SPIKE": 0.45, "NPT": 0.10},
    "Tipam Sandstone": {"MUD_LOSS": 0.45, "KICK": 0.18, "CEMENTING": 0.30, "STUCK_PIPE": 0.10},
    "Barail": {"STUCK_PIPE": 0.40, "MUD_LOSS": 0.25, "KICK": 0.22, "TORQUE_SPIKE": 0.2, "FISHING": 0.06},
    "Kopili Shale": {"KICK": 0.55, "STUCK_PIPE": 0.25, "CEMENTING": 0.15},
    "Sylhet Limestone": {"MUD_LOSS": 0.60, "CEMENTING": 0.30},
    "Langpar": {"KICK": 0.30, "CEMENTING": 0.2},
    "Basement": {"TORQUE_SPIKE": 0.5, "FISHING": 0.15},
}


def make_events(well: m.Well, rng_local, drilled_to: float, spud_year: int, local_bias: dict):
    events = []
    base_date = datetime(spud_year, rng_local.randint(1, 10), rng_local.randint(1, 28))
    for t in well.formation_tops:
        if t["top_m"] >= drilled_to:
            break
        bottom = min(t["bottom_m"], drilled_to)
        for etype, rate in EVENT_RATES.get(t["name"], {}).items():
            p = min(0.95, rate * local_bias.get(etype, 1.0))
            n = (1 if rng_local.random() < p else 0) + (1 if rng_local.random() < p * 0.25 else 0)
            for _ in range(n):
                # Problems cluster in the upper third of a formation (first contact with it).
                depth = round(t["top_m"] + (bottom - t["top_m"]) * min(1, rng_local.betavariate(1.4, 3.0)), 1)
                tmpl = rng_local.choice(TEMPLATES[etype])
                mw = mud_weight_for(t["name"])
                hrs = round(rng_local.uniform(2, 30) if etype in ("STUCK_PIPE", "FISHING", "MUD_LOSS") else rng_local.uniform(1, 12), 1)
                kw = dict(depth=depth, fm=t["name"], rate=rng_local.randint(8, 60), ecd=round(mw + 0.6, 1), ecd_lim=round(mw + 0.3, 1),
                          pill=rng_local.randint(30, 80), hrs=hrs, gain=round(rng_local.uniform(4, 25), 1), pp=round(mw + 0.4, 1),
                          mw=mw, mw2=round(mw + 0.6, 1), sidpp=rng_local.randint(150, 900), gas=rng_local.randint(8, 35),
                          op=rng_local.randint(20, 60), jars=rng_local.randint(10, 60), tq=rng_local.randint(18, 38),
                          rpm=rng_local.choice([80, 90, 100, 110]), wob=rng_local.randint(6, 12), sq=rng_local.randint(20, 60),
                          csg="9 5/8\"" if t["name"] in ("Tipam Sandstone", "Girujan Clay") else "7\"")
                sev = "high" if etype == "KICK" and kw["gain"] > 12 or hrs > 18 else ("medium" if hrs > 6 or etype in ("KICK", "STUCK_PIPE") else "low")
                events.append(m.DrillingEvent(
                    well_id=well.id, event_type=etype, depth_m=depth, formation=t["name"],
                    event_date=(base_date + timedelta(days=int(depth / 90))).strftime("%Y-%m-%d"), severity=sev,
                    npt_hours=hrs, mud_weight_ppg=mw, description=fmt(tmpl["desc"], **kw), cause=fmt(tmpl["cause"], **kw),
                    action_taken=fmt(tmpl["action"], **kw), lesson=fmt(tmpl["lesson"], **kw),
                    source=rng_local.choice(["Sample daily drilling report", "Sample daily drilling report", "Sample well completion report"])))
    return events


def make_depth_logs(well: m.Well, rng_local, drilled_to: float, events):
    rows = []
    rel = rng_local.uniform(-0.3, 0.3)
    torque_events = [e.depth_m for e in events if e.event_type in ("TORQUE_SPIKE", "STUCK_PIPE")]
    kick_events = [e.depth_m for e in events if e.event_type == "KICK"]
    rop_base = {"Alluvium": 40, "Dhekiajuli": 30, "Namsang": 26, "Girujan Clay": 11, "Tipam Sandstone": 22, "Barail": 14,
                "Kopili Shale": 9, "Sylhet Limestone": 6, "Langpar": 10, "Basement": 3}
    for depth in np.arange(50, drilled_to + 1, 50):
        fm = formation_at_depth(well.formation_tops, depth) or "Basement"
        spike = any(abs(depth - d) < 60 for d in torque_events)
        kick = any(abs(depth - d) < 60 for d in kick_events)
        rows.append(m.DepthLog(
            well_id=well.id, depth_m=float(depth), formation=fm,
            rop_m_hr=round(max(1.0, rop_base[fm] * rng_local.uniform(0.75, 1.25)), 1),
            wob_t=round(rng_local.uniform(8, 18) + depth / 800, 1),
            torque_knm=round(4 + depth / 250 + rng_local.uniform(-1, 1) + (rng_local.uniform(8, 14) if spike else 0), 1),
            rpm=round(rng_local.uniform(90, 140)),
            mud_weight_ppg=round(mud_weight_for(fm) + rel * 0.3, 2),
            pore_pressure_ppg=round(pore_pressure_for(fm, rel) + (0.6 if kick else 0), 2),
            gas_pct=round(rng_local.uniform(0.2, 1.5) + (rng_local.uniform(3, 12) if kick else 0) +
                          (rng_local.uniform(0.5, 3) if fm in ("Tipam Sandstone", "Barail") else 0), 2),
        ))
    return rows


# --------------------------------------------------------------------------- #
# Land parcels
# --------------------------------------------------------------------------- #
PARCEL_STEP = 0.03  # degrees (~3.3 km)


def make_parcels(zones, fields):
    parcels = []
    illegal = [z for z in zones if not z["legal_to_drill"]]
    lat_cells = int(round((REGION["max_lat"] - REGION["min_lat"]) / PARCEL_STEP))
    lon_cells = int(round((REGION["max_lon"] - REGION["min_lon"]) / PARCEL_STEP))
    for i in range(lat_cells):
        for j in range(lon_cells):
            lat0 = REGION["min_lat"] + i * PARCEL_STEP
            lon0 = REGION["min_lon"] + j * PARCEL_STEP
            clat, clon = lat0 + PARCEL_STEP / 2, lon0 + PARCEL_STEP / 2
            village = f"{rng.choice(VILLAGE_SYL)}{rng.choice(['gaon', 'pur', 'bari', 'guri', 'pather', ' Grant'])}"
            code = f"AS-{i:02d}{j:03d}"
            in_zone = next((z for z in illegal if geo.point_in_polygon(clat, clon, z["polygon"])), None)
            near_field = min((geo.haversine_m(clat, clon, f.lat, f.lon) for f in fields), default=1e9)
            history = []
            r = rng.random()
            if in_zone:
                status, holder = "government", f"{in_zone.get('authority') or 'Government of Assam'}"
                history = [{"from": 1950 + rng.randint(0, 40), "to": None, "holder": holder, "type": "government reserve"}]
            elif near_field < 6000 and r < 0.7:
                field = min(fields, key=lambda f: geo.haversine_m(clat, clon, f.lat, f.lon))
                status, holder = "leased", f"{field.operator} (mining lease)"
                start = max(field.discovery_year or 1960, 1960) + rng.randint(0, 15)
                prev = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                history = [{"from": start - rng.randint(10, 30), "to": start, "holder": prev, "type": "private owner"},
                           {"from": start, "to": None, "holder": holder, "type": "lease (PML)"}]
                if field.past_operators:
                    history.insert(1, {"from": start - 5, "to": start, "holder": field.past_operators[0], "type": "earlier lease"})
            elif r < 0.25:
                status, holder = "owned", f"{rng.choice(VILLAGE_SYL)}{rng.choice(['jan', 'bari', 'pukhuri'])} Tea Estate"
                history = [{"from": 1880 + rng.randint(0, 60), "to": None, "holder": holder, "type": "tea estate grant"}]
            elif r < 0.55:
                status, holder = "owned", f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                prev = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                y = 1960 + rng.randint(0, 50)
                history = [{"from": y - rng.randint(15, 40), "to": y, "holder": prev, "type": "private owner"},
                           {"from": y, "to": None, "holder": holder, "type": "private owner (sale deed)"}]
            elif r < 0.72:
                status, holder = "government", "Revenue Department, Govt of Assam"
                history = [{"from": 1950, "to": None, "holder": holder, "type": "khas (government) land"}]
            elif r < 0.82:
                status, holder = "leased", f"{rng.choice(FIRST)} {rng.choice(LAST)} (agricultural lease)"
                history = [{"from": 1990 + rng.randint(0, 25), "to": None, "holder": holder, "type": "agricultural lease"}]
            else:
                status, holder = "unclaimed", None
                if rng.random() < 0.5:
                    y = 1965 + rng.randint(0, 30)
                    history = [{"from": y, "to": y + rng.randint(5, 20), "holder": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                                "type": "former lease, lapsed"}]
            parcels.append(m.LandParcel(code=code, village=village, min_lat=lat0, max_lat=lat0 + PARCEL_STEP, min_lon=lon0,
                                        max_lon=lon0 + PARCEL_STEP, status=status, holder=holder, history=history))
    return parcels


# --------------------------------------------------------------------------- #
# Drillers
# --------------------------------------------------------------------------- #
DRILLERS = [
    dict(email="driller@nwis.demo", password="Driller@123", name="Rituraj Baruah", status="approved",
         company="Brahmaputra Drilling Services Pvt Ltd", reg="U11100AS2012PTC0001", phone="+91 94350 00001",
         designation="Rig Superintendent", exp=14, site=(27.5750, 95.3460), area="Baghjan West – AA-OSHP-2024/1 (sample)",
         radius=3000, plan=dict(md=3900, kop=900, build=2.0, inc=30, azi=40),
         rig=dict(name="BDS Rig-3", rig_type="Land rig (1500 HP, AC-VFD)", max_depth_m=5000, max_horizontal_reach_m=1500,
                  hook_load_t=340, power_hp=1500, year_built=2014),
         docs=[("licence", "approved"), ("permit", "approved"), ("id_proof", "approved"), ("environmental_clearance", "approved"), ("insurance", "pending")]),
    dict(email="driller2@nwis.demo", password="Driller@123", name="Pallavi Hazarika", status="approved",
         company="Upper Assam Rig Contractors LLP", reg="AAB-2291", phone="+91 94350 00002",
         designation="Drilling Manager", exp=11, site=(27.1900, 95.0300), area="Moran South (sample)",
         radius=4000, plan=dict(md=3600, kop=1000, build=2.5, inc=35, azi=100),
         rig=dict(name="UARC Rig-7", rig_type="Mobile land rig (2000 HP)", max_depth_m=6000, max_horizontal_reach_m=2500,
                  hook_load_t=450, power_hp=2000, year_built=2018),
         docs=[("licence", "approved"), ("permit", "approved"), ("id_proof", "approved"), ("environmental_clearance", "approved")]),
    dict(email="driller3@nwis.demo", password="Driller@123", name="Kaustav Saikia", status="submitted",
         company="Dihing Energy Services", reg="U11200AS2019PTC0144", phone="+91 94350 00003",
         designation="Head of Drilling", exp=8, site=(26.9600, 94.8000), area="Lakwa East (sample)",
         radius=2500, plan=dict(md=3400, kop=800, build=2.0, inc=25, azi=200),
         rig=dict(name="DES Workover-2", rig_type="Workover rig (750 HP)", max_depth_m=3500, max_horizontal_reach_m=900,
                  hook_load_t=180, power_hp=750, year_built=2011),
         docs=[("licence", "pending"), ("permit", "pending"), ("id_proof", "approved"), ("environmental_clearance", "rejected")]),
    dict(email="driller4@nwis.demo", password="Driller@123", name="Anindita Kalita", status="draft",
         company=None, reg=None, phone=None, designation=None, exp=None, site=None, area=None, radius=None, plan=None, rig=None, docs=[]),
]

CANDIDATES = [
    ("Proposed NHK-L1", 27.310, 95.300, "Tipam Sandstone", 3000, "Naharkatiya planning team"),
    ("Proposed MRN-L4", 27.205, 94.955, "Barail", 3500, "Moran planning team"),
    ("Proposed BGN-L2", 27.560, 95.420, "Barail", 3900, "Baghjan planning team"),
    ("Proposed DP-X1", 27.265, 95.700, "Tipam Sandstone", 2900, "Exploration (inside national park – for test)"),
    ("Proposed LKW-L9", 26.975, 94.890, "Tipam Sandstone", 3100, "Lakwa planning team"),
    ("Proposed GLK-L3", 26.845, 94.760, "Barail", 3300, "Geleki planning team"),
    ("Proposed WLD-A", 27.245, 95.110, "Tipam Sandstone", 3000, "Exploration"),
    ("Proposed WLD-B", 27.070, 94.720, "Barail", 3400, "Exploration"),
    ("Proposed KTL-L5", 27.350, 95.180, "Tipam Sandstone", 3000, "Kathaloni planning team"),
    ("Proposed MG-X2", 27.596, 95.360, "Barail", 3800, "Exploration (wetland – for test)"),
    ("Proposed RDS-L6", 26.940, 94.640, "Tipam Sandstone", 3000, "Rudrasagar planning team"),
    ("Proposed NB-X3", 27.800, 94.700, "Tipam Sandstone", 2600, "Exploration (north bank)"),
]


def seed():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()

    # --- users
    admin = m.User(email="admin@nwis.demo", password_hash=hash_password("Admin@123"), full_name="Meghali Dutta (Admin)", role="admin")
    eng = m.User(email="engineer@nwis.demo", password_hash=hash_password("Engineer@123"), full_name="Ankur Gogoi", role="engineer")
    db.add_all([admin, eng])

    # --- fields
    fields_raw, fields_label = load_fields()
    fields = []
    for f in fields_raw:
        fields.append(m.Field(**f))
    db.add_all(fields)
    db.flush()

    # --- geology, zones, landslides
    units, geology_label = load_units()
    db.add_all([m.GeologyUnit(**u) for u in units])
    zones_raw, zones_label = load_zones()
    for f in fields:
        # Petroleum Mining Lease around each field (sample outline).
        zones_raw.append(dict(name=f"{f.name} PML", zone_type="licensed_block", legal_to_drill=True, authority="MoPNG / DGH",
                              licensee=f.operator, polygon=[[f.lat - 0.07, f.lon - 0.08], [f.lat - 0.07, f.lon + 0.08],
                                                            [f.lat + 0.07, f.lon + 0.08], [f.lat + 0.07, f.lon - 0.08]],
                              source="Sample licence block"))
    zones_raw.append(dict(name="AA-OSHP-2024/1 (Baghjan West)", zone_type="licensed_block", legal_to_drill=True, authority="DGH (OALP round, sample)",
                          licensee="Oil India Limited – contractor: Brahmaputra Drilling Services", source="Sample licence block",
                          polygon=[[27.53, 95.28], [27.53, 95.40], [27.62, 95.40], [27.62, 95.28]]))
    zones_raw.append(dict(name="AA-OSHP-2023/4 (Moran South)", zone_type="licensed_block", legal_to_drill=True, authority="DGH (OALP round, sample)",
                          licensee="Oil India Limited – contractor: Upper Assam Rig Contractors", source="Sample licence block",
                          polygon=[[27.14, 94.97], [27.14, 95.09], [27.24, 95.09], [27.24, 94.97]]))
    for z in zones_raw:
        db.add(m.Zone(name=z["name"], zone_type=z["zone_type"], legal_to_drill=z["legal_to_drill"], authority=z.get("authority"),
                      licensee=z.get("licensee"), polygon=z["polygon"], source=z.get("source", "Sample")))
    slides, slides_label = load_landslides()
    db.add_all([m.LandslideEvent(**s) for s in slides])
    db.flush()

    # --- wells
    wells, all_events = [], []
    used_names = set()
    for f in fields:
        code = FIELD_CODES.get(f.name, f.name[:3].upper())
        n_wells = 3 if (f.reserves_mmbbl or 0) > 25 else 2
        for k in range(n_wells):
            r_local = random.Random(zlib.crc32(f"{f.name}-{k}".encode()))
            bearing, dist = r_local.uniform(0, 360), r_local.uniform(600, 3800)
            lat, lon = geo.destination_point(f.lat, f.lon, bearing, dist)
            play = geology_play_at(units, lat, lon)
            p = true_success_probability(lat, lon, play)
            u = r_local.random()
            outcome = "success" if u < p else ("marginal" if u < p + 0.12 else "dry")
            spud = r_local.randint(max(f.discovery_year or 1960, 1962), 2021)
            status = {"success": r_local.choice(["producing", "producing", "producing", "shut-in", "abandoned"]),
                      "marginal": r_local.choice(["suspended", "abandoned", "producing"]), "dry": "abandoned"}[outcome]
            target = r_local.choice(["Tipam Sandstone", "Tipam Sandstone", "Barail", "Barail", "Sylhet Limestone"])
            num = r_local.randint(20, 480)
            name = f"{code}-{num}"
            while name in used_names:
                num += 1
                name = f"{code}-{num}"
            used_names.add(name)
            w = build_well(name, f, lat, lon, status, outcome, spud, target, r_local, units=units)
            wells.append((w, r_local, spud))
    # exploratory wells away from fields
    explo = [(27.02, 95.00), (27.62, 94.95), (26.72, 94.10), (27.40, 94.60), (26.60, 94.50), (26.95, 94.35)]
    for k, (lat, lon) in enumerate(explo):
        r_local = random.Random(1000 + k)
        play = geology_play_at(units, lat, lon)
        p = true_success_probability(lat, lon, play)
        outcome = "success" if r_local.random() < p else "dry"
        name = f"EXP-{k + 1:02d}"
        used_names.add(name)
        w = build_well(name, None, lat, lon, "producing" if outcome == "success" else "abandoned", outcome,
                       r_local.randint(1970, 2018), "Barail", r_local, units=units)
        w.operator = "Oil India Limited" if lon > 94.9 else "Oil and Natural Gas Corporation"
        wells.append((w, r_local, w.spud_year))

    # active wells being drilled now (the ones the alert engine watches)
    field_by_name = {f.name: f for f in fields}
    active_specs = [("NHK-A01", "Naharkatiya", 1.2, 2400, 1830.0), ("BGN-A07", "Baghjan", -1.3, 2100, 2350.0), ("LKW-A12", "Lakwa", 0.4, 1800, 1460.0)]
    for name, fname, bearing_rad, dist, cur_depth in active_specs:
        f = field_by_name[fname]
        lat, lon = geo.destination_point(f.lat, f.lon, math.degrees(bearing_rad), dist)
        r_local = random.Random(zlib.crc32(name.encode()))
        w = build_well(name, f, lat, lon, "drilling", "pending", 2026, "Sylhet Limestone", r_local, active=True, units=units)
        w.current_depth_m = cur_depth
        wells.append((w, r_local, 2026))

    for w, _, _ in wells:
        db.add(w)
    db.flush()

    # Offset neighbourhood bias so nearby wells share problems (it's the same geology).
    for w, r_local, spud in wells:
        bias = {"MUD_LOSS": 1.0, "KICK": 1.0, "STUCK_PIPE": 1.0}
        if w.lat > 27.45:     # northern fields: more losses in depleted Tipam
            bias["MUD_LOSS"] = 1.4
        if w.lon < 95.0:      # SW fields: more kicks in Kopili/Barail
            bias["KICK"] = 1.4
        drilled_to = w.current_depth_m if w.is_active else w.td_md_m
        evs = make_events(w, r_local, drilled_to, spud, bias)
        db.add_all(evs)
        db.flush()
        all_events += evs
        db.add_all(make_depth_logs(w, r_local, drilled_to, evs))

    # --- Volve events on a relocated well (clearly labelled)
    volve_events, volve_real = load_volve_events()
    if volve_events:
        bounds = [t for _, t in VOLVE_TOPS[1:]] + [3600]
        volve_tops = [{"name": n, "top_m": t, "bottom_m": b} for (n, t), b in zip(VOLVE_TOPS, bounds)]
        f = field_by_name["Moran"]
        lat, lon = geo.destination_point(f.lat, f.lon, 300, 5200)
        vw = m.Well(name="VOLVE-F12 (relocated)", field_id=None, operator="Equinor (Volve, North Sea)", lat=lat, lon=lon,
                    status="abandoned", well_type="directional", spud_year=2007, td_md_m=max(e["depth_m"] or 0 for e in volve_events) + 150,
                    outcome="success", formation_tops=volve_tops,
                    source=("Equinor Volve DDR" if volve_real else "Volve DDR format sample") + " – relocated onto Assam coordinates for the demo")
        db.add(vw)
        db.flush()
        for e in volve_events:
            e = {k: v for k, v in e.items() if k != "well"}
            db.add(m.DrillingEvent(well_id=vw.id, **e))

    # --- land parcels
    db.add_all(make_parcels(zones_raw, fields))

    # --- candidate locations
    for name, lat, lon, fm, td, by in CANDIDATES:
        db.add(m.CandidateLocation(name=name, lat=lat, lon=lon, target_formation=fm, planned_td_m=td, proposed_by=by,
                                   status="proposed", note="Sample candidate location"))

    # --- drillers
    now = datetime.utcnow()
    for d in DRILLERS:
        u = m.User(email=d["email"], password_hash=hash_password(d["password"]), full_name=d["name"], role="driller")
        db.add(u)
        db.flush()
        prof = m.DrillerProfile(user_id=u.id, phone=d["phone"], designation=d["designation"], experience_years=d["exp"],
                                id_number="XXXX-XXXX-" + str(1000 + u.id) if d["phone"] else None,
                                company_name=d["company"], company_reg_no=d["reg"],
                                company_address="Duliajan, Dibrugarh, Assam 786602" if d["company"] else None,
                                licence_number=f"PESO/DL/{2020 + u.id}/{300 + u.id}" if d["company"] else None,
                                work_area_name=d["area"], status=d["status"],
                                submitted_at=now - timedelta(days=5) if d["status"] != "draft" else None,
                                reviewed_at=now - timedelta(days=2) if d["status"] == "approved" else None)
        if d["site"]:
            prof.site_lat, prof.site_lon = d["site"]
            prof.work_radius_m = d["radius"]
            prof.planned_md_m, prof.planned_kop_m = d["plan"]["md"], d["plan"]["kop"]
            prof.planned_build_rate, prof.planned_hold_inc, prof.planned_azimuth = d["plan"]["build"], d["plan"]["inc"], d["plan"]["azi"]
            prof.last_lat, prof.last_lon = d["site"]
        db.add(prof)
        db.flush()
        if d["rig"]:
            db.add(m.Equipment(driller_id=prof.id, **d["rig"]))
        for doc_type, st in d["docs"]:
            db.add(m.DrillerDocument(driller_id=prof.id, doc_type=doc_type, filename=f"{doc_type}_{d['name'].split()[0].lower()}.pdf",
                                     status=st, note="Expired certificate – please re-upload" if st == "rejected" else None,
                                     reviewed_at=now - timedelta(days=2) if st != "pending" else None))
        if d["email"] == "driller@nwis.demo":
            # A little history so the breach log isn't empty on first open.
            db.add(m.BreachEvent(user_id=u.id, event_type="LEFT_ALLOWED_ZONE", status="OUTSIDE", lat=27.5905, lon=95.3690,
                                 distance_m=2620, radius_m=1750, simulated=True, created_at=now - timedelta(days=1, hours=3)))
            db.add(m.BreachEvent(user_id=u.id, event_type="RETURNED_TO_ZONE", status="INSIDE", lat=27.5790, lon=95.3500,
                                 distance_m=560, radius_m=1750, simulated=True, created_at=now - timedelta(days=1, hours=2, minutes=40)))

    db.commit()
    counts = {t: db.query(getattr(m, t)).count() for t in ["Field", "Well", "DrillingEvent", "DepthLog", "Zone", "LandParcel",
                                                          "CandidateLocation", "LandslideEvent", "GeologyUnit", "User"]}
    db.close()
    print("Seeded:", counts)
    print("Sources:", fields_label, "|", zones_label, "|", geology_label, "|", slides_label)


if __name__ == "__main__":
    seed()

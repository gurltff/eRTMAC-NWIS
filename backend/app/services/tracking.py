"""Live driller tracking: allowed zone, breach detection, websocket hub, simulators."""
from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime

from fastapi import WebSocket
from sqlalchemy.orm import Session

from .. import models as m
from ..config import DRILLING_SIM_ENABLED, DRILLING_SIM_INTERVAL_S, DRILLING_SIM_STEP_M
from ..db import SessionLocal
from . import geo
from .spatial import illegal_zones, legality


# --------------------------------------------------------------------------- #
# Allowed zone for a driller
# --------------------------------------------------------------------------- #
def allowed_zone(profile: m.DrillerProfile) -> dict | None:
    """Circle the driller is allowed and able to work in, plus the planned bottom-hole location."""
    if profile.site_lat is None or profile.site_lon is None:
        return None
    reach = max((e.max_horizontal_reach_m for e in profile.equipment), default=500.0)
    max_depth = max((e.max_depth_m for e in profile.equipment), default=None)
    radius = geo.operating_radius_m(reach, profile.work_radius_m)
    zone = {
        "center": {"lat": profile.site_lat, "lon": profile.site_lon},
        **radius,
        "polygon": geo.circle_polygon(profile.site_lat, profile.site_lon, radius["radius_m"]),
        "site_legality": legality(profile.site_lat, profile.site_lon),
        "warnings": [],
        "bottom_hole": None,
    }
    if profile.planned_md_m:
        stations = geo.build_and_hold_plan(profile.planned_kop_m or 0, profile.planned_build_rate or 0,
                                           profile.planned_hold_inc or 0, profile.planned_md_m, profile.planned_azimuth or 0)
        bhl = geo.bottom_hole_location(profile.site_lat, profile.site_lon, stations)
        bhl_legal = legality(bhl["lat"], bhl["lon"])
        zone["bottom_hole"] = {**{k: bhl[k] for k in ("lat", "lon", "tvd_m", "md_m", "horizontal_displacement_m")},
                               "path": [[p["lat"], p["lon"]] for p in bhl["path"][:: max(1, len(bhl["path"]) // 40)]],
                               "legality": bhl_legal["verdict"]}
        if bhl["horizontal_displacement_m"] > reach:
            zone["warnings"].append(f"Planned well reaches {bhl['horizontal_displacement_m']:.0f} m sideways, more than the rig's "
                                    f"{reach:.0f} m reach.")
        if bhl_legal["verdict"] == "ILLEGAL":
            zone["warnings"].append("The planned bottom of the hole ends up under a protected or restricted area.")
        if max_depth and profile.planned_md_m > max_depth:
            zone["warnings"].append(f"Planned depth {profile.planned_md_m:.0f} m is deeper than the rig's {max_depth:.0f} m rating.")
    if zone["site_legality"]["verdict"] == "ILLEGAL":
        zone["warnings"].append("The approved site itself is inside an illegal zone.")
    return zone


# --------------------------------------------------------------------------- #
# Websocket hub
# --------------------------------------------------------------------------- #
class Hub:
    def __init__(self):
        self.clients: dict[WebSocket, dict] = {}

    async def connect(self, ws: WebSocket, user: m.User):
        await ws.accept()
        self.clients[ws] = {"user_id": user.id, "role": user.role}

    def disconnect(self, ws: WebSocket):
        self.clients.pop(ws, None)

    async def broadcast(self, msg: dict, driller_user_id: int | None = None):
        """Office roles see everything; a driller only sees their own messages and well alerts."""
        data = json.dumps(msg, default=str)
        dead = []
        for ws, info in list(self.clients.items()):
            if info["role"] == "driller" and driller_user_id is not None and info["user_id"] != driller_user_id:
                continue
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = Hub()


# --------------------------------------------------------------------------- #
# Position processing
# --------------------------------------------------------------------------- #
def position_payload(profile: m.DrillerProfile, check: geo.RangeCheck | None, simulated: bool) -> dict:
    return {"type": "position", "user_id": profile.user_id, "driller_id": profile.id, "name": profile.user.full_name,
            "company": profile.company_name, "lat": profile.last_lat, "lon": profile.last_lon,
            "status": profile.tracking_status, "check": check.as_dict() if check else None, "simulated": simulated,
            "at": (profile.last_seen_at or datetime.utcnow()).isoformat() + "Z"}


def process_position(db: Session, user: m.User, lat: float, lon: float, accuracy_m: float | None = None,
                     simulated: bool = False) -> tuple[dict, dict | None]:
    """Store a position, classify it, log a breach on status change. Returns (position msg, breach msg or None)."""
    profile = user.driller
    zone = allowed_zone(profile) if profile else None
    check = None
    if zone:
        check = geo.check_position(lat, lon, zone["center"]["lat"], zone["center"]["lon"], zone["radius_m"], illegal_zones(db))
    status = check.status if check else "NO_ZONE"
    db.add(m.TrackingPoint(user_id=user.id, lat=lat, lon=lon, accuracy_m=accuracy_m, status=status, simulated=simulated))
    breach_msg = None
    if profile:
        event = geo.breach_transition(profile.tracking_status, check) if check else None
        profile.tracking_status, profile.last_lat, profile.last_lon, profile.last_seen_at = status, lat, lon, datetime.utcnow()
        if event:
            b = m.BreachEvent(user_id=user.id, event_type=event, status=status, lat=lat, lon=lon, distance_m=check.distance_m,
                              radius_m=check.radius_m, zone_name=check.zone_name, simulated=simulated)
            db.add(b)
            db.flush()
            breach_msg = {"type": "breach", **breach_dict(b, user.full_name)}
    db.commit()
    return (position_payload(profile, check, simulated) if profile else {"type": "position", "user_id": user.id, "lat": lat, "lon": lon}), breach_msg


BREACH_TEXT = {
    "ENTERED_ILLEGAL_ZONE": "Entered an illegal zone",
    "LEFT_ALLOWED_ZONE": "Left the allowed working zone",
    "NEAR_BOUNDARY": "Close to the edge of the allowed zone",
    "RETURNED_TO_ZONE": "Back inside the allowed zone",
}


def breach_dict(b: m.BreachEvent, name: str | None = None) -> dict:
    return {"id": b.id, "user_id": b.user_id, "name": name, "event_type": b.event_type, "text": BREACH_TEXT.get(b.event_type, b.event_type),
            "is_breach": b.event_type in ("ENTERED_ILLEGAL_ZONE", "LEFT_ALLOWED_ZONE"), "status": b.status,
            "lat": b.lat, "lon": b.lon, "distance_m": round(b.distance_m), "radius_m": round(b.radius_m), "zone_name": b.zone_name,
            "simulated": b.simulated, "acknowledged": b.acknowledged, "created_at": b.created_at.isoformat() + "Z"}


# --------------------------------------------------------------------------- #
# Driller movement simulator
# --------------------------------------------------------------------------- #
SIM_SPEED_M_S = 45.0   # fast-forward so a full loop takes ~2-3 minutes in a demo
SIM_TICK_S = 1.5


def simulator_waypoints(zone: dict, zones: list[dict]) -> list[tuple[float, float]]:
    """A loop that wanders inside, walks into the nearest illegal zone (if one is close),
    comes back, then walks out past the edge of the allowed circle and back again."""
    c_lat, c_lon, r = zone["center"]["lat"], zone["center"]["lon"], zone["radius_m"]
    pts = [(c_lat, c_lon), geo.destination_point(c_lat, c_lon, 210, 0.45 * r), geo.destination_point(c_lat, c_lon, 300, 0.6 * r)]
    # nearest illegal zone point reachable within 1.6 × radius
    best = None
    for z in zones:
        ring = z["polygon"]
        cz_lat = sum(p[0] for p in ring) / len(ring)
        cz_lon = sum(p[1] for p in ring) / len(ring)
        bearing = geo.initial_bearing_deg(c_lat, c_lon, cz_lat, cz_lon)
        for step in range(50, int(1.6 * r), 50):
            p = geo.destination_point(c_lat, c_lon, bearing, step)
            if geo.point_in_polygon(p[0], p[1], ring):
                inside = geo.destination_point(c_lat, c_lon, bearing, step + 150)
                if best is None or step < best[0]:
                    best = (step, inside)
                break
    if best:
        pts += [best[1], (c_lat, c_lon)]
    out_bearing = 90 if not best else (geo.initial_bearing_deg(c_lat, c_lon, *best[1]) + 150) % 360
    pts += [geo.destination_point(c_lat, c_lon, out_bearing, 0.8 * r), geo.destination_point(c_lat, c_lon, out_bearing, 1.3 * r),
            geo.destination_point(c_lat, c_lon, out_bearing + 40, 0.5 * r), (c_lat, c_lon)]
    return pts


def interpolate_path(points: list[tuple[float, float]], step_m: float) -> list[tuple[float, float]]:
    path = []
    for (a_lat, a_lon), (b_lat, b_lon) in zip(points, points[1:]):
        d = geo.haversine_m(a_lat, a_lon, b_lat, b_lon)
        n = max(1, int(d / step_m))
        brg = geo.initial_bearing_deg(a_lat, a_lon, b_lat, b_lon)
        for i in range(n):
            path.append(geo.destination_point(a_lat, a_lon, brg, d * i / n))
    path.append(points[-1])
    return path


class SimulatorManager:
    def __init__(self):
        self.tasks: dict[int, asyncio.Task] = {}

    def running(self, user_id: int) -> bool:
        t = self.tasks.get(user_id)
        return bool(t and not t.done())

    def start(self, user_id: int) -> bool:
        if self.running(user_id):
            return False
        self.tasks[user_id] = asyncio.create_task(self._run(user_id))
        return True

    def stop(self, user_id: int) -> bool:
        t = self.tasks.pop(user_id, None)
        if t and not t.done():
            t.cancel()
            return True
        return False

    async def _run(self, user_id: int):
        with SessionLocal() as db:
            user = db.get(m.User, user_id)
            zone = allowed_zone(user.driller) if user and user.driller else None
            if not zone:
                return
            path = interpolate_path(simulator_waypoints(zone, illegal_zones(db)), SIM_SPEED_M_S * SIM_TICK_S)
        i = 0
        try:
            while True:
                lat, lon = path[i % len(path)]
                # tiny GPS-like jitter (±3 m)
                lat, lon = geo.offset_by_ne(lat, lon, 3 * math.sin(i * 1.7), 3 * math.cos(i * 1.3))
                with SessionLocal() as db:
                    user = db.get(m.User, user_id)
                    pos, breach = process_position(db, user, lat, lon, accuracy_m=5.0, simulated=True)
                await hub.broadcast(pos, driller_user_id=user_id)
                if breach:
                    await hub.broadcast(breach, driller_user_id=user_id)
                i += 1
                await asyncio.sleep(SIM_TICK_S)
        except asyncio.CancelledError:
            pass


simulators = SimulatorManager()


# --------------------------------------------------------------------------- #
# Drilling depth simulator (active wells advance, alert engine re-runs)
# --------------------------------------------------------------------------- #
async def drilling_simulator_loop():
    from .well_monitor import alert_dict, analyse_well, persist_alerts
    if not DRILLING_SIM_ENABLED:
        return
    while True:
        await asyncio.sleep(DRILLING_SIM_INTERVAL_S)
        try:
            with SessionLocal() as db:
                for w in db.query(m.Well).filter(m.Well.is_active.is_(True)).all():
                    if w.current_depth_m is None or (w.planned_td_m and w.current_depth_m >= w.planned_td_m):
                        continue
                    w.current_depth_m = round(w.current_depth_m + DRILLING_SIM_STEP_M, 1)
                    db.commit()
                    await hub.broadcast({"type": "depth", "well_id": w.id, "name": w.name, "depth_m": w.current_depth_m})
                    new = persist_alerts(db, w, analyse_well(db, w))
                    for a in new:
                        await hub.broadcast({"type": "well_alert", **alert_dict(a, w.name)})
        except Exception as exc:  # keep the loop alive in a demo
            print("drilling simulator error:", exc)

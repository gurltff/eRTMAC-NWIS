"""Live geolocation: REST for posting positions, websocket for the live feed, simulator controls."""
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models as m
from ..auth import current_user, require_roles, user_from_token
from ..db import SessionLocal, get_db
from ..services.tracking import allowed_zone, breach_dict, hub, process_position, simulators

router = APIRouter(tags=["tracking"])
office = require_roles("admin", "engineer")


class PositionIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = None


@router.post("/api/tracking/position")
async def post_position(body: PositionIn, user: m.User = Depends(require_roles("driller")), db: Session = Depends(get_db)):
    pos, breach = process_position(db, user, body.lat, body.lon, body.accuracy_m, simulated=False)
    await hub.broadcast(pos, driller_user_id=user.id)
    if breach:
        await hub.broadcast(breach, driller_user_id=user.id)
    return {"position": pos, "breach": breach}


class SimIn(BaseModel):
    user_id: int | None = None


def _target(body: SimIn, user: m.User) -> int:
    if user.role == "driller":
        return user.id
    if not body.user_id:
        raise HTTPException(400, "Pick a driller.")
    return body.user_id


@router.post("/api/tracking/simulator/start")
def sim_start(body: SimIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    uid = _target(body, user)
    target = db.get(m.User, uid)
    if not target or not target.driller or not allowed_zone(target.driller):
        raise HTTPException(400, "This driller has no working area yet, so there is nothing to simulate.")
    simulators.start(uid)
    return {"running": True, "user_id": uid}


@router.post("/api/tracking/simulator/stop")
def sim_stop(body: SimIn, user: m.User = Depends(current_user)):
    uid = _target(body, user)
    simulators.stop(uid)
    return {"running": False, "user_id": uid}


@router.get("/api/tracking/simulator/status")
def sim_status(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == "driller":
        return {"running": simulators.running(user.id)}
    return {"running": {p.user_id: simulators.running(p.user_id) for p in db.query(m.DrillerProfile)}}


@router.get("/api/tracking/live")
def live(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(m.DrillerProfile).filter(m.DrillerProfile.site_lat.isnot(None))
    if user.role == "driller":
        q = q.filter(m.DrillerProfile.user_id == user.id)
    out = []
    for p in q.all():
        trail = (db.query(m.TrackingPoint).filter(m.TrackingPoint.user_id == p.user_id)
                 .order_by(m.TrackingPoint.recorded_at.desc()).limit(60).all())
        out.append({"user_id": p.user_id, "driller_id": p.id, "name": p.user.full_name, "company": p.company_name,
                    "status": p.status, "tracking_status": p.tracking_status, "lat": p.last_lat, "lon": p.last_lon,
                    "last_seen_at": p.last_seen_at.isoformat() + "Z" if p.last_seen_at else None,
                    "simulator_running": simulators.running(p.user_id), "zone": allowed_zone(p),
                    "trail": [[t.lat, t.lon] for t in reversed(trail)]})
    return out


@router.get("/api/tracking/breaches")
def breaches(user_id: int | None = None, limit: int = 100, _: m.User = Depends(office), db: Session = Depends(get_db)):
    q = db.query(m.BreachEvent)
    if user_id:
        q = q.filter(m.BreachEvent.user_id == user_id)
    names = {u.id: u.full_name for u in db.query(m.User)}
    return [breach_dict(b, names.get(b.user_id)) for b in q.order_by(m.BreachEvent.created_at.desc()).limit(limit)]


@router.post("/api/tracking/breaches/{breach_id}/ack")
def ack_breach(breach_id: int, _: m.User = Depends(office), db: Session = Depends(get_db)):
    b = db.get(m.BreachEvent, breach_id)
    if not b:
        raise HTTPException(404, "Not found.")
    b.acknowledged = True
    db.commit()
    return {"ok": True}


@router.websocket("/ws/live")
async def ws_live(ws: WebSocket, token: str = Query(...)):
    with SessionLocal() as db:
        user = user_from_token(db, token)
        if not user:
            await ws.close(code=4401)
            return
        user_id, role = user.id, user.role
        await hub.connect(ws, user)
    try:
        while True:
            msg = await ws.receive_json()
            # A logged-in driller's phone can stream GPS over the same socket.
            if msg.get("type") == "position" and role == "driller":
                with SessionLocal() as db:
                    u = db.get(m.User, user_id)
                    pos, breach = process_position(db, u, float(msg["lat"]), float(msg["lon"]), msg.get("accuracy_m"))
                await hub.broadcast(pos, driller_user_id=user_id)
                if breach:
                    await hub.broadcast(breach, driller_user_id=user_id)
    except (WebSocketDisconnect, RuntimeError, ValueError, KeyError):
        hub.disconnect(ws)

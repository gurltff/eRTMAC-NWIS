"""Offset-well alert engine.

For an active well, every problem recorded in offset wells is moved onto the
active well's depth scale by FORMATION correlation (not raw depth), because
the same formation sits at different depths in different wells:

    fraction      = (event_depth − top_offset) / (bottom_offset − top_offset)
    expected_depth = top_active + fraction · (bottom_active − top_active)

If the formation isn't in the active well's prognosis (e.g. Volve wells with
North Sea formation names) the raw depth is used and marked "depth match".

Events are grouped by (problem type, formation). A group raises an alert when
the bit is within `lookahead_m` above the shallowest expected depth, or is
already inside the group's depth window.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .geo import haversine_m

SEVERITY_WEIGHT = {"low": 1, "medium": 2, "high": 3}

RECOMMENDATIONS = {
    "MUD_LOSS": "Mix and hold 100 bbl of LCM pill before {depth} m, add 15-20 ppb LCM to the active system 50 m above, "
                "keep ECD low (reduce flow rate, slow trips).",
    "KICK": "Raise mud weight by 0.3-0.5 ppg before {depth} m, run flow checks on every drilling break, keep the trip tank "
            "lined up and watch pit volume, gas and d-exponent closely.",
    "STUCK_PIPE": "Keep the string moving, back-ream each stand, pump hi-vis sweeps and check hole-cleaning before {depth} m. "
                  "Have jars in the BHA.",
    "TORQUE_SPIKE": "Lower RPM and WOB when torque rises near {depth} m, add lubricant, and consider an anti-balling PDC bit.",
    "CEMENTING": "Plan a lightweight lead slurry and extra centralisers across the zone near {depth} m; run a CBL after the job.",
    "FISHING": "Inspect drill-string and BHA before drilling past {depth} m; keep a fishing tool kit on site.",
    "NPT": "Check spares and logistics before reaching {depth} m.",
}
LABELS = {"MUD_LOSS": "Mud loss", "KICK": "Kick / overpressure", "STUCK_PIPE": "Stuck pipe", "TORQUE_SPIKE": "Torque spike",
          "CEMENTING": "Cementing problem", "FISHING": "Fishing job", "NPT": "Non-productive time"}


@dataclass
class OffsetEvent:
    id: int
    well_id: int
    well_name: str
    event_type: str
    depth_m: float
    formation: str | None
    severity: str
    distance_m: float
    offset_tops: list
    description: str = ""
    action_taken: str | None = None
    lesson: str | None = None


@dataclass
class AlertGroup:
    event_type: str
    formation: str | None
    expected_min_m: float
    expected_max_m: float
    events: list = field(default_factory=list)
    method: str = "formation match"

    @property
    def wells(self) -> set:
        return {e.well_name for e, _ in self.events}


def correlate_depth(event_depth: float, formation: str | None, offset_tops: list, active_tops: list) -> tuple[float, str]:
    off = next((t for t in offset_tops if t["name"] == formation), None) if formation else None
    act = next((t for t in active_tops if t["name"] == formation), None) if formation else None
    if off and act and off["bottom_m"] > off["top_m"]:
        frac = min(1.0, max(0.0, (event_depth - off["top_m"]) / (off["bottom_m"] - off["top_m"])))
        return act["top_m"] + frac * (act["bottom_m"] - act["top_m"]), "formation match"
    return event_depth, "depth match"


def group_events(events: list[OffsetEvent], active_tops: list) -> list[AlertGroup]:
    groups: dict = {}
    for e in events:
        if e.event_type == "NPT":  # NPT like rig repairs isn't a geological risk
            continue
        depth, method = correlate_depth(e.depth_m, e.formation, e.offset_tops, active_tops)
        key = (e.event_type, e.formation)
        g = groups.get(key)
        if not g:
            g = groups[key] = AlertGroup(e.event_type, e.formation, depth, depth, method=method)
        g.expected_min_m = min(g.expected_min_m, depth)
        g.expected_max_m = max(g.expected_max_m, depth)
        g.events.append((e, depth))
    return list(groups.values())


def group_severity(g: AlertGroup, n_offset_wells: int) -> str:
    """Weighted by how many wells hit it, how bad it was and how close those wells are."""
    score = 0.0
    for e, _ in g.events:
        closeness = 1 / (1 + e.distance_m / 2000)  # a well 2 km away counts half
        score += SEVERITY_WEIGHT.get(e.severity, 2) * closeness
    share = len(g.wells) / max(1, n_offset_wells)
    if g.event_type == "KICK" and len(g.wells) >= 2:
        return "high"
    if score >= 4 or share >= 0.5:
        return "high"
    if score >= 1.8 or len(g.wells) >= 2:
        return "medium"
    return "low"


def evaluate(active: dict, offset_events: list[OffsetEvent], n_offset_wells: int, lookahead_m: float = 150.0) -> dict:
    """Pure function: returns current alerts and the upcoming risk zones.

    `active` needs: current_depth_m, formation_tops.
    """
    depth = active["current_depth_m"]
    groups = group_events(offset_events, active["formation_tops"])
    alerts, upcoming = [], []
    for g in groups:
        sev = group_severity(g, n_offset_wells)
        ahead = g.expected_min_m - depth
        if depth > g.expected_max_m + 25:
            state = "PASSED"
        elif g.expected_min_m - 25 <= depth <= g.expected_max_m + 25:
            state = "IN_ZONE"
        elif ahead <= lookahead_m:
            state = "APPROACHING"
        else:
            state = "AHEAD"
        evidence = sorted(g.events, key=lambda x: x[0].distance_m)
        lessons = [e.lesson for e, _ in evidence if e.lesson]
        actions = [e.action_taken for e, _ in evidence if e.action_taken]
        item = {
            "key": f"{g.event_type}:{g.formation}",
            "event_type": g.event_type,
            "label": LABELS.get(g.event_type, g.event_type),
            "formation": g.formation,
            "severity": sev,
            "state": state,
            "expected_from_m": round(g.expected_min_m),
            "expected_to_m": round(g.expected_max_m),
            "distance_ahead_m": round(ahead),
            "wells": sorted(g.wells),
            "event_count": len(g.events),
            "method": g.method,
            "title": f"{LABELS.get(g.event_type)} expected in {g.formation or 'this interval'} at "
                     + (f"{round(g.expected_min_m)} m" if round(g.expected_min_m) == round(g.expected_max_m)
                        else f"{round(g.expected_min_m)}–{round(g.expected_max_m)} m"),
            "message": f"{len(g.events)} {LABELS.get(g.event_type, '').lower()} event(s) in {len(g.wells)} offset well(s): "
                       + ", ".join(sorted(g.wells)[:4]) + ".",
            "recommendation": RECOMMENDATIONS.get(g.event_type, "").format(depth=round(g.expected_min_m)),
            "what_worked": [{"well": e.well_name, "distance_km": round(e.distance_m / 1000, 1), "depth_m": e.depth_m,
                             "action": e.action_taken, "lesson": e.lesson} for e, _ in evidence[:3]],
            "top_lesson": Counter(lessons).most_common(1)[0][0] if lessons else None,
            "top_action": actions[0] if actions else None,
        }
        if state in ("APPROACHING", "IN_ZONE"):
            alerts.append(item)
        if state != "PASSED":
            upcoming.append(item)
    order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda a: (order[a["severity"]], a["distance_ahead_m"]))
    upcoming.sort(key=lambda a: a["expected_from_m"])
    next_zone = next((u for u in upcoming if u["state"] in ("APPROACHING", "AHEAD")), None)
    return {"current_depth_m": depth, "lookahead_m": lookahead_m, "alerts": alerts, "upcoming": upcoming, "next_zone": next_zone}


def collect_offset_events(active_well, wells, events_by_well, radius_m: float) -> tuple[list[OffsetEvent], list]:
    """Turn DB rows into OffsetEvent objects for wells inside the radius."""
    offsets, out = [], []
    for w in wells:
        if w.id == active_well.id:
            continue
        d = haversine_m(active_well.lat, active_well.lon, w.lat, w.lon)
        if d > radius_m:
            continue
        offsets.append((w, d))
        for e in events_by_well.get(w.id, []):
            out.append(OffsetEvent(id=e.id, well_id=w.id, well_name=w.name, event_type=e.event_type, depth_m=e.depth_m,
                                   formation=e.formation, severity=e.severity, distance_m=d, offset_tops=w.formation_tops or [],
                                   description=e.description, action_taken=e.action_taken, lesson=e.lesson))
    return out, offsets


def events_index(events) -> dict:
    idx = defaultdict(list)
    for e in events:
        idx[e.well_id].append(e)
    return idx

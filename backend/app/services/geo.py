"""Geometry and drilling physics helpers.

Everything here is plain Python so it can be unit tested without a database.
Coordinates are WGS84 degrees; distances are metres unless stated otherwise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

EARTH_RADIUS_M = 6_371_000.0  # mean Earth radius used by the haversine formula


# --------------------------------------------------------------------------- #
# Great-circle geometry
# --------------------------------------------------------------------------- #
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points.

    a = sin²(Δφ/2) + cos φ1 · cos φ2 · sin²(Δλ/2)
    d = 2R · atan2(√a, √(1−a))
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Bearing (0-360°, clockwise from true north) to go from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lon2 - lon1)
    x = math.sin(dlmb) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlmb)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination_point(lat: float, lon: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """Point reached by travelling `distance_m` from (lat, lon) along `bearing_deg`."""
    delta = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing_deg)
    phi1, lmb1 = math.radians(lat), math.radians(lon)
    phi2 = math.asin(math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta))
    lmb2 = lmb1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), (math.degrees(lmb2) + 540) % 360 - 180


def offset_by_ne(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    """Move a point by local north/east offsets (flat-earth approximation, fine below ~50 km)."""
    dlat = north_m / EARTH_RADIUS_M
    dlon = east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat)))
    return lat + math.degrees(dlat), lon + math.degrees(dlon)


def circle_polygon(lat: float, lon: float, radius_m: float, segments: int = 64) -> list[list[float]]:
    """Approximate a geodesic circle as a closed polygon of [lat, lon] pairs."""
    pts = [list(destination_point(lat, lon, 360 * i / segments, radius_m)) for i in range(segments)]
    pts.append(pts[0])
    return pts


# --------------------------------------------------------------------------- #
# Polygons
# --------------------------------------------------------------------------- #
def point_in_polygon(lat: float, lon: float, ring: Sequence[Sequence[float]]) -> bool:
    """Ray-casting test. `ring` is a list of [lat, lon] vertices (closed or open).

    A horizontal ray is cast from the point; every edge it crosses flips the
    inside/outside state. Good enough for the small polygons used here.
    """
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        yi, xi = ring[i][0], ring[i][1]
        yj, xj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def distance_to_polyline_m(lat: float, lon: float, line: Sequence[Sequence[float]]) -> float:
    """Shortest distance from a point to a polyline of [lat, lon] vertices.

    Uses a local equirectangular projection around the point, which is
    accurate to well under 1 % at the scales used in this app (< 200 km).
    """
    kx = math.cos(math.radians(lat)) * math.pi * EARTH_RADIUS_M / 180
    ky = math.pi * EARTH_RADIUS_M / 180
    best = float("inf")
    for (a_lat, a_lon), (b_lat, b_lon) in zip(line, line[1:]):
        ax, ay = (a_lon - lon) * kx, (a_lat - lat) * ky
        bx, by = (b_lon - lon) * kx, (b_lat - lat) * ky
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy
        t = 0.0 if seg_len2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg_len2))
        px, py = ax + t * dx, ay + t * dy
        best = min(best, math.hypot(px, py))
    return best


def distance_to_polygon_edge_m(lat: float, lon: float, ring: Sequence[Sequence[float]]) -> float:
    closed = list(ring) if list(ring[0]) == list(ring[-1]) else list(ring) + [ring[0]]
    return distance_to_polyline_m(lat, lon, closed)


# --------------------------------------------------------------------------- #
# Directional drilling: minimum curvature method
# --------------------------------------------------------------------------- #
@dataclass
class SurveyStation:
    md: float   # measured depth along the hole (m)
    inc: float  # inclination from vertical (deg)
    azi: float  # azimuth from true north (deg)


@dataclass
class TrajectoryPoint:
    md: float
    tvd: float    # true vertical depth (m)
    north: float  # displacement north of the surface location (m)
    east: float   # displacement east of the surface location (m)

    @property
    def horizontal_displacement(self) -> float:
        return math.hypot(self.north, self.east)


def minimum_curvature(stations: Sequence[SurveyStation]) -> list[TrajectoryPoint]:
    """Industry-standard minimum curvature method.

    Between two survey stations the well path is assumed to be a circular arc.
    The dogleg angle β between the two direction vectors is

        cos β = cos(I2 − I1) − sin I1 · sin I2 · (1 − cos(A2 − A1))

    and the ratio factor RF = (2/β) · tan(β/2) (→ 1 when β → 0) corrects the
    simple average-angle result for the curvature of the arc:

        ΔN   = ΔMD/2 · (sin I1 cos A1 + sin I2 cos A2) · RF
        ΔE   = ΔMD/2 · (sin I1 sin A1 + sin I2 sin A2) · RF
        ΔTVD = ΔMD/2 · (cos I1 + cos I2) · RF
    """
    if not stations:
        return []
    # The hole above the first station is assumed vertical.
    pts = [TrajectoryPoint(md=stations[0].md, tvd=stations[0].md, north=0.0, east=0.0)]
    for s1, s2 in zip(stations, stations[1:]):
        i1, i2 = math.radians(s1.inc), math.radians(s2.inc)
        a1, a2 = math.radians(s1.azi), math.radians(s2.azi)
        dmd = s2.md - s1.md
        cos_beta = math.cos(i2 - i1) - math.sin(i1) * math.sin(i2) * (1 - math.cos(a2 - a1))
        beta = math.acos(max(-1.0, min(1.0, cos_beta)))
        rf = 1.0 if beta < 1e-9 else (2 / beta) * math.tan(beta / 2)
        prev = pts[-1]
        pts.append(
            TrajectoryPoint(
                md=s2.md,
                tvd=prev.tvd + dmd / 2 * (math.cos(i1) + math.cos(i2)) * rf,
                north=prev.north + dmd / 2 * (math.sin(i1) * math.cos(a1) + math.sin(i2) * math.cos(a2)) * rf,
                east=prev.east + dmd / 2 * (math.sin(i1) * math.sin(a1) + math.sin(i2) * math.sin(a2)) * rf,
            )
        )
    return pts


def build_and_hold_plan(kop_m: float, build_rate_deg_per_30m: float, hold_inc_deg: float,
                        target_md_m: float, azimuth_deg: float, step_m: float = 30.0) -> list[SurveyStation]:
    """Survey stations for a classic 'build and hold' (J-type) directional well.

    Vertical to the kick-off point, then inclination builds at a constant
    rate until the hold angle, then the hole goes straight to target MD.
    """
    stations: list[SurveyStation] = []
    md = 0.0
    while md <= target_md_m + 1e-6:
        if md <= kop_m:
            inc = 0.0
        else:
            inc = min(hold_inc_deg, (md - kop_m) / 30.0 * build_rate_deg_per_30m)
        stations.append(SurveyStation(md=md, inc=inc, azi=azimuth_deg))
        md += step_m
    if stations[-1].md < target_md_m:
        last_inc = stations[-1].inc
        stations.append(SurveyStation(md=target_md_m, inc=last_inc, azi=azimuth_deg))
    return stations


def bottom_hole_location(surface_lat: float, surface_lon: float,
                         stations: Sequence[SurveyStation]) -> dict:
    """Where the bottom of the hole ends up, in map coordinates."""
    path = minimum_curvature(stations)
    end = path[-1]
    lat, lon = offset_by_ne(surface_lat, surface_lon, end.north, end.east)
    return {
        "lat": lat,
        "lon": lon,
        "tvd_m": round(end.tvd, 1),
        "md_m": round(end.md, 1),
        "horizontal_displacement_m": round(end.horizontal_displacement, 1),
        "path": [
            {"md": round(p.md, 1), "tvd": round(p.tvd, 1),
             "lat": offset_by_ne(surface_lat, surface_lon, p.north, p.east)[0],
             "lon": offset_by_ne(surface_lat, surface_lon, p.north, p.east)[1]}
            for p in path
        ],
    }


# --------------------------------------------------------------------------- #
# Operating range from declared equipment
# --------------------------------------------------------------------------- #
SAFETY_MARGIN_FRACTION = 0.10  # 10 % of the rig reach ...
SAFETY_MARGIN_MIN_M = 250.0    # ... but never less than 250 m
NEAR_EDGE_FRACTION = 0.90      # warn once the driller is past 90 % of the radius


def operating_radius_m(max_horizontal_reach_m: float, declared_radius_m: float | None = None) -> dict:
    """Allowed working radius around the approved site.

    radius = rig horizontal reach + safety margin, where the margin is
    max(10 % of reach, 250 m). The declared working area caps it: a driller
    can't be 'allowed' beyond the area they applied for.
    """
    margin = max(SAFETY_MARGIN_FRACTION * max_horizontal_reach_m, SAFETY_MARGIN_MIN_M)
    capability = max_horizontal_reach_m + margin
    radius = min(capability, declared_radius_m) if declared_radius_m else capability
    return {
        "reach_m": round(max_horizontal_reach_m, 1),
        "safety_margin_m": round(margin, 1),
        "capability_radius_m": round(capability, 1),
        "declared_radius_m": declared_radius_m,
        "radius_m": round(radius, 1),
        "limited_by": "declared area" if declared_radius_m and declared_radius_m < capability else "rig reach",
    }


@dataclass
class RangeCheck:
    status: str            # INSIDE | NEAR_EDGE | OUTSIDE | ILLEGAL_ZONE
    distance_m: float      # distance from the site centre
    radius_m: float
    zone_name: str | None = None
    zone_type: str | None = None

    @property
    def is_breach(self) -> bool:
        return self.status in ("OUTSIDE", "ILLEGAL_ZONE")

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "distance_m": round(self.distance_m, 1),
            "radius_m": round(self.radius_m, 1),
            "zone_name": self.zone_name,
            "zone_type": self.zone_type,
            "is_breach": self.is_breach,
        }


def check_position(lat: float, lon: float, center_lat: float, center_lon: float, radius_m: float,
                   illegal_zones: Iterable[dict] = ()) -> RangeCheck:
    """Classify a live position against the allowed circle and the illegal zones.

    Illegal zone wins over everything else: being inside a protected forest
    is a breach even if it's within rig reach.
    """
    d = haversine_m(lat, lon, center_lat, center_lon)
    for z in illegal_zones:
        if point_in_polygon(lat, lon, z["polygon"]):
            return RangeCheck("ILLEGAL_ZONE", d, radius_m, z.get("name"), z.get("zone_type"))
    if d > radius_m:
        return RangeCheck("OUTSIDE", d, radius_m)
    if d > NEAR_EDGE_FRACTION * radius_m:
        return RangeCheck("NEAR_EDGE", d, radius_m)
    return RangeCheck("INSIDE", d, radius_m)


def breach_transition(previous_status: str | None, current: RangeCheck) -> str | None:
    """Decide which event (if any) to log when the status changes.

    We log on transitions only, so a driller standing outside the zone for an
    hour creates one breach record, not thousands.
    """
    if previous_status == current.status:
        return None
    if current.status == "ILLEGAL_ZONE":
        return "ENTERED_ILLEGAL_ZONE"
    if current.status == "OUTSIDE":
        return "LEFT_ALLOWED_ZONE"
    if current.status == "NEAR_EDGE" and previous_status in (None, "INSIDE"):
        return "NEAR_BOUNDARY"
    if previous_status in ("OUTSIDE", "ILLEGAL_ZONE") and current.status in ("INSIDE", "NEAR_EDGE"):
        return "RETURNED_TO_ZONE"
    return None

"""Elevation and slope.

Real data: download SRTM GL1 (30 m) GeoTIFF tiles for the area from
OpenTopography and place them in data/raw/srtm/. If `rasterio` is installed
they are sampled directly. Otherwise a smooth modelled terrain is used
(Brahmaputra valley ~90-150 m, Naga/Patkai hills to the SE, Mikir hills to the SW,
Mishmi foothills to the NE). The modelled surface is sample data.

Slope is computed the same way in both cases: central differences of
elevation on a 30 m grid (the SRTM spacing) around the point:

    dz/dx = (z_east − z_west) / (2·Δ),  dz/dy = (z_north − z_south) / (2·Δ)
    slope = atan(√(dz/dx² + dz/dy²))
"""
from __future__ import annotations

import math
from functools import lru_cache

from ..config import RAW_DIR
from .geo import offset_by_ne

# Approximate trace of the Naga thrust (lat, lon), running SW → NE.
NAGA_THRUST = [(26.25, 93.95), (26.55, 94.35), (26.85, 94.78), (27.05, 95.15), (27.20, 95.45), (27.30, 95.75), (27.42, 96.20)]
GRID_SPACING_M = 30.0


def _thrust_lat_at(lon: float) -> float:
    pts = NAGA_THRUST
    if lon <= pts[0][1]:
        (la0, lo0), (la1, lo1) = pts[0], pts[1]
    elif lon >= pts[-1][1]:
        (la0, lo0), (la1, lo1) = pts[-2], pts[-1]
    else:
        for (la0, lo0), (la1, lo1) in zip(pts, pts[1:]):
            if lo0 <= lon <= lo1:
                break
    t = (lon - lo0) / (lo1 - lo0)
    return la0 + t * (la1 - la0)


def km_southeast_of_thrust(lat: float, lon: float) -> float:
    """Positive = in the hills SE of the thrust, negative = out in the valley."""
    # The thrust trends ~N50E, so a north-south offset is ~cos(40°) of the true normal distance.
    return (_thrust_lat_at(lon) - lat) * 111.0 * 0.77


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def modelled_elevation_m(lat: float, lon: float) -> float:
    base = 95 + 55 * (lon - 93.6) / 2.6 + 12 * math.sin(lat * 40) * math.cos(lon * 33)
    d = km_southeast_of_thrust(lat, lon)
    hills = 950 * _sigmoid((d - 4) / 3.5)
    mikir = 520 * math.exp(-(((lat - 26.30) / 0.12) ** 2 + ((lon - 93.70) / 0.13) ** 2))
    mishmi = 650 * _sigmoid((lat - 27.82) / 0.035) * _sigmoid((lon - 95.72) / 0.05)
    # Ridges and valleys: a few metres on the plain, a couple of hundred in the hills.
    hilliness = max(_sigmoid((d - 3) / 3), mikir / 520, mishmi / 650)
    rough = (6 + 200 * hilliness) * (math.sin(lat * 210 + lon * 60) * math.cos(lon * 170 - lat * 45))
    return max(60.0, base + hills + rough + mikir + mishmi)


@lru_cache(maxsize=1)
def _srtm_datasets():
    folder = RAW_DIR / "srtm"
    if not folder.exists():
        return ()
    try:
        import rasterio  # optional dependency
    except ImportError:
        return ()
    return tuple(rasterio.open(p) for p in sorted(folder.glob("*.tif")))


def elevation_m(lat: float, lon: float) -> tuple[float, str]:
    for ds in _srtm_datasets():
        b = ds.bounds
        if b.left <= lon <= b.right and b.bottom <= lat <= b.top:
            val = next(ds.sample([(lon, lat)]))[0]
            if val > -1000:
                return float(val), "SRTM 30 m (OpenTopography)"
    return modelled_elevation_m(lat, lon), "Modelled terrain (sample; add SRTM tiles for real values)"


def slope_deg(lat: float, lon: float) -> float:
    d = GRID_SPACING_M
    zn = elevation_m(*offset_by_ne(lat, lon, d, 0))[0]
    zs = elevation_m(*offset_by_ne(lat, lon, -d, 0))[0]
    ze = elevation_m(*offset_by_ne(lat, lon, 0, d))[0]
    zw = elevation_m(*offset_by_ne(lat, lon, 0, -d))[0]
    dzdx = (ze - zw) / (2 * d)
    dzdy = (zn - zs) / (2 * d)
    return math.degrees(math.atan(math.hypot(dzdx, dzdy)))


def terrain_summary(lat: float, lon: float) -> dict:
    elev, source = elevation_m(lat, lon)
    # Relief: range of elevation within ~1 km, a proxy for how hilly the area is.
    samples = [elevation_m(*offset_by_ne(lat, lon, n, e))[0] for n in (-1000, 0, 1000) for e in (-1000, 0, 1000)]
    return {
        "elevation_m": round(elev, 1),
        "slope_deg": round(slope_deg(lat, lon), 2),
        "local_relief_m": round(max(samples) - min(samples), 1),
        "source": source,
    }

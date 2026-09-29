"""Shared helpers for the dataset loaders."""
from app.config import REGION


def in_region(lat: float, lon: float, pad: float = 0.0) -> bool:
    return (REGION["min_lat"] - pad <= lat <= REGION["max_lat"] + pad
            and REGION["min_lon"] - pad <= lon <= REGION["max_lon"] + pad)


def simplify_ring(ring, max_points: int = 160):
    """Keep every n-th vertex so large shapefile polygons stay light."""
    if len(ring) <= max_points:
        return ring
    step = max(1, len(ring) // max_points)
    out = ring[::step]
    if out[-1] != ring[-1]:
        out.append(ring[-1])
    return out


def geojson_polygons(feature):
    """Yield [[lat, lon], ...] outer rings from a GeoJSON Polygon/MultiPolygon."""
    g = feature.get("geometry") or {}
    if g.get("type") == "Polygon":
        yield [[lat, lon] for lon, lat in g["coordinates"][0]]
    elif g.get("type") == "MultiPolygon":
        for poly in g["coordinates"]:
            yield [[lat, lon] for lon, lat in poly[0]]


def shapefile_polygons(shape):
    """Yield [[lat, lon], ...] rings from a pyshp shape (assumes WGS84 lon/lat)."""
    pts = shape.points
    parts = list(shape.parts) + [len(pts)]
    for a, b in zip(parts, parts[1:]):
        ring = [[lat, lon] for lon, lat in pts[a:b]]
        if len(ring) >= 4:
            yield ring

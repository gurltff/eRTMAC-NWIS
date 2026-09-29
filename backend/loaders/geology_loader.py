"""Geology polygons: GSI Bhukosh shapefiles, or the sample GeoJSON.

Real data: register on https://bhukosh.gsi.gov.in/Bhukosh/Public, download the
1:2M / 1:50K lithology layers for Assam & Arunachal and unzip the .shp/.dbf/.shx
files into data/raw/bhukosh/. Shapefiles must be in WGS84 (EPSG:4326).
"""
import json

from app.config import RAW_DIR, SAMPLES_DIR
from .common import geojson_polygons, in_region, shapefile_polygons, simplify_ring

# Rough mapping from lithology keywords to our landslide / petroleum inputs.
KEYWORDS = [
    (("alluvium", "alluvial", "sand", "silt", "clay"), "alluvium", 0.25, 0.6),
    (("gneiss", "granite", "schist", "quartzite"), "metamorphic", 0.85, 0.02),
    (("basalt", "dolerite", "igneous"), "igneous", 0.8, 0.02),
    (("shale", "disang"), "sedimentary", 0.3, 0.2),
    (("tipam", "barail", "sandstone", "surma", "dihing", "siwalik"), "sedimentary", 0.4, 0.5),
]


def _classify(text: str):
    t = (text or "").lower()
    for words, rock_class, strength, play in KEYWORDS:
        if any(w in t for w in words):
            return rock_class, strength, play
    return "sedimentary", 0.45, 0.3


def load_units() -> tuple[list[dict], str]:
    shp_dir = RAW_DIR / "bhukosh"
    shps = sorted(shp_dir.glob("*.shp")) if shp_dir.exists() else []
    if shps:
        import shapefile  # pyshp
        units = []
        for shp in shps:
            reader = shapefile.Reader(str(shp))
            names = [f[0] for f in reader.fields[1:]]
            for sr in reader.iterShapeRecords():
                rec = dict(zip(names, sr.record))
                lith = next((str(rec[k]) for k in rec if k.upper() in ("LITHOLOGY", "LITHO", "ROCK_TYPE", "ROCKTYPE", "DESCRIPTIO")), "")
                name = next((str(rec[k]) for k in rec if k.upper() in ("GROUP_NAME", "FORMATION", "NAME", "UNIT")), lith or shp.stem)
                age = next((str(rec[k]) for k in rec if k.upper() in ("AGE", "ERA", "PERIOD")), None)
                rock_class, strength, play = _classify(f"{name} {lith}")
                for ring in shapefile_polygons(sr.shape):
                    if any(in_region(lat, lon) for lat, lon in ring[:: max(1, len(ring) // 20)]):
                        units.append(dict(name=name, lithology=lith or name, age=age, rock_class=rock_class,
                                          strength=strength, petroleum_play=play, polygon=simplify_ring(ring),
                                          source=f"GSI Bhukosh ({shp.name})"))
        # Keep the sample shelf polygon as a fallback so every point gets a unit.
        return units + [u for u in _sample() if u["name"].startswith("Upper Assam shelf")], "GSI Bhukosh shapefiles"
    return _sample(), "Sample geology (simplified, not survey-accurate)"


def _sample():
    data = json.loads((SAMPLES_DIR / "geology_sample.geojson").read_text())
    units = []
    for f in data["features"]:
        p = f["properties"]
        for ring in geojson_polygons(f):
            units.append(dict(name=p["name"], lithology=p["lithology"], age=p.get("age"), rock_class=p["rock_class"],
                              strength=p["strength"], petroleum_play=p["petroleum_play"], polygon=ring,
                              source="Sample geology (modelled on GSI Bhukosh units)"))
    return units

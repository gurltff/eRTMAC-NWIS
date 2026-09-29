"""NASA Global Landslide Catalog.

Real data: export the catalog CSV from https://data.nasa.gov (Global Landslide
Catalog, h9d8-neg4) into data/raw/nasa_glc/. Rows inside the study area are kept.
Otherwise data/samples/landslides_sample.csv (same column layout) is used.
"""
import csv

from app.config import RAW_DIR, SAMPLES_DIR
from .common import in_region


def load_landslides() -> tuple[list[dict], str]:
    folder = RAW_DIR / "nasa_glc"
    files = sorted(folder.glob("*.csv")) if folder.exists() else []
    path = files[0] if files else SAMPLES_DIR / "landslides_sample.csv"
    label = f"NASA Global Landslide Catalog ({path.name})" if files else "Sample (NASA GLC layout)"
    out = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                lat, lon = float(r["latitude"]), float(r["longitude"])
            except (KeyError, ValueError):
                continue
            if not in_region(lat, lon, pad=0.3):
                continue
            out.append(dict(lat=lat, lon=lon, event_date=(r.get("event_date") or "")[:10],
                            trigger=r.get("landslide_trigger"), size=r.get("landslide_size"),
                            place=r.get("location_description") or r.get("event_title"), source=label))
    return out, label

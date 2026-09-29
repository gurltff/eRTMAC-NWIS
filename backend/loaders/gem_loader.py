"""Global Energy Monitor – Global Oil and Gas Extraction Tracker (India rows).

Real data: download the tracker (GEM site or the Kaggle copy
alialmulla97/global-oil-and-gas-extraction-tracker) and put the CSV/XLSX-as-CSV
in data/raw/gem/. This loader keeps rows where Country == India and inside
the study area. Without it, data/samples/gem_india_fields_sample.csv is used.

GEM coordinates are field centroids; the seed script scatters individual
well points around each centroid.
"""
import csv
from pathlib import Path

from app.config import RAW_DIR, SAMPLES_DIR
from .common import in_region

# GEM has changed its column names between releases, so accept a few aliases.
ALIASES = {
    "unit_name": ["unit_name", "Unit name", "Unit Name", "Field name"],
    "country": ["country", "Country", "Country/Area"],
    "subnational_unit": ["subnational_unit", "Subnational unit (province, state)", "Subnational unit"],
    "operator": ["operator", "Operator"],
    "past_operators": ["past_operators", "Owner", "Parent"],
    "discovery_year": ["discovery_year", "Discovery year"],
    "status": ["status", "Status"],
    "lat": ["lat", "Latitude"],
    "lon": ["lon", "Longitude"],
    "reserves_mmbbl": ["reserves_mmbbl"],
    "production_bpd": ["production_bpd"],
}


def _get(row, key):
    for alias in ALIASES.get(key, [key]):
        if alias in row and row[alias] not in ("", None):
            return row[alias]
    return row.get(key)


def _num(v, cast=float):
    try:
        return cast(float(v))
    except (TypeError, ValueError):
        return None


def load_fields() -> tuple[list[dict], str]:
    raw = sorted((RAW_DIR / "gem").glob("*.csv")) if (RAW_DIR / "gem").exists() else []
    path: Path = raw[0] if raw else SAMPLES_DIR / "gem_india_fields_sample.csv"
    label = f"GEM Oil & Gas Extraction Tracker ({path.name})" if raw else "Sample modelled on GEM tracker (approx. centroids, illustrative values)"
    fields = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if (_get(row, "country") or "").strip() != "India":
                continue
            lat, lon = _num(_get(row, "lat")), _num(_get(row, "lon"))
            if lat is None or lon is None or not in_region(lat, lon, pad=0.2):
                continue
            past = _get(row, "past_operators") or ""
            fields.append({
                "name": _get(row, "unit_name"),
                "operator": _get(row, "operator") or "Unknown",
                "past_operators": [p.strip() for p in past.split("|") if p.strip()],
                "discovery_year": _num(_get(row, "discovery_year"), int),
                "status": _get(row, "status"),
                "state": _get(row, "subnational_unit"),
                "basin": row.get("basin") or "Assam-Arakan",
                "lat": lat, "lon": lon,
                "reserves_mmbbl": _num(_get(row, "reserves_mmbbl")),
                "production_bpd": _num(_get(row, "production_bpd")),
                "porosity": _num(row.get("porosity")) or 0.19,
                "water_saturation": _num(row.get("water_saturation")) or 0.40,
                "formation_volume_factor": _num(row.get("formation_volume_factor")) or 1.15,
                "net_pay_m": _num(row.get("net_pay_m")) or 12,
                "recovery_factor": _num(row.get("recovery_factor")) or 0.27,
                "source": label,
            })
    return fields, label

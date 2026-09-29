"""Writes the sample geo files in data/samples/.

These stand in for Bhukosh (geology), WDPA + OSM (zones), the NASA landslide
catalog and river centrelines. Outlines are simplified approximations drawn
for the demo, NOT legally or geologically accurate boundaries.

Run:  python -m scripts.make_sample_geodata   (from backend/)
"""
import csv
import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "data" / "samples"


def feature(name, ring_latlon, props):
    # GeoJSON wants [lon, lat]; our rings are written as (lat, lon) for readability.
    coords = [[lon, lat] for lat, lon in ring_latlon]
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return {"type": "Feature", "properties": {"name": name, **props},
            "geometry": {"type": "Polygon", "coordinates": [coords]}}


def box(lat0, lat1, lon0, lon1):
    return [(lat0, lon0), (lat0, lon1), (lat1, lon1), (lat1, lon0)]


def zones():
    f = []
    illegal = dict(legal_to_drill=False)
    f.append(feature("Dibru-Saikhowa National Park", [
        (27.62, 95.17), (27.70, 95.24), (27.73, 95.45), (27.69, 95.62), (27.62, 95.60), (27.61, 95.45), (27.60, 95.30)],
        dict(zone_type="protected_area", authority="Assam Forest Dept / MoEFCC", source="WDPA (simplified sample outline)", **illegal)))
    f.append(feature("Maguri-Motapung Beel wetland", [
        (27.588, 95.335), (27.600, 95.332), (27.608, 95.352), (27.604, 95.378), (27.592, 95.382), (27.585, 95.360)],
        dict(zone_type="wetland", authority="Eco-sensitive zone, Tinsukia", source="OSM wetland (simplified sample outline)", **illegal)))
    f.append(feature("Dehing Patkai National Park", [
        (27.30, 95.50), (27.33, 95.62), (27.32, 95.80), (27.26, 95.92), (27.19, 95.85), (27.20, 95.62), (27.24, 95.52)],
        dict(zone_type="protected_area", authority="Assam Forest Dept / MoEFCC", source="WDPA (simplified sample outline)", **illegal)))
    f.append(feature("Hollongapar Gibbon Sanctuary", box(26.67, 26.735, 94.325, 94.385),
        dict(zone_type="protected_area", authority="Assam Forest Dept", source="WDPA (simplified sample outline)", **illegal)))
    f.append(feature("Kaziranga National Park (east part)", [
        (26.56, 93.35), (26.68, 93.30), (26.75, 93.55), (26.70, 93.72), (26.60, 93.70)],
        dict(zone_type="protected_area", authority="MoEFCC / UNESCO World Heritage", source="WDPA (simplified sample outline)", **illegal)))
    f.append(feature("Panidihing Bird Sanctuary", box(26.97, 27.005, 94.52, 94.575),
        dict(zone_type="protected_area", authority="Assam Forest Dept", source="WDPA (simplified sample outline)", **illegal)))
    f.append(feature("Upper Dihing (East) Reserved Forest", box(27.40, 27.48, 95.72, 95.86),
        dict(zone_type="reserved_forest", authority="Assam Forest Dept", source="OSM landuse=forest (simplified sample outline)", **illegal)))
    f.append(feature("Doomdooma Reserved Forest", box(27.515, 27.56, 95.62, 95.72),
        dict(zone_type="reserved_forest", authority="Assam Forest Dept", source="OSM landuse=forest (simplified sample outline)", **illegal)))
    f.append(feature("Nambor Reserved Forest", box(26.34, 26.50, 93.62, 93.84),
        dict(zone_type="reserved_forest", authority="Assam Forest Dept", source="OSM landuse=forest (simplified sample outline)", **illegal)))
    f.append(feature("Abhoypur Reserved Forest", box(27.15, 27.22, 95.05, 95.18),
        dict(zone_type="reserved_forest", authority="Assam Forest Dept", source="OSM landuse=forest (simplified sample outline)", **illegal)))
    f.append(feature("Chabua Air Force Station", box(27.458, 27.476, 95.100, 95.132),
        dict(zone_type="restricted", authority="Ministry of Defence", source="Sample restricted area", **illegal)))
    f.append(feature("Digboi Refinery safety buffer", box(27.372, 27.384, 95.632, 95.650),
        dict(zone_type="restricted", authority="PESO / refinery safety", source="Sample restricted area", **illegal)))
    f.append(feature("Dibrugarh town (urban)", box(27.455, 27.500, 94.880, 94.960),
        dict(zone_type="urban", authority="Dibrugarh Municipal Corporation", source="Sample urban limit", **illegal)))
    return f


def geology():
    """Surface geology, checked in list order (first match wins); alluvium is the fallback."""
    naga_thrust = [(26.25, 93.95), (26.55, 94.35), (26.85, 94.78), (27.05, 95.15), (27.20, 95.45), (27.30, 95.75), (27.42, 96.20)]
    # Belt of Schuppen: strip ~12 km SE of the Naga thrust
    schuppen = naga_thrust + [(lat - 0.11, lon + 0.05) for lat, lon in reversed(naga_thrust)]
    naga_hills = [(lat - 0.11, lon + 0.05) for lat, lon in naga_thrust] + [(26.20, 96.20), (26.20, 94.05)]
    return [
        feature("Dihing Group boulder beds (Plio-Pleistocene)", [(27.33, 95.55), (27.44, 95.58), (27.46, 95.95), (27.36, 95.98), (27.31, 95.76)],
                dict(lithology="Poorly sorted sandstone, pebble and boulder beds", age="Plio-Pleistocene", rock_class="sedimentary",
                     strength=0.35, petroleum_play=0.55)),
        feature("Belt of Schuppen – Tipam & Barail sandstones", schuppen,
                dict(lithology="Thrust slices of Tipam sandstone, Barail sandstone-shale-coal", age="Oligocene–Miocene", rock_class="sedimentary",
                     strength=0.45, petroleum_play=0.55)),
        feature("Naga Hills – Disang shale", naga_hills,
                dict(lithology="Dark splintery shale with thin sandstone, highly fractured", age="Upper Cretaceous–Eocene", rock_class="sedimentary",
                     strength=0.28, petroleum_play=0.15)),
        feature("Mikir Hills – Precambrian gneiss", [(26.20, 93.60), (26.46, 93.60), (26.42, 93.78), (26.20, 93.82)],
                dict(lithology="Granite gneiss and porphyritic granite (basement)", age="Precambrian", rock_class="metamorphic",
                     strength=0.85, petroleum_play=0.02)),
        feature("Mishmi foothills – Siwalik sandstone", [(27.78, 95.70), (27.95, 95.70), (27.95, 96.20), (27.70, 96.20)],
                dict(lithology="Soft sandstone, siltstone and conglomerate", age="Mio-Pliocene", rock_class="sedimentary",
                     strength=0.3, petroleum_play=0.2)),
        feature("North-bank alluvium (Quaternary)", [(27.95, 93.60), (26.70, 93.60), (26.78, 93.70), (26.85, 93.95), (26.95, 94.15),
                                                    (27.08, 94.35), (27.25, 94.55), (27.42, 94.75), (27.52, 94.95), (27.62, 95.10),
                                                    (27.70, 95.25), (27.78, 95.45), (27.83, 95.66), (27.95, 95.66)],
                dict(lithology="Sand, silt and clay of the Brahmaputra flood plain (north bank)", age="Quaternary", rock_class="alluvium",
                     strength=0.22, petroleum_play=0.3)),
        # Fallback polygon: the whole study area
        feature("Upper Assam shelf – Brahmaputra alluvium over Tertiary", box(26.2, 27.95, 93.6, 96.2),
                dict(lithology="Alluvial sand, silt and clay over Tipam/Barail reservoirs of the Upper Assam shelf", age="Quaternary (surface)",
                     rock_class="alluvium", strength=0.25, petroleum_play=0.7)),
    ]


def rivers():
    brahmaputra = [(27.83, 95.66), (27.78, 95.45), (27.70, 95.25), (27.62, 95.10), (27.52, 94.95), (27.42, 94.75),
                   (27.25, 94.55), (27.08, 94.35), (26.95, 94.15), (26.85, 93.95), (26.78, 93.70), (26.70, 93.35)]
    burhi_dihing = [(27.30, 95.95), (27.35, 95.70), (27.30, 95.45), (27.25, 95.25), (27.20, 95.05), (27.12, 94.85), (27.05, 94.65), (27.02, 94.55)]
    def line(name, pts):
        return {"type": "Feature", "properties": {"name": name, "source": "Approximate centreline (sample)"},
                "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in pts]}}
    return [line("Brahmaputra", brahmaputra), line("Burhi Dihing", burhi_dihing)]


def landslides():
    rng = random.Random(7)
    hills = [((26.30, 26.90), (94.10, 95.20), "Naga Hills"), ((26.90, 27.25), (95.30, 96.10), "Patkai foothills"),
             ((26.20, 26.45), (93.60, 93.80), "Karbi Anglong"), ((27.75, 27.95), (95.70, 96.20), "Lohit foothills")]
    rows = []
    for i in range(34):
        (la0, la1), (lo0, lo1), place = hills[i % len(hills)]
        rows.append({
            "event_date": f"{rng.randint(2008, 2023)}-{rng.choice(['05','06','07','08','09'])}-{rng.randint(1, 28):02d}",
            "event_title": f"Landslide near {place}",
            "location_description": place,
            "latitude": round(rng.uniform(la0, la1), 4),
            "longitude": round(rng.uniform(lo0, lo1), 4),
            "landslide_category": rng.choice(["landslide", "mudslide", "debris_flow", "rock_fall"]),
            "landslide_trigger": rng.choice(["downpour", "monsoon", "continuous_rain", "rain", "construction"]),
            "landslide_size": rng.choice(["small", "medium", "medium", "large"]),
            "fatality_count": rng.choice([0, 0, 0, 1, 2]),
            "source_name": "SAMPLE – NASA GLC layout",
        })
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "zones_sample.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": zones()}, indent=1))
    (OUT / "geology_sample.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": geology()}, indent=1))
    (OUT / "rivers_sample.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": rivers()}, indent=1))
    rows = landslides()
    with open(OUT / "landslides_sample.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("wrote sample geodata to", OUT)


if __name__ == "__main__":
    main()

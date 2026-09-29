"""Everything the map detail panel shows for one tapped point."""
from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from .. import models as m
from . import ml
from .hazards import all_hazards
from .reserves import estimate
from .soil import soil_at
from .spatial import geology_at, landslides_within, legality, nearest_fields, parcel_at, wells_within
from .subsurface import FORMATION_NAMES, lithology_for, prognosed_column
from .terrain import terrain_summary

FIELD_NOTES = {
    "Digboi": "Asia's oldest producing oil field (oil struck in 1889); Digboi refinery commissioned 1901.",
    "Naharkatiya": "Discovered 1953; its success led to the formation of Oil India Limited in 1959.",
    "Baghjan": "May–June 2020: blowout and fire at well Baghjan-5, next to Dibru-Saikhowa NP and Maguri-Motapung wetland.",
    "Lakwa": "One of ONGC's main onshore fields in Assam, producing since the late 1960s.",
}


def _ownership(parcel: m.LandParcel | None, verdict: str, zone_name: str | None) -> dict:
    if not parcel:
        return {"status": "unknown", "statement": "No land record found for this point."}
    hist = parcel.history or []
    base = {"parcel": parcel.code, "village": parcel.village, "status": parcel.status, "holder": parcel.holder,
            "history": hist, "source": parcel.source}
    since = next((h["from"] for h in reversed(hist) if h.get("to") is None), None)
    if parcel.status == "unclaimed":
        past = [h for h in hist if h.get("to")]
        past_txt = f" It was held by {past[-1]['holder']} ({past[-1]['from']}–{past[-1]['to']}), but that has lapsed." if past else " No past owner or lease on record."
        if verdict == "LEGAL":
            s = "Unclaimed land." + past_txt + " The zone is legal, so work can go ahead (after the usual permits)."
        elif verdict == "NEEDS_LICENCE":
            s = "Unclaimed land." + past_txt + " The area is not restricted, but a petroleum licence is needed before work can start."
        else:
            s = f"No private owner, but this point is inside {zone_name}. Work cannot go ahead."
        base.update(statement=s, can_proceed=verdict == "LEGAL")
    elif parcel.status == "owned":
        base.update(statement=f"Owned by {parcel.holder}{f' since {since}' if since else ''}. You need the owner's consent or land acquisition "
                              f"(RFCTLARR Act, 2013) before work.", can_proceed=False)
    elif parcel.status == "leased":
        base.update(statement=f"Leased to {parcel.holder}{f' since {since}' if since else ''}. Work needs the leaseholder's agreement.",
                    can_proceed=False)
    elif verdict == "ILLEGAL":
        base.update(statement=f"Government land held by {parcel.holder}, inside {zone_name}. Work cannot go ahead.", can_proceed=False)
    else:
        base.update(statement=f"Government land held by {parcel.holder}. Needs government allotment before work.", can_proceed=False)
    return base


def _subsurface(lat: float, lon: float, near_wells: list) -> dict:
    """Expected formation tops: offset wells if any are close, otherwise the structure map."""
    with_tops = [(w, d) for w, d in near_wells if w["formation_tops"] and w["formation_tops"][0]["name"] in FORMATION_NAMES][:4]
    if with_tops:
        tops = []
        for name in FORMATION_NAMES:
            vals = []
            for w, d in with_tops:
                t = next((t for t in w["formation_tops"] if t["name"] == name), None)
                if t:
                    vals.append((t["top_m"], t["bottom_m"], 1 / max(d, 300) ** 2))
            if vals:
                wsum = sum(v[2] for v in vals)
                tops.append({"name": name, "top_m": round(sum(v[0] * v[2] for v in vals) / wsum),
                             "bottom_m": round(sum(v[1] * v[2] for v in vals) / wsum), "lithology": lithology_for(name)})
        method = f"Weighted average of {len(with_tops)} nearby wells ({', '.join(w['name'] for w, _ in with_tops)})"
    else:
        tops = [{**t, "lithology": lithology_for(t["name"])} for t in prognosed_column(lat, lon)]
        method = "Hung from the sample seismic structure map (no wells within 5 km)"
    return {"column": tops, "method": method, "main_targets": ["Tipam Sandstone", "Barail"]}


def location_detail(db: Session, lat: float, lon: float) -> dict:
    terrain = terrain_summary(lat, lon)
    geology = geology_at(lat, lon)
    soil = soil_at(db, lat, lon, geology["rock_class"] if geology else None)
    legal = legality(lat, lon)
    near_wells = wells_within(lat, lon, 10_000)
    near_5 = [x for x in near_wells if x[1] <= 5000]

    # events near the point, grouped for history + hazards
    ids = [w["id"] for w, _ in near_wells]
    events = db.query(m.DrillingEvent).filter(m.DrillingEvent.well_id.in_(ids)).all() if ids else []
    events_by_well = defaultdict(list)
    for e in events:
        events_by_well[e.well_id].append({"event_type": e.event_type})

    prospect = ml.predict_prospect(lat, lon)
    oil = estimate(lat, lon, prospect["probability"])
    parcel = parcel_at(db, lat, lon)
    illegal_zone = next((z["name"] for z in legal["zones"] if not z["legal_to_drill"]), None)
    fields = nearest_fields(lat, lon, k=2)
    slides = landslides_within(lat, lon, 10_000)

    history = {
        "wells": [{"id": w["id"], "name": w["name"], "distance_km": round(d / 1000, 2), "spud_year": w["spud_year"],
                   "operator": w["operator"], "status": w["status"], "outcome": w["outcome"]} for w, d in near_wells[:8]],
        "event_counts": dict(Counter(e.event_type for e in events)),
        "fields": [{"name": f["name"], "distance_km": round(d / 1000, 1), "operator": f["operator"],
                    "discovered": f["discovery_year"], "past_operators": f["past_operators"], "note": FIELD_NOTES.get(f["name"])}
                   for f, d in fields],
        "landslides": [{"date": s["event_date"], "place": s["place"], "size": s["size"], "distance_km": round(d / 1000, 1)} for s, d in slides[:5]],
        "land_use": [f"{h['from']}{'–' + str(h['to']) if h.get('to') else '–now'}: {h['holder']} ({h['type']})" for h in (parcel.history if parcel else [])],
    }
    summary = []
    if near_5:
        n = len(near_5)
        summary.append(f"{n} well{'s' if n > 1 else ''} drilled within 5 km since {min(w['spud_year'] or 9999 for w, _ in near_5)}.")
    else:
        summary.append("No wells drilled within 5 km – this is untested ground.")
    if events:
        top = Counter(e.event_type for e in events).most_common(2)
        summary.append("Most common problems nearby: " + ", ".join(f"{t.replace('_', ' ').lower()} ({n})" for t, n in top) + ".")
    if fields and fields[0][1] < 15000:
        f = fields[0][0]
        summary.append(f"Closest field: {f['name']} ({f['operator']}), discovered {f['discovery_year']}.")
    history["summary"] = " ".join(summary)

    return {
        "lat": lat, "lon": lon,
        "sample_data": True,
        "history": history,
        "terrain": terrain,
        "geology": {"surface": geology, "subsurface": _subsurface(lat, lon, near_wells)},
        "soil": soil,
        "success": prospect,
        "hazards": all_hazards(lat, lon, terrain, geology, soil, events_by_well),
        "legality": legal,
        "oil_estimate": oil,
        "ownership": _ownership(parcel, legal["verdict"], illegal_zone),
        "sources": sorted({s for s in [terrain["source"], soil["source"], geology["source"] if geology else None,
                                       fields[0][0]["source"] if fields else None,
                                       "Land records: sample data (no open dataset)"] if s}),
    }

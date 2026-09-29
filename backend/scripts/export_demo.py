"""Export a snapshot of the sample database for the static browser demo.

    cd backend && python -m scripts.export_demo

Writes frontend/public/demo/snapshot.json. The hosted demo (npm run build:demo)
answers API calls in the browser from this snapshot, using JavaScript ports of
the same geometry, alert and extraction logic. Model outputs that need
scikit-learn (success score, risk curves, untapped spots) are precomputed here.
"""
import json
from pathlib import Path

from app import models as m
from app.config import REGION
from app.db import SessionLocal
from app.routers.driller import DOC_TYPES, REQUIRED_DOCS, profile_dict
from app.routers.map import layers, sources
from app.routers.wells import event_dict, well_summary
from app.services import ml, spatial
from app.services.subsurface import MEAN_THICKNESS, STRATIGRAPHY
from app.services.terrain import terrain_summary
from app.services.tracking import breach_dict
from seed.seed import DRILLERS, PARCEL_STEP

OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo" / "snapshot.json"
PASSWORDS = {"admin@nwis.demo": "Admin@123", "engineer@nwis.demo": "Engineer@123", **{d["email"]: d["password"] for d in DRILLERS}}


def r(x, n=4):
    return round(float(x), n)


def main():
    db = SessionLocal()
    spatial.refresh(db)
    models = ml.get_models(db)

    # Location cells on the model grid: everything the detail panel needs that
    # can't be computed cheaply in the browser.
    geo_names = [g["name"] for g in spatial.get("geology")]
    # Batch version of ml.predict_prospect over the whole grid (same maths, much faster).
    import math
    import numpy as np
    from app.services.geo import haversine_m
    model = models["prospect"]["model"]
    grid = models["grid"]
    X = np.array([ml.prospect_features(c["lat"], c["lon"]) for c in grid])
    prob = model.predict_proba(X)[:, 1]
    tree_std = np.stack([t.predict_proba(X)[:, 1] for t in model.estimators_]).std(axis=0)
    finished = ml._finished_wells()
    producers = [w for w in finished if w["outcome"] == "success"]
    cells = []
    for k, c in enumerate(grid):
        near_km = min(haversine_m(c["lat"], c["lon"], w["lat"], w["lon"]) for w in finished) / 1000
        prod_km = min(haversine_m(c["lat"], c["lon"], w["lat"], w["lon"]) for w in producers) / 1000
        conf = 0.5 * (1 - min(1.0, 2 * float(tree_std[k]))) + 0.5 * math.exp(-near_km / 12)
        t = terrain_summary(c["lat"], c["lon"])
        g = spatial.geology_at(c["lat"], c["lon"])
        closure, tipam, _, ratio, n10 = X[k]
        cells.append([c["lat"], c["lon"], r(prob[k], 3), r(conf, 2), r(closure, 0), r(tipam, 0), r(ratio, 3), int(n10), r(prod_km, 1),
                      r(t["elevation_m"], 0), r(t["slope_deg"], 2), r(t["local_relief_m"], 0), geo_names.index(g["name"]) if g else -1])

    wells = db.query(m.Well).all()
    events = db.query(m.DrillingEvent).all()
    risk = {}
    for w in wells:
        if w.is_active:
            saved = w.current_depth_m
            w.current_depth_m = 0
            risk[w.id] = ml.risk_profile(db, w)
            w.current_depth_m = saved
    db.rollback()

    parcels = {}
    for p in db.query(m.LandParcel).all():
        parcels[p.code] = [p.village, p.status, p.holder, [[h["from"], h.get("to"), h["holder"], h["type"]] for h in p.history]]

    drillers = [profile_dict(p) for p in db.query(m.DrillerProfile).all()]
    users = [{"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role, "password": PASSWORDS.get(u.email)}
             for u in db.query(m.User).all()]
    names = {u.id: u.full_name for u in db.query(m.User)}

    snapshot = {
        "generated_note": "Snapshot of the SAMPLE database for the browser demo.",
        "region": REGION,
        "parcel_step": PARCEL_STEP,
        "grid_step": ml.GRID_STEP,
        "layers": layers(None, db),
        "fields_full": spatial.get("fields"),
        "geology_full": [{k: v for k, v in g.items() if k != "polygon"} for g in spatial.get("geology")],
        "wells": [{**well_summary(w), "formation_tops": w.formation_tops, "trajectory": w.trajectory,
                   "casing_program": w.casing_program, "mud_program": w.mud_program, "cementing": w.cementing,
                   "initial_rate_bpd": w.initial_rate_bpd} for w in wells],
        "events": [event_dict(e, e.well) for e in events],
        "cells": cells,
        "untapped": {"spots": ml.untapped_spots(), "grid": models["grid"], "grid_step": ml.GRID_STEP, "explanation": ml.explain()},
        "risk_profiles": risk,
        "parcels": parcels,
        "stratigraphy": [{"name": n, "mean_thickness": MEAN_THICKNESS[n], "lithology": lith, "hazards": hz} for n, _, lith, hz in STRATIGRAPHY],
        "users": users,
        "drillers": drillers,
        "breaches": [breach_dict(b, names.get(b.user_id)) for b in db.query(m.BreachEvent).all()],
        "doc_types": {"types": DOC_TYPES, "required": REQUIRED_DOCS},
        "sources": sources(db),
        "explain": ml.explain(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, separators=(",", ":"), default=str))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB), {len(cells)} cells")


if __name__ == "__main__":
    main()

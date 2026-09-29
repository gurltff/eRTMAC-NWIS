"""Two small scikit-learn models trained on the (sample) database.

1. Prospect model – "will a well here find oil?"
   Random forest on six location features. Trained on every finished well
   (success vs. dry/marginal). Used for the success score in the detail panel
   and for the untapped-spot layer.

2. Drilling risk model – "what is likely to go wrong at this depth?"
   One random forest per problem type (mud loss, kick, stuck pipe, torque
   spike, cementing) trained on 50 m intervals of offset wells. Features are
   the depth, the formation, mud weight vs pore pressure and how often that
   problem happened in the same formation in nearby wells.

Both are deliberately small and explainable; the UI shows the plain-language
explanation from `explain()`.
"""
from __future__ import annotations

import math
import threading
from collections import defaultdict

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sqlalchemy.orm import Session

from .. import models as m
from ..config import REGION
from .geo import haversine_m
from .spatial import geology_at, get as layer, legality
from .subsurface import FORMATION_INDEX, structure_relief_m, tipam_depth_m

_lock = threading.RLock()
_state: dict = {}

# Distance-to-producer is left out on purpose: with it the model only learns "drill next to
# old wells" and can never point at an undrilled structure.
PROSPECT_FEATURES = ["structural_closure_m", "depth_to_tipam_m", "geology_play_prior",
                     "success_ratio_10km", "wells_within_10km"]
PROSPECT_LABELS = {
    "structural_closure_m": "Size of the structural high (sample seismic map)",
    "depth_to_tipam_m": "Depth to the Tipam reservoir",
    "geology_play_prior": "How favourable the rock setting is for oil",
    "km_to_nearest_producer": "Distance to the nearest producing well",
    "success_ratio_10km": "Share of successful wells within 10 km",
    "wells_within_10km": "Number of wells within 10 km",
}
RISK_TYPES = ["MUD_LOSS", "KICK", "STUCK_PIPE", "TORQUE_SPIKE", "CEMENTING"]
OFFSET_RADIUS_M = 15_000


# --------------------------------------------------------------------------- #
# Prospect model
# --------------------------------------------------------------------------- #
def _finished_wells():
    return [w for w in layer("wells") if w["outcome"] in ("success", "marginal", "dry") and not w["is_active"]
            and not w["name"].startswith("VOLVE")]


def prospect_features(lat: float, lon: float, exclude_id: int | None = None) -> list[float]:
    wells = [w for w in _finished_wells() if w["id"] != exclude_id]
    dists = [(w, haversine_m(lat, lon, w["lat"], w["lon"])) for w in wells]
    near = [w for w, d in dists if d <= 10_000]
    ratio = (sum(w["outcome"] == "success" for w in near) + 1) / (len(near) + 2)  # Laplace-smoothed
    geo_unit = geology_at(lat, lon)
    return [
        structure_relief_m(lat, lon),
        tipam_depth_m(lat, lon),
        geo_unit["petroleum_play"] if geo_unit else 0.5,
        ratio,
        float(len(near)),
    ]


def train_prospect_model() -> dict:
    wells = _finished_wells()
    X = np.array([prospect_features(w["lat"], w["lon"], exclude_id=w["id"]) for w in wells])
    y = np.array([1 if w["outcome"] == "success" else 0 for w in wells])
    model = RandomForestClassifier(n_estimators=300, max_depth=4, min_samples_leaf=3, random_state=0, class_weight="balanced")
    folds = StratifiedKFold(n_splits=min(5, int(min(np.bincount(y)))), shuffle=True, random_state=0)
    acc = cross_val_score(model, X, y, cv=folds, scoring="accuracy")
    auc = cross_val_score(model, X, y, cv=folds, scoring="roc_auc")
    model.fit(X, y)
    importances = sorted(zip(PROSPECT_FEATURES, model.feature_importances_), key=lambda x: -x[1])
    return {
        "model": model,
        "n_samples": int(len(y)),
        "n_success": int(y.sum()),
        "cv_accuracy": round(float(acc.mean()), 3),
        "cv_auc": round(float(auc.mean()), 3),
        "importances": [{"feature": f, "label": PROSPECT_LABELS[f], "importance": round(float(v), 3)} for f, v in importances],
    }


def predict_prospect(lat: float, lon: float) -> dict:
    info = get_models()["prospect"]
    model: RandomForestClassifier = info["model"]
    x = np.array([prospect_features(lat, lon)])
    prob = float(model.predict_proba(x)[0, 1])
    # Confidence = trees agreeing with each other AND having wells nearby to learn from.
    tree_probs = np.array([t.predict_proba(x)[0, 1] for t in model.estimators_])
    agreement = 1 - min(1.0, 2 * float(tree_probs.std()))
    nearest_km = min((haversine_m(lat, lon, w["lat"], w["lon"]) / 1000 for w in _finished_wells()), default=50)
    data_support = math.exp(-nearest_km / 12)
    confidence = 0.5 * agreement + 0.5 * data_support
    feats = dict(zip(PROSPECT_FEATURES, x[0].tolist()))
    feats["km_to_nearest_producer"] = min((haversine_m(lat, lon, w["lat"], w["lon"]) / 1000 for w in _finished_wells()
                                           if w["outcome"] == "success"), default=50.0)
    return {
        "probability": round(prob, 3),
        "score": round(prob * 100),
        "label": "Good" if prob >= 0.6 else ("Fair" if prob >= 0.4 else "Poor"),
        "confidence": round(confidence, 2),
        "confidence_label": "High" if confidence >= 0.66 else ("Medium" if confidence >= 0.45 else "Low"),
        "features": {k: round(v, 2) for k, v in feats.items()},
        "reasons": _prospect_reasons(feats, nearest_km),
    }


def _prospect_reasons(f: dict, nearest_km: float) -> list[str]:
    r = []
    c = f["structural_closure_m"]
    r.append(f"Structural high of about {c:.0f} m on the sample seismic map" if c > 60 else "No clear structural high here (oil has nowhere to collect)")
    r.append(f"Tipam reservoir expected at about {f['depth_to_tipam_m']:.0f} m")
    r.append(f"{f['success_ratio_10km'] * 100:.0f}% of nearby wells found oil ({int(f['wells_within_10km'])} wells within 10 km)")
    r.append(f"Nearest producing well is {f['km_to_nearest_producer']:.1f} km away")
    if nearest_km > 12:
        r.append("Few wells nearby, so the model is less sure here")
    return r


# --------------------------------------------------------------------------- #
# Untapped spots
# --------------------------------------------------------------------------- #
GRID_STEP = 0.025  # degrees (~2.7 km)


def score_grid(model: RandomForestClassifier) -> list[dict]:
    """Prospect probability on a regular grid (for the heatmap)."""
    pts, feats = [], []
    lat = REGION["min_lat"] + GRID_STEP / 2
    while lat < REGION["max_lat"]:
        lon = REGION["min_lon"] + GRID_STEP / 2
        while lon < REGION["max_lon"]:
            pts.append((lat, lon))
            feats.append(prospect_features(lat, lon))
            lon += GRID_STEP
        lat += GRID_STEP
    probs = model.predict_proba(np.array(feats))[:, 1]
    return [{"lat": round(a, 4), "lon": round(b, 4), "p": round(float(p), 3)} for (a, b), p in zip(pts, probs)]


def untapped_spots(max_spots: int = 14, min_prob: float = 0.5, min_well_km: float = 2.5, min_sep_km: float = 5.0) -> list[dict]:
    """Promising grid cells with no well nearby, outside illegal zones, spaced apart."""
    from .reserves import estimate
    grid = get_models()["grid"]
    wells = layer("wells")
    chosen: list[dict] = []
    for cell in sorted(grid, key=lambda c: -c["p"]):
        if cell["p"] < min_prob or len(chosen) >= max_spots:
            break
        if any(haversine_m(cell["lat"], cell["lon"], w["lat"], w["lon"]) < min_well_km * 1000 for w in wells):
            continue
        if any(haversine_m(cell["lat"], cell["lon"], c["lat"], c["lon"]) < min_sep_km * 1000 for c in chosen):
            continue
        if legality(cell["lat"], cell["lon"])["verdict"] == "ILLEGAL":
            continue
        pred = predict_prospect(cell["lat"], cell["lon"])
        est = estimate(cell["lat"], cell["lon"], pred["probability"])
        chosen.append({
            "id": f"U{len(chosen) + 1:02d}",
            "lat": cell["lat"], "lon": cell["lon"],
            "probability": pred["probability"], "score": pred["score"],
            "confidence": pred["confidence"], "confidence_label": pred["confidence_label"],
            "risked_recoverable_bbl": est["risked_recoverable_bbl"],
            "recoverable_p50_bbl": est["recoverable_p50_bbl"],
            "reasons": pred["reasons"],
        })
    return chosen


# --------------------------------------------------------------------------- #
# Drilling risk model
# --------------------------------------------------------------------------- #
def _offset_rates(db: Session, well: m.Well, others: list[m.Well], events_by_well: dict) -> dict:
    """How often each problem type happened per formation in wells within 15 km."""
    counts: dict = defaultdict(lambda: defaultdict(int))
    drilled: dict = defaultdict(int)
    for o in others:
        if o.id == well.id or haversine_m(well.lat, well.lon, o.lat, o.lon) > OFFSET_RADIUS_M:
            continue
        depth_reached = o.current_depth_m if o.is_active else (o.td_md_m or 0)
        for t in o.formation_tops or []:
            if t["top_m"] < depth_reached:
                drilled[t["name"]] += 1
        for e in events_by_well.get(o.id, []):
            counts[e.formation][e.event_type] += 1
    return {fm: {t: counts[fm][t] / max(1, drilled[fm]) for t in RISK_TYPES} for fm in set(drilled) | set(counts)}


def _risk_row(depth, fm, mw, pp, rates):
    r = rates.get(fm, {})
    return [depth, FORMATION_INDEX.get(fm, -1), mw, pp, mw - pp] + [r.get(t, 0.0) for t in RISK_TYPES]


def train_risk_models(db: Session) -> dict:
    wells = db.query(m.Well).all()
    events = db.query(m.DrillingEvent).all()
    events_by_well = defaultdict(list)
    for e in events:
        events_by_well[e.well_id].append(e)
    X, Y = [], {t: [] for t in RISK_TYPES}
    for w in wells:
        if w.is_active or w.name.startswith("VOLVE"):
            continue
        rates = _offset_rates(db, w, wells, events_by_well)
        logs = db.query(m.DepthLog).filter(m.DepthLog.well_id == w.id).all()
        evs = events_by_well[w.id]
        for lg in logs:
            X.append(_risk_row(lg.depth_m, lg.formation, lg.mud_weight_ppg, lg.pore_pressure_ppg, rates))
            for t in RISK_TYPES:
                Y[t].append(1 if any(e.event_type == t and abs(e.depth_m - lg.depth_m) <= 25 for e in evs) else 0)
    X = np.array(X)
    models = {}
    for t in RISK_TYPES:
        y = np.array(Y[t])
        clf = RandomForestClassifier(n_estimators=120, max_depth=6, min_samples_leaf=8, random_state=0, class_weight="balanced_subsample")
        clf.fit(X, y)
        models[t] = {"model": clf, "positives": int(y.sum())}
    return {"models": models, "n_rows": int(len(X))}


def risk_profile(db: Session, well: m.Well, step_m: float = 50.0) -> dict:
    """Risk per problem type for every 50 m from the current depth to planned TD."""
    info = get_models(db)["risk"]
    wells = db.query(m.Well).all()
    events_by_well = defaultdict(list)
    for e in db.query(m.DrillingEvent).all():
        events_by_well[e.well_id].append(e)
    rates = _offset_rates(db, well, wells, events_by_well)
    # Pore pressure per formation = average of offset wells' mud-logging estimate.
    pp_by_fm = defaultdict(list)
    for o, d in [(o, haversine_m(well.lat, well.lon, o.lat, o.lon)) for o in wells if o.id != well.id]:
        if d <= OFFSET_RADIUS_M:
            for lg in db.query(m.DepthLog.formation, m.DepthLog.pore_pressure_ppg).filter(m.DepthLog.well_id == o.id):
                pp_by_fm[lg[0]].append(lg[1])
    start = well.current_depth_m if well.is_active else 0
    end = well.planned_td_m or well.td_md_m or start + 1000
    rows, depths, fms, mws, pps = [], [], [], [], []
    depth = math.floor(start / step_m) * step_m
    while depth <= end:
        fm = next((t["name"] for t in well.formation_tops if t["top_m"] <= depth < t["bottom_m"]), well.formation_tops[-1]["name"])
        mw = next((p["weight_ppg"] for p in well.mud_program if p["from_m"] <= depth <= p["to_m"]), 10.0)
        pp = float(np.mean(pp_by_fm[fm])) if pp_by_fm.get(fm) else 9.5
        rows.append(_risk_row(depth, fm, mw, pp, rates))
        depths.append(depth), fms.append(fm), mws.append(mw), pps.append(round(pp, 2))
        depth += step_m
    out = {t: info["models"][t]["model"].predict_proba(np.array(rows))[:, 1].round(3).tolist() for t in RISK_TYPES} if rows else {}
    points = []
    for i, d in enumerate(depths):
        p = {"depth_m": d, "formation": fms[i], "mud_weight_ppg": mws[i], "pore_pressure_ppg": pps[i],
             "overpressure": pps[i] >= 10.5, **{t: out[t][i] for t in RISK_TYPES}}
        points.append(p)
    return {
        "well_id": well.id,
        "from_m": start,
        "to_m": end,
        "points": points,
        "explanation": ("For every 50 m ahead of the bit, the model looks at the formation, the planned mud weight, "
                        "the pore pressure seen in nearby wells, and how often each problem happened in that same "
                        "formation within 15 km. It gives a 0–100% chance for each problem."),
    }


# --------------------------------------------------------------------------- #
# Model cache
# --------------------------------------------------------------------------- #
def get_models(db: Session | None = None) -> dict:
    """Train lazily on first use and keep the models in memory."""
    with _lock:
        if "prospect" not in _state:
            _state["prospect"] = train_prospect_model()
        if "grid" not in _state:
            _state["grid"] = score_grid(_state["prospect"]["model"])
        if "risk" not in _state:
            if db is None:
                from ..db import SessionLocal
                with SessionLocal() as s:
                    _state["risk"] = train_risk_models(s)
            else:
                _state["risk"] = train_risk_models(db)
        return _state


def reset() -> None:
    with _lock:
        _state.clear()


def explain() -> dict:
    s = get_models()
    p = s["prospect"]
    return {
        "prospect_model": {
            "what": "Random forest (300 small decision trees) that scores how likely a well at a spot is to find oil.",
            "trained_on": f"{p['n_samples']} finished sample wells ({p['n_success']} successful).",
            "checked_by": f"5-fold cross-validation: accuracy {p['cv_accuracy'] * 100:.0f}%, ROC-AUC {p['cv_auc']:.2f}.",
            "inputs": p["importances"],
            "confidence": ("Confidence combines two things: how much the 300 trees agree with each other, and "
                           "how close the nearest drilled well is. Far from any well → low confidence."),
            "untapped": ("Untapped spots are grid cells (about 2.7 km apart) with a score of 50 or more, no well within "
                         "2.5 km, outside protected, forest and restricted zones, and at least 5 km from each other."),
        },
        "risk_model": {
            "what": "One random forest per problem type (mud loss, kick, stuck pipe, torque spike, cementing).",
            "trained_on": f"{s['risk']['n_rows']} depth intervals of 50 m from sample offset wells.",
            "inputs": ["Depth", "Formation", "Planned mud weight", "Pore pressure seen in nearby wells",
                       "Overbalance (mud weight minus pore pressure)", "How often each problem happened in that formation within 15 km"],
        },
        "note": "Both models are trained on SAMPLE data, so the numbers show how the system works, not real predictions.",
    }

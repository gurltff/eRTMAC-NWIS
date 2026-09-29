"""Estimated oil at a location: volumetric method with Monte Carlo ranges.

    STOIIP (bbl) = 7758 · A · h · φ · (1 − Sw) / Bo

      7758 = barrels per acre-foot
      A    = drainage area of one well (acres)
      h    = net oil pay (ft)
      φ    = porosity (fraction)
      Sw   = water saturation (fraction)
      Bo   = oil formation volume factor (reservoir bbl / stock-tank bbl)

    Recoverable = STOIIP · recovery factor
    Risked      = Recoverable · chance of success (from the prospect model)

Reservoir inputs are borrowed from the nearest fields (inverse-distance
weighted); net pay is scaled by the size of the structural closure at the
point. Inputs are sampled 2,000 times to give P90 / P50 / P10.
"""
from __future__ import annotations

import numpy as np

from .spatial import nearest_fields
from .subsurface import structure_relief_m

BBL_PER_ACRE_FT = 7758
M_TO_FT = 3.28084


def _idw(values_and_dists, power=2.0):
    num = den = 0.0
    for v, d in values_and_dists:
        w = 1.0 / max(d, 500.0) ** power
        num += v * w
        den += w
    return num / den


def estimate(lat: float, lon: float, chance_of_success: float, n: int = 2000, seed: int = 0) -> dict:
    near = nearest_fields(lat, lon, k=3)
    def blend(key):
        return _idw([(f[key], d) for f, d in near if f.get(key) is not None])
    phi, sw, bo, pay_m, rf = blend("porosity"), blend("water_saturation"), blend("formation_volume_factor"), blend("net_pay_m"), blend("recovery_factor")
    relief = structure_relief_m(lat, lon)
    closure_factor = float(np.clip(relief / 200.0, 0.25, 1.25))

    rng = np.random.default_rng(seed)
    area = rng.triangular(40, 80, 160, n)                                  # acres
    h = np.clip(rng.normal(pay_m * closure_factor, 0.25 * pay_m * closure_factor, n), 1, None) * M_TO_FT
    phi_s = np.clip(rng.normal(phi, 0.02, n), 0.05, 0.35)
    sw_s = np.clip(rng.normal(sw, 0.05, n), 0.1, 0.9)
    bo_s = np.clip(rng.normal(bo, 0.03, n), 1.0, 1.6)
    rf_s = np.clip(rng.normal(rf, 0.04, n), 0.05, 0.5)
    stoiip = BBL_PER_ACRE_FT * area * h * phi_s * (1 - sw_s) / bo_s
    recoverable = stoiip * rf_s
    # P90 = 90 % chance of at least this much → the 10th percentile.
    p90, p50, p10 = np.percentile(recoverable, [10, 50, 90])
    return {
        "method": "Volumetric (STOIIP = 7758·A·h·φ·(1−Sw)/Bo) × recovery factor, 2,000 Monte Carlo runs",
        "stoiip_p50_bbl": round(float(np.percentile(stoiip, 50))),
        "recoverable_p90_bbl": round(float(p90)),
        "recoverable_p50_bbl": round(float(p50)),
        "recoverable_p10_bbl": round(float(p10)),
        "risked_recoverable_bbl": round(float(recoverable.mean() * chance_of_success)),
        "chance_of_success": round(chance_of_success, 3),
        "inputs": {
            "drainage_area_acres": "40–160 (most likely 80)",
            "net_pay_m": round(pay_m * closure_factor, 1),
            "porosity": round(phi, 3),
            "water_saturation": round(sw, 3),
            "formation_volume_factor": round(bo, 3),
            "recovery_factor": round(rf, 3),
            "structural_closure_m": round(relief),
            "borrowed_from_fields": [f["name"] for f, _ in near],
        },
        "note": "Sample estimate for one well's drainage area. Real numbers need logs, core and a reservoir model.",
    }

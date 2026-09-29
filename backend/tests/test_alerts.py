"""Offset-well alert engine."""
from app.services.alerts import OffsetEvent, correlate_depth, evaluate

ACTIVE_TOPS = [{"name": "Girujan Clay", "top_m": 1500, "bottom_m": 2000},
               {"name": "Tipam Sandstone", "top_m": 2000, "bottom_m": 2400},
               {"name": "Barail", "top_m": 2400, "bottom_m": 3000}]
OFFSET_TOPS = [{"name": "Girujan Clay", "top_m": 1600, "bottom_m": 2200},
               {"name": "Tipam Sandstone", "top_m": 2200, "bottom_m": 2600},
               {"name": "Barail", "top_m": 2600, "bottom_m": 3200}]


def ev(i, etype, depth, fm, sev="medium", dist=2000, well="OFF-1"):
    return OffsetEvent(id=i, well_id=i, well_name=well, event_type=etype, depth_m=depth, formation=fm, severity=sev,
                       distance_m=dist, offset_tops=OFFSET_TOPS, action_taken="Pumped LCM", lesson="Pre-treat with LCM")


def test_correlation_uses_formation_not_raw_depth():
    # 100 m into a 400 m Tipam in the offset → 25 % → 2000 + 0.25·400 = 2100 m in the active well.
    depth, method = correlate_depth(2300, "Tipam Sandstone", OFFSET_TOPS, ACTIVE_TOPS)
    assert depth == 2100 and method == "formation match"


def test_unknown_formation_falls_back_to_depth():
    depth, method = correlate_depth(3185, "Hugin Fm", OFFSET_TOPS, ACTIVE_TOPS)
    assert depth == 3185 and method == "depth match"


def test_alert_when_approaching():
    events = [ev(1, "MUD_LOSS", 2300, "Tipam Sandstone")]
    far = evaluate({"current_depth_m": 1800, "formation_tops": ACTIVE_TOPS}, events, 1, lookahead_m=150)
    assert far["alerts"] == [] and far["next_zone"]["expected_from_m"] == 2100
    near = evaluate({"current_depth_m": 1990, "formation_tops": ACTIVE_TOPS}, events, 1, lookahead_m=150)
    assert len(near["alerts"]) == 1
    a = near["alerts"][0]
    assert a["state"] == "APPROACHING" and a["distance_ahead_m"] == 110
    assert "LCM" in a["recommendation"] and a["what_worked"][0]["lesson"] == "Pre-treat with LCM"


def test_in_zone_and_passed():
    events = [ev(1, "STUCK_PIPE", 1900, "Girujan Clay")]
    # 1900 m is halfway through the offset Girujan → 1750 m in the active well.
    inside = evaluate({"current_depth_m": 1745, "formation_tops": ACTIVE_TOPS}, events, 1)
    assert inside["alerts"][0]["state"] == "IN_ZONE"
    passed = evaluate({"current_depth_m": 2500, "formation_tops": ACTIVE_TOPS}, events, 1)
    assert passed["alerts"] == [] and passed["upcoming"] == []


def test_severity_grows_with_more_wells():
    one = evaluate({"current_depth_m": 2350, "formation_tops": ACTIVE_TOPS},
                   [ev(1, "KICK", 2700, "Barail", sev="low", dist=8000)], 4)
    two = evaluate({"current_depth_m": 2350, "formation_tops": ACTIVE_TOPS},
                   [ev(1, "KICK", 2700, "Barail", well="A"), ev(2, "KICK", 2720, "Barail", well="B")], 4)
    assert one["alerts"][0]["severity"] == "low"
    assert two["alerts"][0]["severity"] == "high"  # kicks in 2+ offset wells are always high


def test_npt_is_not_a_geological_alert():
    res = evaluate({"current_depth_m": 1990, "formation_tops": ACTIVE_TOPS}, [ev(1, "NPT", 2300, "Tipam Sandstone")], 1)
    assert res["alerts"] == []

"""Boundary breach detection."""
from app.services import geo

CENTER = (27.575, 95.346)
RADIUS = 1750
FOREST = {"name": "Test Forest", "zone_type": "reserved_forest",
          "polygon": [[27.59, 95.33], [27.59, 95.36], [27.61, 95.36], [27.61, 95.33]]}


def at(bearing, dist):
    return geo.destination_point(*CENTER, bearing, dist)


def test_inside_near_edge_outside():
    assert geo.check_position(*at(180, 500), *CENTER, RADIUS).status == "INSIDE"
    assert geo.check_position(*at(180, 1650), *CENTER, RADIUS).status == "NEAR_EDGE"
    c = geo.check_position(*at(180, 1800), *CENTER, RADIUS)
    assert c.status == "OUTSIDE" and c.is_breach


def test_exactly_on_boundary_is_not_a_breach():
    c = geo.check_position(*at(90, RADIUS - 0.5), *CENTER, RADIUS)
    assert not c.is_breach


def test_illegal_zone_beats_inside_radius():
    lat, lon = 27.595, 95.345  # ~2.2 km north – inside the forest square
    c = geo.check_position(lat, lon, *CENTER, 5000, [FOREST])
    assert c.status == "ILLEGAL_ZONE" and c.zone_name == "Test Forest"


def test_transitions_log_once():
    inside = geo.check_position(*at(0, 100), *CENTER, RADIUS)
    outside = geo.check_position(*at(90, 2000), *CENTER, RADIUS)
    assert geo.breach_transition(None, inside) is None
    assert geo.breach_transition("INSIDE", outside) == "LEFT_ALLOWED_ZONE"
    assert geo.breach_transition("OUTSIDE", outside) is None          # still outside: no new record
    assert geo.breach_transition("OUTSIDE", inside) == "RETURNED_TO_ZONE"
    illegal = geo.check_position(27.6, 95.345, *CENTER, 5000, [FOREST])
    assert geo.breach_transition("INSIDE", illegal) == "ENTERED_ILLEGAL_ZONE"

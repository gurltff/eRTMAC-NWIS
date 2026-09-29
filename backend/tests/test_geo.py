"""Distance, range and trajectory maths."""
import math

import pytest

from app.services import geo


def test_haversine_known_distance():
    # Dibrugarh → Guwahati: ~348 km in a straight line (the road is ~440 km).
    d = geo.haversine_m(27.4728, 94.9120, 26.1445, 91.7362)
    assert 340_000 < d < 355_000


def test_haversine_one_degree_latitude():
    assert geo.haversine_m(27.0, 95.0, 28.0, 95.0) == pytest.approx(111_195, rel=1e-3)


def test_haversine_zero_and_symmetry():
    assert geo.haversine_m(27.3, 95.3, 27.3, 95.3) == 0
    a = geo.haversine_m(27.1, 95.1, 27.4, 95.6)
    b = geo.haversine_m(27.4, 95.6, 27.1, 95.1)
    assert a == pytest.approx(b)


def test_destination_point_round_trip():
    lat, lon = geo.destination_point(27.5, 95.3, 60, 2500)
    assert geo.haversine_m(27.5, 95.3, lat, lon) == pytest.approx(2500, abs=0.5)
    assert geo.initial_bearing_deg(27.5, 95.3, lat, lon) == pytest.approx(60, abs=0.05)


def test_point_in_polygon():
    square = [[27.0, 95.0], [27.0, 95.1], [27.1, 95.1], [27.1, 95.0]]
    assert geo.point_in_polygon(27.05, 95.05, square)
    assert not geo.point_in_polygon(27.15, 95.05, square)
    assert not geo.point_in_polygon(27.05, 94.99, square)


def test_operating_radius_uses_reach_plus_margin():
    r = geo.operating_radius_m(1500)
    assert r["safety_margin_m"] == 250          # 10 % would be 150, the 250 m floor wins
    assert r["radius_m"] == 1750
    r = geo.operating_radius_m(4000)
    assert r["safety_margin_m"] == 400          # 10 % of 4000
    assert r["radius_m"] == 4400


def test_operating_radius_capped_by_declared_area():
    r = geo.operating_radius_m(4000, declared_radius_m=3000)
    assert r["radius_m"] == 3000 and r["limited_by"] == "declared area"


def test_vertical_well_stays_on_surface_location():
    stations = [geo.SurveyStation(md, 0, 0) for md in range(0, 3001, 30)]
    end = geo.minimum_curvature(stations)[-1]
    assert end.tvd == pytest.approx(3000)
    assert end.horizontal_displacement == pytest.approx(0, abs=1e-6)


def test_straight_inclined_hole():
    # Constant 30° inclination for 1000 m: TVD = 1000·cos30, displacement = 1000·sin30.
    stations = [geo.SurveyStation(0, 30, 90), geo.SurveyStation(1000, 30, 90)]
    end = geo.minimum_curvature(stations)[-1]
    assert end.tvd == pytest.approx(1000 * math.cos(math.radians(30)))
    assert end.east == pytest.approx(500)
    assert end.north == pytest.approx(0, abs=1e-9)


def test_quarter_circle_build():
    # Building from 0° to 90° over an arc: radius R = MD / (π/2); TVD and displacement both equal R.
    md = 1000
    stations = [geo.SurveyStation(0, 0, 0), geo.SurveyStation(md, 90, 0)]
    end = geo.minimum_curvature(stations)[-1]
    radius = md / (math.pi / 2)
    assert end.tvd == pytest.approx(radius, rel=1e-6)
    assert end.north == pytest.approx(radius, rel=1e-6)


def test_bottom_hole_location_moves_along_azimuth():
    plan = geo.build_and_hold_plan(kop_m=900, build_rate_deg_per_30m=2, hold_inc_deg=30, target_md_m=3500, azimuth_deg=90)
    bhl = geo.bottom_hole_location(27.5, 95.3, plan)
    assert bhl["lon"] > 95.3 and bhl["lat"] == pytest.approx(27.5, abs=1e-4)
    moved = geo.haversine_m(27.5, 95.3, bhl["lat"], bhl["lon"])
    assert moved == pytest.approx(bhl["horizontal_displacement_m"], rel=0.01)
    assert 1000 < bhl["horizontal_displacement_m"] < 1400

"""Main API routes, run against a fresh sample database."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import geo

SAMPLE_PDF = Path(__file__).resolve().parents[2] / "data" / "samples" / "drilling_report_sample.pdf"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin(client):
    return login(client, "admin@nwis.demo", "Admin@123")


@pytest.fixture(scope="module")
def engineer(client):
    return login(client, "engineer@nwis.demo", "Engineer@123")


@pytest.fixture(scope="module")
def driller(client):
    return login(client, "driller@nwis.demo", "Driller@123")


def test_login_rejects_bad_password(client):
    assert client.post("/api/auth/login", json={"email": "admin@nwis.demo", "password": "nope"}).status_code == 401


def test_requires_auth(client):
    assert client.get("/api/wells").status_code == 401


def test_roles_are_enforced(client, driller):
    assert client.get("/api/admin/drillers", headers=driller).status_code == 403
    assert client.get("/api/analytics/overview", headers=driller).status_code == 403


def test_map_layers(client, engineer):
    d = client.get("/api/map/layers", headers=engineer).json()
    assert 30 <= len(d["wells"]) <= 55
    assert any(z["zone_type"] == "protected_area" for z in d["zones"])
    assert len(d["candidates"]) >= 10


def test_location_detail_illegal_zone(client, engineer):
    d = client.get("/api/map/location", params={"lat": 27.265, "lon": 95.70}, headers=engineer).json()
    assert d["legality"]["verdict"] == "ILLEGAL"
    assert d["ownership"]["can_proceed"] is False
    for key in ("history", "geology", "soil", "success", "hazards", "oil_estimate"):
        assert key in d
    assert 0 <= d["success"]["score"] <= 100
    assert d["oil_estimate"]["recoverable_p90_bbl"] <= d["oil_estimate"]["recoverable_p10_bbl"]


def test_location_outside_region(client, engineer):
    assert client.get("/api/map/location", params={"lat": 19.0, "lon": 72.8}, headers=engineer).status_code == 400


def test_untapped_spots_avoid_wells_and_illegal_zones(client, engineer):
    d = client.get("/api/map/untapped", headers=engineer).json()
    layers = client.get("/api/map/layers", headers=engineer).json()
    assert d["spots"], "expected some untapped spots"
    for s in d["spots"]:
        assert s["probability"] >= 0.5
        assert min(geo.haversine_m(s["lat"], s["lon"], w["lat"], w["lon"]) for w in layers["wells"]) >= 2500
        assert s["confidence_label"] in ("Low", "Medium", "High")


def test_offsets_and_alert_engine(client, engineer):
    active = client.get("/api/wells", params={"active": True}, headers=engineer).json()
    well = active[0]
    d = client.get(f"/api/wells/{well['id']}/offsets", params={"radius_km": 15}, headers=engineer).json()
    assert d["offset_wells"] and all(w["distance_km"] <= 15 for w in d["offset_wells"])
    # Move the bit to just above the next risk zone: an alert must fire and be stored.
    nxt = d["next_zone"]
    assert nxt is not None
    r = client.post(f"/api/wells/{well['id']}/depth", json={"depth_m": nxt["expected_from_m"] - 50}, headers=engineer)
    assert r.status_code == 200 and r.json()["alerts"]
    stored = client.get("/api/alerts", params={"well_id": well["id"]}, headers=engineer).json()
    assert stored and stored[0]["recommendation"]


def test_risk_profile(client, engineer):
    well = client.get("/api/wells", params={"active": True}, headers=engineer).json()[0]
    d = client.get(f"/api/wells/{well['id']}/risk-profile", headers=engineer).json()
    assert d["points"] and all(0 <= p["KICK"] <= 1 for p in d["points"])


def test_event_search(client, engineer):
    d = client.get("/api/events", params={"q": "Girujan", "event_type": "STUCK_PIPE"}, headers=engineer).json()
    assert d["total"] > 0 and all(e["event_type"] == "STUCK_PIPE" for e in d["items"])


def test_tracking_breach_is_logged(client, driller):
    me = client.get("/api/driller/me", headers=driller).json()
    zone = me["zone"]
    c = zone["center"]
    inside = client.post("/api/tracking/position", json={"lat": c["lat"], "lon": c["lon"]}, headers=driller).json()
    assert inside["position"]["status"] in ("INSIDE", "NEAR_EDGE")
    lat, lon = geo.destination_point(c["lat"], c["lon"], 180, zone["radius_m"] + 400)
    out = client.post("/api/tracking/position", json={"lat": lat, "lon": lon}, headers=driller).json()
    assert out["position"]["status"] == "OUTSIDE"
    assert out["breach"]["event_type"] == "LEFT_ALLOWED_ZONE"
    # Staying outside must not create a second record.
    again = client.post("/api/tracking/position", json={"lat": lat, "lon": lon + 0.0001}, headers=driller).json()
    assert again["breach"] is None
    # Walk into the Maguri-Motapung wetland (inside the allowed circle).
    wet = client.post("/api/tracking/position", json={"lat": 27.595, "lon": 95.355}, headers=driller).json()
    assert wet["position"]["status"] == "ILLEGAL_ZONE"
    history = client.get("/api/driller/breaches", headers=driller).json()
    assert history[0]["event_type"] == "ENTERED_ILLEGAL_ZONE"


def test_websocket_receives_positions(client, engineer, driller):
    token = engineer["Authorization"].split()[1]
    with client.websocket_connect(f"/ws/live?token={token}") as ws:
        me = client.get("/api/driller/me", headers=driller).json()
        c = me["zone"]["center"]
        client.post("/api/tracking/position", json={"lat": c["lat"], "lon": c["lon"]}, headers=driller)
        msg = ws.receive_json()
        while msg["type"] != "position":
            msg = ws.receive_json()
        assert msg["name"] == "Rituraj Baruah"


def test_registration_and_approval_flow(client, admin):
    r = client.post("/api/auth/register", json={"email": "new.head@example.com", "password": "Password1", "full_name": "Test Head"})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.post("/api/driller/submit", headers=h).status_code == 400  # incomplete
    client.put("/api/driller/profile", json={"phone": "+91 90000 00000", "designation": "Head of Drilling", "experience_years": 9,
                                            "company_name": "Test Drilling", "licence_number": "LIC-1"}, headers=h)
    client.post("/api/driller/equipment", json={"name": "Rig-1", "rig_type": "Land rig", "max_depth_m": 4500,
                                                "max_horizontal_reach_m": 2000}, headers=h)
    client.put("/api/driller/work-area", json={"work_area_name": "Test area", "site_lat": 27.19, "site_lon": 95.03,
                                               "work_radius_m": 3000, "planned_md_m": 3200, "planned_kop_m": 900,
                                               "planned_build_rate": 2, "planned_hold_inc": 25, "planned_azimuth": 45}, headers=h)
    for t in ("licence", "permit", "id_proof", "environmental_clearance"):
        r = client.post("/api/driller/documents", data={"doc_type": t}, files={"file": (f"{t}.pdf", b"%PDF-1.4 test", "application/pdf")}, headers=h)
        assert r.status_code == 200, r.text
    me = client.post("/api/driller/submit", headers=h).json()
    assert me["status"] == "submitted"
    assert me["zone"]["radius_m"] == 2250  # 2000 m reach + 250 m margin, under the 3000 m declared radius
    # Admin can't approve before every document is approved.
    assert client.post(f"/api/admin/drillers/{me['id']}/decision", json={"decision": "approve"}, headers=admin).status_code == 400
    for d in me["documents"]:
        assert client.post(f"/api/admin/documents/{d['id']}/decision", json={"status": "approved"}, headers=admin).status_code == 200
    r = client.post(f"/api/admin/drillers/{me['id']}/decision", json={"decision": "approve", "note": "OK"}, headers=admin)
    assert r.json()["status"] == "approved"


def test_document_extraction_creates_well_and_events(client, engineer):
    with SAMPLE_PDF.open("rb") as fh:
        r = client.post("/api/documents/extract", files={"file": ("drilling_report_sample.pdf", fh, "application/pdf")}, headers=engineer)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["extract_method"] == "rules" and d["well_name"] == "HGJ-77" and d["events_created"] >= 4
    found = client.get("/api/events", params={"q": "HGJ-77"}, headers=engineer).json()
    assert found["total"] >= 4
    layers = client.get("/api/map/layers", headers=engineer).json()
    assert any(w["name"] == "HGJ-77" for w in layers["wells"])

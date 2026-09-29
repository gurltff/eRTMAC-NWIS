"""Database tables.

Geometry is stored as plain lat/lon columns and JSON polygons ([[lat, lon], ...]),
so the app runs on SQLite with no GIS extension. Spatial queries are done in
Python (see services/geo.py). Swapping to PostGIS later only touches this file
and the query helpers.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.utcnow()


# --------------------------------------------------------------------------- #
# People
# --------------------------------------------------------------------------- #
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="driller")  # driller | engineer | admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    driller: Mapped["DrillerProfile | None"] = relationship(back_populates="user", uselist=False)


class DrillerProfile(Base):
    """The 'head of drilling' registration: company, person, site and plan."""
    __tablename__ = "driller_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    # personal
    phone: Mapped[str | None] = mapped_column(String(40))
    designation: Mapped[str | None] = mapped_column(String(120))
    experience_years: Mapped[int | None] = mapped_column(Integer)
    id_number: Mapped[str | None] = mapped_column(String(60))
    # company
    company_name: Mapped[str | None] = mapped_column(String(200))
    company_reg_no: Mapped[str | None] = mapped_column(String(80))
    company_address: Mapped[str | None] = mapped_column(Text)
    licence_number: Mapped[str | None] = mapped_column(String(80))
    # working area (approved site = centre of the allowed circle)
    work_area_name: Mapped[str | None] = mapped_column(String(200))
    site_lat: Mapped[float | None] = mapped_column(Float)
    site_lon: Mapped[float | None] = mapped_column(Float)
    work_radius_m: Mapped[float | None] = mapped_column(Float)
    # planned well geometry (used to compute bottom-hole location)
    planned_md_m: Mapped[float | None] = mapped_column(Float)
    planned_kop_m: Mapped[float | None] = mapped_column(Float)
    planned_build_rate: Mapped[float | None] = mapped_column(Float)  # deg / 30 m
    planned_hold_inc: Mapped[float | None] = mapped_column(Float)
    planned_azimuth: Mapped[float | None] = mapped_column(Float)
    # review
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|submitted|approved|rejected
    review_note: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    # live tracking state
    tracking_status: Mapped[str | None] = mapped_column(String(20))
    last_lat: Mapped[float | None] = mapped_column(Float)
    last_lon: Mapped[float | None] = mapped_column(Float)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="driller")
    documents: Mapped[list["DrillerDocument"]] = relationship(back_populates="driller", cascade="all, delete-orphan")
    equipment: Mapped[list["Equipment"]] = relationship(back_populates="driller", cascade="all, delete-orphan")


class DrillerDocument(Base):
    __tablename__ = "driller_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    driller_id: Mapped[int] = mapped_column(ForeignKey("driller_profiles.id"))
    doc_type: Mapped[str] = mapped_column(String(40))  # licence | permit | id_proof | environmental_clearance | insurance | other
    filename: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected
    note: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)

    driller: Mapped[DrillerProfile] = relationship(back_populates="documents")


class Equipment(Base):
    __tablename__ = "equipment"
    id: Mapped[int] = mapped_column(primary_key=True)
    driller_id: Mapped[int] = mapped_column(ForeignKey("driller_profiles.id"))
    name: Mapped[str] = mapped_column(String(120))
    rig_type: Mapped[str] = mapped_column(String(60))  # land rig | mobile rig | workover rig | coiled tubing
    max_depth_m: Mapped[float] = mapped_column(Float)
    max_horizontal_reach_m: Mapped[float] = mapped_column(Float)
    hook_load_t: Mapped[float | None] = mapped_column(Float)
    power_hp: Mapped[float | None] = mapped_column(Float)
    year_built: Mapped[int | None] = mapped_column(Integer)

    driller: Mapped[DrillerProfile] = relationship(back_populates="equipment")


# --------------------------------------------------------------------------- #
# Wells and the offset knowledge base
# --------------------------------------------------------------------------- #
class Field(Base):
    __tablename__ = "fields"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    operator: Mapped[str] = mapped_column(String(120))
    past_operators: Mapped[list] = mapped_column(JSON, default=list)
    discovery_year: Mapped[int | None] = mapped_column(Integer)
    basin: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(60))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(String(40))
    reserves_mmbbl: Mapped[float | None] = mapped_column(Float)
    production_bpd: Mapped[float | None] = mapped_column(Float)
    # reservoir parameters used by the volumetric estimate
    porosity: Mapped[float | None] = mapped_column(Float)
    water_saturation: Mapped[float | None] = mapped_column(Float)
    formation_volume_factor: Mapped[float | None] = mapped_column(Float)
    net_pay_m: Mapped[float | None] = mapped_column(Float)
    recovery_factor: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(200))


class Well(Base):
    __tablename__ = "wells"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    field_id: Mapped[int | None] = mapped_column(ForeignKey("fields.id"))
    operator: Mapped[str | None] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30))  # producing | abandoned | dry | suspended | drilling | shut-in
    well_type: Mapped[str] = mapped_column(String(30), default="vertical")
    spud_year: Mapped[int | None] = mapped_column(Integer)
    td_md_m: Mapped[float | None] = mapped_column(Float)
    td_tvd_m: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    current_depth_m: Mapped[float | None] = mapped_column(Float)
    planned_td_m: Mapped[float | None] = mapped_column(Float)
    outcome: Mapped[str | None] = mapped_column(String(30))  # success | marginal | dry | pending
    cum_oil_bbl: Mapped[float | None] = mapped_column(Float)
    initial_rate_bpd: Mapped[float | None] = mapped_column(Float)
    formation_tops: Mapped[list] = mapped_column(JSON, default=list)  # [{name, top_m, bottom_m}]
    trajectory: Mapped[dict | None] = mapped_column(JSON)             # {kop, build_rate, hold_inc, azimuth}
    casing_program: Mapped[list] = mapped_column(JSON, default=list)
    mud_program: Mapped[list] = mapped_column(JSON, default=list)
    cementing: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(200), default="Sample data")
    field: Mapped[Field | None] = relationship()


class DepthLog(Base):
    """Drilling parameters every 50 m (mud-logging style)."""
    __tablename__ = "depth_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id"), index=True)
    depth_m: Mapped[float] = mapped_column(Float)
    formation: Mapped[str] = mapped_column(String(80))
    rop_m_hr: Mapped[float] = mapped_column(Float)
    wob_t: Mapped[float] = mapped_column(Float)
    torque_knm: Mapped[float] = mapped_column(Float)
    rpm: Mapped[float] = mapped_column(Float)
    mud_weight_ppg: Mapped[float] = mapped_column(Float)
    pore_pressure_ppg: Mapped[float] = mapped_column(Float)
    gas_pct: Mapped[float] = mapped_column(Float)


class DrillingEvent(Base):
    __tablename__ = "drilling_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(30), index=True)  # MUD_LOSS | KICK | STUCK_PIPE | TORQUE_SPIKE | CEMENTING | NPT | FISHING
    depth_m: Mapped[float] = mapped_column(Float)
    formation: Mapped[str | None] = mapped_column(String(80))
    event_date: Mapped[str | None] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(10), default="medium")  # low | medium | high
    npt_hours: Mapped[float | None] = mapped_column(Float)
    mud_weight_ppg: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text)
    cause: Mapped[str | None] = mapped_column(Text)
    action_taken: Mapped[str | None] = mapped_column(Text)
    lesson: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200), default="Sample daily drilling report")
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    well: Mapped[Well] = relationship()


# --------------------------------------------------------------------------- #
# Land, zones and surface data
# --------------------------------------------------------------------------- #
class Zone(Base):
    __tablename__ = "zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    zone_type: Mapped[str] = mapped_column(String(40))  # protected_area | reserved_forest | wetland | restricted | urban | licensed_block
    legal_to_drill: Mapped[bool] = mapped_column(Boolean)
    authority: Mapped[str | None] = mapped_column(String(200))
    licensee: Mapped[str | None] = mapped_column(String(200))
    polygon: Mapped[list] = mapped_column(JSON)  # [[lat, lon], ...]
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200), default="Sample data")


class LandParcel(Base):
    __tablename__ = "land_parcels"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    village: Mapped[str | None] = mapped_column(String(120))
    min_lat: Mapped[float] = mapped_column(Float, index=True)
    max_lat: Mapped[float] = mapped_column(Float)
    min_lon: Mapped[float] = mapped_column(Float, index=True)
    max_lon: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))  # owned | leased | government | unclaimed
    holder: Mapped[str | None] = mapped_column(String(200))
    history: Mapped[list] = mapped_column(JSON, default=list)  # [{from, to, holder, type}]
    source: Mapped[str] = mapped_column(String(200), default="Sample data (no open land-record dataset)")


class CandidateLocation(Base):
    __tablename__ = "candidate_locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    target_formation: Mapped[str | None] = mapped_column(String(80))
    planned_td_m: Mapped[float | None] = mapped_column(Float)
    proposed_by: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="proposed")
    note: Mapped[str | None] = mapped_column(Text)


class LandslideEvent(Base):
    __tablename__ = "landslide_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    event_date: Mapped[str | None] = mapped_column(String(20))
    trigger: Mapped[str | None] = mapped_column(String(60))
    size: Mapped[str | None] = mapped_column(String(30))
    place: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(200))


class GeologyUnit(Base):
    __tablename__ = "geology_units"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    lithology: Mapped[str] = mapped_column(String(200))
    age: Mapped[str | None] = mapped_column(String(80))
    rock_class: Mapped[str] = mapped_column(String(40))  # alluvium | sedimentary | metamorphic | igneous
    strength: Mapped[float] = mapped_column(Float, default=0.5)  # 0 weak .. 1 strong (landslide input)
    petroleum_play: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1 prior for oil potential
    polygon: Mapped[list] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(200))


class SoilCache(Base):
    __tablename__ = "soil_cache"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# --------------------------------------------------------------------------- #
# Live tracking and alerts
# --------------------------------------------------------------------------- #
class TrackingPoint(Base):
    __tablename__ = "tracking_points"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class BreachEvent(Base):
    __tablename__ = "breach_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    distance_m: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[float] = mapped_column(Float)
    zone_name: Mapped[str | None] = mapped_column(String(200))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class WellAlert(Base):
    __tablename__ = "well_alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("wells.id"), index=True)
    alert_key: Mapped[str] = mapped_column(String(120), index=True)  # dedupe key
    alert_type: Mapped[str] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    formation: Mapped[str | None] = mapped_column(String(80))
    expected_depth_m: Mapped[float | None] = mapped_column(Float)
    depth_at_alert_m: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(300))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="processed")
    text_method: Mapped[str] = mapped_column(String(40))     # pdf-text | ocr | plain-text
    extract_method: Mapped[str] = mapped_column(String(40))  # llm | rules
    text_excerpt: Mapped[str | None] = mapped_column(Text)
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    well_id: Mapped[int | None] = mapped_column(ForeignKey("wells.id"))
    events_created: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

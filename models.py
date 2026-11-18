"""
SQLAlchemy and Pydantic models for Bengaluru SafeRoute.
Enforces complete provenance, verified types, and geospatial structures.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    ForeignKey,
    DateTime,
    Text
)
from sqlalchemy.orm import declarative_base, relationship
from pydantic import BaseModel, Field, field_validator

Base = declarative_base()


# ---------------------------------------------------------------------------
# SQLAlchemy Database Models
# ---------------------------------------------------------------------------

class SourceModel(Base):
    """Provenance and lineage registry for every safety record."""
    __tablename__ = "sources"

    source_id = Column(String(50), primary_key=True)
    source_name = Column(String(200), nullable=False)
    source_url = Column(String(500), nullable=False)
    source_type = Column(String(50), nullable=False)
    licence_or_usage_note = Column(Text, nullable=False)
    retrieved_at = Column(String(50), nullable=False)
    coverage_period = Column(String(100), nullable=False)
    verification_status = Column(String(50), nullable=False)
    last_updated = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)

    # Relationships
    accidents = relationship("AccidentModel", back_populates="source", cascade="all, delete-orphan")
    blackspots = relationship("BlackspotModel", back_populates="source", cascade="all, delete-orphan")
    speed_limits = relationship("SpeedLimitModel", back_populates="source", cascade="all, delete-orphan")
    road_curves = relationship("RoadCurveModel", back_populates="source", cascade="all, delete-orphan")


class AccidentModel(Base):
    """Accident incident record table."""
    __tablename__ = "accidents"

    accident_id = Column(String(50), primary_key=True)
    date = Column(String(20), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    road_name = Column(String(150), nullable=False)
    ward = Column(String(100), nullable=True)
    severity = Column(String(50), nullable=False)  # Fatal, Grievous, Minor
    vehicle_type = Column(String(50), nullable=True)
    cause = Column(Text, nullable=True)
    source_id = Column(String(50), ForeignKey("sources.source_id"), nullable=False)
    confidence_level = Column(String(50), nullable=False)

    source = relationship("SourceModel", back_populates="accidents")


class BlackspotModel(Base):
    """Identified high-frequency accident cluster / blackspot table."""
    __tablename__ = "blackspots"

    blackspot_id = Column(String(50), primary_key=True)
    name = Column(String(200), nullable=False)
    road_name = Column(String(150), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    radius_meters = Column(Float, nullable=False, default=100.0)
    accident_count = Column(Integer, nullable=False, default=0)
    fatal_count = Column(Integer, nullable=False, default=0)
    risk_score = Column(Float, nullable=False, default=0.0)
    status = Column(String(50), nullable=False)  # verified_official, verified_admin, demo
    source_id = Column(String(50), ForeignKey("sources.source_id"), nullable=False)
    verified_date = Column(String(20), nullable=False)

    source = relationship("SourceModel", back_populates="blackspots")


class SpeedLimitModel(Base):
    """Known and verified speed limits table."""
    __tablename__ = "speed_limits"

    speed_limit_id = Column(String(50), primary_key=True)
    road_name = Column(String(150), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed_kmph = Column(Integer, nullable=False)
    direction = Column(String(50), nullable=False, default="Both")
    source_id = Column(String(50), ForeignKey("sources.source_id"), nullable=False)
    verified_date = Column(String(20), nullable=False)
    confidence_level = Column(String(50), nullable=False)

    source = relationship("SourceModel", back_populates="speed_limits")


class RoadCurveModel(Base):
    """Detected or geometry-derived road curvature table."""
    __tablename__ = "road_curves"

    curve_id = Column(String(50), primary_key=True)
    road_name = Column(String(150), nullable=False)
    geometry = Column(Text, nullable=False)  # GeoJSON string or coordinate list
    curve_severity = Column(String(50), nullable=False)  # sharp, moderate, gentle
    estimated_radius_meters = Column(Float, nullable=True)
    warning_text = Column(Text, nullable=False)
    source_id = Column(String(50), ForeignKey("sources.source_id"), nullable=False)
    confidence_level = Column(String(50), nullable=False, default="geometry-derived")

    source = relationship("SourceModel", back_populates="road_curves")


# ---------------------------------------------------------------------------
# Pydantic Schemas for Validation and API Serialization
# ---------------------------------------------------------------------------

class SourceSchema(BaseModel):
    source_id: str = Field(..., min_length=2, max_length=50)
    source_name: str = Field(..., min_length=2, max_length=200)
    source_url: str
    source_type: str
    licence_or_usage_note: str
    retrieved_at: str
    coverage_period: str
    verification_status: str
    last_updated: str
    notes: Optional[str] = None


class AccidentSchema(BaseModel):
    accident_id: str
    date: str
    latitude: float = Field(..., ge=12.5, le=13.5)
    longitude: float = Field(..., ge=77.2, le=78.0)
    road_name: str
    ward: Optional[str] = "Bengaluru Urban"
    severity: str  # Fatal, Grievous, Minor
    vehicle_type: Optional[str] = "Unknown"
    cause: Optional[str] = "Unspecified"
    source_id: str
    confidence_level: str

    @field_validator("severity")
    def validate_severity(cls, v: str) -> str:
        valid = {"Fatal", "Grievous", "Minor", "fatal", "grievous", "minor"}
        if v.capitalize() not in {"Fatal", "Grievous", "Minor"}:
            raise ValueError(f"Severity must be Fatal, Grievous, or Minor. Got: {v}")
        return v.capitalize()


class BlackspotSchema(BaseModel):
    blackspot_id: str
    name: str
    road_name: str
    latitude: float = Field(..., ge=12.5, le=13.5)
    longitude: float = Field(..., ge=77.2, le=78.0)
    radius_meters: float = Field(100.0, ge=10.0, le=1000.0)
    accident_count: int = Field(0, ge=0)
    fatal_count: int = Field(0, ge=0)
    risk_score: float = Field(..., ge=0.0, le=100.0)
    status: str
    source_id: str
    verified_date: str

    @field_validator("status")
    def validate_status(cls, v: str) -> str:
        # Enforce that news articles cannot claim to be verified blackspots
        v_lower = v.lower()
        if "news" in v_lower:
            raise ValueError("News-derived records cannot be saved as verified blackspots.")
        return v


class SpeedLimitSchema(BaseModel):
    speed_limit_id: str
    road_name: str
    latitude: float = Field(..., ge=12.5, le=13.5)
    longitude: float = Field(..., ge=77.2, le=78.0)
    speed_kmph: int = Field(..., ge=10, le=120)
    direction: str = "Both"
    source_id: str
    verified_date: str
    confidence_level: str


class RoadCurveSchema(BaseModel):
    curve_id: str
    road_name: str
    geometry: str  # JSON coordinates or geometry string
    curve_severity: str  # sharp, moderate, gentle
    estimated_radius_meters: Optional[float] = None
    warning_text: str
    source_id: str
    confidence_level: str = "geometry-derived"

    @field_validator("curve_severity")
    def validate_curve_severity(cls, v: str) -> str:
        if v.lower() not in {"sharp", "moderate", "gentle"}:
            raise ValueError(f"Curve severity must be sharp, moderate, or gentle. Got: {v}")
        return v.lower()


class RouteRequest(BaseModel):
    start_lat: float
    start_lon: float
    dest_lat: float
    dest_lon: float
    mode: str = "car"
    corridor_buffer_meters: float = 30.0
    alternative_index: int = 0

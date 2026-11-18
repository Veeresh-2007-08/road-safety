"""
Database engine, session management, and startup data seeding for Bengaluru SafeRoute.
"""

import json
import logging
from pathlib import Path
import pandas as pd
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.config import DATABASE_URL, BASE_DIR, DATA_DIR
from src.models import (
    Base,
    SourceModel,
    AccidentModel,
    BlackspotModel,
    SpeedLimitModel,
    RoadCurveModel
)

logger = logging.getLogger(__name__)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Contextual database session generator."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables in SQLite."""
    Base.metadata.create_all(bind=engine)


def seed_sources_from_yaml(db: Session) -> int:
    """Populate the sources table from data_sources.yaml or data/sources.csv."""
    yaml_path = BASE_DIR / "data_sources.yaml"
    csv_path = DATA_DIR / "sources.csv"
    count = 0

    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            sources_list = data.get("sources", [])
            for s in sources_list:
                existing = db.query(SourceModel).filter_by(source_id=s["source_id"]).first()
                if not existing:
                    src_obj = SourceModel(
                        source_id=s["source_id"],
                        source_name=s["source_name"],
                        source_url=s["source_url"],
                        source_type=s["source_type"],
                        licence_or_usage_note=s["licence_or_usage_note"],
                        retrieved_at=s["retrieved_at"],
                        coverage_period=s["coverage_period"],
                        verification_status=s["verification_status"],
                        last_updated=s["last_updated"],
                        notes=s.get("notes")
                    )
                    db.add(src_obj)
                    count += 1
            db.commit()
    elif csv_path.exists():
        df = pd.read_csv(csv_path)
        for _, row in df.iterrows():
            existing = db.query(SourceModel).filter_by(source_id=row["source_id"]).first()
            if not existing:
                src_obj = SourceModel(
                    source_id=str(row["source_id"]),
                    source_name=str(row["source_name"]),
                    source_url=str(row["source_url"]),
                    source_type=str(row["source_type"]),
                    licence_or_usage_note=str(row["licence_or_usage_note"]),
                    retrieved_at=str(row["retrieved_at"]),
                    coverage_period=str(row["coverage_period"]),
                    verification_status=str(row["verification_status"]),
                    last_updated=str(row["last_updated"]),
                    notes=str(row.get("notes", ""))
                )
                db.add(src_obj)
                count += 1
        db.commit()

    return count


def seed_demo_data(db: Session) -> dict:
    """Seed demo datasets into database if empty."""
    counts = {"sources": 0, "accidents": 0, "blackspots": 0, "speed_limits": 0, "road_curves": 0}

    # 1. Sources
    counts["sources"] = seed_sources_from_yaml(db)

    # 2. Blackspots from demo_blackspots.geojson
    bs_path = DATA_DIR / "demo_blackspots.geojson"
    if bs_path.exists() and db.query(BlackspotModel).count() == 0:
        with open(bs_path, "r", encoding="utf-8") as f:
            geojson = json.load(f)
            for feat in geojson.get("features", []):
                props = feat.get("properties", {})
                coords = feat.get("geometry", {}).get("coordinates", [0, 0])
                bs_obj = BlackspotModel(
                    blackspot_id=props["blackspot_id"],
                    name=props["name"],
                    road_name=props["road_name"],
                    latitude=float(props.get("latitude", coords[1])),
                    longitude=float(props.get("longitude", coords[0])),
                    radius_meters=float(props.get("radius_meters", 100)),
                    accident_count=int(props.get("accident_count", 0)),
                    fatal_count=int(props.get("fatal_count", 0)),
                    risk_score=float(props.get("risk_score", 50.0)),
                    status=str(props.get("status", "demo")),
                    source_id=str(props.get("source_id", "SRC_DEMO_BENCHMARK")),
                    verified_date=str(props.get("verified_date", "2026-01-01"))
                )
                db.add(bs_obj)
                counts["blackspots"] += 1
            db.commit()

    # 3. Accidents from demo_accidents.csv
    acc_path = DATA_DIR / "demo_accidents.csv"
    if acc_path.exists() and db.query(AccidentModel).count() == 0:
        df = pd.read_csv(acc_path)
        for _, row in df.iterrows():
            acc_obj = AccidentModel(
                accident_id=str(row["accident_id"]),
                date=str(row["date"]),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                road_name=str(row["road_name"]),
                ward=str(row.get("ward", "Bengaluru Urban")),
                severity=str(row["severity"]),
                vehicle_type=str(row.get("vehicle_type", "Unknown")),
                cause=str(row.get("cause", "Unspecified")),
                source_id=str(row["source_id"]),
                confidence_level=str(row["confidence_level"])
            )
            db.add(acc_obj)
            counts["accidents"] += 1
        db.commit()

    # 4. Speed Limits from demo_speed_limits.csv
    spd_path = DATA_DIR / "demo_speed_limits.csv"
    if spd_path.exists() and db.query(SpeedLimitModel).count() == 0:
        df = pd.read_csv(spd_path)
        for _, row in df.iterrows():
            spd_obj = SpeedLimitModel(
                speed_limit_id=str(row["speed_limit_id"]),
                road_name=str(row["road_name"]),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                speed_kmph=int(row["speed_kmph"]),
                direction=str(row.get("direction", "Both")),
                source_id=str(row["source_id"]),
                verified_date=str(row["verified_date"]),
                confidence_level=str(row["confidence_level"])
            )
            db.add(spd_obj)
            counts["speed_limits"] += 1
        db.commit()

    # 5. Curves from demo_curves.geojson
    crv_path = DATA_DIR / "demo_curves.geojson"
    if crv_path.exists() and db.query(RoadCurveModel).count() == 0:
        with open(crv_path, "r", encoding="utf-8") as f:
            geojson = json.load(f)
            for feat in geojson.get("features", []):
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})
                crv_obj = RoadCurveModel(
                    curve_id=props["curve_id"],
                    road_name=props["road_name"],
                    geometry=json.dumps(geom),
                    curve_severity=str(props["curve_severity"]),
                    estimated_radius_meters=float(props["estimated_radius_meters"]) if props.get("estimated_radius_meters") else None,
                    warning_text=str(props["warning_text"]),
                    source_id=str(props["source_id"]),
                    confidence_level=str(props.get("confidence_level", "geometry-derived (demo)"))
                )
                db.add(crv_obj)
                counts["road_curves"] += 1
            db.commit()

    return counts


def init_and_seed_db(force_reseed: bool = False):
    """Convenience bootstrap function."""
    init_db()
    with SessionLocal() as db:
        if force_reseed:
            db.query(AccidentModel).delete()
            db.query(BlackspotModel).delete()
            db.query(SpeedLimitModel).delete()
            db.query(RoadCurveModel).delete()
            db.query(SourceModel).delete()
            db.commit()
        return seed_demo_data(db)

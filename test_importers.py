"""
Tests for data import and validation logic.
"""

import sys
import json
from pathlib import Path
import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models import Base, SourceModel
from src.database import seed_sources_from_yaml, seed_demo_data
from src.importers import (
    import_accidents_from_df,
    import_blackspots_from_geojson,
    import_speed_limits_from_df
)

# ── In-memory SQLite for all tests ──────────────────────────────────────────
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
TestSession = sessionmaker(bind=engine)


def fresh_db():
    db = TestSession()
    # Pre-seed required source
    if not db.query(SourceModel).filter_by(source_id="SRC_DEMO_BENCHMARK").first():
        db.add(SourceModel(
            source_id="SRC_DEMO_BENCHMARK",
            source_name="Bengaluru SafeRoute Synthetic Benchmark Dataset",
            source_url="local://demo-data",
            source_type="demonstration_synthetic",
            licence_or_usage_note="Demonstration and Educational Testing Only",
            retrieved_at="2026-03-15T00:00:00",
            coverage_period="Demonstration Sample",
            verification_status="demo",
            last_updated="2026-03-15",
            notes="Demo dataset."
        ))
        db.add(SourceModel(
            source_id="SRC_NEWS_ARCHIVE",
            source_name="Local Media Traffic News Archive",
            source_url="https://timesofindia.indiatimes.com/city/bengaluru",
            source_type="media_report",
            licence_or_usage_note="Reference Only - Unverified",
            retrieved_at="2026-01-10T11:00:00",
            coverage_period="2024-2025",
            verification_status="unverified_reference",
            last_updated="2026-01-10",
            notes="Media reports stored as reference only."
        ))
        db.commit()
    return db


# ── Accident Import Tests ─────────────────────────────────────────────────────

class TestAccidentImport:
    def test_valid_accident_records_are_imported(self):
        db = fresh_db()
        df = pd.DataFrame([{
            "accident_id": "ACC_TEST_001",
            "date": "2025-10-10",
            "latitude": 12.9177,
            "longitude": 77.6238,
            "road_name": "Hosur Road",
            "ward": "Madivala",
            "severity": "Fatal",
            "vehicle_type": "Two-wheeler",
            "cause": "Rear-end collision",
            "source_id": "SRC_DEMO_BENCHMARK",
            "confidence_level": "demo"
        }])
        result = import_accidents_from_df(df, db)
        assert result["imported"] == 1
        assert result["errors"] == []
        db.close()

    def test_severity_normalization(self):
        db = fresh_db()
        df = pd.DataFrame([{
            "accident_id": "ACC_TEST_002",
            "date": "2025-10-11",
            "latitude": 12.9200,
            "longitude": 77.6300,
            "road_name": "Outer Ring Road",
            "ward": "HSR Layout",
            "severity": "grievous",   # lowercase input
            "vehicle_type": "Car",
            "cause": "Braking",
            "source_id": "SRC_DEMO_BENCHMARK",
            "confidence_level": "demo"
        }])
        result = import_accidents_from_df(df, db)
        assert result["imported"] == 1
        db.close()

    def test_out_of_bounds_latitude_rejected(self):
        db = fresh_db()
        df = pd.DataFrame([{
            "accident_id": "ACC_TEST_003",
            "date": "2025-10-12",
            "latitude": 14.5,  # outside Bengaluru bbox
            "longitude": 77.5,
            "road_name": "Some Road",
            "severity": "Minor",
            "source_id": "SRC_DEMO_BENCHMARK",
            "confidence_level": "demo"
        }])
        result = import_accidents_from_df(df, db)
        assert result["imported"] == 0
        assert len(result["errors"]) == 1
        db.close()

    def test_missing_source_id_rejected(self):
        db = fresh_db()
        df = pd.DataFrame([{
            "accident_id": "ACC_TEST_004",
            "date": "2025-10-13",
            "latitude": 12.95,
            "longitude": 77.60,
            "road_name": "MG Road",
            "severity": "Minor",
            "source_id": "SRC_NONEXISTENT_999",  # No such source
            "confidence_level": "demo"
        }])
        result = import_accidents_from_df(df, db)
        assert result["imported"] == 0
        assert any("Foreign key" in e or "not found" in e for e in result["errors"])
        db.close()

    def test_invalid_severity_raises_error(self):
        db = fresh_db()
        df = pd.DataFrame([{
            "accident_id": "ACC_TEST_005",
            "date": "2025-10-14",
            "latitude": 12.96,
            "longitude": 77.61,
            "road_name": "Residency Road",
            "severity": "Critical",   # Not a valid severity
            "source_id": "SRC_DEMO_BENCHMARK",
            "confidence_level": "demo"
        }])
        result = import_accidents_from_df(df, db)
        assert result["imported"] == 0
        db.close()


# ── Blackspot Import Tests ────────────────────────────────────────────────────

class TestBlackspotImport:
    def _make_geojson(self, props):
        return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [props.get("longitude", 77.62), props.get("latitude", 12.91)]},
                "properties": props
            }]
        }

    def test_valid_blackspot_imported(self):
        db = fresh_db()
        gj = self._make_geojson({
            "blackspot_id": "BS_TEST_001",
            "name": "Test Junction",
            "road_name": "Hosur Road",
            "latitude": 12.9177,
            "longitude": 77.6238,
            "radius_meters": 100,
            "accident_count": 15,
            "fatal_count": 3,
            "risk_score": 75.0,
            "status": "demo",
            "source_id": "SRC_DEMO_BENCHMARK",
            "verified_date": "2026-01-01"
        })
        result = import_blackspots_from_geojson(gj, db)
        assert result["imported"] == 1
        assert result["errors"] == []
        db.close()

    def test_news_source_cannot_create_verified_blackspot(self):
        """Core policy test: news/media records must never become verified blackspots."""
        db = fresh_db()
        gj = self._make_geojson({
            "blackspot_id": "BS_TEST_NEWS_001",
            "name": "Newspaper Reported Spot",
            "road_name": "Some Road",
            "latitude": 12.93,
            "longitude": 77.59,
            "radius_meters": 80,
            "accident_count": 5,
            "fatal_count": 1,
            "risk_score": 65.0,
            "status": "verified_official",   # Attempting to claim official verification
            "source_id": "SRC_NEWS_ARCHIVE",  # But source is news/media
            "verified_date": "2026-01-05"
        })
        result = import_blackspots_from_geojson(gj, db)
        assert result["imported"] == 0
        assert any("Media" in e or "News" in e or "REJECTED" in e for e in result["errors"])
        db.close()

    def test_risk_score_out_of_range_rejected(self):
        db = fresh_db()
        gj = self._make_geojson({
            "blackspot_id": "BS_TEST_002",
            "name": "Over-scored spot",
            "road_name": "Outer Ring Road",
            "latitude": 12.91,
            "longitude": 77.62,
            "radius_meters": 100,
            "accident_count": 5,
            "fatal_count": 1,
            "risk_score": 150.0,  # > 100.0 — invalid
            "status": "demo",
            "source_id": "SRC_DEMO_BENCHMARK",
            "verified_date": "2026-01-01"
        })
        result = import_blackspots_from_geojson(gj, db)
        assert result["imported"] == 0
        db.close()


# ── Speed Limit Import Tests ──────────────────────────────────────────────────

class TestSpeedLimitImport:
    def test_valid_speed_limit_record(self):
        db = fresh_db()
        df = pd.DataFrame([{
            "speed_limit_id": "SPD_TEST_001",
            "road_name": "Hosur Elevated Expressway",
            "latitude": 12.90,
            "longitude": 77.63,
            "speed_kmph": 80,
            "direction": "Both",
            "source_id": "SRC_DEMO_BENCHMARK",
            "verified_date": "2026-02-01",
            "confidence_level": "verified_demo"
        }])
        result = import_speed_limits_from_df(df, db)
        assert result["imported"] == 1
        db.close()

    def test_speed_above_120_rejected(self):
        db = fresh_db()
        df = pd.DataFrame([{
            "speed_limit_id": "SPD_TEST_002",
            "road_name": "Expressway",
            "latitude": 12.91,
            "longitude": 77.64,
            "speed_kmph": 180,   # unrealistic / invalid
            "direction": "Both",
            "source_id": "SRC_DEMO_BENCHMARK",
            "verified_date": "2026-02-01",
            "confidence_level": "demo"
        }])
        result = import_speed_limits_from_df(df, db)
        assert result["imported"] == 0
        db.close()

    def test_speed_below_minimum_rejected(self):
        db = fresh_db()
        df = pd.DataFrame([{
            "speed_limit_id": "SPD_TEST_003",
            "road_name": "Some Road",
            "latitude": 12.92,
            "longitude": 77.65,
            "speed_kmph": 5,   # below 10 kmph minimum
            "direction": "Both",
            "source_id": "SRC_DEMO_BENCHMARK",
            "verified_date": "2026-02-01",
            "confidence_level": "demo"
        }])
        result = import_speed_limits_from_df(df, db)
        assert result["imported"] == 0
        db.close()

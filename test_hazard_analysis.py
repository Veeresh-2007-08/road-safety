"""
Tests for route-corridor hazard matching and risk-score calculation.
"""

import sys
import json
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shapely.geometry import LineString, Point
from shapely.ops import transform
import pyproj

from src.models import Base, SourceModel, BlackspotModel, AccidentModel, SpeedLimitModel
from src.hazard_analysis import create_safety_corridor, analyze_corridor_hazards
from src.config import PROJECTED_CRS, GEOGRAPHIC_CRS

# ── In-memory test DB ─────────────────────────────────────────────────────────
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
TestSession = sessionmaker(bind=engine)

transformer_to_projected = pyproj.Transformer.from_crs(GEOGRAPHIC_CRS, PROJECTED_CRS, always_xy=True).transform
transformer_to_geographic = pyproj.Transformer.from_crs(PROJECTED_CRS, GEOGRAPHIC_CRS, always_xy=True).transform


def _seed_test_db(db):
    """Seed minimal test data."""
    if not db.query(SourceModel).filter_by(source_id="SRC_DEMO_BENCHMARK").first():
        db.add(SourceModel(
            source_id="SRC_DEMO_BENCHMARK",
            source_name="Test Demo Source",
            source_url="local://demo",
            source_type="demonstration_synthetic",
            licence_or_usage_note="Test Only",
            retrieved_at="2026-01-01",
            coverage_period="2026",
            verification_status="demo",
            last_updated="2026-01-01",
            notes="Test source"
        ))
    db.commit()


# ── Corridor Creation Tests ───────────────────────────────────────────────────

class TestCorridorCreation:
    def test_corridor_has_nonzero_area(self):
        coords = [(12.9177, 77.6238), (12.9344, 77.6258), (12.9553, 77.7011)]
        _, corridor_utm, geojson = create_safety_corridor(coords, buffer_meters=30.0)
        assert corridor_utm.area > 0, "Corridor polygon must have non-zero area"

    def test_corridor_contains_route_points(self):
        """An actual waypoint on the route must fall within the safety corridor."""
        coords = [(12.9177, 77.6238), (12.9344, 77.6258), (12.9553, 77.7011)]
        _, corridor_utm, _ = create_safety_corridor(coords, buffer_meters=30.0)
        # Use the SECOND waypoint which is exactly on the route
        on_route_pt = Point(77.6258, 12.9344)   # (lon, lat) for Shapely
        on_route_utm = transform(transformer_to_projected, on_route_pt)
        # Must be within or exactly on the boundary (distance = 0 for route waypoints)
        assert corridor_utm.contains(on_route_utm) or corridor_utm.distance(on_route_utm) < 1.0

    def test_corridor_excludes_distant_points(self):
        """A point 5 km away must NOT intersect the corridor."""
        coords = [(12.9177, 77.6238), (12.9344, 77.6258)]
        _, corridor_utm, _ = create_safety_corridor(coords, buffer_meters=30.0)
        far_pt = Point(77.3000, 12.6000)   # ~40 km SW
        far_pt_utm = transform(transformer_to_projected, far_pt)
        assert not corridor_utm.contains(far_pt_utm)
        assert corridor_utm.distance(far_pt_utm) > 1000.0

    def test_minimum_route_length(self):
        """Single-point routes should raise an error."""
        with pytest.raises(ValueError):
            create_safety_corridor([(12.9177, 77.6238)], buffer_meters=30.0)


# ── Hazard Matching Tests ─────────────────────────────────────────────────────

class TestHazardMatching:
    # Route: Silk Board → Marathahalli (east along ORR)
    ROUTE_COORDS = [
        (12.9177, 77.6238),
        (12.9280, 77.6500),
        (12.9400, 77.6700),
        (12.9553, 77.7011)
    ]

    def _build_route_primitives(self):
        route_line = LineString([(lon, lat) for lat, lon in self.ROUTE_COORDS])
        _, corridor_utm, _ = create_safety_corridor(self.ROUTE_COORDS, 30.0)
        return route_line, corridor_utm

    def test_on_route_blackspot_is_matched(self):
        """A blackspot placed directly on the route must be matched."""
        db = TestSession()
        _seed_test_db(db)
        # Blackspot on midpoint of route
        db.add(BlackspotModel(
            blackspot_id="BS_HAZ_001",
            name="On-route Test Blackspot",
            road_name="Outer Ring Road Test",
            latitude=12.9400,
            longitude=77.6700,
            radius_meters=100.0,
            accident_count=10,
            fatal_count=2,
            risk_score=80.0,
            status="demo",
            source_id="SRC_DEMO_BENCHMARK",
            verified_date="2026-01-01"
        ))
        db.commit()

        route_line, corridor_utm = self._build_route_primitives()
        result = analyze_corridor_hazards(db, corridor_utm, route_line, buffer_meters=30.0, mode="car")
        matched_ids = [b["id"] for b in result["matched_hazards"]["blackspots"]]
        assert "BS_HAZ_001" in matched_ids
        db.close()

    def test_off_route_blackspot_not_matched(self):
        """A blackspot 15 km away must NOT be matched."""
        db = TestSession()
        _seed_test_db(db)
        db.add(BlackspotModel(
            blackspot_id="BS_HAZ_OFFROUTE",
            name="Far Away Spot",
            road_name="Somewhere Else",
            latitude=13.3000,     # ~40 km north
            longitude=77.9000,
            radius_meters=50.0,
            accident_count=5,
            fatal_count=1,
            risk_score=50.0,
            status="demo",
            source_id="SRC_DEMO_BENCHMARK",
            verified_date="2026-01-01"
        ))
        db.commit()

        route_line, corridor_utm = self._build_route_primitives()
        result = analyze_corridor_hazards(db, corridor_utm, route_line, buffer_meters=30.0, mode="car")
        matched_ids = [b["id"] for b in result["matched_hazards"]["blackspots"]]
        assert "BS_HAZ_OFFROUTE" not in matched_ids
        db.close()

    def test_on_route_accident_matched(self):
        db = TestSession()
        _seed_test_db(db)
        db.add(AccidentModel(
            accident_id="ACC_HAZ_001",
            date="2025-12-01",
            latitude=12.9280,
            longitude=77.6500,
            road_name="ORR Bellandur",
            ward="HSR",
            severity="Grievous",
            vehicle_type="Two-wheeler",
            cause="Skid",
            source_id="SRC_DEMO_BENCHMARK",
            confidence_level="demo"
        ))
        db.commit()

        route_line, corridor_utm = self._build_route_primitives()
        result = analyze_corridor_hazards(db, corridor_utm, route_line, buffer_meters=30.0, mode="car")
        matched_ids = [a["id"] for a in result["matched_hazards"]["accidents"]]
        assert "ACC_HAZ_001" in matched_ids
        db.close()


# ── Risk Score Tests ──────────────────────────────────────────────────────────

class TestRiskScore:
    ROUTE_COORDS = [
        (12.9177, 77.6238),
        (12.9344, 77.6258),
        (12.9553, 77.7011)
    ]

    def test_score_bounded_zero_to_100(self):
        db = TestSession()
        _seed_test_db(db)
        route_line = LineString([(lon, lat) for lat, lon in self.ROUTE_COORDS])
        _, corridor_utm, _ = create_safety_corridor(self.ROUTE_COORDS, 30.0)
        result = analyze_corridor_hazards(db, corridor_utm, route_line, mode="car")
        score = result["final_risk_score"]
        assert 0.0 <= score <= 100.0, f"Risk score out of range: {score}"
        db.close()

    def test_pedestrian_higher_score_than_car_same_route(self):
        """Pedestrian vulnerability multiplier > 1.0 raises score for identical routes."""
        db = TestSession()
        _seed_test_db(db)
        db.add(BlackspotModel(
            blackspot_id="BS_SCORE_001",
            name="Score Test Blackspot",
            road_name="ORR",
            latitude=12.9344,
            longitude=77.6258,
            radius_meters=100.0,
            accident_count=12,
            fatal_count=3,
            risk_score=80.0,
            status="demo",
            source_id="SRC_DEMO_BENCHMARK",
            verified_date="2026-01-01"
        ))
        db.commit()

        route_line = LineString([(lon, lat) for lat, lon in self.ROUTE_COORDS])
        _, corridor_utm, _ = create_safety_corridor(self.ROUTE_COORDS, 30.0)

        result_car = analyze_corridor_hazards(db, corridor_utm, route_line, mode="car")
        result_ped = analyze_corridor_hazards(db, corridor_utm, route_line, mode="pedestrian")

        # Pedestrian score must be >= car score (same hazards, higher vulnerability)
        assert result_ped["final_risk_score"] >= result_car["final_risk_score"]
        db.close()

    def test_zero_hazards_score_is_low(self):
        """A corridor with no recorded hazards should return a low or zero score."""
        db = TestSession()
        _seed_test_db(db)
        # Use a remote coordinates patch with no hazards
        far_coords = [(12.5100, 77.2100), (12.5200, 77.2200)]
        route_line = LineString([(lon, lat) for lat, lon in far_coords])
        _, corridor_utm, _ = create_safety_corridor(far_coords, 30.0)
        result = analyze_corridor_hazards(db, corridor_utm, route_line, mode="car")
        # With no hazards, only possible penalty is unknown_speed_limit (5 × 1.0)
        assert result["final_risk_score"] <= 10.0
        db.close()

    def test_fatal_accidents_add_to_score(self):
        """Adding a fatal accident near the route should increase the score."""
        db = TestSession()
        _seed_test_db(db)

        base_coords = [(12.9177, 77.6238), (12.9344, 77.6258)]
        route_line = LineString([(lon, lat) for lat, lon in base_coords])
        _, corridor_utm, _ = create_safety_corridor(base_coords, 30.0)

        result_before = analyze_corridor_hazards(db, corridor_utm, route_line, mode="car")

        # Add a fatal accident on route
        db.add(AccidentModel(
            accident_id="ACC_SCORE_FATAL",
            date="2025-12-15",
            latitude=12.9177,
            longitude=77.6238,
            road_name="Hosur Road",
            severity="Fatal",
            source_id="SRC_DEMO_BENCHMARK",
            confidence_level="demo"
        ))
        db.commit()

        result_after = analyze_corridor_hazards(db, corridor_utm, route_line, mode="car")
        assert result_after["final_risk_score"] > result_before["final_risk_score"]
        db.close()

    def test_score_components_sum_matches_raw_total(self):
        db = TestSession()
        _seed_test_db(db)
        route_line = LineString([(lon, lat) for lat, lon in [(12.92, 77.63), (12.93, 77.64)]])
        _, corridor_utm, _ = create_safety_corridor([(12.92, 77.63), (12.93, 77.64)], 30.0)
        result = analyze_corridor_hazards(db, corridor_utm, route_line, mode="car")
        sc = result["score_components"]
        # Sum of individual components (divided back by multiplier) ≈ raw_total
        component_sum = (
            sc["blackspot_penalty"] +
            sc["fatal_accident_penalty"] +
            sc["grievous_accident_penalty"] +
            sc["minor_accident_penalty"] +
            sc["sharp_curve_penalty"] +
            sc["moderate_curve_penalty"] +
            sc["unknown_speed_penalty"]
        )
        assert abs(component_sum - sc["raw_total"]) < 0.1
        db.close()

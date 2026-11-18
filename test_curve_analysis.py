"""
Tests for road geometry curve detection and severity classification.
"""

import sys
import math
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.curve_analysis import (
    calculate_bearing,
    calculate_bearing_difference,
    haversine_distance_meters,
    classify_curve_severity,
    detect_curves_from_coordinates
)


class TestBearingCalculation:
    def test_north_bearing(self):
        """Due north should give ~0°."""
        b = calculate_bearing(12.9000, 77.6000, 13.0000, 77.6000)
        assert abs(b - 0.0) < 1.0, f"Expected ~0°, got {b}"

    def test_east_bearing(self):
        """Due east should give ~90°."""
        b = calculate_bearing(12.9000, 77.6000, 12.9000, 77.7000)
        assert abs(b - 90.0) < 2.0, f"Expected ~90°, got {b}"

    def test_south_bearing(self):
        """Due south should give ~180°."""
        b = calculate_bearing(13.0000, 77.6000, 12.9000, 77.6000)
        assert abs(b - 180.0) < 1.5, f"Expected ~180°, got {b}"


class TestBearingDifference:
    def test_right_turn(self):
        """Turning from east to south should be a positive (right) deflection."""
        diff = calculate_bearing_difference(90.0, 180.0)
        assert diff > 0

    def test_left_turn(self):
        """Turning from east to north should be a negative (left) deflection."""
        diff = calculate_bearing_difference(90.0, 0.0)
        assert diff < 0

    def test_straight_line_no_deflection(self):
        """No bearing change should give near-zero deflection."""
        diff = calculate_bearing_difference(45.0, 45.0)
        assert abs(diff) < 0.01

    def test_wraparound_north(self):
        """Bearings crossing 360°/0° boundary handled correctly."""
        diff = calculate_bearing_difference(350.0, 10.0)
        assert abs(diff - 20.0) < 1.0


class TestHaversineDistance:
    def test_known_distance(self):
        """
        Silk Board to Hebbal is roughly 14 km along Bellary Road.
        Straight-line great-circle should be ~12.5 km.
        """
        d = haversine_distance_meters(12.9177, 77.6238, 13.0359, 77.5971)
        assert 10_000 < d < 15_000, f"Expected ~12.5km, got {d/1000:.2f}km"

    def test_same_point_zero(self):
        d = haversine_distance_meters(12.9177, 77.6238, 12.9177, 77.6238)
        assert d == 0.0

    def test_symmetry(self):
        """Distance A→B must equal distance B→A."""
        d1 = haversine_distance_meters(12.9177, 77.6238, 12.9553, 77.7011)
        d2 = haversine_distance_meters(12.9553, 77.7011, 12.9177, 77.6238)
        assert abs(d1 - d2) < 0.01


class TestCurveSeverityClassification:
    def test_sharp_high_deflection(self):
        severity, _, _ = classify_curve_severity(50.0, 60.0)
        assert severity == "sharp"

    def test_moderate_mid_deflection(self):
        severity, _, _ = classify_curve_severity(25.0, 100.0)
        assert severity == "moderate"

    def test_gentle_low_deflection(self):
        severity, _, _ = classify_curve_severity(10.0, 150.0)
        assert severity == "gentle"

    def test_straight_zero_deflection(self):
        severity, _, _ = classify_curve_severity(1.0, 200.0)
        assert severity == "straight"

    def test_radius_estimated_for_sufficient_deflection(self):
        """Radius should be estimated when deflection ≥ ~4.5°."""
        _, est_radius, _ = classify_curve_severity(45.0, 80.0)
        assert est_radius is not None
        assert 20.0 <= est_radius <= 300.0

    def test_no_radius_for_tiny_deflection(self):
        """Radius should NOT be claimed for tiny (<4.5°) deflection."""
        _, est_radius, _ = classify_curve_severity(2.0, 50.0)
        assert est_radius is None


class TestCurveDetection:
    def test_straight_road_no_sharp_curves(self):
        """A perfectly straight north-south road should produce no sharp/moderate curves."""
        straight = [(12.90, 77.60), (12.92, 77.60), (12.94, 77.60), (12.96, 77.60)]
        curves = detect_curves_from_coordinates(straight)
        # May have tiny floating-point deflections but no meaningful curves
        severe_curves = [c for c in curves if c["curve_severity"] in ("sharp", "moderate")]
        assert len(severe_curves) == 0, f"Straight road should have no sharp/moderate curves; got {severe_curves}"

    def test_sharp_bend_detected(self):
        """An abrupt 90° corner must be detected as a sharp curve."""
        # Route going east then abruptly north
        bend = [
            (12.9000, 77.5000),
            (12.9000, 77.6000),  # going east
            (13.0000, 77.6000)   # sharp turn north
        ]
        curves = detect_curves_from_coordinates(bend)
        sharp = [c for c in curves if c["curve_severity"] == "sharp"]
        assert len(sharp) >= 1, "90° turn should be detected as sharp curve"

    def test_curve_has_required_fields(self):
        """Every detected curve must carry required provenance fields."""
        bend = [
            (12.9177, 77.6238),
            (12.9177, 77.6400),
            (12.9344, 77.6400)
        ]
        curves = detect_curves_from_coordinates(bend, road_name="Test Road", source_id="SRC_DEMO_BENCHMARK")
        for c in curves:
            assert "curve_id" in c
            assert "road_name" in c
            assert "curve_severity" in c
            assert "warning_text" in c
            assert "source_id" in c
            assert c["confidence_level"] == "geometry-derived"

    def test_too_few_points_returns_empty(self):
        """Less than 3 points should return an empty list, not raise."""
        result = detect_curves_from_coordinates([(12.9177, 77.6238), (12.9344, 77.6258)])
        assert result == []

    def test_empty_coords_returns_empty(self):
        result = detect_curves_from_coordinates([])
        assert result == []

    def test_confidence_always_geometry_derived(self):
        """Detected curves must NEVER claim to be verified by field survey."""
        bend = [
            (12.9000, 77.5000),
            (12.9000, 77.6000),
            (12.9500, 77.6000)
        ]
        curves = detect_curves_from_coordinates(bend)
        for c in curves:
            assert c["confidence_level"] == "geometry-derived", (
                f"Confidence must be 'geometry-derived', not '{c['confidence_level']}'"
            )

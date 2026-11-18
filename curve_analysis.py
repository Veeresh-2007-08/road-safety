"""
Road geometry curve detection and severity classification module.
Analyzes road polyline coordinates, segment bearings, and deflection rates.
All detected records are strictly tagged as 'geometry-derived'.
"""

import math
from typing import List, Tuple, Dict, Any, Optional


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate initial compass bearing from point 1 to point 2 in degrees [0, 360).
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing_rad = math.atan2(y, x)
    bearing_deg = (math.degrees(bearing_rad) + 360.0) % 360.0
    return bearing_deg


def calculate_bearing_difference(bearing1: float, bearing2: float) -> float:
    """
    Compute signed minimal angle difference from bearing1 to bearing2 in degrees [-180, 180].
    Positive indicates right turn, negative indicates left turn.
    """
    diff = (bearing2 - bearing1 + 180.0) % 360.0 - 180.0
    return diff


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance between two geographic coordinates in meters.
    """
    r = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def split_segment(p1: Tuple[float, float], p2: Tuple[float, float], max_length_m: float = 40.0) -> List[Tuple[float, float]]:
    """
    Subdivide long line segment into subsegments not exceeding max_length_m.
    Coordinates are (lat, lon).
    """
    dist = haversine_distance_meters(p1[0], p1[1], p2[0], p2[1])
    if dist <= max_length_m or dist == 0:
        return [p1, p2]

    num_segments = math.ceil(dist / max_length_m)
    points = [p1]
    for i in range(1, num_segments):
        fraction = i / float(num_segments)
        lat = p1[0] + fraction * (p2[0] - p1[0])
        lon = p1[1] + fraction * (p2[1] - p1[1])
        points.append((lat, lon))
    points.append(p2)
    return points


def classify_curve_severity(deflection_deg: float, length_m: float) -> Tuple[str, Optional[float], str]:
    """
    Classify curvature based on heading deflection and segment length.
    Returns: (severity, estimated_radius_meters, rationale)
    """
    abs_deflection = abs(deflection_deg)

    # Calculate deflection rate per 100 meters
    if length_m > 0:
        rate_per_100m = (abs_deflection / length_m) * 100.0
    else:
        rate_per_100m = 0.0

    # Reliable radius estimation: R = L / radians(deflection)
    rad = math.radians(abs_deflection)
    if rad > 0.08:  # at least ~4.5 degrees deflection
        calc_radius = length_m / rad
        if 15.0 <= calc_radius <= 600.0:
            est_radius = round(calc_radius, 1)
        else:
            est_radius = None
    else:
        est_radius = None

    if abs_deflection >= 42.0 or (rate_per_100m >= 38.0 and abs_deflection >= 25.0):
        severity = "sharp"
        rationale = f"Severe turn ({abs_deflection:.1f}° deflection over {length_m:.0f}m). High rollover and blind-spot risk."
    elif abs_deflection >= 20.0 or (rate_per_100m >= 20.0 and abs_deflection >= 14.0):
        severity = "moderate"
        rationale = f"Moderate curve ({abs_deflection:.1f}° deflection over {length_m:.0f}m). Requires steering adjustment."
    elif abs_deflection >= 8.0:
        severity = "gentle"
        rationale = f"Gentle curve ({abs_deflection:.1f}° deflection over {length_m:.0f}m). Standard corridor bend."
    else:
        severity = "straight"
        rationale = "Nearly straight section."

    return severity, est_radius, rationale


def detect_curves_from_coordinates(
    coords: List[Tuple[float, float]],
    road_name: str = "Bengaluru Corridor",
    source_id: str = "SRC_OSM_OVERPASS",
    prefix_id: str = "CRV_CALC"
) -> List[Dict[str, Any]]:
    """
    Analyze sequence of (lat, lon) coordinates along a road or route and return detected curves.
    All returned curve entities are marked confidence_level='geometry-derived'.
    """
    if len(coords) < 3:
        return []

    # Subdivide polyline into balanced segments
    subdivided_points: List[Tuple[float, float]] = []
    for i in range(len(coords) - 1):
        seg = split_segment(coords[i], coords[i + 1], max_length_m=45.0)
        if not subdivided_points:
            subdivided_points.extend(seg)
        else:
            subdivided_points.extend(seg[1:])

    detected_curves = []
    curve_counter = 1

    for i in range(1, len(subdivided_points) - 1):
        p_prev = subdivided_points[i - 1]
        p_curr = subdivided_points[i]
        p_next = subdivided_points[i + 1]

        b_in = calculate_bearing(p_prev[0], p_prev[1], p_curr[0], p_curr[1])
        b_out = calculate_bearing(p_curr[0], p_curr[1], p_next[0], p_next[1])
        deflection = calculate_bearing_difference(b_in, b_out)

        d1 = haversine_distance_meters(p_prev[0], p_prev[1], p_curr[0], p_curr[1])
        d2 = haversine_distance_meters(p_curr[0], p_curr[1], p_next[0], p_next[1])
        avg_len = (d1 + d2) / 2.0

        severity, est_radius, rationale = classify_curve_severity(deflection, avg_len)

        if severity in ("sharp", "moderate"):
            turn_direction = "right" if deflection > 0 else "left"
            warning_text = (
                f"{severity.capitalize()} {turn_direction} bend detected: {rationale} "
                f"{f'Estimated radius: {est_radius}m.' if est_radius else 'Radius not determinable without CAD alignment.'} "
                f"Reduce speed before entering."
            )

            curve_id = f"{prefix_id}_{curve_counter:03d}"
            curve_counter += 1

            detected_curves.append({
                "curve_id": curve_id,
                "road_name": road_name,
                "latitude": p_curr[0],
                "longitude": p_curr[1],
                "coordinates": [
                    [p_prev[1], p_prev[0]],
                    [p_curr[1], p_curr[0]],
                    [p_next[1], p_next[0]]
                ],
                "curve_severity": severity,
                "deflection_degrees": round(abs(deflection), 1),
                "estimated_radius_meters": est_radius,
                "warning_text": warning_text,
                "source_id": source_id,
                "confidence_level": "geometry-derived"
            })

    return detected_curves

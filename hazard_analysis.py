"""
Route safety corridor generation, hazard spatial querying, and transparent risk scoring.
All distance buffering and intersection checks utilize UTM Zone 43N (EPSG:32643).
"""

import json
from typing import List, Tuple, Dict, Any, Optional
from shapely.geometry import LineString, Point, shape, mapping
from shapely.ops import transform
import pyproj
from sqlalchemy.orm import Session

from src.config import (
    PROJECTED_CRS,
    GEOGRAPHIC_CRS,
    CORRIDOR_BUFFER_METERS,
    RISK_WEIGHTS,
    TRANSPORT_MODES,
    SAFETY_DISCLAIMER
)
from src.models import (
    BlackspotModel,
    AccidentModel,
    SpeedLimitModel,
    RoadCurveModel
)

# Set up spatial coordinate transformers
# EPSG:4326 (lon, lat) to EPSG:32643 (x, y)
transformer_to_projected = pyproj.Transformer.from_crs(
    GEOGRAPHIC_CRS, PROJECTED_CRS, always_xy=True
).transform

# EPSG:32643 (x, y) to EPSG:4326 (lon, lat)
transformer_to_geographic = pyproj.Transformer.from_crs(
    PROJECTED_CRS, GEOGRAPHIC_CRS, always_xy=True
).transform


def create_safety_corridor(
    coords_lat_lon: List[Tuple[float, float]],
    buffer_meters: float = CORRIDOR_BUFFER_METERS
) -> Tuple[LineString, Any, Dict[str, Any]]:
    """
    Generate route LineString and buffered safety corridor in UTM 43N,
    returning: (route_line_wgs84, corridor_poly_utm, corridor_geojson_wgs84)
    """
    if len(coords_lat_lon) < 2:
        raise ValueError("At least 2 points required to create a route corridor.")

    # Shapely coordinates are (lon, lat)
    coords_lon_lat = [(lon, lat) for lat, lon in coords_lat_lon]
    route_line_wgs84 = LineString(coords_lon_lat)

    # Project route to UTM Zone 43N
    route_line_utm = transform(transformer_to_projected, route_line_wgs84)

    # Create safety corridor buffer in meters
    corridor_poly_utm = route_line_utm.buffer(buffer_meters)

    # Project buffer polygon back to WGS84 for map rendering
    corridor_poly_wgs84 = transform(transformer_to_geographic, corridor_poly_utm)
    corridor_geojson = mapping(corridor_poly_wgs84)

    return route_line_wgs84, corridor_poly_utm, corridor_geojson


def analyze_corridor_hazards(
    db: Session,
    corridor_poly_utm: Any,
    route_line_wgs84: LineString,
    buffer_meters: float = CORRIDOR_BUFFER_METERS,
    mode: str = "car",
    geometry_curves: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Intersect corridor with blackspots, accidents, speed limits, and curves.
    Calculate transparent hazard breakdown and composite safety score.
    """
    mode_info = TRANSPORT_MODES.get(mode.lower(), TRANSPORT_MODES["car"])
    vulnerability_mult = mode_info.get("vulnerability_multiplier", 1.0)

    # 1. Query & Intersect Blackspots
    all_blackspots = db.query(BlackspotModel).all()
    matched_blackspots = []
    for bs in all_blackspots:
        # Create blackspot point in WGS84 and project to UTM
        bs_pt_wgs84 = Point(bs.longitude, bs.latitude)
        bs_pt_utm = transform(transformer_to_projected, bs_pt_wgs84)

        # Blackspots have their own radius of influence (e.g. 100m)
        bs_geom_utm = bs_pt_utm.buffer(float(bs.radius_meters))
        if corridor_poly_utm.intersects(bs_geom_utm):
            # Compute distance in meters from corridor centerline
            centerline_utm = transform(transformer_to_projected, route_line_wgs84)
            dist_m = round(centerline_utm.distance(bs_pt_utm), 1)
            matched_blackspots.append({
                "id": bs.blackspot_id,
                "name": bs.name,
                "road_name": bs.road_name,
                "latitude": bs.latitude,
                "longitude": bs.longitude,
                "distance_from_route_m": dist_m,
                "radius_meters": bs.radius_meters,
                "accident_count": bs.accident_count,
                "fatal_count": bs.fatal_count,
                "risk_score": bs.risk_score,
                "status": bs.status,
                "source_id": bs.source_id,
                "verified_date": bs.verified_date,
                "type": "blackspot"
            })

    # 2. Query & Intersect Accidents
    all_accidents = db.query(AccidentModel).all()
    matched_accidents = []
    for acc in all_accidents:
        acc_pt_wgs84 = Point(acc.longitude, acc.latitude)
        acc_pt_utm = transform(transformer_to_projected, acc_pt_wgs84)
        if corridor_poly_utm.contains(acc_pt_utm) or corridor_poly_utm.distance(acc_pt_utm) < 1.0:
            centerline_utm = transform(transformer_to_projected, route_line_wgs84)
            dist_m = round(centerline_utm.distance(acc_pt_utm), 1)
            matched_accidents.append({
                "id": acc.accident_id,
                "date": acc.date,
                "latitude": acc.latitude,
                "longitude": acc.longitude,
                "distance_from_route_m": dist_m,
                "road_name": acc.road_name,
                "ward": acc.ward,
                "severity": acc.severity,
                "vehicle_type": acc.vehicle_type,
                "cause": acc.cause,
                "source_id": acc.source_id,
                "confidence_level": acc.confidence_level,
                "type": "accident"
            })

    # 3. Query & Intersect Speed Limits
    all_speed_limits = db.query(SpeedLimitModel).all()
    matched_speed_limits = []
    for spd in all_speed_limits:
        spd_pt_wgs84 = Point(spd.longitude, spd.latitude)
        spd_pt_utm = transform(transformer_to_projected, spd_pt_wgs84)
        # Check if within safety corridor + 20m tolerance for signposts
        if corridor_poly_utm.distance(spd_pt_utm) <= 20.0:
            centerline_utm = transform(transformer_to_projected, route_line_wgs84)
            dist_m = round(centerline_utm.distance(spd_pt_utm), 1)
            matched_speed_limits.append({
                "id": spd.speed_limit_id,
                "road_name": spd.road_name,
                "latitude": spd.latitude,
                "longitude": spd.longitude,
                "distance_from_route_m": dist_m,
                "speed_kmph": spd.speed_kmph,
                "direction": spd.direction,
                "source_id": spd.source_id,
                "verified_date": spd.verified_date,
                "confidence_level": spd.confidence_level,
                "type": "speed_limit"
            })

    # 4. Query & Intersect Curves (from DB or dynamically detected)
    matched_curves = []
    # Dynamic geometry curves passed from route analysis
    if geometry_curves:
        for crv in geometry_curves:
            crv_pt_wgs84 = Point(crv["longitude"], crv["latitude"])
            crv_pt_utm = transform(transformer_to_projected, crv_pt_wgs84)
            if corridor_poly_utm.contains(crv_pt_utm) or corridor_poly_utm.distance(crv_pt_utm) < 5.0:
                centerline_utm = transform(transformer_to_projected, route_line_wgs84)
                dist_m = round(centerline_utm.distance(crv_pt_utm), 1)
                matched_curves.append({
                    "id": crv["curve_id"],
                    "road_name": crv["road_name"],
                    "latitude": crv["latitude"],
                    "longitude": crv["longitude"],
                    "distance_from_route_m": dist_m,
                    "curve_severity": crv["curve_severity"],
                    "estimated_radius_meters": crv.get("estimated_radius_meters"),
                    "warning_text": crv["warning_text"],
                    "source_id": crv["source_id"],
                    "confidence_level": crv["confidence_level"],
                    "type": "curve"
                })

    # Also check DB pre-registered curves
    db_curves = db.query(RoadCurveModel).all()
    for crv in db_curves:
        try:
            geom_dict = json.loads(crv.geometry)
            shp = shape(geom_dict)
            shp_utm = transform(transformer_to_projected, shp)
            if corridor_poly_utm.intersects(shp_utm):
                center = shp.centroid
                matched_curves.append({
                    "id": crv.curve_id,
                    "road_name": crv.road_name,
                    "latitude": center.y,
                    "longitude": center.x,
                    "distance_from_route_m": 0.0,
                    "curve_severity": crv.curve_severity,
                    "estimated_radius_meters": crv.estimated_radius_meters,
                    "warning_text": crv.warning_text,
                    "source_id": crv.source_id,
                    "confidence_level": crv.confidence_level,
                    "type": "curve"
                })
        except Exception:
            pass

    # Deduplicate curves by id
    unique_curves = {}
    for c in matched_curves:
        if c["id"] not in unique_curves:
            unique_curves[c["id"]] = c
    matched_curves = list(unique_curves.values())

    # 5. Transparent Risk Score Breakdown
    fatal_count = sum(1 for a in matched_accidents if a["severity"].lower() == "fatal")
    grievous_count = sum(1 for a in matched_accidents if a["severity"].lower() == "grievous")
    minor_count = sum(1 for a in matched_accidents if a["severity"].lower() == "minor")

    sharp_curve_count = sum(1 for c in matched_curves if c["curve_severity"] == "sharp")
    moderate_curve_count = sum(1 for c in matched_curves if c["curve_severity"] == "moderate")
    gentle_curve_count = sum(1 for c in matched_curves if c["curve_severity"] == "gentle")

    blackspot_count = len(matched_blackspots)

    # Component weights
    bs_penalty = blackspot_count * RISK_WEIGHTS["verified_blackspot"]
    fatal_penalty = fatal_count * RISK_WEIGHTS["fatal_accident"]
    grievous_penalty = grievous_count * RISK_WEIGHTS["grievous_accident"]
    minor_penalty = minor_count * RISK_WEIGHTS["minor_accident"]
    sharp_curve_penalty = sharp_curve_count * RISK_WEIGHTS["sharp_curve"]
    moderate_curve_penalty = moderate_curve_count * RISK_WEIGHTS["moderate_curve"]

    # Speed limit coverage: if no speed limit records exist near corridor, add unknown speed penalty
    if not matched_speed_limits:
        unknown_speed_penalty = RISK_WEIGHTS["unknown_speed_limit"]
        speed_status = "Unknown / Missing Speed-Limit Signage"
    else:
        unknown_speed_penalty = 0.0
        speed_status = f"{len(matched_speed_limits)} Verified Signpost(s) Encountered"

    raw_score = (
        bs_penalty +
        fatal_penalty +
        grievous_penalty +
        minor_penalty +
        sharp_curve_penalty +
        moderate_curve_penalty +
        unknown_speed_penalty
    ) * vulnerability_mult

    # Clamp score between 0.0 and 100.0
    final_score = round(min(100.0, max(0.0, raw_score)), 1)

    # Safety Rating Classification
    if final_score <= 25.0:
        safety_level = "Low Hazard"
        safety_badge_color = "success"
    elif final_score <= 55.0:
        safety_level = "Moderate Caution"
        safety_badge_color = "warning"
    elif final_score <= 80.0:
        safety_level = "Elevated Hazard Alert"
        safety_badge_color = "danger"
    else:
        safety_level = "High Hazard / Critical Blackspot Corridor"
        safety_badge_color = "dark"

    # 6. Generate Actionable Safety Precautions
    precautions = []
    if blackspot_count > 0:
        names = ", ".join([b["name"] for b in matched_blackspots[:2]])
        precautions.append(
            f"This corridor intersects {blackspot_count} verified blackspot zone(s) ({names}). "
            f"Expect sudden lane merges, turning traffic, and heavy braking."
        )

    if sharp_curve_count > 0:
        precautions.append(
            f"Caution: {sharp_curve_count} sharp curve(s) detected. Decelerate well before entering bends and avoid overtaking."
        )
    elif moderate_curve_count > 0:
        precautions.append(
            f"Note: {moderate_curve_count} moderate curve(s) on route. Maintain lane discipline."
        )

    if fatal_count > 0 or grievous_count > 0:
        precautions.append(
            f"Incident history: {fatal_count} fatal and {grievous_count} serious injury crashes reported in this vicinity. Keep safe following distance."
        )

    if not matched_speed_limits:
        precautions.append(
            "Speed-limit information is unavailable for portions of this corridor; strictly adhere to posted on-road signs."
        )
    else:
        limits = ", ".join([f"{s['road_name']}: {s['speed_kmph']} km/h" for s in matched_speed_limits[:2]])
        precautions.append(f"Adhere to verified limits ({limits}). Follow local signage.")

    if mode.lower() in ("motorcycle", "bicycle"):
        precautions.append(
            "Two-wheeler advisory: Watch out for bus blind spots, uneven flyover expansion joints, and roadside gravel."
        )
    elif mode.lower() == "pedestrian":
        precautions.append(
            "Pedestrian advisory: Use designated footbridges and zebra crossings. Avoid crossing unlit dual-carriageway sections."
        )

    precautions.append(SAFETY_DISCLAIMER)

    return {
        "final_risk_score": final_score,
        "safety_level": safety_level,
        "safety_badge_color": safety_badge_color,
        "mode": mode,
        "mode_label": mode_info.get("label", "Car"),
        "vulnerability_multiplier": vulnerability_mult,
        "corridor_buffer_meters": buffer_meters,
        "speed_limit_status": speed_status,
        "score_components": {
            "blackspot_penalty": round(bs_penalty * vulnerability_mult, 1),
            "fatal_accident_penalty": round(fatal_penalty * vulnerability_mult, 1),
            "grievous_accident_penalty": round(grievous_penalty * vulnerability_mult, 1),
            "minor_accident_penalty": round(minor_penalty * vulnerability_mult, 1),
            "sharp_curve_penalty": round(sharp_curve_penalty * vulnerability_mult, 1),
            "moderate_curve_penalty": round(moderate_curve_penalty * vulnerability_mult, 1),
            "unknown_speed_penalty": round(unknown_speed_penalty * vulnerability_mult, 1),
            "raw_total": round(raw_score, 1),
            "final_score": final_score
        },
        "counts": {
            "blackspots": blackspot_count,
            "fatal_accidents": fatal_count,
            "grievous_accidents": grievous_count,
            "minor_accidents": minor_count,
            "total_accidents": len(matched_accidents),
            "sharp_curves": sharp_curve_count,
            "moderate_curves": moderate_curve_count,
            "speed_limits": len(matched_speed_limits)
        },
        "matched_hazards": {
            "blackspots": matched_blackspots,
            "accidents": matched_accidents,
            "speed_limits": matched_speed_limits,
            "curves": matched_curves
        },
        "precautions": precautions
    }

"""
Map marker and legend builder for Bengaluru SafeRoute.
Generates dash-leaflet component data (markers, polylines, polygons, tooltips).
"""

from typing import List, Dict, Any, Optional, Tuple
import dash_leaflet as dl

# Colour scheme (must match legend and disclaimer)
MARKER_COLORS = {
    "blackspot": "#DC2626",           # Red  – verified blackspot
    "accident_cluster": "#EA580C",    # Orange – accident cluster / high-risk
    "speed_limit": "#2563EB",         # Blue  – known speed limit
    "curve_sharp": "#7C3AED",         # Purple – sharp curve
    "curve_moderate": "#9333EA",      # Purple-lite – moderate curve
    "curve_gentle": "#A78BFA",        # Light purple – gentle curve
    "demo": "#6B7280",                # Grey  – demo / unverified record
    "route": "#16A34A",               # Green – chosen route
    "corridor": "#16A34A"             # Green – safety corridor fill
}

SEVERITY_ICON = {
    "Fatal": "💀",
    "Grievous": "🔴",
    "Minor": "🟡"
}

CURVE_ICON = {
    "sharp": "⚠️ Sharp Bend",
    "moderate": "↩ Moderate Bend",
    "gentle": "↪ Gentle Bend"
}


def _status_badge(status: str) -> str:
    badges = {
        "verified_official": "✅ Verified Official",
        "verified_admin": "🔵 Verified Admin",
        "demo": "🔸 Demo Data",
        "community_verified": "🟢 OSM Community",
        "geometry-derived": "📐 Geometry-Derived",
        "unverified_reference": "⬜ Unverified Reference"
    }
    return badges.get(status, f"ℹ️ {status}")


def build_blackspot_markers(blackspots: List[Dict[str, Any]]) -> List[dl.CircleMarker]:
    markers = []
    for bs in blackspots:
        is_demo = "demo" in bs.get("status", "").lower()
        color = MARKER_COLORS["demo"] if is_demo else MARKER_COLORS["blackspot"]
        demo_note = " [DEMO DATA]" if is_demo else ""

        popup_content = f"""
<div style='min-width:220px; font-family:sans-serif'>
  <strong>🔴 Blackspot{demo_note}</strong><br/>
  <b>{bs.get('name', 'Unknown Location')}</b><br/>
  <small style='color:#555'>{bs.get('road_name', '')}</small><br/><hr/>
  <b>Accident Count:</b> {bs.get('accident_count', '?')}<br/>
  <b>Fatal Count:</b> {bs.get('fatal_count', '?')}<br/>
  <b>Risk Score:</b> {bs.get('risk_score', '?')}/100<br/>
  <b>Radius:</b> {bs.get('radius_meters', '?')}m<br/><hr/>
  <b>Status:</b> {_status_badge(bs.get('status', ''))}<br/>
  <b>Source:</b> {bs.get('source_id', '?')}<br/>
  <b>Verified:</b> {bs.get('verified_date', 'Unknown')}<br/><hr/>
  <i style='color:#B91C1C'>⚠ Precaution:</i> Reduce speed, watch for sudden lane merging and turning vehicles.<br/>
  <small style='color:#888'>Safety info may be incomplete or outdated.</small>
</div>"""

        marker = dl.CircleMarker(
            center=[bs["latitude"], bs["longitude"]],
            radius=14,
            color=color,
            fillColor=color,
            fillOpacity=0.75,
            weight=2,
            children=[dl.Popup(children=[popup_content], maxWidth=320)]
        )
        markers.append(marker)
    return markers


def build_accident_markers(accidents: List[Dict[str, Any]]) -> List[dl.CircleMarker]:
    markers = []
    for acc in accidents:
        is_demo = "demo" in acc.get("confidence_level", "").lower()
        color = MARKER_COLORS["demo"] if is_demo else MARKER_COLORS["accident_cluster"]
        severity = acc.get("severity", "Minor")
        icon = SEVERITY_ICON.get(severity, "🟡")
        demo_note = " [DEMO DATA]" if is_demo else ""

        popup_content = f"""
<div style='min-width:200px; font-family:sans-serif'>
  <strong>{icon} Accident Record{demo_note}</strong><br/>
  <b>{acc.get('road_name', 'Unknown Road')}</b><br/>
  <small style='color:#555'>{acc.get('ward', '')}</small><br/><hr/>
  <b>Date:</b> {acc.get('date', '?')}<br/>
  <b>Severity:</b> {severity}<br/>
  <b>Vehicle:</b> {acc.get('vehicle_type', 'Unknown')}<br/>
  <b>Cause:</b> {acc.get('cause', 'Unspecified')}<br/><hr/>
  <b>Source:</b> {acc.get('source_id', '?')}<br/>
  <b>Confidence:</b> {_status_badge(acc.get('confidence_level', ''))}<br/>
  <small style='color:#888'>Safety info may be incomplete or outdated.</small>
</div>"""

        marker = dl.CircleMarker(
            center=[acc["latitude"], acc["longitude"]],
            radius=9,
            color=color,
            fillColor=color,
            fillOpacity=0.65,
            weight=2,
            children=[dl.Popup(children=[popup_content], maxWidth=300)]
        )
        markers.append(marker)
    return markers


def build_speed_limit_markers(speed_limits: List[Dict[str, Any]]) -> List[dl.CircleMarker]:
    markers = []
    for spd in speed_limits:
        is_demo = "demo" in spd.get("confidence_level", "").lower()
        color = MARKER_COLORS["demo"] if is_demo else MARKER_COLORS["speed_limit"]
        demo_note = " [DEMO]" if is_demo else ""

        popup_content = f"""
<div style='min-width:200px; font-family:sans-serif'>
  <strong>🔵 Speed Limit{demo_note}</strong><br/>
  <b>{spd.get('road_name', 'Unknown Road')}</b><br/><hr/>
  <b>Limit:</b> <span style='font-size:1.4em;font-weight:bold;color:#2563EB'>{spd.get('speed_kmph', '?')} km/h</span><br/>
  <b>Direction:</b> {spd.get('direction', 'Both')}<br/>
  <b>Source:</b> {spd.get('source_id', '?')}<br/>
  <b>Verified:</b> {spd.get('verified_date', 'Unknown')}<br/>
  <b>Confidence:</b> {_status_badge(spd.get('confidence_level', ''))}<br/>
  <small style='color:#888'>Follow posted signage. Limits here are for awareness only.</small>
</div>"""

        marker = dl.CircleMarker(
            center=[spd["latitude"], spd["longitude"]],
            radius=10,
            color=color,
            fillColor=color,
            fillOpacity=0.7,
            weight=2,
            children=[dl.Popup(children=[popup_content], maxWidth=300)]
        )
        markers.append(marker)
    return markers


def build_curve_markers(curves: List[Dict[str, Any]]) -> List[dl.CircleMarker]:
    markers = []
    for crv in curves:
        severity = crv.get("curve_severity", "moderate")
        color_key = f"curve_{severity}" if f"curve_{severity}" in MARKER_COLORS else "curve_moderate"
        color = MARKER_COLORS[color_key]
        icon = CURVE_ICON.get(severity, "↩ Curve")
        radius_text = (
            f"{crv['estimated_radius_meters']}m" if crv.get("estimated_radius_meters") else
            "Not determinable without CAD data"
        )
        is_demo = "demo" in crv.get("confidence_level", "").lower()
        demo_note = " [DEMO DATA]" if is_demo else ""

        popup_content = f"""
<div style='min-width:200px; font-family:sans-serif'>
  <strong>🟣 {icon}{demo_note}</strong><br/>
  <b>{crv.get('road_name', 'Unnamed Corridor')}</b><br/><hr/>
  <b>Severity:</b> {severity.capitalize()}<br/>
  <b>Est. Radius:</b> {radius_text}<br/>
  <b>Warning:</b> {crv.get('warning_text', '')}<br/><hr/>
  <b>Source:</b> {crv.get('source_id', '?')}<br/>
  <b>Confidence:</b> {_status_badge(crv.get('confidence_level', 'geometry-derived'))}<br/>
  <small style='color:#888'>Derived from road geometry. Not verified by field survey.</small>
</div>"""

        lat = crv.get("latitude")
        lon = crv.get("longitude")
        if lat is None or lon is None:
            continue

        marker = dl.CircleMarker(
            center=[lat, lon],
            radius=11,
            color=color,
            fillColor=color,
            fillOpacity=0.7,
            weight=2,
            children=[dl.Popup(children=[popup_content], maxWidth=320)]
        )
        markers.append(marker)
    return markers


def build_route_polyline(coords_lat_lon: List[Tuple[float, float]], route_title: str = "Route") -> dl.Polyline:
    """Convert list of (lat, lon) coordinates to a styled Leaflet polyline."""
    return dl.Polyline(
        positions=[[lat, lon] for lat, lon in coords_lat_lon],
        color=MARKER_COLORS["route"],
        weight=5,
        opacity=0.85,
        dashArray=None,
        children=[dl.Tooltip(children=[route_title])]
    )


def build_all_map_elements(
    route_coords: List[Tuple[float, float]],
    blackspots: List[Dict],
    accidents: List[Dict],
    speed_limits: List[Dict],
    curves: List[Dict],
    route_title: str = "Selected Route"
) -> List[Any]:
    """Assemble all map layer elements: route, markers, popups."""
    elements = []
    if route_coords:
        elements.append(build_route_polyline(route_coords, route_title))
    elements.extend(build_blackspot_markers(blackspots))
    elements.extend(build_accident_markers(accidents))
    elements.extend(build_speed_limit_markers(speed_limits))
    elements.extend(build_curve_markers(curves))
    return elements
